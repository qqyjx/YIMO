#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对象抽取与三层架构关联 API
Object Extraction & Three-Tier Architecture Association API

功能：
1. 抽取对象管理 API
2. 对象与三层架构关联查询 API
3. 对象抽取执行 API

作者: YIMO Team
日期: 2026-02
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, render_template, Response

import pymysql
from pymysql.cursors import DictCursor

# 添加脚本目录到路径
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
sys.path.insert(0, SCRIPT_DIR)

# 创建 Blueprint
olm_api = Blueprint('olm_api', __name__)

# JSON 数据文件目录
OUTPUTS_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / 'outputs'


# ============================================================================
# JSON 文件后备数据源（当数据库不可用时使用）
# ============================================================================

_json_cache = {}

def load_json_data(domain: str = 'shupeidian') -> dict:
    """加载 JSON 文件数据作为后备数据源"""
    cache_key = f"extraction_{domain}"

    # 检查缓存
    if cache_key in _json_cache:
        return _json_cache[cache_key]

    # 尝试加载 JSON 文件
    json_file = OUTPUTS_DIR / f"extraction_{domain}.json"
    if not json_file.exists():
        # 尝试不带域后缀的文件
        json_file = OUTPUTS_DIR / "extraction_result.json"

    if json_file.exists():
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _json_cache[cache_key] = data
                return data
        except Exception as e:
            print(f"[WARN] 加载 JSON 文件失败: {e}")

    return {}


def get_objects_from_json(domain: str = '') -> list:
    """从 JSON 文件获取对象列表，从 relations 预计算各层关联数量"""
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    relations = data.get('relations', [])

    # 预计算每个 object_code 在各层的关联数量
    stats_map = {}  # {object_code: {concept: N, logical: N, physical: N}}
    for rel in relations:
        code = rel.get('object_code', '')
        layer = rel.get('entity_layer', '').lower()
        if code and layer in ('concept', 'logical', 'physical'):
            if code not in stats_map:
                stats_map[code] = {'concept': 0, 'logical': 0, 'physical': 0}
            stats_map[code][layer] += 1

    # 预计算业务对象匹配数
    biz_matches = data.get('biz_obj_matches', {})

    result = []
    for idx, obj in enumerate(objects, start=1):
        obj_code = obj.get('object_code', '')
        st = obj.get('stats') or stats_map.get(obj_code, {'concept': 0, 'logical': 0, 'physical': 0})
        st['biz_match_count'] = len(biz_matches.get(obj_code, []))
        result.append({
            'object_id': idx,
            'object_code': obj_code,
            'object_name': obj.get('object_name', ''),
            'object_name_en': obj.get('object_name_en', ''),
            'object_type': obj.get('object_type', 'CORE'),
            'data_domain': domain or data.get('data_domain', 'shupeidian'),
            'description': obj.get('description', ''),
            'stats': st
        })

    return result


def get_relations_from_json(object_code: str, domain: str = '') -> dict:
    """从 JSON 文件获取对象关联（支持层级结构）"""
    data = load_json_data(domain or 'shupeidian')
    relations = data.get('relations', [])

    result = {'concept': [], 'logical': [], 'physical': []}

    for rel in relations:
        if rel.get('object_code') == object_code:
            layer = rel.get('entity_layer', '').lower()
            if layer in result:
                entry = {
                    'entity_name': rel.get('entity_name', ''),
                    'entity_code': rel.get('entity_code', ''),
                    'relation_type': rel.get('relation_type', 'CLUSTER'),
                    'relation_strength': rel.get('relation_strength', 0.8),
                    'data_domain': rel.get('data_domain', domain)
                }
                if layer == 'logical':
                    entry['via_concept_entity'] = rel.get('via_concept_entity', '')
                result[layer].append(entry)

    # 限制返回数量
    for layer in result:
        result[layer] = result[layer][:200]

    return result


def is_db_available() -> bool:
    """检查数据库是否可用"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception:
        return False


# ============================================================================
# 数据库连接
# ============================================================================

def get_conn():
    """获取数据库连接"""
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3307")),
        user=os.getenv("MYSQL_USER", "eav_user"),
        password=os.getenv("MYSQL_PASSWORD", "eavpass123"),
        database=os.getenv("MYSQL_DB", "eav_db"),
        charset="utf8mb4",
        autocommit=True,
        cursorclass=DictCursor,
    )


def execute_query(sql, params=None, fetch=True):
    """执行SQL查询"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch:
                    return cur.fetchall()
                return cur.lastrowid
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# 页面路由
# ============================================================================

@olm_api.route('/extraction')
def extraction_page():
    """对象抽取与三层架构关联 - 重定向到主页 10.0"""
    from flask import redirect
    return redirect('/?v=10.0')


# ============================================================================
# 抽取对象管理 API
# ============================================================================

