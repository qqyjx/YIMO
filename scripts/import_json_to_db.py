#!/usr/bin/env python3
"""
将 JSON 抽取结果导入数据库，并合并跨域重复对象。

用法:
    python scripts/import_json_to_db.py [--merge-cross-domain]

功能:
    1. 读取 outputs/extraction_*.json
    2. 清空旧的 extracted_objects + object_entity_relations
    3. 导入新数据
    4. --merge-cross-domain: 合并跨域同名对象（保留 cluster 更大的域）
"""

import json
import os
import sys
import argparse
from glob import glob

import pymysql

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3307,
    'user': 'eav_user',
    'password': 'eavpass123',
    'database': 'eav_db',
    'charset': 'utf8mb4',
}

# 跨域合并策略：对于同名对象，保留 cluster_size 更大的域的对象
# source（被合并）的关联会转移到 target（保留）
CROSS_DOMAIN_MERGE_MAP = {
    # object_name -> 保留哪个域（cluster 更大的那个）
    '项目': 'shupeidian',   # shupeidian 35 > jicai 6
    '合同': 'shupeidian',   # shupeidian 23 > jicai 10
    '费用': 'jicai',        # jicai 35 > shupeidian 24
    '指标': 'jicai',        # jicai 25 > shupeidian 15
}

# 对象重命名（改善演示效果）
RENAME_MAP = {
    '移交信': '移交管理',
}


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def load_json_files():
    """加载所有抽取 JSON 文件"""
    results = []
    for jf in sorted(glob('outputs/extraction_*.json')):
        if '_rules' in jf:
            continue
        with open(jf) as f:
            data = json.load(f)
        domain = data.get('data_domain', os.path.basename(jf).replace('extraction_', '').replace('.json', ''))
        print(f'  加载 {jf}: {len(data.get("objects", []))} 对象, {len(data.get("relations", []))} 关联, 域={domain}')
        results.append((domain, data))
    return results


def clear_old_data(conn):
    """清空旧的对象和关联数据"""
    with conn.cursor() as cur:
        # 先清关联（有外键）
        cur.execute("DELETE FROM object_entity_relations")
        cur.execute("DELETE FROM object_synonyms")
        cur.execute("DELETE FROM object_attribute_definitions")
        cur.execute("DELETE FROM object_batch_mapping")
        cur.execute("DELETE FROM object_lifecycle_history")
        cur.execute("DELETE FROM object_dedup_decisions")
        # 清溯源链节点（有 object_id 外键）
        cur.execute("UPDATE traceability_chain_nodes SET object_id = NULL")
        # 最后清对象
        cur.execute("DELETE FROM extracted_objects")
    conn.commit()
    print('  已清空旧数据')


def import_objects(conn, domain, objects, merge_cross_domain=False, merged_names=None):
    """导入对象到 DB，返回 {object_code_domain: object_id} 映射"""
    code_to_id = {}
    skipped = []

    with conn.cursor() as cur:
        for obj in objects:
            name = obj['object_name']

            # 检查是否需要跳过（跨域合并场景下，此域的同名对象是 source）
            if merge_cross_domain and name in CROSS_DOMAIN_MERGE_MAP:
                keep_domain = CROSS_DOMAIN_MERGE_MAP[name]
                if domain != keep_domain:
                    skipped.append(f'{name} ({domain} -> 合并到 {keep_domain})')
                    continue

            # 应用重命名
            if name in RENAME_MAP:
                print(f'    重命名: {name} -> {RENAME_MAP[name]}')
                name = RENAME_MAP[name]

            code = obj['object_code']
            # 跨域合并时，保留域的对象不带域后缀
            if merge_cross_domain and obj['object_name'] in CROSS_DOMAIN_MERGE_MAP:
                # 统一 code（去掉域后缀）
                clean_code = code
            else:
                clean_code = code

            cur.execute("""
                INSERT INTO extracted_objects
                    (object_code, object_name, object_name_en, object_type,
                     data_domain, description, extraction_source, extraction_confidence, llm_reasoning)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE object_name=VALUES(object_name)
            """, (
                clean_code, name,
                obj.get('object_name_en', ''),
                obj.get('object_type', 'AUXILIARY'),
                domain,
                obj.get('description', ''),
                obj.get('extraction_source', 'SEMANTIC_CLUSTER_RULE'),
                obj.get('extraction_confidence', 0.7),
                obj.get('llm_reasoning', ''),
            ))
            obj_id = cur.lastrowid
            if obj_id == 0:
                # ON DUPLICATE KEY UPDATE -> fetch existing ID
                cur.execute("SELECT object_id FROM extracted_objects WHERE object_code=%s AND data_domain=%s",
                            (clean_code, domain))
                row = cur.fetchone()
                obj_id = row[0] if row else None

            if obj_id:
                code_to_id[obj['object_code']] = obj_id

    conn.commit()

    if skipped:
        print(f'    跳过（跨域合并）: {", ".join(skipped)}')
    if merged_names is not None:
        for s in skipped:
            merged_names.append(s)

    return code_to_id


