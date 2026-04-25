"""清理本地对象的垃圾名 (半截/中文 code).

策略:
 - 检测垃圾: object_code 含中文 OR object_name 是 3-4 字"X 完/单/信/管/市/业"等截断模式
 - 取该对象的 sample_entities 喂给 V4 Pro 推理模式
 - 让 LLM 给 (新 object_name, 新 object_code 拼音) 建议
 - UPDATE 数据库 + 更新 outputs/extraction_<域>.json 同步

只改名字, 不动关联 (relation_id/object_id 不变, sample_entities 不变).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pymysql
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = PROJECT_ROOT / "outputs"

DB_CONF = dict(host='127.0.0.1', port=3307, user='eav_user', password='eavpass123',
               database='eav_db', charset='utf8mb4')

DEEPSEEK_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
# 命名是简单分类任务, 不需要推理. 临时用 deepseek-chat 非推理模式更快更稳.
# (主管道还是 V4 Pro, 仅本脚本覆盖)
DEEPSEEK_MODEL = os.getenv("CLEANUP_LLM_MODEL", "deepseek-chat")


CHINESE = re.compile(r'[一-鿿]')
TRUNCATED_SUFFIX = ('完', '单', '信', '管', '市', '业')


def is_garbage(code: str, name: str) -> bool:
    if CHINESE.search(code):
        return True
    if 1 <= len(name) - len(name.rstrip(''.join(TRUNCATED_SUFFIX))) and 3 <= len(name) <= 4:
        if any(name.endswith(s) for s in TRUNCATED_SUFFIX):
            return True
    if name.endswith(('的', '与', '和')):
        return True
    return False


def call_llm(prompt: str) -> str | None:
    if not DEEPSEEK_KEY:
        return None
    try:
        r = requests.post(
            f"{DEEPSEEK_BASE.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.2,
            },
            timeout=90,
        )
        d = r.json()
        return (d.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    except Exception as e:
        print(f"  [LLM ERR] {e}")
        return None


PROMPT_TPL = """你是企业架构对象抽取助手. 给定一组语义相似的实体名 (来自南方电网某业务域的数据架构),
请总结一个抽象的"对象名"作为这组实体的统一抽象, 并给一个英文 code.

要求:
  1. 对象名: 2-4 字中文, 表达一个明确的业务概念 (如 项目/合同/票据/资产)
  2. 不要用截断的半截词 (例如 "业务完", 错; "业务完成", 对; 但更优是抽象成 "业务" 或 "活动")
  3. 不要直接用最长样例, 要抽象/概括
  4. code: 大写英文 + 下划线, 形如 OBJ_PROJECT, OBJ_CONTRACT

输入实体名 (top {n_samples}, 每行一个):
{samples}

只输出一行 JSON, 不要 markdown, 不要解释:
{{"name": "新对象名", "code": "OBJ_ENGLISH"}}"""


def parse_json_line(text: str) -> dict | None:
    text = text.strip()
    # 抠出 {...}
    m = re.search(r'\{[^{}]*\}', text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def main() -> int:
    if not DEEPSEEK_KEY:
        print("[ERR] DEEPSEEK_API_KEY 未设置")
        return 2

    conn = pymysql.connect(**DB_CONF)
    cur = conn.cursor()
    cur.execute("""
        SELECT object_id, object_code, object_name, data_domain
        FROM extracted_objects
        ORDER BY data_domain, object_name
    """)
    all_objs = cur.fetchall()
    garbage = [(oid, code, name, dom) for oid, code, name, dom in all_objs
               if is_garbage(code, name)]
    print(f"[INFO] 共 {len(all_objs)} 对象, 检测到垃圾 {len(garbage)} 个:")
    for r in garbage:
        print(f"  id={r[0]} code={r[1]:18s} name={r[2]:8s} domain={r[3]}")
    if not garbage:
        print("[INFO] 无需清理")
        return 0

    # 加载所有域 JSON 一次, 取 sample_entities
    json_cache = {}    # domain → blob
    for f in sorted(OUTPUTS.glob('extraction_*.json')):
        if 'global' in f.name or 'join_sample' in f.name:
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
            dom = d.get('data_domain') or f.stem.replace('extraction_', '')
            json_cache[dom] = (f, d)
        except Exception:
            pass

    fixes = []   # (oid, old_code, old_name, new_code, new_name, domain)
    for oid, old_code, old_name, dom in garbage:
        # 找该对象的 sample_entities
        if dom not in json_cache:
            print(f"  [SKIP] {oid} {dom}: JSON 不在")
            continue
        _, blob = json_cache[dom]
        samples = []
        for o in blob.get('objects', []):
            if o.get('object_code') == old_code or o.get('object_name') == old_name:
                samples = (o.get('sample_entities') or [])[:8]
                break
        if not samples:
            print(f"  [SKIP] {oid} {dom}/{old_name}: 无 sample_entities")
            continue

        prompt = PROMPT_TPL.format(n_samples=len(samples), samples='\n'.join(samples))
        print(f"  [LLM] {dom}/{old_name} ← {samples[:3]}...")
        ans = call_llm(prompt)
        if not ans:
            print(f"    LLM 无响应")
            continue
        parsed = parse_json_line(ans)
        if not parsed or 'name' not in parsed or 'code' not in parsed:
            print(f"    解析失败: {ans[:100]}")
            continue

        new_name = (parsed['name'] or '').strip()
        new_code = (parsed['code'] or '').strip().upper()
        if not new_name or not new_code or CHINESE.search(new_code):
            print(f"    LLM 输出仍不合规: name={new_name!r} code={new_code!r}")
            continue

        # 确保 (new_code, dom) 在 DB 里不冲突 (UNIQUE 复合键)
        cur.execute("SELECT object_id FROM extracted_objects WHERE object_code=%s AND data_domain=%s",
                    (new_code, dom))
        existed = cur.fetchone()
        if existed and existed[0] != oid:
            new_code = new_code + "_2"   # 简单避撞
        fixes.append((oid, old_code, old_name, new_code, new_name, dom))
        print(f"    → name={new_name}, code={new_code}")

        time.sleep(0.5)   # 避免 rate limit

    print(f"\n[INFO] 即将修复 {len(fixes)} 个对象:")
    for f_ in fixes:
        print(f"  {f_[5]:10s} {f_[1]:15s} '{f_[2]}' → {f_[3]:15s} '{f_[4]}'")

    # 应用 DB 改动
    for oid, old_code, old_name, new_code, new_name, dom in fixes:
        cur.execute("""
            UPDATE extracted_objects SET object_code=%s, object_name=%s
            WHERE object_id=%s
        """, (new_code, new_name, oid))
    conn.commit()
    print(f"[INFO] DB 已更新 {len(fixes)} 行")

    # 同步 JSON 文件
    for f_path, blob in json_cache.values():
        modified = False
        for oid, old_code, old_name, new_code, new_name, dom in fixes:
            if blob.get('data_domain') != dom and dom not in str(f_path):
                continue
            for o in blob.get('objects', []):
                if o.get('object_code') == old_code:
                    o['object_code'] = new_code
                    o['object_name'] = new_name
                    modified = True
            for r in blob.get('relations', []):
                if r.get('object_code') == old_code:
                    r['object_code'] = new_code
            if 'stats' in blob and isinstance(blob['stats'], dict):
                if old_code in blob['stats']:
                    blob['stats'][new_code] = blob['stats'].pop(old_code)
                    if isinstance(blob['stats'][new_code], dict):
                        blob['stats'][new_code]['object_name'] = new_name
        if modified:
            f_path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"  JSON 已更新: {f_path.name}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
