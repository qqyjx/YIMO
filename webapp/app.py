#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YIMO Flask Web 应用 - 对象抽取与三层架构关联

Endpoints:
- GET /            : 主界面 (v10.0)
- GET /extraction  : 对象抽取与三层架构关联页面
- GET /health      : 健康检查
- POST /rag/query  : RAG 查询接口
- POST /deepseek/chat : Deepseek API 代理

作者: YIMO Team
日期: 2026-02
"""
import os
import json
from functools import lru_cache
from dataclasses import dataclass
from typing import List, Dict, Any, Sequence, cast
from flask import Flask, request, jsonify, render_template
import pymysql
import requests
import numpy as np
import importlib
from importlib import util as importlib_util

# Optional imports
_faiss_spec = importlib_util.find_spec("faiss")
faiss = importlib.import_module("faiss") if _faiss_spec else None

_dotenv_spec = importlib_util.find_spec("dotenv")
if _dotenv_spec:
    from dotenv import load_dotenv
else:
    def load_dotenv():
        return False

# Optional sentence_transformers import
_sbert_spec = importlib_util.find_spec("sentence_transformers")
if _sbert_spec:
    from sentence_transformers import SentenceTransformer
    HAS_SBERT = True
else:
    SentenceTransformer = None
    HAS_SBERT = False
    print(" * WARNING: sentence_transformers not installed, RAG features disabled")

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

# 注册对象抽取 API Blueprint
try:
    from olm_api import olm_api
    app.register_blueprint(olm_api)
    print(" * Object Extraction API registered")
except ImportError as e:
    print(f" * WARNING: Object Extraction API not loaded: {e}")

# =================== 配置 ===================
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_DB = os.getenv("MYSQL_DB", "eav_db")
MYSQL_USER = os.getenv("MYSQL_USER", "eav_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "eavpass123")
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "eav")
MODEL_NAME = os.getenv("EMBED_MODEL", "shibing624/text2vec-base-chinese")
MODEL_CACHE = os.getenv("MODEL_CACHE", "./models")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", MODEL_CACHE)

# 数据域名称映射
DOMAIN_NAMES = {
    "shupeidian": "输配电",
    "jicai": "计划财务",
    "yingxiao": "营销",
    "caiwu": "财务",
    "renliziyuan": "人力资源",
}
os.environ.setdefault("HF_HOME", MODEL_CACHE)

# =================== 数据库 ===================

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
    if not HAS_SBERT:
        raise RuntimeError("sentence_transformers not installed")
    return SentenceTransformer(MODEL_NAME, cache_folder=MODEL_CACHE)

# =================== EAV 查询 ===================

def list_datasets() -> Sequence[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id,name,source_file,imported_at FROM {TABLE_PREFIX}_datasets ORDER BY id")
        rows = cur.fetchall()
    return cast(Sequence[Dict[str, Any]], list(rows))

def list_attributes(dataset_id: int) -> Sequence[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id,name,data_type FROM {TABLE_PREFIX}_attributes WHERE dataset_id=%s ORDER BY id", (dataset_id,))
        rows = cur.fetchall()
    return cast(Sequence[Dict[str, Any]], list(rows))

# =================== RAG ===================
@dataclass
class RagIndex:
    dsid: int
    texts: List[str]
    index: Any
    emb: np.ndarray

_rag_cache: Dict[int, RagIndex] = {}

def build_rag_index(dataset_id: int) -> RagIndex:
    if dataset_id in _rag_cache:
        return _rag_cache[dataset_id]
    if faiss is None:
        raise RuntimeError("FAISS not installed")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT canon_text FROM {TABLE_PREFIX}_semantic_canon LIMIT 50000")
        rows = cur.fetchall()
    texts = [r['canon_text'] for r in rows if r.get('canon_text')]
    if not texts:
        texts = ["无数据"]
    model = get_model()
    emb = model.encode(texts, batch_size=256, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
    emb = emb.astype('float32')
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    ri = RagIndex(dataset_id, texts, index, emb)
    _rag_cache[dataset_id] = ri
    return ri

# =================== Deepseek API ===================

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

# =================== 路由 ===================

@app.route('/')
def home():
    try:
        from pathlib import Path

        # 扫描 DATA/ 目录下所有 xlsx 文件
        data_dir = Path(__file__).parent.parent / "DATA"
        stats = []
        idx = 1
        if data_dir.exists():
            for subdir in sorted(data_dir.iterdir()):
                if not subdir.is_dir():
                    continue
                for f in sorted(subdir.glob("*.xlsx")):
                    stats.append({
                        'id': idx,
                        'domain': DOMAIN_NAMES.get(subdir.name, subdir.name),
                        'name': f.name,
                        'source_file': str(f),
                        'size': f"{f.stat().st_size / 1024:.0f} KB",
                    })
                    idx += 1

        # 默认使用 v10.0 模板
        v = request.args.get('v', '10.0')
        if not all(c.isalnum() or c == '.' for c in v):
            v = '10.0'

        template_name = f"{v}.html"
        # 使用 Jinja2 loader 检查模板是否存在
        try:
            app.jinja_env.get_template(template_name)
        except Exception:
            template_name = 'home.html'

        return render_template(template_name, stats=stats)
    except Exception as e:
        return (
            f"<h2>YIMO 对象抽取与三层架构关联系统</h2>"
            f"<p>启动失败: {str(e)}</p>"
            f"<p><a href='/extraction'>进入对象抽取页面</a></p>",
            500,
            {"Content-Type": "text/html; charset=utf-8"}
        )

@app.route('/health')
def health():
    return jsonify({"status": "ok", "faiss": bool(faiss is not None)})


@app.route('/api/domains')
def api_domains():
    """自动发现DATA目录下的所有数据域

    扫描DATA/目录下的子文件夹，每个包含.xlsx文件的子文件夹即为一个域。
    支持通过domain.json配置文件自定义域名称。
    """
    from pathlib import Path

    data_dir = Path(__file__).parent.parent / "DATA"
    domains = []

    # 使用模块级 DOMAIN_NAMES 常量

    if not data_dir.exists():
        return jsonify([])

    # 扫描所有子目录
    for subdir in sorted(data_dir.iterdir()):
        if not subdir.is_dir():
            continue

        # 查找该域下的Excel文件
        excel_files = list(subdir.glob("*.xlsx"))
        if not excel_files:
            continue  # 跳过没有数据文件的目录

        domain_code = subdir.name
        domain_info = {
            "code": domain_code,
            "name": DOMAIN_NAMES.get(domain_code, domain_code),
            "files": [f.name for f in sorted(excel_files)],
            "has_files": True
        }

        # 可选：读取域配置文件 domain.json
        config_file = subdir / "domain.json"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding='utf-8'))
                domain_info["name"] = config.get("name", domain_info["name"])
            except Exception:
                pass

        domains.append(domain_info)

    return jsonify(domains)

@app.route('/extraction')
def extraction_page():
    """对象抽取与三层架构关联页面"""
    return render_template('object_extraction.html')

@app.route('/dataset/<int:dsid>/attributes')
def api_attributes(dsid: int):
    return jsonify(list_attributes(dsid))

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


# =================== 基础模板 ===================
HOME_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>YIMO 对象抽取与三层架构关联</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 1.5rem; background: #1e1b4b; color: #e2e8f0; }
    h1 { color: #818cf8; }
    a { color: #818cf8; }
    .card { background: rgba(30, 27, 75, 0.6); padding: 1.5rem; border-radius: 12px; margin: 1rem 0; }
    .btn { padding: 12px 24px; background: linear-gradient(135deg, #6366f1, #4f46e5); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; }
    .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4); }
  </style>
</head>
<body>
  <h1>🎯 YIMO 对象抽取与三层架构关联系统</h1>
  <div class="card">
    <h2>快速入口</h2>
    <p><a href="/extraction">→ 对象抽取与三层架构关联</a></p>
    <p><a href="/?v=10.0">→ 主控制台 (v10.0)</a></p>
  </div>
  <div class="card">
    <h2>系统状态</h2>
    <p>数据集数量: {{ stats|length }}</p>
    {% for row in stats %}
    <p>- {{ row.name }} (规范值: {{ row.canon }})</p>
    {% endfor %}
  </div>
</body>
</html>"""

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