@olm_api.route('/api/olm/extracted-objects')
def api_extracted_objects():
    """获取抽取的对象列表

    Query参数:
        domain (str): 数据域过滤，支持逗号分隔多域如 'shupeidian,jicai'，默认返回所有域
    """
    domain = request.args.get('domain', '')
    domains = [d.strip() for d in domain.split(',') if d.strip()] if domain else []

    # 优先尝试数据库
    if is_db_available():
        try:
            # 构建查询SQL（支持多域过滤）
            if len(domains) == 1:
                result = execute_query("""
                    SELECT o.*,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'CONCEPT') as concept_count,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') as logical_count,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'PHYSICAL') as physical_count
                    FROM extracted_objects o
                    WHERE o.data_domain = %s
                    ORDER BY o.object_type, o.object_name
                """, (domains[0],))
            elif len(domains) > 1:
                placeholders = ','.join(['%s'] * len(domains))
                result = execute_query(f"""
                    SELECT o.*,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'CONCEPT') as concept_count,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') as logical_count,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'PHYSICAL') as physical_count
                    FROM extracted_objects o
                    WHERE o.data_domain IN ({placeholders})
                    ORDER BY o.data_domain, o.object_type, o.object_name
                """, tuple(domains))
            else:
                result = execute_query("""
                    SELECT o.*,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'CONCEPT') as concept_count,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') as logical_count,
                           (SELECT COUNT(*) FROM object_entity_relations r
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'PHYSICAL') as physical_count
                    FROM extracted_objects o
                    ORDER BY o.data_domain, o.object_type, o.object_name
                """)

            if not isinstance(result, dict) or 'error' not in result:
                objects = []
                for row in result:
                    # 处理日期时间
                    for key in ['created_at', 'updated_at', 'verified_at']:
                        if row.get(key):
                            row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])

                    # 添加统计信息
                    row['stats'] = {
                        'concept': row.pop('concept_count', 0),
                        'logical': row.pop('logical_count', 0),
                        'physical': row.pop('physical_count', 0),
                        'biz_match_count': 0
                    }
                    objects.append(row)

                return jsonify({'objects': objects, 'total': len(objects), 'domain': domain or 'all', 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 数据库查询失败，使用 JSON 后备: {e}")

    # 数据库不可用或查询失败，使用 JSON 后备
    objects = get_objects_from_json(domain or 'shupeidian')
    return jsonify({
        'objects': objects,
        'total': len(objects),
        'domain': domain or 'shupeidian',
        'source': 'json_file'
    })


@olm_api.route('/api/olm/object-relations/<object_code>')
def api_object_relations(object_code):
    """获取对象与三层架构的关联关系

    Query参数:
        domain (str): 数据域过滤，默认返回所有域的关联
    """
    domain = request.args.get('domain', '')

    # 优先尝试数据库
    if is_db_available():
        try:
            # 获取对象ID（支持域限定）
            if domain:
                obj_result = execute_query(
                    "SELECT object_id, data_domain FROM extracted_objects WHERE object_code = %s AND data_domain = %s",
                    (object_code, domain)
                )
            else:
                obj_result = execute_query(
                    "SELECT object_id, data_domain FROM extracted_objects WHERE object_code = %s",
                    (object_code,)
                )

            if obj_result and not isinstance(obj_result, dict):
                object_id = obj_result[0]['object_id']

                # 构建关联查询（支持domain过滤）
                domain_filter = " AND r.data_domain = %s" if domain else ""
                params = (object_id, domain) if domain else (object_id,)

                concept_result = execute_query(f"""
                    SELECT r.entity_name, r.entity_code, r.relation_type,
                           r.relation_strength, r.data_domain,
                           (SELECT COUNT(DISTINCT r2.entity_name) FROM object_entity_relations r2
                            WHERE r2.object_id = r.object_id AND r2.entity_layer = 'LOGICAL'
                            AND r2.via_concept_entity = r.entity_name) as logical_count
                    FROM object_entity_relations r
                    WHERE r.object_id = %s AND r.entity_layer = 'CONCEPT'{domain_filter}
                    ORDER BY r.relation_strength DESC
                    LIMIT 50
                """, params)

                logical_result = execute_query(f"""
                    SELECT entity_name, entity_code, relation_type,
                           relation_strength, data_domain, via_concept_entity
                    FROM object_entity_relations r
                    WHERE object_id = %s AND entity_layer = 'LOGICAL'{domain_filter}
                    ORDER BY via_concept_entity, relation_strength DESC
                    LIMIT 200
                """, params)

                physical_result = execute_query(f"""
                    SELECT entity_name, entity_code, relation_type,
                           relation_strength, data_domain
                    FROM object_entity_relations r
                    WHERE object_id = %s AND entity_layer = 'PHYSICAL'{domain_filter}
                    ORDER BY relation_strength DESC
                    LIMIT 50
                """, params)

                return jsonify({
                    'concept': concept_result if not isinstance(concept_result, dict) else [],
                    'logical': logical_result if not isinstance(logical_result, dict) else [],
                    'physical': physical_result if not isinstance(physical_result, dict) else [],
                    'domain': domain or 'all',
                    'source': 'database'
                })
        except Exception as e:
            print(f"[WARN] 数据库查询关联失败，使用 JSON 后备: {e}")

    # 数据库不可用或查询失败，使用 JSON 后备
    relations = get_relations_from_json(object_code, domain or 'shupeidian')
    return jsonify({
        'concept': relations.get('concept', []),
        'logical': relations.get('logical', []),
        'physical': relations.get('physical', []),
        'domain': domain or 'shupeidian',
        'source': 'json_file'
    })


@olm_api.route('/api/olm/relation-stats')
def api_relation_stats():
    """获取对象关联统计

    Query参数:
        domain (str): 数据域过滤
    """
    try:
        domain = request.args.get('domain', '')

        if domain:
            result = execute_query("""
                SELECT * FROM v_object_relation_stats
                WHERE data_domain = %s
                ORDER BY total_entity_count DESC
            """, (domain,))
        else:
            result = execute_query("""
                SELECT * FROM v_object_relation_stats
                ORDER BY data_domain, total_entity_count DESC
            """)

        if isinstance(result, dict) and 'error' in result:
            return jsonify({'stats': [], 'error': result['error']})

        # 处理 Decimal 类型
        for row in result:
            if row.get('avg_relation_strength'):
                row['avg_relation_strength'] = float(row['avg_relation_strength'])

        return jsonify({'stats': result, 'total': len(result), 'domain': domain or 'all'})
    except Exception as e:
        return jsonify({'stats': [], 'error': str(e)})


# ============================================================================
# BA-04 业务对象桥接 API
# ============================================================================

@olm_api.route('/api/olm/object-business-objects/<object_code>')
def api_object_business_objects(object_code):
    """查询抽取对象匹配的BA-04业务对象"""
    domain = request.args.get('domain', '')

    # 尝试数据库
    if is_db_available():
        try:
            query = """
                SELECT m.business_object_name, m.match_method, m.match_score, m.data_domain
                FROM object_business_object_mapping m
                WHERE m.object_code = %s
            """
            params = [object_code]
            if domain:
                query += " AND m.data_domain = %s"
                params.append(domain)
            query += " ORDER BY m.match_score DESC LIMIT 100"
            result = execute_query(query, tuple(params))
            if isinstance(result, list):
                for row in result:
                    if row.get('match_score'):
                        row['match_score'] = float(row['match_score'])
                return jsonify({'business_objects': result, 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 查询业务对象映射失败: {e}")

    # JSON 后备
    data = load_json_data(domain or 'shupeidian')
    biz_matches = data.get('biz_obj_matches', {}).get(object_code, [])
    result = [{'business_object_name': name, 'match_score': score,
               'match_method': 'CLUSTER_ENTITY'} for name, score in biz_matches]
    return jsonify({'business_objects': result, 'source': 'json_file'})


@olm_api.route('/api/olm/small-objects')
def api_small_objects():
    """列出实体数量过少的小对象及推荐合并目标"""
    domain = request.args.get('domain', '')
    threshold = int(request.args.get('threshold', '3'))

    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    stats = data.get('stats', {})

    small_objects = []
    large_objects = []
    for obj in objects:
        obj_stats = stats.get(obj.get('object_code', ''), {})
        cluster_size = obj.get('cluster_size', 0)
        if cluster_size < threshold:
            small_objects.append({
                'object_code': obj['object_code'],
                'object_name': obj['object_name'],
                'cluster_size': cluster_size,
                'concept_count': obj_stats.get('concept', 0),
                'logical_count': obj_stats.get('logical', 0)
            })
        else:
            large_objects.append({
                'object_code': obj['object_code'],
                'object_name': obj['object_name'],
                'cluster_size': cluster_size
            })

    # 推荐合并目标: 按 cluster_size 排序的大对象
    large_objects.sort(key=lambda x: -x['cluster_size'])
    for so in small_objects:
        so['merge_candidates'] = [lo['object_code'] for lo in large_objects[:5]]

    return jsonify({
        'small_objects': small_objects,
        'threshold': threshold,
        'total_objects': len(objects),
        'small_count': len(small_objects)
    })


@olm_api.route('/api/olm/merge-objects', methods=['POST'])
def api_merge_objects():
    """合并两个对象（将 source 的关联合并到 target）"""
    body = request.get_json(force=True)
    source_code = body.get('source_code')
    target_code = body.get('target_code')

    if not source_code or not target_code:
        return jsonify({'success': False, 'error': '缺少 source_code 或 target_code'}), 400

    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        # 获取 source 和 target 的 object_id
        src = execute_query("SELECT object_id FROM extracted_objects WHERE object_code = %s", (source_code,))
        tgt = execute_query("SELECT object_id FROM extracted_objects WHERE object_code = %s", (target_code,))
        if not src or not tgt:
            return jsonify({'success': False, 'error': '对象不存在'}), 404

        src_id = src[0]['object_id']
        tgt_id = tgt[0]['object_id']

        # 将 source 的关联转移到 target（降低 strength 0.9 倍）
        execute_query("""
            INSERT IGNORE INTO object_entity_relations
            (object_id, entity_layer, entity_name, entity_code, relation_type,
             relation_strength, match_method, via_concept_entity, data_domain,
             data_subdomain, source_file, source_sheet, source_row)
            SELECT %s, entity_layer, entity_name, entity_code, relation_type,
                   relation_strength * 0.9, 'MERGE', via_concept_entity, data_domain,
                   data_subdomain, source_file, source_sheet, source_row
            FROM object_entity_relations WHERE object_id = %s
        """, (tgt_id, src_id), fetch=False)

        # 删除 source 对象及其关联
        execute_query("DELETE FROM object_entity_relations WHERE object_id = %s", (src_id,), fetch=False)
        execute_query("DELETE FROM object_business_object_mapping WHERE object_id = %s", (src_id,), fetch=False)
        execute_query("DELETE FROM extracted_objects WHERE object_id = %s", (src_id,), fetch=False)

        return jsonify({
            'success': True,
            'message': f'已将 {source_code} 合并到 {target_code}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/graph-data/<object_code>')
def api_graph_data(object_code):
    """获取单对象的知识图谱数据（ECharts Graph 格式）

    展示层级关系：对象 → 概念实体 → 逻辑实体 → 物理实体
    边表示层级归属关系，而非全部直连到对象节点。
    """
    domain = request.args.get('domain', '')
    max_concept = int(request.args.get('max_concept', '15'))
    max_logical = int(request.args.get('max_logical', '30'))
    max_physical = int(request.args.get('max_physical', '20'))

    # 复用 object-relations 数据
    data = load_json_data(domain or 'shupeidian')
    relations = data.get('relations', [])

    obj_info = None
    for obj in data.get('objects', []):
        if obj.get('object_code') == object_code:
            obj_info = obj
            break
    if not obj_info:
        return jsonify({'nodes': [], 'links': [], 'categories': []})

    categories = [
        {"name": "抽取对象"},
        {"name": "概念实体"},
        {"name": "逻辑实体"},
        {"name": "物理实体"}
    ]

    # 对象节点
    obj_stats = data.get('stats', {}).get(object_code, {})
    nodes = [{
        "id": object_code,
        "name": obj_info.get('object_name', object_code),
        "category": 0,
        "symbolSize": 50,
        "value": obj_stats.get('total', 0),
        "label": {"show": True}
    }]
    links = []
    added_nodes = {object_code}

    # 筛选该对象的关联
    obj_rels = [r for r in relations if r.get('object_code') == object_code]

    # ---- 概念实体 ----
    concept_rels = sorted(
        [r for r in obj_rels if r.get('entity_layer') == 'CONCEPT'],
        key=lambda r: -r.get('relation_strength', 0)
    )[:max_concept]
    concept_names = set()
    for r in concept_rels:
        name = r.get('entity_name', '')
        nid = f"concept_{name}"
        concept_names.add(name)
        if nid not in added_nodes:
            added_nodes.add(nid)
            nodes.append({"id": nid, "name": name, "category": 1, "value": 5})
        is_bridge = r.get('match_method') == 'BA04_BRIDGE'
        links.append({
            "source": object_code, "target": nid,
            "value": r.get('relation_strength', 0.5),
            "lineStyle": {"width": 2, "type": "dashed" if is_bridge else "solid"}
        })

    # ---- 逻辑实体（连到对应的概念实体节点而非对象节点） ----
    logical_rels = sorted(
        [r for r in obj_rels if r.get('entity_layer') == 'LOGICAL'],
        key=lambda r: -r.get('relation_strength', 0)
    )[:max_logical]
    logical_names = set()
    for r in logical_rels:
        name = r.get('entity_name', '')
        nid = f"logical_{name}"
        via = r.get('via_concept_entity', '')
        logical_names.add(name)
        if nid not in added_nodes:
            added_nodes.add(nid)
            nodes.append({"id": nid, "name": name, "category": 2, "value": 3})
        # 连到via_concept_entity对应的概念实体节点（如果存在且在图中）
        parent_id = f"concept_{via}" if via and via in concept_names else object_code
        links.append({
            "source": parent_id, "target": nid,
            "value": r.get('relation_strength', 0.5),
            "lineStyle": {"width": 1.5, "opacity": 0.5}
        })

    # ---- 物理实体（连到对应的逻辑实体节点） ----
    physical_rels = sorted(
        [r for r in obj_rels if r.get('entity_layer') == 'PHYSICAL'],
        key=lambda r: -r.get('relation_strength', 0)
    )[:max_physical]
    for r in physical_rels:
        name = r.get('entity_name', '')
        nid = f"physical_{name}"
        via = r.get('via_concept_entity', '')  # 此处via存的是逻辑实体名
        if nid not in added_nodes:
            added_nodes.add(nid)
            nodes.append({"id": nid, "name": name, "category": 3, "value": 2})
        parent_id = f"logical_{via}" if via and via in logical_names else object_code
        links.append({
            "source": parent_id, "target": nid,
            "value": r.get('relation_strength', 0.5),
            "lineStyle": {"width": 1, "opacity": 0.4}
        })

    return jsonify({
        "nodes": nodes,
        "links": links,
        "categories": categories
    })


@olm_api.route('/api/olm/graph-data-global')
def api_graph_data_global():
    """获取全局知识图谱数据（所有对象 + Top概念实体）"""
    domain = request.args.get('domain', '')
    top_concepts = int(request.args.get('top_concepts', '5'))

    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    relations = data.get('relations', [])
    stats = data.get('stats', {})

    categories = [
        {"name": "对象"},
        {"name": "概念实体"},
        {"name": "逻辑实体"}
    ]

    nodes = []
    links = []
    added_nodes = set()

    for obj in objects:
        obj_code = obj.get('object_code', '')
        obj_stats = stats.get(obj_code, {})
        size = min(60, max(20, obj.get('cluster_size', 1) * 2))
        nodes.append({
            "id": obj_code,
            "name": obj.get('object_name', obj_code),
            "category": 0,
            "symbolSize": size,
            "value": obj_stats.get('total', 0),
            "label": {"show": True}
        })
        added_nodes.add(obj_code)

        # Top N concept entities per object
        obj_concepts = sorted(
            [r for r in relations if r.get('object_code') == obj_code and r.get('entity_layer') == 'CONCEPT'],
            key=lambda r: -r.get('relation_strength', 0)
        )[:top_concepts]

        for r in obj_concepts:
            entity_name = r.get('entity_name', '')
            node_id = f"concept_{entity_name}"
            if node_id not in added_nodes:
                added_nodes.add(node_id)
                nodes.append({
                    "id": node_id,
                    "name": entity_name,
                    "category": 1,
                    "symbolSize": 15,
                    "value": r.get('relation_strength', 0.5)
                })
            links.append({
                "source": obj_code,
                "target": node_id,
                "value": r.get('relation_strength', 0.5)
            })

    return jsonify({
        "nodes": nodes,
        "links": links,
        "categories": categories
    })


@olm_api.route('/api/olm/granularity-report')
def api_granularity_report():
    """颗粒度分析报告"""
    domain = request.args.get('domain', '')
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    stats = data.get('stats', {})

    report = []
    for obj in objects:
        obj_code = obj.get('object_code', '')
        obj_stats = stats.get(obj_code, {})
        report.append({
            'object_code': obj_code,
            'object_name': obj.get('object_name', ''),
            'object_type': obj.get('object_type', ''),
            'cluster_size': obj.get('cluster_size', 0),
            'concept_count': obj_stats.get('concept', 0),
            'logical_count': obj_stats.get('logical', 0),
            'physical_count': obj_stats.get('physical', 0),
            'total_relations': obj_stats.get('total', 0),
            'cluster_relations': obj_stats.get('cluster_relations', 0),
            'bridge_relations': obj_stats.get('bridge_relations', 0)
        })

    report.sort(key=lambda x: -x['cluster_size'])

    sizes = [r['cluster_size'] for r in report]
    return jsonify({
        'report': report,
        'summary': {
            'total_objects': len(report),
            'avg_cluster_size': round(sum(sizes) / len(sizes), 1) if sizes else 0,
            'max_cluster_size': max(sizes) if sizes else 0,
            'min_cluster_size': min(sizes) if sizes else 0,
            'small_objects': len([s for s in sizes if s < 3]),
            'domain': domain or 'all'
        }
    })


# ============================================================================
# 对象抽取执行 API
# ============================================================================

@olm_api.route('/api/olm/run-extraction', methods=['POST'])
def api_run_extraction():
    """执行对象抽取

    请求参数:
        use_llm (bool): 是否使用LLM命名，默认False
        target_clusters (int): 目标聚类数，默认15
        domains (list): 要处理的数据域列表，如 ['shupeidian', 'jicai']，默认 ['shupeidian']
        excel_files (dict): 可选，指定每个域的Excel文件列表，如 {'shupeidian': ['1.xlsx', '2.xlsx']}
    """
    try:
        data = request.json or {}
        use_llm = data.get('use_llm', False)
        target_clusters = data.get('target_clusters', 15)
        domains = data.get('domains', ['shupeidian'])
        excel_files_map = data.get('excel_files', {})  # 每个域对应的文件列表

        # 导入抽取模块
        from object_extractor import SemanticObjectExtractionPipeline

        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(__file__))
        data_dir = os.path.join(project_root, 'DATA')

        # 配置数据库
        db_config = {
            'host': os.getenv("MYSQL_HOST", "127.0.0.1"),
            'port': int(os.getenv("MYSQL_PORT", "3307")),
            'user': os.getenv("MYSQL_USER", "eav_user"),
            'password': os.getenv("MYSQL_PASSWORD", "eavpass123"),
            'database': os.getenv("MYSQL_DB", "eav_db")
        }

        # 合并结果
        total_objects = []
        total_relations = 0
        all_clusters = []
        processed_domains = []

        # 对每个域执行抽取（所有文件都在DATA目录下）
        for domain in domains:
            # 获取该域的文件列表（从请求参数或使用默认配置）
            domain_files = excel_files_map.get(domain, None)

            pipeline = SemanticObjectExtractionPipeline(
                data_dir=data_dir,
                db_config=db_config,
                target_clusters=target_clusters,
                data_domain=domain,
                excel_files=domain_files  # 如果为None，将使用DOMAIN_CONFIG配置
            )
            result = pipeline.run(use_llm=use_llm)

            total_objects.extend(result.get('objects', []))
            total_relations += result.get('relations_count', 0)
            all_clusters.extend(result.get('clusters', []))
            processed_domains.append({
                'domain': domain,
                'domain_name': result.get('data_domain_name', ''),
                'objects_count': len(result.get('objects', [])),
                'relations_count': result.get('relations_count', 0)
            })

        return jsonify({
            'success': True,
            'objects_count': len(total_objects),
            'relations_count': total_relations,
            'clusters': all_clusters,
            'domains_processed': processed_domains
        })

    except ImportError as e:
        return jsonify({
            'success': False,
            'error': f'对象抽取模块未安装: {str(e)}'
        }), 503
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@olm_api.route('/api/olm/export-objects')
def api_export_objects():
    """导出抽取的对象和关联关系

    Query参数:
        domain (str): 数据域过滤，默认导出所有域
    """
    try:
        domain = request.args.get('domain', '')

        # 获取对象（支持domain过滤）
        if domain:
            objects = execute_query("""
                SELECT * FROM extracted_objects WHERE data_domain = %s
                ORDER BY object_type, object_name
            """, (domain,))
            relations = execute_query("""
                SELECT o.object_code, o.data_domain as object_domain, r.entity_layer, r.entity_name, r.entity_code,
                       r.relation_type, r.relation_strength, r.via_concept_entity, r.data_domain
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE o.data_domain = %s
                ORDER BY o.object_code, r.entity_layer, r.relation_strength DESC
            """, (domain,))
        else:
            objects = execute_query("""
                SELECT * FROM extracted_objects ORDER BY data_domain, object_type, object_name
            """)
            relations = execute_query("""
                SELECT o.object_code, o.data_domain as object_domain, r.entity_layer, r.entity_name, r.entity_code,
                       r.relation_type, r.relation_strength, r.via_concept_entity, r.data_domain
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                ORDER BY o.data_domain, o.object_code, r.entity_layer, r.relation_strength DESC
            """)

        # 处理日期时间
        if not isinstance(objects, dict):
            for obj in objects:
                for key in ['created_at', 'updated_at', 'verified_at']:
                    if obj.get(key):
                        obj[key] = obj[key].isoformat() if hasattr(obj[key], 'isoformat') else str(obj[key])

        if not isinstance(relations, dict):
            for rel in relations:
                if rel.get('relation_strength'):
                    rel['relation_strength'] = float(rel['relation_strength'])

        export_data = {
            'export_time': datetime.now().isoformat(),
            'domain': domain or 'all',
            'objects': objects if not isinstance(objects, dict) else [],
            'relations': relations if not isinstance(relations, dict) else []
        }

        filename = f'extracted_objects_{domain}.json' if domain else 'extracted_objects_all.json'
        return Response(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# 对象管理 CRUD API
# ============================================================================

@olm_api.route('/api/olm/objects', methods=['POST'])
def api_create_object():
    """创建新对象

    请求参数:
        object_code (str): 对象编码
        object_name (str): 对象名称
        data_domain (str): 数据域，默认'default'
        ...其他字段
    """
    try:
        data = request.json or {}

        object_code = data.get('object_code')
        object_name = data.get('object_name')
        data_domain = data.get('data_domain', 'default')

        if not object_code or not object_name:
            return jsonify({'error': 'Missing object_code or object_name'}), 400

        sql = """
            INSERT INTO extracted_objects
            (object_code, object_name, object_name_en, object_type, data_domain, description,
             extraction_source, extraction_confidence, is_verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        result = execute_query(sql, (
            object_code,
            object_name,
            data.get('object_name_en', ''),
            data.get('object_type', 'CORE'),
            data_domain,
            data.get('description', ''),
            'MANUAL',
            1.0,
            True
        ), fetch=False)

        if isinstance(result, dict) and 'error' in result:
            return jsonify(result), 500

        return jsonify({'success': True, 'object_id': result, 'data_domain': data_domain})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@olm_api.route('/api/olm/objects/<object_code>', methods=['PUT'])
def api_update_object(object_code):
    """更新对象"""
    try:
        data = request.json or {}

        updates = []
        params = []

        if 'object_name' in data:
            updates.append('object_name = %s')
            params.append(data['object_name'])

        if 'object_name_en' in data:
            updates.append('object_name_en = %s')
            params.append(data['object_name_en'])

        if 'object_type' in data:
            updates.append('object_type = %s')
            params.append(data['object_type'])

        if 'description' in data:
            updates.append('description = %s')
            params.append(data['description'])

        if 'is_verified' in data:
            updates.append('is_verified = %s')
            params.append(data['is_verified'])
            if data['is_verified']:
                updates.append('verified_at = NOW()')

        if not updates:
            return jsonify({'error': 'No fields to update'}), 400

        params.append(object_code)
        sql = f"UPDATE extracted_objects SET {', '.join(updates)} WHERE object_code = %s"

        execute_query(sql, tuple(params), fetch=False)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@olm_api.route('/api/olm/objects/<object_code>', methods=['DELETE'])
def api_delete_object(object_code):
    """删除对象"""
    try:
        execute_query(
            "DELETE FROM extracted_objects WHERE object_code = %s",
            (object_code,),
            fetch=False
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# 抽取批次 API
# ============================================================================

@olm_api.route('/api/olm/batches')
def api_extraction_batches():
    """获取抽取批次列表"""
    try:
        result = execute_query("""
            SELECT * FROM object_extraction_batches
            ORDER BY extraction_time DESC
            LIMIT 50
        """)

        if isinstance(result, dict) and 'error' in result:
            return jsonify({'batches': [], 'error': result['error']})

        for row in result:
            if row.get('extraction_time'):
                row['extraction_time'] = row['extraction_time'].isoformat()
            if row.get('source_files') and isinstance(row['source_files'], str):
                try:
                    row['source_files'] = json.loads(row['source_files'])
                except:
                    pass

        return jsonify({'batches': result, 'total': len(result)})
    except Exception as e:
        return jsonify({'batches': [], 'error': str(e)})


# ============================================================================
# 统计 API
# ============================================================================

@olm_api.route('/api/olm/stats')
def api_stats():
    """获取系统统计信息

    Query参数:
        domain (str): 数据域过滤，默认返回全局统计
    """
    try:
        domain = request.args.get('domain', '')
        stats = {'domain': domain or 'all'}

        # 对象统计
        if domain:
            result = execute_query("SELECT COUNT(*) as cnt FROM extracted_objects WHERE data_domain = %s", (domain,))
        else:
            result = execute_query("SELECT COUNT(*) as cnt FROM extracted_objects")
        stats['objects_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

        # 关联关系统计
        if domain:
            result = execute_query("""
                SELECT COUNT(*) as cnt FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE o.data_domain = %s
            """, (domain,))
        else:
            result = execute_query("SELECT COUNT(*) as cnt FROM object_entity_relations")
        stats['relations_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

        # 按层级统计关联
        if domain:
            result = execute_query("""
                SELECT r.entity_layer, COUNT(*) as cnt
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE o.data_domain = %s
                GROUP BY r.entity_layer
            """, (domain,))
        else:
            result = execute_query("""
                SELECT entity_layer, COUNT(*) as cnt
                FROM object_entity_relations
                GROUP BY entity_layer
            """)
        if result and not isinstance(result, dict):
            stats['relations_by_layer'] = {r['entity_layer']: r['cnt'] for r in result}
        else:
            stats['relations_by_layer'] = {}

        # 按对象类型统计
        if domain:
            result = execute_query("""
                SELECT object_type, COUNT(*) as cnt
                FROM extracted_objects
                WHERE data_domain = %s
                GROUP BY object_type
            """, (domain,))
        else:
            result = execute_query("""
                SELECT object_type, COUNT(*) as cnt
                FROM extracted_objects
                GROUP BY object_type
            """)
        if result and not isinstance(result, dict):
            stats['objects_by_type'] = {r['object_type']: r['cnt'] for r in result}
        else:
            stats['objects_by_type'] = {}

        # 批次统计
        if domain:
            result = execute_query("SELECT COUNT(*) as cnt FROM object_extraction_batches WHERE data_domain = %s", (domain,))
        else:
            result = execute_query("SELECT COUNT(*) as cnt FROM object_extraction_batches")
        stats['batches_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@olm_api.route('/api/olm/domain-stats')
def api_domain_stats():
    """获取各数据域的统计信息"""
    try:
        result = execute_query("""
            SELECT * FROM v_domain_stats ORDER BY object_count DESC
        """)

        if isinstance(result, dict) and 'error' in result:
            return jsonify({'stats': [], 'error': result['error']})

        # 处理 Decimal 类型
        for row in result:
            if row.get('avg_relation_strength'):
                row['avg_relation_strength'] = float(row['avg_relation_strength'])

        return jsonify({'stats': result, 'total': len(result)})
    except Exception as e:
        return jsonify({'stats': [], 'error': str(e)})


# ============================================================================
# 桑基图数据 API
# ============================================================================

def get_sankey_from_json(domain: str = '') -> dict:
    """从 JSON 文件构建桑基图数据"""
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    relations = data.get('relations', [])

    nodes = []
    links = []
    node_set = set()

    # 按 object_code 分组 relations
    obj_concepts = {}  # {obj_code: [(entity_name, strength, logical_count)]}
    layer_counts = {'LOGICAL': 0, 'PHYSICAL': 0}

    for rel in relations:
        layer = rel.get('entity_layer', '').upper()
        if layer in ('LOGICAL', 'PHYSICAL'):
            layer_counts[layer] += 1

    # 构建 concept→logical 映射
    concept_logical_count = {}
    for rel in relations:
        if rel.get('entity_layer', '').upper() == 'LOGICAL':
            via = rel.get('via_concept_entity', '')
            obj_code = rel.get('object_code', '')
            key = (obj_code, via)
            concept_logical_count[key] = concept_logical_count.get(key, 0) + 1

    for obj in objects:
        code = obj.get('object_code', '')
        name = obj.get('object_name', '')
        if name and name not in node_set:
            nodes.append({'name': name, 'depth': 0, 'type': 'object'})
            node_set.add(name)

        # 该对象的 concept 实体
        obj_concepts_list = []
        for rel in relations:
            if rel.get('object_code') == code and rel.get('entity_layer', '').upper() == 'CONCEPT':
                e_name = rel.get('entity_name', '')
                strength = rel.get('relation_strength', 0)
                lc = concept_logical_count.get((code, e_name), 0)
                obj_concepts_list.append((e_name, strength, lc))

        # Top 5 by strength
        obj_concepts_list.sort(key=lambda x: x[1], reverse=True)
        for e_name, strength, lc in obj_concepts_list[:5]:
            concept_node = f"{e_name}({name})"
            if concept_node not in node_set:
                nodes.append({'name': concept_node, 'depth': 1, 'type': 'concept'})
                node_set.add(concept_node)
            links.append({'source': name, 'target': concept_node, 'value': max(1, lc)})
            if lc > 0:
                links.append({'source': concept_node, 'target': '逻辑实体层', 'value': lc})

    # 聚合节点
    if layer_counts['LOGICAL'] > 0:
        if '逻辑实体层' not in node_set:
            nodes.append({'name': '逻辑实体层', 'depth': 2, 'type': 'logical_agg'})
            node_set.add('逻辑实体层')
    if layer_counts['PHYSICAL'] > 0:
        if '物理实体层' not in node_set:
            nodes.append({'name': '物理实体层', 'depth': 3, 'type': 'physical_agg'})
            node_set.add('物理实体层')
        links.append({'source': '逻辑实体层', 'target': '物理实体层', 'value': layer_counts['PHYSICAL']})

    return {'nodes': nodes, 'links': links, 'domain': domain or 'shupeidian'}


@olm_api.route('/api/olm/sankey-data')
def api_sankey_data():
    """获取桑基图可视化数据

    返回对象→Top5概念实体→逻辑实体层→物理实体层的完整流向数据。

    Query参数:
        domain (str): 数据域过滤
    """
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            # 1. 获取对象列表
            if domain:
                objects = execute_query(
                    "SELECT object_id, object_code, object_name FROM extracted_objects WHERE data_domain = %s ORDER BY object_type, object_name",
                    (domain,)
                )
            else:
                objects = execute_query(
                    "SELECT object_id, object_code, object_name FROM extracted_objects ORDER BY object_type, object_name"
                )

            if isinstance(objects, dict) and 'error' in objects:
                raise Exception(objects['error'])

            nodes = []
            links = []
            node_set = set()

            # 2. 为每个对象查询 Top-5 概念实体
            for obj in objects:
                obj_name = obj['object_name']
                obj_id = obj['object_id']

                if obj_name not in node_set:
                    nodes.append({'name': obj_name, 'depth': 0, 'type': 'object'})
                    node_set.add(obj_name)

                top_concepts = execute_query("""
                    SELECT r.entity_name, r.relation_strength,
                           (SELECT COUNT(DISTINCT r2.entity_name) FROM object_entity_relations r2
                            WHERE r2.object_id = r.object_id AND r2.entity_layer = 'LOGICAL'
                            AND r2.via_concept_entity = r.entity_name) as logical_count
                    FROM object_entity_relations r
                    WHERE r.object_id = %s AND r.entity_layer = 'CONCEPT'
                    ORDER BY r.relation_strength DESC
                    LIMIT 5
                """, (obj_id,))

                if isinstance(top_concepts, dict):
                    continue

                for c in top_concepts:
                    concept_node = f"{c['entity_name']}({obj_name})"
                    lc = c.get('logical_count', 0)
                    if concept_node not in node_set:
                        nodes.append({'name': concept_node, 'depth': 1, 'type': 'concept'})
                        node_set.add(concept_node)
                    links.append({'source': obj_name, 'target': concept_node, 'value': max(1, lc)})
                    if lc > 0:
                        links.append({'source': concept_node, 'target': '逻辑实体层', 'value': lc})

            # 3. 汇总逻辑和物理层总数
            domain_filter = " AND o.data_domain = %s" if domain else ""
            params = (domain,) if domain else ()
            layer_agg = execute_query(f"""
                SELECT r.entity_layer, COUNT(*) as cnt
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE r.entity_layer IN ('LOGICAL', 'PHYSICAL'){domain_filter}
                GROUP BY r.entity_layer
            """, params)

            layer_map = {}
            if not isinstance(layer_agg, dict):
                layer_map = {r['entity_layer']: r['cnt'] for r in layer_agg}

            if layer_map.get('LOGICAL', 0) > 0:
                if '逻辑实体层' not in node_set:
                    nodes.append({'name': '逻辑实体层', 'depth': 2, 'type': 'logical_agg'})
                    node_set.add('逻辑实体层')

            if layer_map.get('PHYSICAL', 0) > 0:
                if '物理实体层' not in node_set:
                    nodes.append({'name': '物理实体层', 'depth': 3, 'type': 'physical_agg'})
                    node_set.add('物理实体层')
                links.append({'source': '逻辑实体层', 'target': '物理实体层', 'value': layer_map['PHYSICAL']})

            return jsonify({'nodes': nodes, 'links': links, 'domain': domain or 'all', 'source': 'database'})

        except Exception as e:
            print(f"[WARN] 桑基图数据库查询失败，使用 JSON 后备: {e}")

    result = get_sankey_from_json(domain)
    result['source'] = 'json_file'
    return jsonify(result)


# ============================================================================
# 实体搜索 API
# ============================================================================

def search_entities_from_json(query: str, layer: str = '', domain: str = '', limit: int = 30) -> list:
    """从 JSON 文件搜索实体"""
    data = load_json_data(domain or 'shupeidian')
    relations = data.get('relations', [])
    objects = {o.get('object_code', ''): o.get('object_name', '') for o in data.get('objects', [])}

    q = query.lower()
    results = []
    seen = set()

    for rel in relations:
        e_name = rel.get('entity_name', '')
        e_layer = rel.get('entity_layer', '').upper()
        obj_code = rel.get('object_code', '')

        if layer and e_layer != layer.upper():
            continue
        if q not in e_name.lower():
            continue

        key = (e_name, e_layer, obj_code)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            'entity_name': e_name,
            'entity_layer': e_layer,
            'object_code': obj_code,
            'object_name': objects.get(obj_code, ''),
            'relation_strength': rel.get('relation_strength', 0)
        })

        if len(results) >= limit:
            break

    results.sort(key=lambda x: x.get('relation_strength', 0), reverse=True)
    return results


@olm_api.route('/api/olm/search-entities')
def api_search_entities():
    """搜索实体名称

    在三层架构的实体中按名称模糊搜索。

    Query参数:
        q (str): 搜索关键词（必填）
        layer (str): 层级过滤 concept/logical/physical（可选）
        domain (str): 数据域过滤（可选）
        limit (int): 返回上限，默认30，最大100
    """
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'q parameter is required', 'results': []}), 400

    layer = request.args.get('layer', '').strip().upper()
    domain = request.args.get('domain', '').strip()
    limit = min(int(request.args.get('limit', '30')), 100)

    if layer and layer not in ('CONCEPT', 'LOGICAL', 'PHYSICAL'):
        return jsonify({'error': 'layer must be concept, logical, or physical', 'results': []}), 400

    if is_db_available():
        try:
            like_q = f'%{query}%'

            # 构建动态 WHERE 条件
            conditions = ["r.entity_name LIKE %s"]
            params = [like_q]

            if layer:
                conditions.append("r.entity_layer = %s")
                params.append(layer)

            if domain:
                conditions.append("o.data_domain = %s")
                params.append(domain)

            params.append(limit)

            where_clause = " AND ".join(conditions)
            result = execute_query(f"""
                SELECT DISTINCT r.entity_name, r.entity_layer,
                       o.object_code, o.object_name, r.relation_strength
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE {where_clause}
                ORDER BY r.relation_strength DESC
                LIMIT %s
            """, tuple(params))

            if isinstance(result, dict) and 'error' in result:
                raise Exception(result['error'])

            # 处理 Decimal 类型
            for row in result:
                if row.get('relation_strength'):
                    row['relation_strength'] = float(row['relation_strength'])

            return jsonify({
                'results': result,
                'total': len(result),
                'query': query,
                'source': 'database'
            })
        except Exception as e:
            print(f"[WARN] 实体搜索数据库查询失败，使用 JSON 后备: {e}")

    results = search_entities_from_json(query, layer, domain, limit)
    return jsonify({
        'results': results,
        'total': len(results),
        'query': query,
        'source': 'json_file'
    })


# ============================================================================
# 汇总统计 API
# ============================================================================

def get_summary_from_json(domain: str = '') -> dict:
    """从 JSON 文件计算汇总统计"""
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    relations = data.get('relations', [])

    by_type = {}
    for obj in objects:
        t = obj.get('object_type', 'CORE')
        by_type[t] = by_type.get(t, 0) + 1

    concept_count = 0
    logical_count = 0
    physical_count = 0
    by_rel_type = {}

    for rel in relations:
        layer = rel.get('entity_layer', '').upper()
        if layer == 'CONCEPT':
            concept_count += 1
        elif layer == 'LOGICAL':
            logical_count += 1
        elif layer == 'PHYSICAL':
            physical_count += 1

        rt = rel.get('relation_type', '')
        by_rel_type[rt] = by_rel_type.get(rt, 0) + 1

    # Top objects
    obj_totals = {}
    for rel in relations:
        code = rel.get('object_code', '')
        obj_totals[code] = obj_totals.get(code, 0) + 1
    obj_name_map = {o.get('object_code', ''): o.get('object_name', '') for o in objects}
    top_objects = sorted(
        [{'object_code': k, 'object_name': obj_name_map.get(k, k), 'total_relations': v}
         for k, v in obj_totals.items()],
        key=lambda x: x['total_relations'], reverse=True
    )[:5]

    return {
        'domain': domain or 'shupeidian',
        'objects_count': len(objects),
        'objects_by_type': by_type,
        'concept_count': concept_count,
        'logical_count': logical_count,
        'physical_count': physical_count,
        'relations_count': len(relations),
        'relations_by_type': by_rel_type,
        'top_objects': top_objects,
    }


@olm_api.route('/api/olm/summary')
def api_summary():
    """获取仪表板汇总统计

    一次请求返回前端仪表板需要的所有统计数据。

    Query参数:
        domain (str): 数据域过滤，默认返回全局统计
    """
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            summary = {'domain': domain or 'all'}

            domain_filter = " WHERE data_domain = %s" if domain else ""
            rel_domain_filter = " AND o.data_domain = %s" if domain else ""
            params = (domain,) if domain else ()

            # 对象统计
            result = execute_query(
                f"SELECT COUNT(*) as cnt FROM extracted_objects{domain_filter}", params
            )
            summary['objects_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

            # 按类型统计
            result = execute_query(
                f"SELECT object_type, COUNT(*) as cnt FROM extracted_objects{domain_filter} GROUP BY object_type",
                params
            )
            summary['objects_by_type'] = {r['object_type']: r['cnt'] for r in result} if result and not isinstance(result, dict) else {}

            # 各层关联数量
            result = execute_query(f"""
                SELECT r.entity_layer, COUNT(*) as cnt
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE 1=1{rel_domain_filter}
                GROUP BY r.entity_layer
            """, params)
            layer_map = {}
            if result and not isinstance(result, dict):
                layer_map = {r['entity_layer']: r['cnt'] for r in result}

            summary['concept_count'] = layer_map.get('CONCEPT', 0)
            summary['logical_count'] = layer_map.get('LOGICAL', 0)
            summary['physical_count'] = layer_map.get('PHYSICAL', 0)
            summary['relations_count'] = sum(layer_map.values())

            # 按关联类型统计
            result = execute_query(f"""
                SELECT r.relation_type, COUNT(*) as cnt
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE 1=1{rel_domain_filter}
                GROUP BY r.relation_type
            """, params)
            summary['relations_by_type'] = {r['relation_type']: r['cnt'] for r in result} if result and not isinstance(result, dict) else {}

            # Top 对象
            result = execute_query(f"""
                SELECT o.object_code, o.object_name, COUNT(*) as total_relations
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE 1=1{rel_domain_filter}
                GROUP BY o.object_code, o.object_name
                ORDER BY total_relations DESC
                LIMIT 5
            """, params)
            summary['top_objects'] = list(result) if result and not isinstance(result, dict) else []

            summary['source'] = 'database'
            return jsonify(summary)

        except Exception as e:
            print(f"[WARN] 汇总统计数据库查询失败，使用 JSON 后备: {e}")

    result = get_summary_from_json(domain)
    result['source'] = 'json_file'
    return jsonify(result)