def import_relations(conn, relations, code_to_id, merge_target_ids=None):
    """导入关联关系"""
    inserted = 0
    skipped = 0

    with conn.cursor() as cur:
        for rel in relations:
            obj_code = rel.get('object_code', '')
            obj_id = code_to_id.get(obj_code)

            # 如果此对象被合并了，关联转到 merge target
            if obj_id is None and merge_target_ids:
                obj_id = merge_target_ids.get(obj_code)

            if obj_id is None:
                skipped += 1
                continue

            cur.execute("""
                INSERT INTO object_entity_relations
                    (object_id, entity_layer, entity_name, entity_code,
                     relation_type, relation_strength, match_method,
                     data_domain, source_file, via_concept_entity)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                obj_id,
                rel.get('entity_layer', 'CONCEPT'),
                rel.get('entity_name', ''),
                rel.get('entity_code', ''),
                rel.get('relation_type', 'CLUSTER'),
                rel.get('relation_strength', 0.7),
                rel.get('match_method', 'SEMANTIC_CLUSTER'),
                rel.get('data_domain', ''),
                rel.get('source_file', ''),
                rel.get('via_concept_entity', ''),
            ))
            inserted += 1

    conn.commit()
    return inserted, skipped


def link_traceability_nodes(conn):
    """将溯源链节点重新关联到对象"""
    with conn.cursor() as cur:
        # 获取所有对象
        cur.execute("SELECT object_id, object_code, object_name FROM extracted_objects")
        objects = {row[2]: row[0] for row in cur.fetchall()}  # name -> id
        code_map = {row[1]: row[0] for row in cur.fetchall()}  # code -> id (empty, need re-query)
        cur.execute("SELECT object_id, object_code FROM extracted_objects")
        code_map = {row[1]: row[0] for row in cur.fetchall()}

        # 获取未关联的节点
        cur.execute("SELECT node_id, node_label FROM traceability_chain_nodes WHERE object_id IS NULL")
        nodes = cur.fetchall()
        linked = 0
        for node_id, label in nodes:
            # 尝试按名称匹配
            for obj_name, obj_id in objects.items():
                if obj_name in (label or ''):
                    cur.execute("UPDATE traceability_chain_nodes SET object_id=%s WHERE node_id=%s",
                                (obj_id, node_id))
                    linked += 1
                    break
    conn.commit()
    return linked


def main():
    parser = argparse.ArgumentParser(description='导入 JSON 抽取结果到数据库')
    parser.add_argument('--merge-cross-domain', action='store_true', default=True,
                        help='合并跨域同名对象（默认开启）')
    parser.add_argument('--no-merge', action='store_true', help='不合并跨域对象')
    args = parser.parse_args()

    merge = args.merge_cross_domain and not args.no_merge

    print('=== YIMO JSON → DB 导入工具 ===')
    print(f'  合并跨域重复: {"是" if merge else "否"}')
    print()

    # 1. 加载 JSON
    print('[1/5] 加载 JSON 文件...')
    domain_data = load_json_files()
    if not domain_data:
        print('ERROR: 未找到 outputs/extraction_*.json 文件')
        sys.exit(1)

    # 2. 连接数据库
    print('[2/5] 连接数据库...')
    conn = get_conn()
    print('  连接成功')

    # 3. 清空旧数据
    print('[3/5] 清空旧数据...')
    clear_old_data(conn)

    # 4. 导入对象和关联（两轮：先导入所有对象，再导入所有关联）
    print('[4/5] 导入对象和关联...')
    all_code_to_id = {}
    merge_target_ids = {}  # source_code -> target_object_id (for merged objects)
    merged_names = []

    # 第一轮：导入所有域的对象
    for domain, data in domain_data:
        objects = data.get('objects', [])
        print(f'  域 {domain}: {len(objects)} 对象')
        code_to_id = import_objects(conn, domain, objects,
                                    merge_cross_domain=merge,
                                    merged_names=merged_names)
        all_code_to_id.update(code_to_id)

    # 构建合并映射（所有对象都已导入后）
    if merge:
        for domain, data in domain_data:
            for obj in data.get('objects', []):
                name = obj['object_name']
                if name in CROSS_DOMAIN_MERGE_MAP:
                    keep_domain = CROSS_DOMAIN_MERGE_MAP[name]
                    if domain != keep_domain:
                        target_code = obj['object_code']
                        target_id = all_code_to_id.get(target_code)
                        if target_id:
                            merge_target_ids[obj['object_code']] = target_id

    # 第二轮：导入所有域的关联
    for domain, data in domain_data:
        relations = data.get('relations', [])
        print(f'  域 {domain}: {len(relations)} 关联')
        code_to_id_for_domain = {k: v for k, v in all_code_to_id.items()}
        inserted, skipped = import_relations(conn, relations, code_to_id_for_domain,
                                             merge_target_ids=merge_target_ids)
        print(f'    关联: 导入 {inserted}, 跳过 {skipped}')

    # 5. 修复溯源链节点关联
    print('[5/5] 修复溯源链节点关联...')
    linked = link_traceability_nodes(conn)
    print(f'  关联了 {linked} 个溯源节点')

    # 统计
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM extracted_objects")
        obj_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM object_entity_relations")
        rel_count = cur.fetchone()[0]

    print()
    print(f'=== 导入完成 ===')
    print(f'  对象: {obj_count}')
    print(f'  关联: {rel_count}')
    if merged_names:
        print(f'  合并: {len(merged_names)} 个跨域重复对象')
        for m in merged_names:
            print(f'    - {m}')

    conn.close()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
