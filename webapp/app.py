#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal Flask webapp to browse EAV semantic tables and provide
Deepseek API proxy + simple RAG (FAISS + SBERT).

Endpoints
- GET /            : Dashboard, dataset list & quick stats.
- GET /dataset/<int:dsid>/attributes : JSON list of attributes.
- GET /dataset/<int:dsid>/attribute/<int:aid>/canon : JSON list of canon values.
- GET /dataset/<int:dsid>/attribute/<int:aid>/mapping?limit=... : Mapping rows.
- POST /deepseek/chat : Proxy a chat completion to Deepseek API.
- POST /rag/query : Run RAG over semantic canon texts (per dataset) and call Deepseek.

RAG minimal design
- Build (in-memory) FAISS index of canonical texts for requested dataset (lazy cache).
- Embed by sentence-transformers (shibing624/text2vec-base-chinese by default). 
- Top-K retrieval -> join canonical_texts into a context -> ask Deepseek.

Security NOTE: This is a local development script; do NOT expose without adding auth & rate limiting.
"""
import os
import time
import json
from functools import lru_cache
from dataclasses import dataclass
from typing import List, Dict, Any
from flask import Flask, request, jsonify, render_template
import pymysql
import requests
import numpy as np
import importlib
from importlib import util as importlib_util
from typing import Sequence, cast

# Optional imports via importlib to reduce static unresolved warnings
_faiss_spec = importlib_util.find_spec("faiss")
faiss = importlib.import_module("faiss") if _faiss_spec else None  # type: ignore

_dotenv_spec = importlib_util.find_spec("dotenv")
if _dotenv_spec:
    from dotenv import load_dotenv  # type: ignore
else:  # fallback noop
    def load_dotenv():
        return False

from sentence_transformers import SentenceTransformer

load_dotenv()  # loads .env if present

app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------------- Config ----------------
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DB = os.getenv("MYSQL_DB", "eav_db")
MYSQL_USER = os.getenv("MYSQL_USER", "eav_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Eav_pass_1234")
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "eav")
MODEL_NAME = os.getenv("EMBED_MODEL", "shibing624/text2vec-base-chinese")
MODEL_CACHE = os.getenv("MODEL_CACHE", "/data1/xyf/models")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-6d5df25a5d654ccf936de83c1797ba0a")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", MODEL_CACHE)
os.environ.setdefault("HF_HOME", MODEL_CACHE)

# ---------------- DB Helpers ----------------

def get_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

@lru_cache(maxsize=1)
def get_model():
    return SentenceTransformer(MODEL_NAME, cache_folder=MODEL_CACHE)

# ---------------- Simple Queries ----------------

def list_datasets() -> Sequence[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id,name,source_file,imported_at FROM {TABLE_PREFIX}_datasets ORDER BY id")
    rows = cur.fetchall()
    return cast(Sequence[Dict[str, Any]], list(rows))

def list_attributes(dataset_id: int) -> Sequence[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id,name,display_name,data_type FROM {TABLE_PREFIX}_attributes WHERE dataset_id=%s ORDER BY id", (dataset_id,))
    rows = cur.fetchall()
    return cast(Sequence[Dict[str, Any]], list(rows))

def list_canon(dataset_id: int, attribute_id: int, limit: int = 200) -> Sequence[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id,canonical_text,cluster_size,created_at FROM {TABLE_PREFIX}_semantic_canon WHERE dataset_id=%s AND attribute_id=%s ORDER BY cluster_size DESC, id LIMIT %s", (dataset_id, attribute_id, limit))
    rows = cur.fetchall()
    return cast(Sequence[Dict[str, Any]], list(rows))

def list_mapping(dataset_id: int, attribute_id: int, limit: int = 500) -> Sequence[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT from_text,canonical_id,similarity,freq,created_at FROM {TABLE_PREFIX}_semantic_mapping WHERE dataset_id=%s AND attribute_id=%s ORDER BY freq DESC, similarity DESC LIMIT %s", (dataset_id, attribute_id, limit))
    rows = cur.fetchall()
    return cast(Sequence[Dict[str, Any]], list(rows))

# ---------------- RAG Index Cache ----------------
@dataclass
class RagIndex:
    dsid: int
    texts: List[str]
    index: Any  # faiss.IndexFlatIP
    emb: np.ndarray

_rag_cache: Dict[int, RagIndex] = {}

def build_rag_index(dataset_id: int) -> RagIndex:
    if dataset_id in _rag_cache:
        return _rag_cache[dataset_id]
    if faiss is None:
        raise RuntimeError("FAISS not installed; install faiss-cpu to enable RAG")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT canonical_text FROM {TABLE_PREFIX}_semantic_canon WHERE dataset_id=%s LIMIT 50000", (dataset_id,))
        rows = cur.fetchall()
    texts = [r['canonical_text'] for r in rows if r.get('canonical_text')]
    model = get_model()
    emb = model.encode(texts, batch_size=256, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
    emb = emb.astype('float32')
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    ri = RagIndex(dataset_id, texts, index, emb)
    _rag_cache[dataset_id] = ri
    return ri

# ---------------- Deepseek Proxy ----------------

def call_deepseek(messages: List[Dict[str, str]], model: str = "deepseek-chat") -> Dict[str, Any]:
    if not DEEPSEEK_API_KEY:
        return {"error": "DEEPSEEK_API_KEY not set"}
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages}
    url = f"{DEEPSEEK_API_BASE.rstrip('/')}/chat/completions"
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# ---------------- Routes ----------------
@app.route('/')
def home():
    try:
        ds = list_datasets()
        stats = []
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT dataset_id, COUNT(*) c FROM {TABLE_PREFIX}_semantic_canon GROUP BY dataset_id")
            canon_counts = {r['dataset_id']: r['c'] for r in cur.fetchall()}
            cur.execute(f"SELECT dataset_id, COUNT(*) c FROM {TABLE_PREFIX}_semantic_mapping GROUP BY dataset_id")
            map_counts = {r['dataset_id']: r['c'] for r in cur.fetchall()}
        for d in ds:
            stats.append({
                'id': d['id'],
                'name': d['name'],
                'source_file': d.get('source_file'),
                'canon': canon_counts.get(d['id'], 0),
                'mapping': map_counts.get(d['id'], 0),
            })
        
        # Template selection logic
        v = request.args.get('v', '3.0')
        # Allow alphanumeric and dots
        if not all(c.isalnum() or c == '.' for c in v):
             v = '3.0'
        
        template_name = f"{v}.html"
        folder = app.template_folder if app.template_folder else 'templates'
        if not os.path.exists(os.path.join(folder, template_name)):
             template_name = '3.0.html'
            
        return render_template(template_name, stats=stats)
    except Exception as e:
        # Render minimal inline message to avoid template dependency when DB is down
        return (
            f"<h2>Webapp running</h2>"
            f"<p>But failed to query MySQL: {str(e)}</p>"
            f"<p>Please set .env (MYSQL_HOST/PORT/DB/USER/PASSWORD, TABLE_PREFIX) and ensure DB is reachable.</p>",
            200,
            {"Content-Type": "text/html; charset=utf-8"}
        )

@app.route('/health')
def health():
    return jsonify({"status": "ok", "faiss": bool(faiss is not None)})

@app.route('/dataset/<int:dsid>/attributes')
def api_attributes(dsid: int):
    return jsonify(list_attributes(dsid))

@app.route('/dataset/<int:dsid>/attribute/<int:aid>/canon')
def api_canon(dsid: int, aid: int):
    limit = int(request.args.get('limit', 200))
    return jsonify(list_canon(dsid, aid, limit))

@app.route('/dataset/<int:dsid>/attribute/<int:aid>/mapping')
def api_mapping(dsid: int, aid: int):
    limit = int(request.args.get('limit', 500))
    return jsonify(list_mapping(dsid, aid, limit))

@app.route('/deepseek/chat', methods=['POST'])
def api_deepseek_chat():
    data = request.json or {}
    messages = data.get('messages', [])
    model = data.get('model', 'deepseek-chat')
    return jsonify(call_deepseek(messages, model))

@app.route('/rag/query', methods=['POST'])
def api_rag_query():
    data = request.json or {}
    dsid = int(data.get('dataset_id', 1))
    query = data.get('query', '').strip()
    top_k = int(data.get('top_k', RAG_TOP_K))
    if top_k < 1:
        top_k = 1
    if top_k > 50:
        top_k = 50
    if not query:
        return jsonify({'error': 'query empty'}), 400
    # Build / fetch index
    ri = build_rag_index(dsid)
    model = get_model()
    q_emb = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0].astype('float32')
    q_emb = q_emb.reshape(1, -1)
    D, I = ri.index.search(q_emb, top_k)
    retrieved = [ri.texts[i] for i in I[0] if i < len(ri.texts)]
    context = '\n'.join(retrieved)
    messages = [
        {"role": "system", "content": "你是一个知识助手，利用给定的上下文回答问题。"},
        {"role": "user", "content": f"上下文:\n{context}\n\n问题: {query}"}
    ]
    llm_resp = call_deepseek(messages)
    return jsonify({"query": query, "retrieved": retrieved, "llm": llm_resp})

# ---------------- Templates ----------------
# Basic Jinja template
HOME_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>EAV 语义库概览</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 1.5rem; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 4px 8px; }
    th { background: #f5f5f5; }
    .small { font-size: 12px; color: #666; }
    .mono { font-family: monospace; }
        .row { display: flex; gap: 1rem; align-items: center; }
        .col { flex: 1; }
        textarea { width: 100%; height: 120px; }
        input[type="text"] { width: 100%; }
        pre { background: #f7f7f7; padding: 8px; overflow-x: auto; }
        .muted { color:#888; font-size: 12px; }
        .btn { padding: 6px 12px; cursor: pointer; }
  </style>
</head>
<body>
<h1>EAV 语义库概览</h1>
<table>
  <thead>
    <tr><th>ID</th><th>Name</th><th>Source File</th><th>Canon Rows</th><th>Mapping Rows</th></tr>
  </thead>
  <tbody>
  {% for row in stats %}
    <tr>
      <td>{{ row.id }}</td>
      <td>{{ row.name }}</td>
      <td class="small">{{ row.source_file }}</td>
      <td>{{ row.canon }}</td>
      <td>{{ row.mapping }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>

<h2>RAG 检索 + LLM 回答</h2>
<div class="row">
    <div class="col" style="max-width:220px;">
        <label>选择数据集：</label>
        <select id="dsid">
            {% for row in stats %}
                <option value="{{ row.id }}">[{{ row.id }}] {{ row.name }}</option>
            {% endfor %}
        </select>
        <p class="muted">注意：首次检索会构建索引，较慢；随后相同 dataset 会缓存。</p>
    </div>
    <div class="col">
        <label>问题（将基于所选数据集的 canonical_text 进行 Top-K 检索）：</label>
        <input id="rag_q" type="text" placeholder="例如：某字段的含义？或如何映射X到标准值？" />
        <div style="margin-top:8px;">
            <button class="btn" onclick="doRag()">提交 RAG 查询</button>
        </div>
    </div>
</div>
<div class="row" style="margin-top:12px;">
    <div class="col">
        <h3>检索到的上下文</h3>
        <pre id="rag_ctx">(尚无)</pre>
    </div>
    <div class="col">
        <h3>LLM 回答</h3>
        <pre id="rag_ans">(尚无)</pre>
    </div>
    <div class="col" style="max-width:220px;">
        <h3>诊断</h3>
        <pre id="rag_dbg" class="muted">(等待查询)</pre>
    </div>
</div>

<h2>直接调用 LLM API（无检索）</h2>
<div class="row">
    <div class="col">
        <label>对话消息（JSON 数组），例如：[{"role":"user","content":"你好"}]</label>
        <textarea id="chat_msgs">[{"role":"user","content":"你好，做一个自我介绍。"}]</textarea>
        <div style="margin-top:8px;">
            <button class="btn" onclick="doChat()">发送</button>
        </div>
    </div>
    <div class="col">
        <h3>响应</h3>
        <pre id="chat_resp">(尚无)</pre>
    </div>
</div>

<script>
async function doRag(){
    const dsid = document.getElementById('dsid').value;
    const q = document.getElementById('rag_q').value.trim();
    if(!q){ alert('请输入问题'); return; }
    document.getElementById('rag_dbg').textContent = '检索中...';
    try{
        const resp = await fetch('/rag/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dataset_id: Number(dsid), query: q })
        });
        const data = await resp.json();
        if(data.error){
            document.getElementById('rag_dbg').textContent = '错误: ' + data.error;
            return;
        }
        document.getElementById('rag_ctx').textContent = (data.retrieved||[]).join('\n\n');
        const llm = data.llm || {};
        // deepseek 返回结构兼容 openai 格式
        let text = '';
        try { text = llm.choices[0].message.content; } catch(e) { text = JSON.stringify(llm, null, 2); }
        document.getElementById('rag_ans').textContent = text;
        document.getElementById('rag_dbg').textContent = 'OK';
    }catch(err){
        document.getElementById('rag_dbg').textContent = '异常: ' + err;
    }
}

async function doChat(){
    let msgsRaw = document.getElementById('chat_msgs').value;
    let msgs;
    try{ msgs = JSON.parse(msgsRaw); }
    catch(e){ alert('消息 JSON 解析失败: ' + e); return; }
    const resp = await fetch('/deepseek/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: msgs, model: 'deepseek-chat' })
    });
    const data = await resp.json();
    if(data.error){
        document.getElementById('chat_resp').textContent = '错误: ' + data.error;
        return;
    }
    let text = '';
    try { text = data.choices[0].message.content; } catch(e) { text = JSON.stringify(data, null, 2); }
    document.getElementById('chat_resp').textContent = text;
}
</script>
</body>
</html>"""

# Instead of separate file, register the template programmatically
# Prefer filesystem templates; also write HOME_HTML into templates/home.html on first run if missing.
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "home.html")
if not os.path.exists(TEMPLATE_PATH):
    try:
        os.makedirs(os.path.dirname(TEMPLATE_PATH), exist_ok=True)
        with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
            f.write(HOME_HTML)
    except Exception:
        pass

if __name__ == '__main__':
    if DEEPSEEK_API_KEY:
        print(f" * DeepSeek API Key loaded: {DEEPSEEK_API_KEY[:4]}...{DEEPSEEK_API_KEY[-4:]}")
    else:
        print(" * WARNING: DEEPSEEK_API_KEY is missing!")
    app.run(host='0.0.0.0', port=5000, debug=True)
