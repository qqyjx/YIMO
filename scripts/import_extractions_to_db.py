"""把 outputs/extraction_<中文域>.json 的抽取结果写入 MySQL.

不删旧 jicai/shupeidian 数据 (保留 lifecycle/traceability 的 FK parent),
只追加 22 中文域的对象与关联.

写入:
 - extracted_objects (每个 object 一行, data_domain=中文)
 - object_entity_relations (每个 relation 一行, object_id 取新生成的)
 - object_extraction_batches (每域一条批次记录)
 - object_batch_mapping (批次 × 对象 映射)

重复入库保护: 启动时 DELETE WHERE data_domain IN (22 个中文域名),
避免多次执行累积. jicai/shupeidian 旧数据不动.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = PROJECT_ROOT / "outputs"

DB = dict(host='127.0.0.1', port=3307, user='eav_user',
          password='eavpass123', database='eav_db', charset='utf8mb4')

# 从 DATA/ 下扫出所有中文域名
def get_chinese_domains() -> list[str]:
    data_dir = PROJECT_ROOT / 'DATA'
    return sorted([d.name for d in data_dir.iterdir()
                   if d.is_dir() and not d.name.startswith('_')])


def main() -> int:
    domains = get_chinese_domains()
    conn = pymysql.connect(**DB)
    cur = conn.cursor()

    # 1) 清除本次要导入的 22 域旧记录 (避免重复执行累积)
    print(f"[INFO] 清理 22 中文域的历史记录 (jicai/shupeidian 旧数据不动)...")
    placeholders = ','.join(['%s'] * len(domains))
    cur.execute(f"DELETE FROM object_entity_relations WHERE data_domain IN ({placeholders})", domains)
    del_rel = cur.rowcount
    cur.execute(f"DELETE FROM object_batch_mapping WHERE object_id IN (SELECT object_id FROM extracted_objects WHERE data_domain IN ({placeholders}))", domains)
    cur.execute(f"DELETE FROM extracted_objects WHERE data_domain IN ({placeholders})", domains)
    del_obj = cur.rowcount
    cur.execute(f"DELETE FROM object_extraction_batches WHERE data_domain IN ({placeholders})", domains)
    print(f"  清理 {del_obj} 对象, {del_rel} 关联")
    conn.commit()

    total_objs = 0
    total_rels = 0
    for domain in domains:
        jf = OUTPUTS / f"extraction_{domain}.json"
        if not jf.exists():
            print(f"  [SKIP] {domain}: JSON 不存在")
            continue
        with open(jf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        objects = data.get('objects', [])
        relations = data.get('relations', [])

        # 建批次 (真实列名见 DESC object_extraction_batches)
        import uuid
        batch_code = f"BATCH_{domain}_{uuid.uuid4().hex[:8]}"
        cur.execute("""
            INSERT INTO object_extraction_batches
                (batch_code, data_domain, data_domain_name,
                 total_objects_extracted, total_relations_created,
                 llm_model, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, 'COMPLETED', %s)
        """, (batch_code, domain, domain, len(objects), len(relations),
              'SEMANTIC_CLUSTER_RULE', 'batch_import_script'))
        batch_id = cur.lastrowid

        # 写对象, 维护 code → new object_id 映射
        code_to_id = {}
        for o in objects:
            cur.execute("""
                INSERT INTO extracted_objects
                    (object_code, object_name, object_name_en, object_type, data_domain,
                     description, extraction_source, extraction_confidence, llm_reasoning)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                o.get('object_code', ''), o.get('object_name', ''),
                o.get('object_name_en'), o.get('object_type', 'CORE'),
                domain, o.get('description'),
                o.get('extraction_source', 'SEMANTIC_CLUSTER_RULE'),
                o.get('extraction_confidence', 0.7),
                o.get('llm_reasoning'),
            ))
            oid = cur.lastrowid
            code_to_id[o.get('object_code', '')] = oid
            cur.execute("INSERT INTO object_batch_mapping (batch_id, object_id) VALUES (%s,%s)",
                        (batch_id, oid))

        # 写关联 (批量)
        rel_rows = []
        for r in relations:
            code = r.get('object_code', '')
            oid = code_to_id.get(code)
            if not oid:
                continue
            layer = (r.get('entity_layer') or '').upper()
            if layer not in ('CONCEPT', 'LOGICAL', 'PHYSICAL'):
                continue
            rel_rows.append((
                oid, layer,
                r.get('entity_name', '')[:512],
                (r.get('entity_code') or '')[:256] or None,
                r.get('relation_type', 'CLUSTER'),
                r.get('relation_strength', 0.7),
                r.get('match_method', 'SEMANTIC_CLUSTER'),
                r.get('via_concept_entity'),
                r.get('semantic_similarity'),
                domain,
                r.get('source_file'),
            ))

        if rel_rows:
            cur.executemany("""
                INSERT INTO object_entity_relations
                    (object_id, entity_layer, entity_name, entity_code,
                     relation_type, relation_strength, match_method,
                     via_concept_entity, semantic_similarity,
                     data_domain, source_file)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, rel_rows)

        conn.commit()
        total_objs += len(objects)
        total_rels += len(rel_rows)
        print(f"  ✓ {domain}: {len(objects)} 对象 / {len(rel_rows)} 关联 (batch={batch_id})")

    print(f"\n[DONE] 22 中文域: {total_objs} 对象 / {total_rels} 关联 入库完成")

    # 最终统计
    cur.execute("SELECT COUNT(*) FROM extracted_objects")
    print(f"  extracted_objects 总计: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM object_entity_relations")
    print(f"  object_entity_relations 总计: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(DISTINCT data_domain) FROM extracted_objects")
    print(f"  data_domain 去重数: {cur.fetchone()[0]} 个")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
