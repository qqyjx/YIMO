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
import time
import threading
from collections import deque
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
# TP/AP 工作负载追踪器（内存计数器，用于 HTAP 融合可视化）
# ============================================================================

# API 端点 → 工作负载类型映射
_WORKLOAD_MAP = {
    # TP（事务处理）: 写入操作
    'POST /api/olm/objects': 'TP',
    'PUT /api/olm/objects': 'TP',
    'DELETE /api/olm/objects': 'TP',
    'POST /api/olm/object-lifecycle': 'TP',
    'POST /api/olm/lifecycle-batch-advance': 'TP',
    'POST /api/olm/relation-rules': 'TP',
    'PUT /api/olm/relation-rules': 'TP',
    'DELETE /api/olm/relation-rules': 'TP',
    'POST /api/olm/relation-rules/evaluate': 'TP',
    'POST /api/olm/relation-rules/evaluate-with-eav': 'TP',
    'POST /api/olm/formula-chains': 'TP',
    'POST /api/olm/mechanism-functions': 'TP',
    'PUT /api/olm/mechanism-functions': 'TP',
    'DELETE /api/olm/mechanism-functions': 'TP',
    'POST /api/olm/mechanism-functions/evaluate': 'TP',
    'POST /api/olm/alerts': 'TP',
    'POST /api/olm/alerts/resolve': 'TP',
    'POST /api/olm/alerts/run-check': 'TP',
    'POST /api/olm/traceability-chains': 'TP',
    'POST /api/olm/merge-objects': 'TP',
    'POST /api/olm/dedup-objects': 'TP',
    'POST /api/olm/bulk-merge-small': 'TP',
    'POST /api/olm/run-extraction': 'TP',
    'POST /api/olm/lifecycle-templates': 'TP',
    # AP（分析处理）: 聚合查询
    'GET /api/olm/governance/metrics': 'AP',
    'GET /api/olm/governance/completeness': 'AP',
    'GET /api/olm/governance/defects': 'AP',
    'GET /api/olm/governance/domain-comparison': 'AP',
    'GET /api/olm/lifecycle-stats': 'AP',
    'GET /api/olm/field-lineage': 'AP',
    'GET /api/olm/graph-data-three-tier': 'AP',
    'GET /api/olm/graph-data-global': 'AP',
    'GET /api/olm/sankey-data': 'AP',
    'GET /api/olm/relation-rules/graph': 'AP',
    'GET /api/olm/relation-stats': 'AP',
    'GET /api/olm/domain-stats': 'AP',
    'GET /api/olm/granularity-report': 'AP',
    'GET /api/olm/cross-domain-duplicates': 'AP',
    'GET /api/olm/summary': 'AP',
    'GET /api/olm/stats': 'AP',
    'GET /api/olm/formula-chains': 'AP',
    'GET /api/olm/lifecycle-templates': 'AP',
}

_workload_lock = threading.Lock()
_workload_log = deque(maxlen=50)  # 最近 50 条操作记录
_workload_counters = {'TP': 0, 'AP': 0, 'tp_total_ms': 0.0, 'ap_total_ms': 0.0}


def _classify_workload(method: str, path: str) -> str:
    """根据 HTTP 方法和路径分类工作负载类型"""
    key = f"{method} {path}"
    # 精确匹配
    if key in _WORKLOAD_MAP:
        return _WORKLOAD_MAP[key]
    # 前缀匹配（处理带路径参数的端点）
    for pattern, wtype in _WORKLOAD_MAP.items():
        pm, pp = pattern.split(' ', 1)
        if method == pm and path.startswith(pp):
            return wtype
    # 默认：POST/PUT/DELETE → TP, GET → AP
    if method in ('POST', 'PUT', 'DELETE'):
        return 'TP'
    return 'AP'


@olm_api.before_request
def _record_request_start():
    """记录请求开始时间"""
    request._workload_start = time.time()


@olm_api.after_request
def _record_workload(response):
    """记录工作负载并添加 X-Workload-Type header"""
    if not request.path.startswith('/api/olm/'):
        return response
    # 跳过 workload-stats 自身
    if request.path == '/api/olm/workload-stats':
        return response

    elapsed_ms = (time.time() - getattr(request, '_workload_start', time.time())) * 1000
    wtype = _classify_workload(request.method, request.path)
    response.headers['X-Workload-Type'] = wtype

    # 生成简短描述
    desc = f"{request.method} {request.path.replace('/api/olm/', '')}"
    if len(desc) > 60:
        desc = desc[:57] + '...'

    entry = {
        'type': wtype,
        'method': request.method,
        'path': request.path,
        'desc': desc,
        'ms': round(elapsed_ms, 1),
        'status': response.status_code,
        'ts': datetime.now().strftime('%H:%M:%S'),
    }

    with _workload_lock:
        _workload_log.append(entry)
        _workload_counters[wtype] += 1
        _workload_counters[f'{wtype.lower()}_total_ms'] += elapsed_ms

    return response


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
        samples = obj.get('sample_entities', [])
        result.append({
            'object_id': idx,
            'object_code': obj_code,
            'object_name': obj.get('object_name', ''),
            'object_name_en': obj.get('object_name_en', ''),
            'object_type': obj.get('object_type', 'CORE'),
            'data_domain': domain or data.get('data_domain', 'shupeidian'),
            'description': obj.get('description', ''),
            'extraction_source': obj.get('extraction_source', 'SEMANTIC_CLUSTER_RULE'),
            'extraction_confidence': obj.get('extraction_confidence', 0.7),
            'llm_reasoning': obj.get('llm_reasoning', ''),
            'cluster_size': obj.get('cluster_size', len(samples)),
            'sample_entities': samples,
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


def _load_data_from_db(domain=''):
    """从数据库加载对象和关联数据，返回与 load_json_data() 兼容的 dict 格式。
    DB优先策略：成功时返回 dict，失败或DB不可用时返回 None，调用方应回退到 load_json_data()。
    """
    if not is_db_available():
        return None
    try:
        # 查询对象
        if domain:
            objects_raw = execute_query(
                "SELECT * FROM extracted_objects WHERE data_domain = %s ORDER BY object_type, object_name",
                (domain,))
        else:
            objects_raw = execute_query(
                "SELECT * FROM extracted_objects ORDER BY data_domain, object_type, object_name")
        if isinstance(objects_raw, dict):
            return None

        # 查询关联
        rel_sql = """
            SELECT o.object_code, r.entity_layer, r.entity_name, r.entity_code,
                   r.relation_type, r.relation_strength, r.via_concept_entity,
                   r.match_method, r.data_domain, r.source_file
            FROM object_entity_relations r
            JOIN extracted_objects o ON o.object_id = r.object_id
        """
        if domain:
            rel_sql += " WHERE o.data_domain = %s"
            relations_raw = execute_query(rel_sql, (domain,))
        else:
            relations_raw = execute_query(rel_sql)
        if isinstance(relations_raw, dict):
            relations_raw = []

        # Decimal → float
        for r in relations_raw:
            if r.get('relation_strength') is not None:
                r['relation_strength'] = float(r['relation_strength'])

        # 计算统计（与JSON中stats格式一致）
        stats = {}
        for r in relations_raw:
            code = r.get('object_code', '')
            layer = (r.get('entity_layer') or '').lower()
            if code not in stats:
                stats[code] = {'concept': 0, 'logical': 0, 'physical': 0, 'total': 0,
                               'cluster_relations': 0, 'bridge_relations': 0}
            if layer in ('concept', 'logical', 'physical'):
                stats[code][layer] += 1
                stats[code]['total'] += 1

        # 格式化对象
        objects = []
        for obj in objects_raw:
            code = obj.get('object_code', '')
            for key in ['created_at', 'updated_at', 'verified_at']:
                if obj.get(key):
                    obj[key] = obj[key].isoformat() if hasattr(obj[key], 'isoformat') else str(obj[key])
            obj['cluster_size'] = stats.get(code, {}).get('total', 0)
            objects.append(obj)

        return {
            'objects': objects,
            'relations': relations_raw,
            'stats': stats,
            'data_domain': domain or 'all',
            'source': 'database'
        }
    except Exception:
        return None


def _load_data(domain=''):
    """统一数据加载入口：DB优先，JSON回退"""
    db_data = _load_data_from_db(domain)
    if db_data is not None:
        return db_data
    return load_json_data(domain or 'shupeidian')


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
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') as logical_count
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
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') as logical_count
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
                            WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') as logical_count
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

                    # 处理 Decimal 类型
                    if row.get('extraction_confidence') is not None:
                        row['extraction_confidence'] = float(row['extraction_confidence'])

                    # 添加统计信息
                    row['stats'] = {
                        'concept': row.pop('concept_count', 0),
                        'logical': row.pop('logical_count', 0),
                        'physical': 0,
                        'biz_match_count': 0
                    }
                    objects.append(row)

                # DB 空但 JSON 文件存在 (新抽取尚未入库)时, 降级到 JSON 读取
                if not objects and domains:
                    json_union = []
                    for d in domains:
                        if (OUTPUTS_DIR / f'extraction_{d}.json').exists():
                            json_union.extend(get_objects_from_json(d))
                    if json_union:
                        return jsonify({
                            'objects': json_union, 'total': len(json_union),
                            'domain': domain, 'source': 'json_file',
                            'note': 'DB 无此域数据, 已回落到 outputs/extraction_*.json'
                        })
                elif not objects and not domains:
                    # 无 domain 过滤时, DB 空 = 全部走 JSON 汇总
                    import glob as _glob
                    all_objs = []
                    for jf in sorted(_glob.glob(str(OUTPUTS_DIR / 'extraction_*.json'))):
                        if jf.endswith('extraction_global.json'):
                            continue
                        try:
                            with open(jf, 'r', encoding='utf-8') as _f:
                                _d = json.load(_f)
                            dom_name = _d.get('data_domain') or os.path.basename(jf).replace('extraction_', '').replace('.json', '')
                            for _o in _d.get('objects', []):
                                _o2 = dict(_o)
                                _o2['data_domain'] = dom_name
                                all_objs.append(_o2)
                        except Exception:
                            pass
                    if all_objs:
                        return jsonify({
                            'objects': all_objs, 'total': len(all_objs),
                            'domain': 'all', 'source': 'json_file_aggregate'
                        })

                # 补充 sample_entities（DB中不存此字段，从JSON获取）
                _enrich_sample_entities(objects, domain)

                # 为缺少 llm_reasoning 的对象动态生成解释
                _generate_name_explanations(objects)

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
    domain = request.args.get('domain', '')

    # DB优先
    if is_db_available():
        try:
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

            if not isinstance(result, dict) or 'error' not in result:
                for row in result:
                    if row.get('avg_relation_strength'):
                        row['avg_relation_strength'] = float(row['avg_relation_strength'])
                return jsonify({'stats': result, 'total': len(result), 'domain': domain or 'all', 'source': 'database'})
        except Exception:
            pass

    # JSON回退：从JSON计算关联统计
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    stats_map = data.get('stats', {})
    result = []
    for obj in objects:
        code = obj.get('object_code', '')
        s = stats_map.get(code, {})
        result.append({
            'object_code': code,
            'object_name': obj.get('object_name', ''),
            'data_domain': domain or data.get('data_domain', ''),
            'concept_count': s.get('concept', 0),
            'logical_count': s.get('logical', 0),
            'physical_count': s.get('physical', 0),
            'total_entity_count': s.get('total', 0),
            'avg_relation_strength': 0.8
        })
    return jsonify({'stats': result, 'total': len(result), 'domain': domain or 'all', 'source': 'json'})


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

    data = _load_data(domain)
    objects = data.get('objects', [])
    stats = data.get('stats', {})
    _enrich_sample_entities(objects, domain)

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

    # 推荐合并目标: 按语义相似度排序（而非仅按大小）
    # 先为每个 small_object 收集 sample_entities
    obj_samples = {}
    for obj in objects:
        code = obj.get('object_code', '')
        obj_samples[code] = obj.get('sample_entities', [])

    for so in small_objects:
        so_samples = obj_samples.get(so['object_code'], [])
        scored_candidates = []
        for lo in large_objects:
            lo_samples = obj_samples.get(lo['object_code'], [])
            sim = _compute_keyword_overlap(so_samples, lo_samples)
            scored_candidates.append({
                'object_code': lo['object_code'],
                'object_name': lo['object_name'],
                'cluster_size': lo['cluster_size'],
                'similarity': round(sim, 4)
            })
        scored_candidates.sort(key=lambda x: -x['similarity'])
        so['merge_candidates'] = scored_candidates[:5]

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


# ============================================================================
# 对象去重与稀疏对象管理 API
# ============================================================================


def _enrich_sample_entities(objects, domain=''):
    """为对象列表补充 sample_entities（从 JSON 文件获取，DB 中不存此字段）"""
    # 构建 JSON 数据中的 sample_entities 索引
    json_samples = {}
    if domain:
        domains = [domain]
    else:
        domains = [f.stem.replace('extraction_', '') for f in OUTPUTS_DIR.glob('extraction_*.json')]

    for d in domains:
        jdata = load_json_data(d)
        for obj in jdata.get('objects', []):
            code = obj.get('object_code', '')
            samples = obj.get('sample_entities', [])
            if samples:
                json_samples[code] = samples
                # 也用带域后缀的 key
                json_samples[code + '_' + d] = samples

    for obj in objects:
        if not obj.get('sample_entities'):
            code = obj.get('object_code', '')
            obj['sample_entities'] = json_samples.get(code, [])


def _generate_name_explanations(objects):
    """为缺少 llm_reasoning 的对象动态生成名称解释（含关键词频率统计）"""
    for obj in objects:
        if obj.get('llm_reasoning'):
            continue
        samples = obj.get('sample_entities', [])
        name = obj.get('object_name', '')
        source = obj.get('extraction_source', 'MANUAL')
        cluster_size = obj.get('cluster_size') or len(samples)

        if source == 'MANUAL':
            obj['llm_reasoning'] = f'「{name}」为系统预置核心对象，由领域专家根据电力资产管理业务模型手动定义。'
        elif samples:
            top_samples = ', '.join(samples[:5])
            # 关键词频率统计：对象名在实体名中出现的次数
            keyword_count = sum(1 for s in samples if name and name in s)
            keyword_info = ''
            if keyword_count > 0 and name:
                keyword_info = f'关键词「{name}」在实体中出现{keyword_count}次，'
            # 计算置信度
            confidence = min(0.95, 0.5 + (keyword_count / max(cluster_size, 1)) * 0.5)
            if source == 'SEMANTIC_CLUSTER_LLM':
                confidence = max(confidence, 0.8)
            obj['extraction_confidence'] = round(confidence, 2)
            obj['llm_reasoning'] = (
                f'通过语义聚类分析，该聚类包含{cluster_size}个实体。'
                f'{keyword_info}'
                f'代表性实体包括：{top_samples}。'
                f'基于实体语义相似性将该聚类命名为「{name}」。'
            )
        else:
            obj['llm_reasoning'] = f'基于数据架构文档中的实体分布，自动聚类并命名为「{name}」。'


def _compute_keyword_overlap(entities_a, entities_b):
    """计算两组实体名的关键词重叠度（2-3字子串交集比例）"""
    def extract_keywords(entities):
        kw = set()
        for e in entities:
            if not e:
                continue
            for length in (2, 3):
                for i in range(len(e) - length + 1):
                    word = e[i:i+length]
                    if not any(c in word for c in "0123456789-_()（）、，。 "):
                        kw.add(word)
        return kw

    kw_a = extract_keywords(entities_a)
    kw_b = extract_keywords(entities_b)
    if not kw_a or not kw_b:
        return 0.0
    intersection = len(kw_a & kw_b)
    union = len(kw_a | kw_b)
    return intersection / union if union > 0 else 0.0


@olm_api.route('/api/olm/duplicate-candidates')
def api_duplicate_candidates():
    """检测跨域/域内语义重复对象

    参数:
      threshold: 相似度阈值 (默认 0.3)
      domain: 限定域 (空=全部)
    """
    threshold = float(request.args.get('threshold', '0.3'))
    domain = request.args.get('domain', '')

    # 加载所有域的对象
    all_objects = []
    if domain:
        data = _load_data(domain)
        for obj in data.get('objects', []):
            obj['_domain'] = domain
            all_objects.append(obj)
    else:
        # 扫描所有可用域的 JSON 文件
        for json_file in OUTPUTS_DIR.glob('extraction_*.json'):
            d = json_file.stem.replace('extraction_', '')
            data = _load_data(d)
            for obj in data.get('objects', []):
                obj['_domain'] = d
                all_objects.append(obj)

    # 补充 sample_entities（DB 中不存此字段）
    _enrich_sample_entities(all_objects, domain)

    # 查询已决策的对
    decided_pairs = set()
    if is_db_available():
        rows = execute_query("SELECT source_object_code, source_domain, target_object_code, target_domain FROM object_dedup_decisions")
        if isinstance(rows, list):
            for r in rows:
                decided_pairs.add((r['source_object_code'], r.get('source_domain', ''),
                                   r['target_object_code'], r.get('target_domain', '')))

    candidates = []
    for i, obj_a in enumerate(all_objects):
        for j in range(i + 1, len(all_objects)):
            obj_b = all_objects[j]

            code_a = obj_a.get('object_code', '')
            code_b = obj_b.get('object_code', '')
            domain_a = obj_a.get('_domain', '')
            domain_b = obj_b.get('_domain', '')

            # 跳过同域同对象
            if code_a == code_b and domain_a == domain_b:
                continue

            # 跳过已决策对
            pair_key = (code_a, domain_a, code_b, domain_b)
            pair_key_r = (code_b, domain_b, code_a, domain_a)
            if pair_key in decided_pairs or pair_key_r in decided_pairs:
                continue

            # 精确匹配：同 code 跨域
            if code_a == code_b and domain_a != domain_b:
                candidates.append({
                    'object_a': code_a, 'name_a': obj_a.get('object_name', ''),
                    'domain_a': domain_a,
                    'object_b': code_b, 'name_b': obj_b.get('object_name', ''),
                    'domain_b': domain_b,
                    'similarity': 1.0, 'match_type': 'EXACT_CODE'
                })
                continue

            # 名称匹配
            name_a = obj_a.get('object_name', '')
            name_b = obj_b.get('object_name', '')
            if name_a and name_b and name_a == name_b:
                candidates.append({
                    'object_a': code_a, 'name_a': name_a, 'domain_a': domain_a,
                    'object_b': code_b, 'name_b': name_b, 'domain_b': domain_b,
                    'similarity': 0.95, 'match_type': 'EXACT_NAME'
                })
                continue

            # 语义相似度：用实体名关键词重叠
            samples_a = obj_a.get('sample_entities', [])
            samples_b = obj_b.get('sample_entities', [])
            if samples_a and samples_b:
                sim = _compute_keyword_overlap(samples_a, samples_b)
                if sim >= threshold:
                    candidates.append({
                        'object_a': code_a, 'name_a': name_a, 'domain_a': domain_a,
                        'object_b': code_b, 'name_b': name_b, 'domain_b': domain_b,
                        'similarity': round(sim, 4), 'match_type': 'SEMANTIC'
                    })

    candidates.sort(key=lambda x: -x['similarity'])
    return jsonify({
        'candidates': candidates,
        'total': len(candidates),
        'threshold': threshold
    })


@olm_api.route('/api/olm/dedup-objects', methods=['POST'])
def api_dedup_objects():
    """执行对象去重操作

    Body: {source_code, source_domain, target_code, target_domain, action: "merge"|"link"|"ignore"}
    """
    body = request.get_json(force=True)
    source_code = body.get('source_code')
    target_code = body.get('target_code')
    action = body.get('action', 'merge')
    source_domain = body.get('source_domain', '')
    target_domain = body.get('target_domain', '')
    similarity = body.get('similarity', 0)

    if not source_code or not target_code:
        return jsonify({'success': False, 'error': '缺少 source_code 或 target_code'}), 400
    if action not in ('merge', 'link', 'ignore'):
        return jsonify({'success': False, 'error': 'action 必须为 merge/link/ignore'}), 400

    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        # 记录决策
        execute_query("""
            INSERT INTO object_dedup_decisions
            (source_object_code, source_domain, target_object_code, target_domain, decision, similarity_score)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (source_code, source_domain, target_code, target_domain,
              action.upper() if action == 'ignore' else 'MERGED' if action == 'merge' else 'LINKED',
              similarity), fetch=False)

        if action == 'merge':
            # 复用已有合并逻辑
            src = execute_query(
                "SELECT object_id FROM extracted_objects WHERE object_code = %s AND data_domain = %s",
                (source_code, source_domain))
            tgt = execute_query(
                "SELECT object_id FROM extracted_objects WHERE object_code = %s AND data_domain = %s",
                (target_code, target_domain))
            if not src or not tgt or isinstance(src, dict) or isinstance(tgt, dict):
                return jsonify({'success': False, 'error': '对象不存在'}), 404

            src_id = src[0]['object_id']
            tgt_id = tgt[0]['object_id']

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

            execute_query("DELETE FROM object_entity_relations WHERE object_id = %s", (src_id,), fetch=False)
            execute_query("DELETE FROM object_business_object_mapping WHERE object_id = %s", (src_id,), fetch=False)
            execute_query("DELETE FROM extracted_objects WHERE object_id = %s", (src_id,), fetch=False)

            return jsonify({'success': True, 'message': f'已将 {source_code}({source_domain}) 合并到 {target_code}({target_domain})'})

        elif action == 'link':
            # 创建同义词链接
            tgt = execute_query(
                "SELECT object_id FROM extracted_objects WHERE object_code = %s AND data_domain = %s",
                (target_code, target_domain))
            if tgt and not isinstance(tgt, dict):
                execute_query("""
                    INSERT IGNORE INTO object_synonyms (object_id, synonym, source)
                    VALUES (%s, %s, 'DEDUP_LINK')
                """, (tgt[0]['object_id'], f"{source_code}@{source_domain}"), fetch=False)
            return jsonify({'success': True, 'message': f'已关联 {source_code} ↔ {target_code}'})

        else:  # ignore
            return jsonify({'success': True, 'message': f'已标记为忽略'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/bulk-merge-small', methods=['POST'])
def api_bulk_merge_small():
    """批量合并稀疏对象

    Body: {threshold: 5, preview: true, domain: ""}
    preview=true 仅返回合并计划，preview=false 执行合并
    """
    body = request.get_json(force=True)
    threshold = int(body.get('threshold', 5))
    preview = body.get('preview', True)
    domain = body.get('domain', '')

    # 必须保留的对象
    required_codes = {'OBJ_PROJECT', 'OBJ_DEVICE', 'OBJ_ASSET'}

    data = _load_data(domain)
    objects = data.get('objects', [])
    stats = data.get('stats', {})
    _enrich_sample_entities(objects, domain)

    small_objects = []
    large_objects = []
    for obj in objects:
        code = obj.get('object_code', '')
        cluster_size = obj.get('cluster_size', 0)
        if code in required_codes:
            large_objects.append(obj)
        elif cluster_size < threshold:
            small_objects.append(obj)
        else:
            large_objects.append(obj)

    if not large_objects:
        return jsonify({'success': False, 'error': '没有可用的合并目标'}), 400

    # 为每个小对象找最佳合并目标（基于关键词重叠度）
    merge_plan = []
    for so in small_objects:
        so_samples = so.get('sample_entities', [])
        best_target, best_sim = None, 0
        for lo in large_objects:
            lo_samples = lo.get('sample_entities', [])
            sim = _compute_keyword_overlap(so_samples, lo_samples)
            if sim > best_sim:
                best_sim, best_target = sim, lo

        if best_target:
            merge_plan.append({
                'source_code': so['object_code'],
                'source_name': so.get('object_name', ''),
                'source_size': so.get('cluster_size', 0),
                'target_code': best_target['object_code'],
                'target_name': best_target.get('object_name', ''),
                'target_size': best_target.get('cluster_size', 0),
                'similarity': round(best_sim, 4)
            })

    if preview:
        return jsonify({
            'preview': True,
            'merge_plan': merge_plan,
            'small_count': len(small_objects),
            'merge_count': len(merge_plan),
            'threshold': threshold
        })

    # 执行合并
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用，无法执行合并'}), 503

    merged = 0
    errors = []
    for item in merge_plan:
        try:
            src = execute_query(
                "SELECT object_id FROM extracted_objects WHERE object_code = %s",
                (item['source_code'],))
            tgt = execute_query(
                "SELECT object_id FROM extracted_objects WHERE object_code = %s",
                (item['target_code'],))
            if not src or not tgt or isinstance(src, dict) or isinstance(tgt, dict):
                errors.append(f"{item['source_code']}: 对象不存在")
                continue

            src_id = src[0]['object_id']
            tgt_id = tgt[0]['object_id']

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

            execute_query("DELETE FROM object_entity_relations WHERE object_id = %s", (src_id,), fetch=False)
            execute_query("DELETE FROM object_business_object_mapping WHERE object_id = %s", (src_id,), fetch=False)
            execute_query("DELETE FROM extracted_objects WHERE object_id = %s", (src_id,), fetch=False)

            # 记录决策
            execute_query("""
                INSERT INTO object_dedup_decisions
                (source_object_code, source_domain, target_object_code, target_domain, decision, similarity_score)
                VALUES (%s, %s, %s, %s, 'MERGED', %s)
            """, (item['source_code'], domain, item['target_code'], domain, item['similarity']), fetch=False)

            merged += 1
        except Exception as e:
            errors.append(f"{item['source_code']}: {str(e)}")

    return jsonify({
        'success': True,
        'merged': merged,
        'errors': errors,
        'message': f'已合并 {merged}/{len(merge_plan)} 个稀疏对象'
    })


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

    # DB优先，JSON回退
    data = _load_data(domain)
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

    data = _load_data(domain)
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


@olm_api.route('/api/olm/graph-data-three-tier')
def api_graph_data_three_tier():
    """全局三层架构知识图谱：对象→概念实体→逻辑实体→物理实体

    Parameters:
        domain: 数据域过滤
        depth: 展示深度 2=对象+概念, 3=+逻辑, 4=+物理 (default 3)
        max_concepts: 每个对象最多显示的概念实体数 (default 8)
        max_logicals: 每个概念实体最多显示的逻辑实体数 (default 3)
        max_physicals: 每个逻辑实体最多显示的物理实体数 (default 2)
    """
    domain = request.args.get('domain', '')
    depth = int(request.args.get('depth', '3'))
    max_concepts = int(request.args.get('max_concepts', '8'))
    max_logicals = int(request.args.get('max_logicals', '3'))
    max_physicals = int(request.args.get('max_physicals', '2'))

    data = _load_data(domain)
    objects = data.get('objects', [])
    relations = data.get('relations', [])
    stats = data.get('stats', {})

    # 四类节点分类
    categories = [
        {"name": "对象", "itemStyle": {"color": "#6366f1"}},
        {"name": "概念实体", "itemStyle": {"color": "#818cf8"}},
        {"name": "逻辑实体", "itemStyle": {"color": "#10b981"}},
        {"name": "物理实体", "itemStyle": {"color": "#f59e0b"}}
    ]

    nodes = []
    links = []
    added_nodes = set()

    # 预构建关联索引：按 object_code + entity_layer 分组
    from collections import defaultdict
    obj_concept_rels = defaultdict(list)
    concept_logical_rels = defaultdict(list)
    logical_physical_rels = defaultdict(list)

    for r in relations:
        oc = r.get('object_code', '')
        layer = r.get('entity_layer', '')
        if layer == 'CONCEPT':
            obj_concept_rels[oc].append(r)
        elif layer == 'LOGICAL':
            via = r.get('via_concept_entity', '')
            concept_logical_rels[(oc, via)].append(r)
        elif layer == 'PHYSICAL':
            via = r.get('via_concept_entity', '')
            logical_physical_rels[(oc, via)].append(r)

    # Layer 1: 对象节点
    for obj in objects:
        obj_code = obj.get('object_code', '')
        obj_stats = stats.get(obj_code, {})
        size = min(60, max(25, obj.get('cluster_size', 1) * 2))
        nodes.append({
            "id": obj_code,
            "name": obj.get('object_name', obj_code),
            "category": 0,
            "symbolSize": size,
            "value": obj_stats.get('total', 0),
            "label": {"show": True, "fontSize": 14, "fontWeight": "bold"}
        })
        added_nodes.add(obj_code)

        # Layer 2: 概念实体（每对象 Top N）
        concepts = sorted(
            obj_concept_rels.get(obj_code, []),
            key=lambda r: -r.get('relation_strength', 0)
        )[:max_concepts]

        for cr in concepts:
            c_name = cr.get('entity_name', '')
            c_id = f"C:{c_name}"
            if c_id not in added_nodes:
                added_nodes.add(c_id)
                nodes.append({
                    "id": c_id,
                    "name": c_name,
                    "category": 1,
                    "symbolSize": 14,
                    "value": cr.get('relation_strength', 0.5)
                })
            links.append({
                "source": obj_code,
                "target": c_id,
                "value": cr.get('relation_strength', 0.5),
                "lineStyle": {"width": 2}
            })

            # Layer 3: 逻辑实体
            if depth >= 3:
                logicals = sorted(
                    concept_logical_rels.get((obj_code, c_name), []),
                    key=lambda r: -r.get('relation_strength', 0)
                )[:max_logicals]

                for lr in logicals:
                    l_name = lr.get('entity_name', '')
                    l_id = f"L:{l_name}"
                    if l_id not in added_nodes:
                        added_nodes.add(l_id)
                        nodes.append({
                            "id": l_id,
                            "name": l_name,
                            "category": 2,
                            "symbolSize": 10,
                            "value": lr.get('relation_strength', 0.3)
                        })
                    links.append({
                        "source": c_id,
                        "target": l_id,
                        "value": lr.get('relation_strength', 0.3),
                        "lineStyle": {"width": 1}
                    })

                    # Layer 4: 物理实体
                    if depth >= 4:
                        physicals = sorted(
                            logical_physical_rels.get((obj_code, l_name), []),
                            key=lambda r: -r.get('relation_strength', 0)
                        )[:max_physicals]

                        for pr in physicals:
                            p_name = pr.get('entity_name', '')
                            p_id = f"P:{p_name}"
                            if p_id not in added_nodes:
                                added_nodes.add(p_id)
                                nodes.append({
                                    "id": p_id,
                                    "name": p_name,
                                    "category": 3,
                                    "symbolSize": 7,
                                    "value": pr.get('relation_strength', 0.2)
                                })
                            links.append({
                                "source": l_id,
                                "target": p_id,
                                "value": pr.get('relation_strength', 0.2),
                                "lineStyle": {"width": 0.5, "type": "dashed"}
                            })

    return jsonify({
        "nodes": nodes,
        "links": links,
        "categories": categories,
        "depth": depth,
        "node_count": len(nodes),
        "link_count": len(links)
    })


@olm_api.route('/api/olm/granularity-report')
def api_granularity_report():
    """颗粒度分析报告"""
    domain = request.args.get('domain', '')
    data = _load_data(domain)
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

        # 导入抽取模块（scripts/ 目录不在默认路径中）
        project_root = os.path.dirname(os.path.dirname(__file__))
        scripts_dir = os.path.join(project_root, 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from object_extractor import SemanticObjectExtractionPipeline
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
    domain = request.args.get('domain', '')

    # DB优先
    if is_db_available():
        try:
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
                'relations': relations if not isinstance(relations, dict) else [],
                'source': 'database'
            }

            filename = f'extracted_objects_{domain}.json' if domain else 'extracted_objects_all.json'
            return Response(
                json.dumps(export_data, ensure_ascii=False, indent=2),
                mimetype='application/json',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
        except Exception:
            pass

    # JSON回退
    data = load_json_data(domain or 'shupeidian')
    export_data = {
        'export_time': datetime.now().isoformat(),
        'domain': domain or data.get('data_domain', 'all'),
        'objects': data.get('objects', []),
        'relations': data.get('relations', []),
        'source': 'json'
    }
    filename = f'extracted_objects_{domain}.json' if domain else 'extracted_objects_all.json'
    return Response(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


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
    # DB优先
    if is_db_available():
        try:
            result = execute_query("""
                SELECT * FROM object_extraction_batches
                ORDER BY extraction_time DESC
                LIMIT 50
            """)

            if not isinstance(result, dict) or 'error' not in result:
                for row in result:
                    if row.get('extraction_time'):
                        row['extraction_time'] = row['extraction_time'].isoformat()
                    if row.get('source_files') and isinstance(row['source_files'], str):
                        try:
                            row['source_files'] = json.loads(row['source_files'])
                        except Exception:
                            pass
                return jsonify({'batches': result, 'total': len(result), 'source': 'database'})
        except Exception:
            pass

    # JSON回退：批次信息仅存在于数据库，返回空列表
    return jsonify({'batches': [], 'total': 0, 'source': 'json', 'message': '数据库不可用，批次信息无法获取'})


# ============================================================================
# 统计 API
# ============================================================================

@olm_api.route('/api/olm/stats')
def api_stats():
    """获取系统统计信息

    Query参数:
        domain (str): 数据域过滤，默认返回全局统计
    """
    domain = request.args.get('domain', '')

    # DB优先
    if is_db_available():
        try:
            stats = {'domain': domain or 'all'}

            if domain:
                result = execute_query("SELECT COUNT(*) as cnt FROM extracted_objects WHERE data_domain = %s", (domain,))
            else:
                result = execute_query("SELECT COUNT(*) as cnt FROM extracted_objects")
            stats['objects_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

            if domain:
                result = execute_query("""
                    SELECT COUNT(*) as cnt FROM object_entity_relations r
                    JOIN extracted_objects o ON o.object_id = r.object_id
                    WHERE o.data_domain = %s
                """, (domain,))
            else:
                result = execute_query("SELECT COUNT(*) as cnt FROM object_entity_relations")
            stats['relations_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

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

            if domain:
                result = execute_query("SELECT COUNT(*) as cnt FROM object_extraction_batches WHERE data_domain = %s", (domain,))
            else:
                result = execute_query("SELECT COUNT(*) as cnt FROM object_extraction_batches")
            stats['batches_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

            stats['source'] = 'database'
            return jsonify(stats)
        except Exception:
            pass

    # JSON回退：从JSON计算统计
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    relations = data.get('relations', [])

    layer_counts = {}
    for r in relations:
        layer = r.get('entity_layer', '')
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    type_counts = {}
    for obj in objects:
        t = obj.get('object_type', 'CORE')
        type_counts[t] = type_counts.get(t, 0) + 1

    return jsonify({
        'domain': domain or 'all',
        'objects_count': len(objects),
        'relations_count': len(relations),
        'relations_by_layer': layer_counts,
        'objects_by_type': type_counts,
        'batches_count': 0,
        'source': 'json'
    })


@olm_api.route('/api/olm/domain-stats')
def api_domain_stats():
    """获取各数据域的统计信息"""
    # DB优先
    if is_db_available():
        try:
            result = execute_query("""
                SELECT * FROM v_domain_stats ORDER BY object_count DESC
            """)

            if not isinstance(result, dict) or 'error' not in result:
                for row in result:
                    if row.get('avg_relation_strength'):
                        row['avg_relation_strength'] = float(row['avg_relation_strength'])

                # 扫 outputs/extraction_*.json 看是否比 DB 涵盖的域更多, 若是则合并
                import glob as _glob_mod
                db_domains = {r.get('data_domain') for r in result}
                json_files = _glob_mod.glob(str(OUTPUTS_DIR / 'extraction_*.json'))
                json_domains_extra = []
                for jf in json_files:
                    base = os.path.basename(jf)
                    if base in ('extraction_global.json',):
                        continue
                    dom = base.replace('extraction_', '').replace('.json', '')
                    if dom in db_domains:
                        continue
                    try:
                        with open(jf, 'r', encoding='utf-8') as _f:
                            _d = json.load(_f)
                        json_domains_extra.append({
                            'data_domain': dom,
                            'object_count': len(_d.get('objects', [])),
                            'relation_count': len(_d.get('relations', [])),
                            'concept_entity_count': sum(1 for r in _d.get('relations', []) if r.get('entity_layer') == 'CONCEPT'),
                            'logical_entity_count': sum(1 for r in _d.get('relations', []) if r.get('entity_layer') == 'LOGICAL'),
                            'physical_entity_count': sum(1 for r in _d.get('relations', []) if r.get('entity_layer') == 'PHYSICAL'),
                            'avg_relation_strength': 0.7,
                            'source': 'json_file',
                        })
                    except Exception:
                        pass
                merged = list(result) + json_domains_extra
                merged.sort(key=lambda r: -(r.get('object_count') or 0))
                return jsonify({
                    'stats': merged, 'total': len(merged),
                    'source': 'database+json' if json_domains_extra else 'database',
                })
        except Exception:
            pass

    # JSON回退：扫描所有域的JSON文件
    import glob as glob_mod
    result = []
    json_files = glob_mod.glob(str(OUTPUTS_DIR / 'extraction_*.json'))
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                d = json.load(f)
            domain_name = d.get('data_domain', '')
            objects = d.get('objects', [])
            relations = d.get('relations', [])
            result.append({
                'data_domain': domain_name,
                'object_count': len(objects),
                'relation_count': len(relations),
                'avg_relation_strength': 0.8
            })
        except Exception:
            pass
    return jsonify({'stats': result, 'total': len(result), 'source': 'json'})


@olm_api.route('/api/olm/cross-domain-duplicates')
def api_cross_domain_duplicates():
    """检测跨域重复对象：同名对象在多个数据域中出现"""
    import glob as glob_mod
    from collections import defaultdict

    # 收集所有域的对象
    domain_objects = defaultdict(list)
    json_files = glob_mod.glob(str(OUTPUTS_DIR / 'extraction_*.json'))
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                d = json.load(f)
            domain = d.get('data_domain', d.get('data_domain_name', ''))
            for obj in d.get('objects', []):
                domain_objects[obj.get('object_name', '')].append({
                    'domain': domain,
                    'object_code': obj.get('object_code', ''),
                    'cluster_size': obj.get('cluster_size', 0),
                    'sample_entities': obj.get('sample_entities', [])[:5]
                })
        except Exception:
            pass

    # 找到跨域重复
    duplicates = []
    for name, entries in domain_objects.items():
        if len(entries) >= 2:
            domains = [e['domain'] for e in entries]
            if len(set(domains)) >= 2:
                duplicates.append({
                    'object_name': name,
                    'occurrences': entries,
                    'domain_count': len(set(domains))
                })

    return jsonify({
        'duplicates': duplicates,
        'total': len(duplicates)
    })


# ============================================================================
# 跨域融合 (组内 + 组间) API
# ============================================================================

def _load_global() -> dict:
    """读取 outputs/extraction_global.json (跨域融合产物)."""
    path = OUTPUTS_DIR / 'extraction_global.json'
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] 读取 extraction_global.json 失败: {e}")
        return {}


@olm_api.route('/api/olm/global-objects')
def api_global_objects():
    """跨域融合对象清单.
    参数:
        mode: literal(默认,字面对齐) | semantic(语义聚类) | both
        cross_only: 1=只返回跨域组 (present_in_domains>=2)
    """
    mode = request.args.get('mode', 'literal')
    cross_only = request.args.get('cross_only', '0') in ('1', 'true', 'yes')

    g = _load_global()
    if not g:
        return jsonify({
            'available': False,
            'message': '请先运行 scripts/cross_domain_merge.py 生成 extraction_global.json'
        }), 200

    def filter_cross(groups):
        return [x for x in groups if len(x.get('present_in_domains', [])) >= 2] \
            if cross_only else groups

    payload = {
        'available': True,
        'meta': g.get('meta', {}),
        'domains': g.get('domains', []),
    }
    if mode in ('literal', 'both'):
        payload['literal_groups'] = filter_cross(g.get('literal_groups', []))
    if mode in ('semantic', 'both'):
        payload['semantic_groups'] = filter_cross(g.get('semantic_groups', []))
    return jsonify(payload)


@olm_api.route('/api/olm/global-summary')
def api_global_summary():
    """跨域融合汇总卡片数据 (轻量, 仅 meta + 前 10 个跨域组)."""
    g = _load_global()
    if not g:
        return jsonify({'available': False}), 200
    lit = g.get('literal_groups', [])
    sem = g.get('semantic_groups', [])
    top_lit_cross = sorted(
        [x for x in lit if len(x.get('present_in_domains', [])) >= 2],
        key=lambda x: -len(x.get('present_in_domains', []))
    )[:10]
    top_sem_cross = sorted(
        [x for x in sem if len(x.get('present_in_domains', [])) >= 2],
        key=lambda x: -len(x.get('present_in_domains', []))
    )[:10]
    return jsonify({
        'available': True,
        'meta': g.get('meta', {}),
        'top_literal_cross_domain': top_lit_cross,
        'top_semantic_cross_domain': top_sem_cross,
    })


# ============================================================================
# 桑基图数据 API
# ============================================================================

def get_sankey_from_json(domain: str = '') -> dict:
    """从 JSON 文件构建桑基图数据（三层：对象→概念→逻辑，物理层待接入）"""
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    relations = data.get('relations', [])

    MAX_LOGICAL_PER_CONCEPT = 3

    nodes = []
    links = []
    node_set = set()

    # 预处理：按 object_code 分组 relations
    from collections import defaultdict
    obj_concept_rels = defaultdict(list)
    concept_logical_rels = defaultdict(list)

    for rel in relations:
        layer = rel.get('entity_layer', '').upper()
        code = rel.get('object_code', '')
        if layer == 'CONCEPT':
            obj_concept_rels[code].append(rel)
        elif layer == 'LOGICAL':
            via = rel.get('via_concept_entity', '')
            concept_logical_rels[(code, via)].append(rel)

    for obj in objects:
        code = obj.get('object_code', '')
        name = obj.get('object_name', '')
        if not name:
            continue
        if name not in node_set:
            nodes.append({'name': name, 'depth': 0, 'type': 'object'})
            node_set.add(name)

        # Top 5 concepts by strength
        concepts = sorted(obj_concept_rels.get(code, []), key=lambda x: x.get('relation_strength', 0), reverse=True)[:5]

        for crel in concepts:
            concept_name = crel.get('entity_name', '')
            concept_node = f"{concept_name}({name})"

            logicals = concept_logical_rels.get((code, concept_name), [])
            logicals.sort(key=lambda x: x.get('relation_strength', 0), reverse=True)
            total_logical = len(logicals)

            if total_logical == 0:
                if concept_node not in node_set:
                    nodes.append({'name': concept_node, 'depth': 1, 'type': 'concept'})
                    node_set.add(concept_node)
                links.append({'source': name, 'target': concept_node, 'value': 1})
                continue

            if concept_node not in node_set:
                nodes.append({'name': concept_node, 'depth': 1, 'type': 'concept'})
                node_set.add(concept_node)
            links.append({'source': name, 'target': concept_node, 'value': total_logical})

            shown_logicals = logicals[:MAX_LOGICAL_PER_CONCEPT]
            rest_logical_count = total_logical - len(shown_logicals)

            for lg_rel in shown_logicals:
                lg_name = lg_rel.get('entity_name', '')
                lg_node = lg_name
                if lg_node not in node_set:
                    nodes.append({'name': lg_node, 'depth': 2, 'type': 'logical'})
                    node_set.add(lg_node)
                links.append({'source': concept_node, 'target': lg_node, 'value': 1})

            if rest_logical_count > 0:
                agg_lg = f"其他{rest_logical_count}个逻辑实体({concept_name})"
                if agg_lg not in node_set:
                    nodes.append({'name': agg_lg, 'depth': 2, 'type': 'logical_agg'})
                    node_set.add(agg_lg)
                links.append({'source': concept_node, 'target': agg_lg, 'value': rest_logical_count})

    return {'nodes': nodes, 'links': links, 'domain': domain or 'shupeidian'}


@olm_api.route('/api/olm/sankey-data')
def api_sankey_data():
    """获取桑基图可视化数据

    返回对象→概念实体→逻辑实体的三层流向数据。
    概念层每个概念取Top-3逻辑实体，超出部分用"其他N个"聚合节点。
    物理实体层待接入生产系统后再展示。

    Query参数:
        domain (str): 数据域过滤，支持逗号分隔多域
    """
    domain = request.args.get('domain', '')
    domains = [d.strip() for d in domain.split(',') if d.strip()] if domain else []
    MAX_LOGICAL_PER_CONCEPT = 3

    if is_db_available():
        try:
            # 1. 获取对象列表
            if len(domains) == 1:
                objects = execute_query(
                    "SELECT object_id, object_code, object_name FROM extracted_objects WHERE data_domain = %s ORDER BY object_type, object_name",
                    (domains[0],)
                )
            elif len(domains) > 1:
                placeholders = ','.join(['%s'] * len(domains))
                objects = execute_query(
                    f"SELECT object_id, object_code, object_name FROM extracted_objects WHERE data_domain IN ({placeholders}) ORDER BY object_type, object_name",
                    tuple(domains)
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

            # 2. 为每个对象查询 Top-5 概念实体 + 其下逻辑实体
            for obj in objects:
                obj_name = obj['object_name']
                obj_id = obj['object_id']

                if obj_name not in node_set:
                    nodes.append({'name': obj_name, 'depth': 0, 'type': 'object'})
                    node_set.add(obj_name)

                # Top-5 概念实体
                top_concepts = execute_query("""
                    SELECT r.entity_name, r.relation_strength
                    FROM object_entity_relations r
                    WHERE r.object_id = %s AND r.entity_layer = 'CONCEPT'
                    ORDER BY r.relation_strength DESC
                    LIMIT 5
                """, (obj_id,))

                if isinstance(top_concepts, dict):
                    continue

                for c in top_concepts:
                    concept_name = c['entity_name']
                    concept_node = f"{concept_name}({obj_name})"

                    # 查询该概念下的逻辑实体
                    logicals = execute_query("""
                        SELECT r.entity_name, r.relation_strength
                        FROM object_entity_relations r
                        WHERE r.object_id = %s AND r.entity_layer = 'LOGICAL'
                        AND r.via_concept_entity = %s
                        ORDER BY r.relation_strength DESC
                    """, (obj_id, concept_name))

                    if isinstance(logicals, dict):
                        logicals = []

                    total_logical = len(logicals)

                    if total_logical == 0:
                        if concept_node not in node_set:
                            nodes.append({'name': concept_node, 'depth': 1, 'type': 'concept'})
                            node_set.add(concept_node)
                        links.append({'source': obj_name, 'target': concept_node, 'value': 1})
                        continue

                    if concept_node not in node_set:
                        nodes.append({'name': concept_node, 'depth': 1, 'type': 'concept'})
                        node_set.add(concept_node)

                    links.append({'source': obj_name, 'target': concept_node, 'value': total_logical})

                    # 展示 Top-N 逻辑实体
                    shown_logicals = logicals[:MAX_LOGICAL_PER_CONCEPT]
                    rest_logical_count = total_logical - len(shown_logicals)

                    for lg in shown_logicals:
                        lg_name = lg['entity_name']
                        lg_node = lg_name
                        if lg_node not in node_set:
                            nodes.append({'name': lg_node, 'depth': 2, 'type': 'logical'})
                            node_set.add(lg_node)
                        links.append({'source': concept_node, 'target': lg_node, 'value': 1})

                    # 剩余逻辑实体聚合
                    if rest_logical_count > 0:
                        agg_lg = f"其他{rest_logical_count}个逻辑实体({concept_name})"
                        if agg_lg not in node_set:
                            nodes.append({'name': agg_lg, 'depth': 2, 'type': 'logical_agg'})
                            node_set.add(agg_lg)
                        links.append({'source': concept_node, 'target': agg_lg, 'value': rest_logical_count})

            return jsonify({'nodes': nodes, 'links': links, 'domain': domain or 'all', 'source': 'database'})

        except Exception as e:
            print(f"[WARN] 桑基图数据库查询失败，使用 JSON 后备: {e}")

    result = get_sankey_from_json(domains[0] if len(domains) == 1 else (domain or ''))
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
    layer = request.args.get('layer', '').strip().upper()
    domain = request.args.get('domain', '').strip()
    limit = min(int(request.args.get('limit', '500')), 500)

    # q 可选: 仅当 q/layer/domain 三者均为空时才拒绝 (避免返回全库)
    if not query and not layer and not domain:
        return jsonify({'error': 'at least one of q/layer/domain is required', 'results': []}), 400

    if layer and layer not in ('CONCEPT', 'LOGICAL', 'PHYSICAL'):
        return jsonify({'error': 'layer must be concept, logical, or physical', 'results': []}), 400

    if is_db_available():
        try:
            # 构建动态 WHERE 条件
            conditions = []
            params = []

            if query:
                conditions.append("r.entity_name LIKE %s")
                params.append(f'%{query}%')

            if layer:
                conditions.append("r.entity_layer = %s")
                params.append(layer)

            if domain:
                conditions.append("o.data_domain = %s")
                params.append(domain)

            params.append(limit)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
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
        domain (str): 数据域过滤，支持逗号分隔多域，默认返回全局统计
    """
    domain = request.args.get('domain', '')
    domains = [d.strip() for d in domain.split(',') if d.strip()] if domain else []

    if is_db_available():
        try:
            summary = {'domain': domain or 'all'}

            # 构建域过滤条件
            if len(domains) == 1:
                domain_filter = " WHERE data_domain = %s"
                rel_domain_filter = " AND o.data_domain = %s"
                params = (domains[0],)
            elif len(domains) > 1:
                placeholders = ','.join(['%s'] * len(domains))
                domain_filter = f" WHERE data_domain IN ({placeholders})"
                rel_domain_filter = f" AND o.data_domain IN ({placeholders})"
                params = tuple(domains)
            else:
                domain_filter = ""
                rel_domain_filter = ""
                params = ()

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
            summary['physical_count'] = 0  # 物理实体待接入生产系统
            summary['relations_count'] = layer_map.get('CONCEPT', 0) + layer_map.get('LOGICAL', 0)

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


# ============================================================================
# Phase 2: 全生命周期管理 API
# ============================================================================

@olm_api.route('/api/olm/object-lifecycle/<object_code>')
def api_object_lifecycle(object_code):
    """查询对象的生命周期历史"""
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            query = """
                SELECT h.*, o.object_name
                FROM object_lifecycle_history h
                JOIN extracted_objects o ON o.object_id = h.object_id
                WHERE o.object_code = %s
            """
            params = [object_code]
            if domain:
                query += " AND h.data_domain = %s"
                params.append(domain)
            query += " ORDER BY h.stage_entered_at ASC"

            result = execute_query(query, tuple(params))
            if isinstance(result, list):
                for row in result:
                    for key in ['stage_entered_at', 'stage_exited_at', 'created_at']:
                        if row.get(key):
                            row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
                    if row.get('attributes_snapshot') and isinstance(row['attributes_snapshot'], str):
                        try:
                            row['attributes_snapshot'] = json.loads(row['attributes_snapshot'])
                        except Exception:
                            pass
                return jsonify({'lifecycle': result, 'object_code': object_code, 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 生命周期查询失败: {e}")

    return jsonify({'lifecycle': [], 'object_code': object_code, 'source': 'json_file'})


@olm_api.route('/api/olm/object-lifecycle/<object_code>', methods=['POST'])
def api_create_lifecycle(object_code):
    """新增生命周期阶段记录（含状态机约束）"""
    STAGE_ORDER = ['Planning', 'Design', 'Construction', 'Operation']

    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        data = request.get_json(force=True)
        obj = execute_query("SELECT object_id FROM extracted_objects WHERE object_code = %s", (object_code,))
        if not obj or isinstance(obj, dict):
            return jsonify({'success': False, 'error': '对象不存在'}), 404

        object_id = obj[0]['object_id']
        new_stage = data.get('lifecycle_stage', 'Planning')

        if new_stage not in STAGE_ORDER:
            return jsonify({'success': False, 'error': f'无效阶段: {new_stage}，允许值: {STAGE_ORDER}'}), 400

        # 状态机约束：查询当前最新阶段
        current = execute_query("""
            SELECT lifecycle_stage, history_id FROM object_lifecycle_history
            WHERE object_id = %s ORDER BY stage_entered_at DESC LIMIT 1
        """, (object_id,))

        if isinstance(current, list) and current:
            cur_stage = current[0]['lifecycle_stage']
            cur_idx = STAGE_ORDER.index(cur_stage) if cur_stage in STAGE_ORDER else -1
            new_idx = STAGE_ORDER.index(new_stage)

            # 禁止跳阶段（跳过中间阶段）
            if new_idx > cur_idx + 1:
                skipped = STAGE_ORDER[cur_idx + 1:new_idx]
                return jsonify({'success': False, 'error': f'不能从 {cur_stage} 直接跳到 {new_stage}，需先经过: {", ".join(skipped)}'}), 400

            # 允许回退但需要 notes
            if new_idx < cur_idx and not data.get('notes'):
                return jsonify({'success': False, 'error': f'从 {cur_stage} 回退到 {new_stage} 需在 notes 中说明理由'}), 400

            # 自动关闭上一阶段
            entered_at = data.get('stage_entered_at', datetime.now().isoformat())
            execute_query("""
                UPDATE object_lifecycle_history SET stage_exited_at = %s
                WHERE history_id = %s AND stage_exited_at IS NULL
            """, (entered_at, current[0]['history_id']), fetch=False)

        attrs_json = json.dumps(data.get('attributes_snapshot', {}), ensure_ascii=False) if data.get('attributes_snapshot') else None

        result = execute_query("""
            INSERT INTO object_lifecycle_history
            (object_id, lifecycle_stage, stage_entered_at, attributes_snapshot, data_domain, source_system, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            object_id,
            new_stage,
            data.get('stage_entered_at', datetime.now().isoformat()),
            attrs_json,
            data.get('data_domain', ''),
            data.get('source_system', ''),
            data.get('notes', '')
        ), fetch=False)

        # Auto-trigger: 查询阶段模板的 trigger_functions，自动求值机理函数
        triggered_alerts = []
        try:
            obj_type = execute_query(
                "SELECT object_type FROM extracted_objects WHERE object_id = %s", (object_id,))
            if obj_type and not isinstance(obj_type, dict):
                tmpl = execute_query("""
                    SELECT trigger_functions FROM lifecycle_stage_templates
                    WHERE object_type = %s AND lifecycle_stage = %s
                """, (obj_type[0]['object_type'], new_stage))
                if tmpl and not isinstance(tmpl, dict) and tmpl[0].get('trigger_functions'):
                    func_codes = tmpl[0]['trigger_functions']
                    if isinstance(func_codes, str):
                        func_codes = json.loads(func_codes)
                    for fc in (func_codes or []):
                        mf = execute_query(
                            "SELECT * FROM mechanism_functions WHERE func_code = %s AND is_active = 1", (fc,))
                        if not mf or isinstance(mf, dict):
                            continue
                        mf = mf[0]
                        expr = mf.get('expression', '{}')
                        if isinstance(expr, str):
                            expr = json.loads(expr)
                        snapshot = data.get('attributes_snapshot', {})
                        eval_result = _evaluate_expression(expr, snapshot)
                        if eval_result.get('triggered'):
                            execute_query("""
                                INSERT INTO alert_records
                                (func_id, alert_level, alert_title, alert_detail, related_object_id, trigger_value, threshold_value)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (
                                mf['func_id'], mf.get('severity', 'WARNING'),
                                f"生命周期触发: {mf.get('func_name', fc)}",
                                eval_result.get('message', ''),
                                object_id,
                                str(eval_result.get('actual_value', '')),
                                str(eval_result.get('threshold', ''))
                            ), fetch=False)
                            triggered_alerts.append({
                                'func_code': fc,
                                'func_name': mf.get('func_name', fc),
                                'severity': mf.get('severity', 'WARNING'),
                                'message': eval_result.get('message', '')
                            })
        except Exception as trigger_err:
            triggered_alerts.append({'error': str(trigger_err)})

        return jsonify({'success': True, 'history_id': result, 'stage': new_stage, 'triggered_alerts': triggered_alerts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/lifecycle-stats')
def api_lifecycle_stats():
    """各生命周期阶段对象分布统计"""
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            query = """
                SELECT h.lifecycle_stage, COUNT(DISTINCT h.object_id) as object_count
                FROM object_lifecycle_history h
            """
            params = []
            if domain:
                query += " WHERE h.data_domain = %s"
                params.append(domain)
            query += " GROUP BY h.lifecycle_stage ORDER BY FIELD(h.lifecycle_stage, 'Planning','Design','Construction','Operation')"

            result = execute_query(query, tuple(params) if params else None)
            if isinstance(result, list):
                return jsonify({'stats': result, 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 生命周期统计失败: {e}")

    return jsonify({'stats': [], 'source': 'json_file'})


@olm_api.route('/api/olm/lifecycle-analytics')
def api_lifecycle_analytics():
    """生命周期分析：阶段时长统计 + 跨对象对比"""
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            where = "WHERE h.data_domain = %s" if domain else ""
            params = (domain,) if domain else None

            # 各阶段时长统计
            duration_query = f"""
                SELECT h.lifecycle_stage,
                       COUNT(*) as record_count,
                       ROUND(AVG(DATEDIFF(COALESCE(h.stage_exited_at, NOW()), h.stage_entered_at)), 1) as avg_days,
                       MIN(DATEDIFF(COALESCE(h.stage_exited_at, NOW()), h.stage_entered_at)) as min_days,
                       MAX(DATEDIFF(COALESCE(h.stage_exited_at, NOW()), h.stage_entered_at)) as max_days
                FROM object_lifecycle_history h
                {where}
                GROUP BY h.lifecycle_stage
                ORDER BY FIELD(h.lifecycle_stage, 'Planning','Design','Construction','Operation')
            """
            duration_stats = execute_query(duration_query, params)

            # 跨对象对比数据
            compare_query = f"""
                SELECT o.object_code, o.object_name,
                       h.lifecycle_stage,
                       h.stage_entered_at, h.stage_exited_at,
                       DATEDIFF(COALESCE(h.stage_exited_at, NOW()), h.stage_entered_at) as duration_days
                FROM object_lifecycle_history h
                JOIN extracted_objects o ON o.object_id = h.object_id
                {where}
                ORDER BY o.object_name, FIELD(h.lifecycle_stage, 'Planning','Design','Construction','Operation')
            """
            compare_data = execute_query(compare_query, params)

            if isinstance(duration_stats, list) and isinstance(compare_data, list):
                # 处理 Decimal/datetime
                for row in duration_stats:
                    for k in ['avg_days', 'min_days', 'max_days']:
                        if row.get(k) is not None:
                            row[k] = float(row[k])

                # 按对象分组
                obj_map = {}
                for row in compare_data:
                    code = row['object_code']
                    if code not in obj_map:
                        obj_map[code] = {'object_code': code, 'object_name': row['object_name'], 'stages': []}
                    for k in ['stage_entered_at', 'stage_exited_at']:
                        if row.get(k):
                            row[k] = row[k].isoformat() if hasattr(row[k], 'isoformat') else str(row[k])
                    if row.get('duration_days') is not None:
                        row['duration_days'] = int(row['duration_days'])
                    obj_map[code]['stages'].append({
                        'lifecycle_stage': row['lifecycle_stage'],
                        'stage_entered_at': row.get('stage_entered_at'),
                        'stage_exited_at': row.get('stage_exited_at'),
                        'duration_days': row.get('duration_days', 0)
                    })

                # 找瓶颈阶段
                bottleneck = max(duration_stats, key=lambda x: x.get('avg_days', 0)) if duration_stats else None

                return jsonify({
                    'duration_stats': duration_stats,
                    'objects': list(obj_map.values()),
                    'bottleneck': bottleneck['lifecycle_stage'] if bottleneck else None,
                    'source': 'database'
                })
        except Exception as e:
            print(f"[WARN] 生命周期分析失败: {e}")

    return jsonify({'duration_stats': [], 'objects': [], 'bottleneck': None, 'source': 'json_file'})


@olm_api.route('/api/olm/lifecycle-report/<object_code>')
def api_lifecycle_report(object_code):
    """生命周期报告导出"""
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            # 对象基本信息
            obj_result = execute_query(
                "SELECT * FROM extracted_objects WHERE object_code = %s LIMIT 1",
                (object_code,))
            if not isinstance(obj_result, list) or not obj_result:
                return jsonify({'error': f'对象 {object_code} 不存在'}), 404

            obj = obj_result[0]
            for k in ['created_at', 'updated_at', 'verified_at']:
                if obj.get(k):
                    obj[k] = obj[k].isoformat() if hasattr(obj[k], 'isoformat') else str(obj[k])
            if obj.get('extraction_confidence') is not None:
                obj['extraction_confidence'] = float(obj['extraction_confidence'])

            # 生命周期历史
            lc_result = execute_query("""
                SELECT * FROM object_lifecycle_history
                WHERE object_id = %s
                ORDER BY FIELD(lifecycle_stage, 'Planning','Design','Construction','Operation')
            """, (obj['object_id'],))

            lifecycle = []
            if isinstance(lc_result, list):
                for row in lc_result:
                    for k in ['stage_entered_at', 'stage_exited_at', 'created_at']:
                        if row.get(k):
                            row[k] = row[k].isoformat() if hasattr(row[k], 'isoformat') else str(row[k])
                    # 计算持续天数
                    if row.get('stage_entered_at'):
                        from datetime import datetime
                        entered = datetime.fromisoformat(row['stage_entered_at'])
                        exited = datetime.fromisoformat(row['stage_exited_at']) if row.get('stage_exited_at') else datetime.now()
                        row['duration_days'] = (exited - entered).days
                    lifecycle.append(row)

            return jsonify({
                'object': obj,
                'lifecycle': lifecycle,
                'stage_count': len(lifecycle),
                'total_days': sum(r.get('duration_days', 0) for r in lifecycle),
                'generated_at': datetime.now().isoformat() if lifecycle else None,
                'source': 'database'
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': '数据库不可用'}), 503


# ============================================================================
# Phase 3: 穿透式业务溯源 API
# ============================================================================

@olm_api.route('/api/olm/traceability-chains')
def api_traceability_chains():
    """列出所有溯源链路"""
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            query = "SELECT * FROM traceability_chains"
            params = []
            if domain:
                query += " WHERE data_domain = %s"
                params.append(domain)
            query += " ORDER BY created_at DESC"

            result = execute_query(query, tuple(params) if params else None)
            if isinstance(result, list):
                for row in result:
                    for key in ['created_at', 'updated_at']:
                        if row.get(key):
                            row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
                return jsonify({'chains': result, 'total': len(result), 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 溯源链路查询失败: {e}")

    return jsonify({'chains': [], 'total': 0, 'source': 'json_file'})


@olm_api.route('/api/olm/traceability-chains', methods=['POST'])
def api_create_chain():
    """创建溯源链路"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        data = request.get_json(force=True)
        chain_code = data.get('chain_code')
        chain_name = data.get('chain_name')
        if not chain_code or not chain_name:
            return jsonify({'success': False, 'error': '缺少 chain_code 或 chain_name'}), 400

        chain_id = execute_query("""
            INSERT INTO traceability_chains (chain_code, chain_name, chain_type, data_domain, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            chain_code, chain_name,
            data.get('chain_type', 'CUSTOM'),
            data.get('data_domain', ''),
            data.get('description', '')
        ), fetch=False)

        # 插入节点
        nodes = data.get('nodes', [])
        for node in nodes:
            obj_id = None
            if node.get('object_code'):
                obj_result = execute_query(
                    "SELECT object_id FROM extracted_objects WHERE object_code = %s LIMIT 1",
                    (node['object_code'],)
                )
                if isinstance(obj_result, list) and obj_result:
                    obj_id = obj_result[0]['object_id']

            execute_query("""
                INSERT INTO traceability_chain_nodes
                (chain_id, node_order, object_id, entity_layer, entity_name, node_label, node_type, source_file, source_sheet, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                chain_id, node.get('node_order', 0), obj_id,
                node.get('entity_layer'), node.get('entity_name', ''),
                node.get('node_label', node.get('entity_name', '')),
                node.get('node_type', 'INTERMEDIATE'),
                node.get('source_file', ''), node.get('source_sheet', ''),
                json.dumps(node.get('metadata', {}), ensure_ascii=False) if node.get('metadata') else None
            ), fetch=False)

        return jsonify({'success': True, 'chain_id': chain_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/traceability-chain/<int:chain_id>')
def api_chain_detail(chain_id):
    """查询链路详情（含全部节点）"""
    if is_db_available():
        try:
            chain = execute_query("SELECT * FROM traceability_chains WHERE chain_id = %s", (chain_id,))
            if not isinstance(chain, list) or not chain:
                return jsonify({'error': '链路不存在'}), 404

            chain_info = chain[0]
            for key in ['created_at', 'updated_at']:
                if chain_info.get(key):
                    chain_info[key] = chain_info[key].isoformat() if hasattr(chain_info[key], 'isoformat') else str(chain_info[key])

            nodes = execute_query("""
                SELECT n.*, o.object_code, o.object_name
                FROM traceability_chain_nodes n
                LEFT JOIN extracted_objects o ON o.object_id = n.object_id
                WHERE n.chain_id = %s
                ORDER BY n.node_order
            """, (chain_id,))

            if isinstance(nodes, list):
                for node in nodes:
                    if node.get('metadata') and isinstance(node['metadata'], str):
                        try:
                            node['metadata'] = json.loads(node['metadata'])
                        except Exception:
                            pass

            chain_info['nodes'] = nodes if isinstance(nodes, list) else []
            return jsonify({'chain': chain_info, 'source': 'database'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': '数据库不可用，溯源链路详情仅在数据库模式下可查询', 'chain': None, 'source': 'json'}), 503


@olm_api.route('/api/olm/trace-object/<object_code>')
def api_trace_object(object_code):
    """从对象出发追溯所有关联链路"""
    if is_db_available():
        try:
            result = execute_query("""
                SELECT DISTINCT c.*
                FROM traceability_chains c
                JOIN traceability_chain_nodes n ON n.chain_id = c.chain_id
                JOIN extracted_objects o ON o.object_id = n.object_id
                WHERE o.object_code = %s
                ORDER BY c.created_at DESC
            """, (object_code,))

            if isinstance(result, list):
                for row in result:
                    for key in ['created_at', 'updated_at']:
                        if row.get(key):
                            row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
                return jsonify({'chains': result, 'object_code': object_code, 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 对象溯源查询失败: {e}")

    return jsonify({'chains': [], 'object_code': object_code, 'source': 'json_file'})


# ============================================================================
# Phase 4: 机理函数框架 API
# ============================================================================

@olm_api.route('/api/olm/mechanism-functions')
def api_mechanism_functions():
    """列出所有机理函数"""
    func_type = request.args.get('type', '')
    is_active = request.args.get('active', '')

    if is_db_available():
        try:
            query = "SELECT * FROM mechanism_functions WHERE 1=1"
            params = []
            if func_type:
                query += " AND func_type = %s"
                params.append(func_type)
            if is_active != '':
                query += " AND is_active = %s"
                params.append(is_active == 'true')
            query += " ORDER BY created_at DESC"

            result = execute_query(query, tuple(params) if params else None)
            if isinstance(result, list):
                for row in result:
                    for key in ['created_at', 'updated_at']:
                        if row.get(key):
                            row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
                    if row.get('expression') and isinstance(row['expression'], str):
                        try:
                            row['expression'] = json.loads(row['expression'])
                        except Exception:
                            pass
                return jsonify({'functions': result, 'total': len(result), 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 机理函数查询失败: {e}")

    return jsonify({'functions': [], 'total': 0, 'source': 'json_file'})


@olm_api.route('/api/olm/mechanism-functions', methods=['POST'])
def api_create_mechanism_function():
    """创建机理函数"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        data = request.get_json(force=True)
        func_code = data.get('func_code')
        func_name = data.get('func_name')
        func_type = data.get('func_type')
        expression = data.get('expression')

        if not all([func_code, func_name, func_type, expression]):
            return jsonify({'success': False, 'error': '缺少必填字段: func_code, func_name, func_type, expression'}), 400

        expr_json = json.dumps(expression, ensure_ascii=False) if isinstance(expression, dict) else expression

        result = execute_query("""
            INSERT INTO mechanism_functions
            (func_code, func_name, func_type, category, expression, description,
             source_object_code, target_object_code, severity, is_active, data_domain)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            func_code, func_name, func_type,
            data.get('category', 'BUSINESS'), expr_json,
            data.get('description', ''),
            data.get('source_object_code', ''),
            data.get('target_object_code', ''),
            data.get('severity', 'WARNING'),
            data.get('is_active', True),
            data.get('data_domain', '')
        ), fetch=False)

        return jsonify({'success': True, 'func_id': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/mechanism-functions/<int:func_id>', methods=['PUT'])
def api_update_mechanism_function(func_id):
    """更新机理函数"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        data = request.get_json(force=True)
        updates = []
        params = []

        for field in ['func_name', 'func_type', 'category', 'description',
                       'source_object_code', 'target_object_code', 'severity', 'data_domain']:
            if field in data:
                updates.append(f'{field} = %s')
                params.append(data[field])

        if 'expression' in data:
            updates.append('expression = %s')
            expr = data['expression']
            params.append(json.dumps(expr, ensure_ascii=False) if isinstance(expr, dict) else expr)

        if 'is_active' in data:
            updates.append('is_active = %s')
            params.append(data['is_active'])

        if not updates:
            return jsonify({'success': False, 'error': '无更新字段'}), 400

        params.append(func_id)
        execute_query(f"UPDATE mechanism_functions SET {', '.join(updates)} WHERE func_id = %s",
                      tuple(params), fetch=False)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/mechanism-functions/<int:func_id>', methods=['DELETE'])
def api_delete_mechanism_function(func_id):
    """删除机理函数"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        execute_query("DELETE FROM mechanism_functions WHERE func_id = %s", (func_id,), fetch=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/mechanism-functions/evaluate', methods=['POST'])
def api_evaluate_function():
    """执行函数评估（给定输入值）"""
    try:
        data = request.get_json(force=True)
        func_id = data.get('func_id')
        input_values = data.get('input_values', {})

        # 从数据库或请求体获取函数定义
        expression = data.get('expression')
        if func_id and is_db_available():
            func = execute_query("SELECT * FROM mechanism_functions WHERE func_id = %s", (func_id,))
            if isinstance(func, list) and func:
                expr_raw = func[0].get('expression', '{}')
                expression = json.loads(expr_raw) if isinstance(expr_raw, str) else expr_raw

        if not expression:
            return jsonify({'success': False, 'error': '未找到函数定义'}), 400

        # 评估表达式
        result = _evaluate_expression(expression, input_values)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _evaluate_expression(expression: dict, input_values: dict) -> dict:
    """评估机理函数表达式"""
    expr_type = expression.get('type', '')

    if expr_type == 'THRESHOLD':
        field = expression.get('field', '')
        operator = expression.get('operator', '>')
        threshold = float(expression.get('value', 0))
        actual = float(input_values.get(field, 0))

        ops = {'>': actual > threshold, '<': actual < threshold,
               '>=': actual >= threshold, '<=': actual <= threshold,
               '==': actual == threshold, '!=': actual != threshold}
        triggered = ops.get(operator, False)

        return {
            'triggered': triggered,
            'field': field,
            'actual_value': actual,
            'threshold': threshold,
            'operator': operator,
            'message': expression.get('message', '') if triggered else '未触发'
        }

    elif expr_type == 'FORMULA':
        variables = expression.get('variables', [])
        result_name = expression.get('result', '结果')
        values = {v: float(input_values.get(v, 0)) for v in variables}

        # 简单公式求值（乘法/加法/减法/除法）
        expr_str = expression.get('expression', '')
        computed = None
        if '*' in expr_str and len(variables) == 2:
            computed = values[variables[0]] * values[variables[1]]
        elif '+' in expr_str and len(variables) == 2:
            computed = values[variables[0]] + values[variables[1]]
        elif '-' in expr_str and len(variables) == 2:
            computed = values[variables[0]] - values[variables[1]]
        elif '/' in expr_str and len(variables) == 2 and values[variables[1]] != 0:
            computed = values[variables[0]] / values[variables[1]]

        return {
            'result_name': result_name,
            'computed_value': computed,
            'unit': expression.get('unit', ''),
            'input_values': values
        }

    elif expr_type == 'RULE':
        condition = expression.get('condition', '')
        then_action = expression.get('then', '')
        else_action = expression.get('else', '')

        # 简单条件判断
        triggered = False
        for field, value in input_values.items():
            if field in condition:
                try:
                    parts = condition.split()
                    if len(parts) >= 3:
                        op = parts[1]
                        threshold = float(parts[2])
                        actual = float(value)
                        ops = {'>': actual > threshold, '<': actual < threshold,
                               '>=': actual >= threshold, '<=': actual <= threshold}
                        triggered = ops.get(op, False)
                except (ValueError, IndexError):
                    pass

        return {
            'triggered': triggered,
            'action': then_action if triggered else else_action,
            'condition': condition
        }

    return {'error': f'不支持的表达式类型: {expr_type}'}


@olm_api.route('/api/olm/mechanism-functions/presets')
def api_mechanism_presets():
    """获取预置函数模板"""
    presets = [
        {
            'name': '阈值检查',
            'type': 'THRESHOLD',
            'template': {
                'type': 'THRESHOLD',
                'field': '字段名',
                'operator': '>',
                'value': 0,
                'unit': '',
                'action': 'ALERT',
                'message': '超出阈值时的提示信息'
            }
        },
        {
            'name': '计算公式',
            'type': 'FORMULA',
            'template': {
                'type': 'FORMULA',
                'expression': '结果 = 变量A * 变量B',
                'variables': ['变量A', '变量B'],
                'result': '结果',
                'unit': ''
            }
        },
        {
            'name': '条件规则',
            'type': 'RULE',
            'template': {
                'type': 'RULE',
                'condition': '字段名 > 阈值',
                'then': '满足时执行',
                'else': '不满足时执行',
                'description': '规则描述'
            }
        }
    ]
    return jsonify({'presets': presets})


# ============================================================================
# Phase 5: 穿透式预警与辅助决策 API
# ============================================================================

@olm_api.route('/api/olm/alerts')
def api_alerts():
    """查询预警记录"""
    level = request.args.get('level', '')
    resolved = request.args.get('resolved', '')
    limit = min(int(request.args.get('limit', '50')), 200)

    if is_db_available():
        try:
            query = """
                SELECT a.*, f.func_name, f.func_type, f.severity as func_severity
                FROM alert_records a
                JOIN mechanism_functions f ON f.func_id = a.func_id
                WHERE 1=1
            """
            params = []
            if level:
                query += " AND a.alert_level = %s"
                params.append(level)
            if resolved != '':
                query += " AND a.is_resolved = %s"
                params.append(resolved == 'true')
            query += " ORDER BY a.is_resolved ASC, a.created_at DESC LIMIT %s"
            params.append(limit)

            result = execute_query(query, tuple(params))
            if isinstance(result, list):
                for row in result:
                    for key in ['created_at', 'resolved_at']:
                        if row.get(key):
                            row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
                return jsonify({'alerts': result, 'total': len(result), 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 预警查询失败: {e}")

    return jsonify({'alerts': [], 'total': 0, 'source': 'json_file'})


@olm_api.route('/api/olm/alerts/<int:alert_id>/resolve', methods=['POST'])
def api_resolve_alert(alert_id):
    """标记预警已处理"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        data = request.get_json(force=True) if request.is_json else {}
        execute_query("""
            UPDATE alert_records
            SET is_resolved = TRUE, resolved_by = %s, resolved_at = CURRENT_TIMESTAMP(6)
            WHERE alert_id = %s
        """, (data.get('resolved_by', 'system'), alert_id), fetch=False)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/alerts/summary')
def api_alerts_summary():
    """预警统计概览"""
    if is_db_available():
        try:
            total = execute_query("SELECT COUNT(*) as cnt FROM alert_records")
            unresolved = execute_query("SELECT COUNT(*) as cnt FROM alert_records WHERE is_resolved = FALSE")
            by_level = execute_query("""
                SELECT alert_level, COUNT(*) as cnt
                FROM alert_records WHERE is_resolved = FALSE
                GROUP BY alert_level
            """)

            return jsonify({
                'total': total[0]['cnt'] if isinstance(total, list) and total else 0,
                'unresolved': unresolved[0]['cnt'] if isinstance(unresolved, list) and unresolved else 0,
                'by_level': {r['alert_level']: r['cnt'] for r in by_level} if isinstance(by_level, list) else {},
                'source': 'database'
            })
        except Exception as e:
            print(f"[WARN] 预警统计失败: {e}")

    return jsonify({'total': 0, 'unresolved': 0, 'by_level': {}, 'source': 'json_file'})


@olm_api.route('/api/olm/alerts/run-check', methods=['POST'])
def api_run_alert_check():
    """手动触发全量规则检查"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        # 获取所有活跃的机理函数
        functions = execute_query("SELECT * FROM mechanism_functions WHERE is_active = TRUE")
        if not isinstance(functions, list):
            return jsonify({'success': True, 'alerts_created': 0, 'message': '无活跃机理函数'})

        alerts_created = 0
        for func in functions:
            expr_raw = func.get('expression', '{}')
            expression = json.loads(expr_raw) if isinstance(expr_raw, str) else expr_raw
            func_type = expression.get('type', '')

            # 对于 THRESHOLD 类型，从 EAV 数据中检查
            if func_type == 'THRESHOLD':
                field = expression.get('field', '')
                threshold = float(expression.get('value', 0))
                operator = expression.get('operator', '>')

                # 从 EAV 值表中查找匹配的属性值
                eav_values = execute_query("""
                    SELECT v.value_number, a.name as attr_name, e.entity_label
                    FROM eav_values v
                    JOIN eav_attributes a ON a.id = v.attribute_id
                    JOIN eav_entities e ON e.id = v.entity_id
                    WHERE a.name LIKE %s AND v.value_number IS NOT NULL
                    LIMIT 100
                """, (f'%{field}%',))

                if isinstance(eav_values, list):
                    for val in eav_values:
                        actual = float(val.get('value_number', 0))
                        ops = {'>': actual > threshold, '<': actual < threshold,
                               '>=': actual >= threshold, '<=': actual <= threshold}
                        if ops.get(operator, False):
                            execute_query("""
                                INSERT INTO alert_records
                                (func_id, alert_level, alert_title, alert_detail,
                                 related_entity_name, trigger_value, threshold_value)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (
                                func['func_id'],
                                func.get('severity', 'WARNING'),
                                f"{func['func_name']} - {val.get('entity_label', '')}",
                                expression.get('message', '规则触发'),
                                val.get('entity_label', ''),
                                str(actual),
                                str(threshold)
                            ), fetch=False)
                            alerts_created += 1

        return jsonify({
            'success': True,
            'alerts_created': alerts_created,
            'functions_checked': len(functions)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Phase 6: 财务数据一致性治理看板 API
# ============================================================================

def _compute_governance_from_json(domain: str) -> dict:
    """从 JSON 文件计算治理指标（数据库不可用时的后备）"""
    data = load_json_data(domain or 'shupeidian')
    objects = data.get('objects', [])
    relations = data.get('relations', [])

    if not objects:
        return {'metrics': {}, 'completeness': [], 'defects': [], 'source': 'json_file'}

    # 按对象统计各层关联
    obj_layers = {}  # {code: {concept:N, logical:N, physical:N}}
    strength_list = []
    for rel in relations:
        code = rel.get('object_code', '')
        layer = rel.get('entity_layer', '').lower()
        if code and layer in ('concept', 'logical', 'physical'):
            if code not in obj_layers:
                obj_layers[code] = {'concept': 0, 'logical': 0, 'physical': 0}
            obj_layers[code][layer] += 1
        s = rel.get('relation_strength', 0)
        if s:
            strength_list.append(float(s))

    total_obj = len(objects)
    complete = sum(1 for c in obj_layers.values() if c['concept'] > 0 and c['logical'] > 0 and c['physical'] > 0)
    partial = sum(1 for code, c in obj_layers.items() if (c['concept'] + c['logical'] + c['physical']) > 0 and not (c['concept'] > 0 and c['logical'] > 0 and c['physical'] > 0))
    empty_obj = total_obj - len(obj_layers)

    avg_strength = sum(strength_list) / len(strength_list) if strength_list else 0
    strong_count = sum(1 for s in strength_list if s >= 0.8)

    metrics = {
        'total_objects': total_obj,
        'complete_objects': complete,
        'partial_objects': partial,
        'empty_objects': empty_obj,
        'completeness_rate': round(complete / total_obj * 100, 1) if total_obj else 0,
        'total_relations': len(relations),
        'avg_strength': round(avg_strength, 3),
        'strong_relation_rate': round(strong_count / len(strength_list) * 100, 1) if strength_list else 0,
        'weak_relations': sum(1 for s in strength_list if s < 0.5),
        'attr_coverage_rate': 0,
        'lifecycle_coverage_rate': 0,
        'traceability_coverage_rate': 0,
    }

    # 完整性详情
    completeness = []
    for obj in objects:
        code = obj.get('object_code', '')
        layers = obj_layers.get(code, {'concept': 0, 'logical': 0, 'physical': 0})
        status = 'COMPLETE' if (layers['concept'] > 0 and layers['logical'] > 0 and layers['physical'] > 0) else ('EMPTY' if sum(layers.values()) == 0 else 'PARTIAL')
        completeness.append({
            'object_code': code,
            'object_name': obj.get('object_name', ''),
            'object_type': obj.get('object_type', ''),
            'concept_count': layers['concept'],
            'logical_count': layers['logical'],
            'physical_count': layers['physical'],
            'completeness_status': status,
            'attr_defined_count': 0,
            'lifecycle_record_count': 0,
            'traceability_chain_count': 0,
        })

    # 缺陷识别
    defects = []
    for obj in objects:
        code = obj.get('object_code', '')
        layers = obj_layers.get(code, {'concept': 0, 'logical': 0, 'physical': 0})
        for layer_name, label in [('concept', '概念'), ('logical', '逻辑'), ('physical', '物理')]:
            if layers[layer_name] == 0 and sum(layers.values()) > 0:
                defects.append({
                    'object_code': code, 'object_name': obj.get('object_name', ''),
                    'defect_type': 'MISSING_LAYER', 'defect_detail': f'缺少{label}层关联',
                    'severity': 'WARNING'
                })

    for rel in relations:
        s = rel.get('relation_strength', 1)
        if s and float(s) < 0.5:
            defects.append({
                'object_code': rel.get('object_code', ''),
                'object_name': '',
                'defect_type': 'WEAK_RELATION',
                'defect_detail': f"弱关联: {rel.get('entity_name','')} (强度={round(float(s),2)})",
                'severity': 'INFO'
            })

    return {'metrics': metrics, 'completeness': completeness, 'defects': defects[:100], 'source': 'json_file'}


@olm_api.route('/api/olm/governance/metrics')
def api_governance_metrics():
    """治理看板汇总指标"""
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            # 对象总数
            q_total = "SELECT COUNT(*) as cnt FROM extracted_objects"
            p = []
            if domain:
                q_total += " WHERE data_domain = %s"
                p.append(domain)
            total_result = execute_query(q_total, tuple(p) if p else None)
            total_obj = total_result[0]['cnt'] if isinstance(total_result, list) and total_result else 0

            # 完整性统计
            comp_result = execute_query("""
                SELECT completeness_status, COUNT(*) as cnt
                FROM v_governance_completeness
                """ + ("WHERE data_domain = %s " if domain else "") + """
                GROUP BY completeness_status
            """, (domain,) if domain else None)

            complete = partial = empty_obj = 0
            if isinstance(comp_result, list):
                for row in comp_result:
                    if row['completeness_status'] == 'COMPLETE':
                        complete = row['cnt']
                    elif row['completeness_status'] == 'PARTIAL':
                        partial = row['cnt']
                    elif row['completeness_status'] == 'EMPTY':
                        empty_obj = row['cnt']

            # 关联强度
            strength_q = "SELECT AVG(relation_strength) as avg_s, COUNT(*) as total, SUM(CASE WHEN relation_strength >= 0.8 THEN 1 ELSE 0 END) as strong, SUM(CASE WHEN relation_strength < 0.5 THEN 1 ELSE 0 END) as weak FROM object_entity_relations"
            if domain:
                strength_q += " WHERE data_domain = %s"
            strength_result = execute_query(strength_q, (domain,) if domain else None)
            sr = strength_result[0] if isinstance(strength_result, list) and strength_result else {}

            # 属性覆盖
            attr_q = "SELECT COUNT(DISTINCT object_id) as cnt FROM object_attribute_definitions"
            attr_result = execute_query(attr_q)
            attr_covered = attr_result[0]['cnt'] if isinstance(attr_result, list) and attr_result else 0

            # 生命周期覆盖
            life_q = "SELECT COUNT(DISTINCT object_id) as cnt FROM object_lifecycle_history"
            life_result = execute_query(life_q)
            life_covered = life_result[0]['cnt'] if isinstance(life_result, list) and life_result else 0

            # 溯源覆盖
            trace_q = "SELECT COUNT(DISTINCT cn.object_id) as cnt FROM traceability_chain_nodes cn WHERE cn.object_id IS NOT NULL"
            trace_result = execute_query(trace_q)
            trace_covered = trace_result[0]['cnt'] if isinstance(trace_result, list) and trace_result else 0

            total_rels = int(sr.get('total', 0) or 0)
            metrics = {
                'total_objects': total_obj,
                'complete_objects': complete,
                'partial_objects': partial,
                'empty_objects': empty_obj,
                'completeness_rate': round(complete / total_obj * 100, 1) if total_obj else 0,
                'total_relations': total_rels,
                'avg_strength': round(float(sr.get('avg_s', 0) or 0), 3),
                'strong_relation_rate': round(int(sr.get('strong', 0) or 0) / total_rels * 100, 1) if total_rels else 0,
                'weak_relations': int(sr.get('weak', 0) or 0),
                'attr_coverage_rate': round(attr_covered / total_obj * 100, 1) if total_obj else 0,
                'lifecycle_coverage_rate': round(life_covered / total_obj * 100, 1) if total_obj else 0,
                'traceability_coverage_rate': round(trace_covered / total_obj * 100, 1) if total_obj else 0,
            }
            return jsonify({'metrics': metrics, 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 治理指标数据库查询失败: {e}")

    result = _compute_governance_from_json(domain)
    return jsonify({'metrics': result['metrics'], 'source': result['source']})


@olm_api.route('/api/olm/governance/completeness')
def api_governance_completeness():
    """治理看板：对象完整性详情"""
    domain = request.args.get('domain', '')

    if is_db_available():
        try:
            query = "SELECT * FROM v_governance_completeness"
            params = []
            if domain:
                query += " WHERE data_domain = %s"
                params.append(domain)
            query += " ORDER BY completeness_status ASC, object_code"

            result = execute_query(query, tuple(params) if params else None)
            if isinstance(result, list):
                return jsonify({'completeness': result, 'total': len(result), 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 治理完整性查询失败: {e}")

    result = _compute_governance_from_json(domain)
    return jsonify({'completeness': result['completeness'], 'total': len(result['completeness']), 'source': result['source']})


@olm_api.route('/api/olm/governance/defects')
def api_governance_defects():
    """治理看板：缺陷识别列表"""
    domain = request.args.get('domain', '')
    severity = request.args.get('severity', '')

    if is_db_available():
        try:
            query = "SELECT * FROM v_governance_defects WHERE 1=1"
            params = []
            if domain:
                query += " AND data_domain = %s"
                params.append(domain)
            if severity:
                query += " AND severity = %s"
                params.append(severity)
            query += " ORDER BY severity DESC, object_code LIMIT 200"

            result = execute_query(query, tuple(params) if params else None)
            if isinstance(result, list):
                return jsonify({'defects': result, 'total': len(result), 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 治理缺陷查询失败: {e}")

    result = _compute_governance_from_json(domain)
    defects = result['defects']
    if severity:
        defects = [d for d in defects if d.get('severity') == severity]
    return jsonify({'defects': defects, 'total': len(defects), 'source': result['source']})


@olm_api.route('/api/olm/governance/domain-comparison')
def api_governance_domain_comparison():
    """治理看板：跨域对象一致性对比"""
    all_domains = set()
    domain_objects = {}  # {domain: set(object_codes)}

    if is_db_available():
        try:
            result = execute_query("SELECT DISTINCT data_domain, object_code FROM extracted_objects WHERE data_domain != 'default'")
            if isinstance(result, list):
                for row in result:
                    d = row['data_domain']
                    all_domains.add(d)
                    domain_objects.setdefault(d, set()).add(row['object_code'])
        except Exception:
            pass

    # JSON 后备
    if not all_domains:
        for json_file in OUTPUTS_DIR.glob('extraction_*.json'):
            domain_name = json_file.stem.replace('extraction_', '')
            data = load_json_data(domain_name)
            if data.get('objects'):
                all_domains.add(domain_name)
                domain_objects[domain_name] = set(o.get('object_code', '') for o in data['objects'])

    if len(all_domains) < 2:
        return jsonify({'comparison': [], 'message': '需要至少两个数据域才能进行对比', 'source': 'json_file'})

    # 计算交集和差集
    all_codes = set()
    for codes in domain_objects.values():
        all_codes.update(codes)

    comparison = []
    for code in sorted(all_codes):
        present_in = [d for d in sorted(all_domains) if code in domain_objects.get(d, set())]
        missing_in = [d for d in sorted(all_domains) if code not in domain_objects.get(d, set())]
        comparison.append({
            'object_code': code,
            'present_in': present_in,
            'missing_in': missing_in,
            'coverage': f"{len(present_in)}/{len(all_domains)}",
            'is_consistent': len(missing_in) == 0
        })

    consistent_count = sum(1 for c in comparison if c['is_consistent'])
    return jsonify({
        'comparison': comparison,
        'domains': sorted(all_domains),
        'total_objects': len(all_codes),
        'consistent_count': consistent_count,
        'consistency_rate': round(consistent_count / len(all_codes) * 100, 1) if all_codes else 0,
        'source': 'database' if is_db_available() else 'json_file'
    })


# ============================================================================
# 对象间关系规则 API（Phase 3）
# ============================================================================

@olm_api.route('/api/olm/relation-rules')
def api_relation_rules():
    """列出所有关系规则（支持按 source/target/category 过滤）"""
    source = request.args.get('source')
    target = request.args.get('target')
    category = request.args.get('category')
    active_only = request.args.get('active_only', 'true').lower() == 'true'

    if not is_db_available():
        return jsonify({'rules': [], 'total': 0, 'source': 'unavailable', 'message': '数据库不可用'})

    try:
        query = "SELECT * FROM object_relation_rules WHERE 1=1"
        params = []
        if source:
            query += " AND source_object_code = %s"
            params.append(source)
        if target:
            query += " AND target_object_code = %s"
            params.append(target)
        if category:
            query += " AND rule_category = %s"
            params.append(category)
        if active_only:
            query += " AND is_active = TRUE"
        query += " ORDER BY rule_id"

        rules = execute_query(query, tuple(params) if params else None)
        if isinstance(rules, dict) and 'error' in rules:
            return jsonify({'rules': [], 'total': 0, 'error': rules['error']})

        for r in rules:
            if isinstance(r.get('expression'), str):
                try:
                    r['expression'] = json.loads(r['expression'])
                except json.JSONDecodeError:
                    pass
            if isinstance(r.get('applicable_stages'), str):
                try:
                    r['applicable_stages'] = json.loads(r['applicable_stages'])
                except json.JSONDecodeError:
                    pass

        return jsonify({'rules': rules, 'total': len(rules), 'source': 'database'})
    except Exception as e:
        return jsonify({'rules': [], 'total': 0, 'error': str(e)})


@olm_api.route('/api/olm/relation-rules', methods=['POST'])
def api_create_relation_rule():
    """创建关系规则"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        data = request.get_json(force=True)
        required = ['rule_code', 'rule_name', 'source_object_code', 'target_object_code',
                     'relation_type', 'rule_category', 'expression']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400

        expression = data['expression']
        if isinstance(expression, dict):
            expression = json.dumps(expression, ensure_ascii=False)

        applicable_stages = data.get('applicable_stages')
        if isinstance(applicable_stages, list):
            applicable_stages = json.dumps(applicable_stages, ensure_ascii=False)

        execute_query("""
            INSERT INTO object_relation_rules
            (rule_code, rule_name, source_object_code, target_object_code, relation_type,
             rule_category, expression, description, direction, priority,
             applicable_stages, severity, is_active, data_domain)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['rule_code'], data['rule_name'],
            data['source_object_code'], data['target_object_code'],
            data['relation_type'], data['rule_category'],
            expression, data.get('description', ''),
            data.get('direction', 'UNIDIRECTIONAL'),
            data.get('priority', 0),
            applicable_stages,
            data.get('severity', 'INFO'),
            data.get('is_active', True),
            data.get('data_domain')
        ), fetch=False)

        return jsonify({'success': True, 'message': '关系规则创建成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/relation-rules/<int:rule_id>', methods=['PUT'])
def api_update_relation_rule(rule_id):
    """更新关系规则"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        data = request.get_json(force=True)
        allowed = ['rule_name', 'source_object_code', 'target_object_code', 'relation_type',
                    'rule_category', 'expression', 'description', 'direction', 'priority',
                    'applicable_stages', 'severity', 'is_active', 'data_domain']

        updates = []
        params = []
        for field in allowed:
            if field in data:
                val = data[field]
                if field == 'expression' and isinstance(val, dict):
                    val = json.dumps(val, ensure_ascii=False)
                if field == 'applicable_stages' and isinstance(val, list):
                    val = json.dumps(val, ensure_ascii=False)
                updates.append(f"`{field}` = %s")
                params.append(val)

        if not updates:
            return jsonify({'success': False, 'error': '没有可更新的字段'}), 400

        params.append(rule_id)
        execute_query(f"UPDATE object_relation_rules SET {', '.join(updates)} WHERE rule_id = %s",
                      tuple(params), fetch=False)
        return jsonify({'success': True, 'message': '关系规则更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/relation-rules/<int:rule_id>', methods=['DELETE'])
def api_delete_relation_rule(rule_id):
    """删除关系规则"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503

    try:
        execute_query("DELETE FROM object_relation_rules WHERE rule_id = %s", (rule_id,), fetch=False)
        return jsonify({'success': True, 'message': '关系规则已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/relation-rules/evaluate', methods=['POST'])
def api_evaluate_relation_rule():
    """执行关系规则求值（输入变量值 → 返回计算结果）"""
    try:
        data = request.get_json(force=True)
        rule_id = data.get('rule_id')
        variables = data.get('variables', {})

        expression = data.get('expression')
        rule_meta = {}

        if rule_id and is_db_available():
            rows = execute_query("SELECT * FROM object_relation_rules WHERE rule_id = %s", (rule_id,))
            if isinstance(rows, list) and rows:
                rule = rows[0]
                expr_raw = rule.get('expression', '{}')
                expression = json.loads(expr_raw) if isinstance(expr_raw, str) else expr_raw
                rule_meta = {
                    'rule_name': rule.get('rule_name'),
                    'source': rule.get('source_object_code'),
                    'target': rule.get('target_object_code'),
                    'relation_type': rule.get('relation_type'),
                    'rule_category': rule.get('rule_category')
                }

        if not expression:
            return jsonify({'success': False, 'error': '未找到规则定义'}), 400

        result = _evaluate_relation_rule(expression, variables)
        result['rule_meta'] = rule_meta
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _evaluate_relation_rule(expression: dict, variables: dict) -> dict:
    """评估关系规则表达式（增强版，支持多种公式格式）"""
    formula = expression.get('formula', '')

    # --- PHYSICAL_FORMULA / DERIVED_CALC: 公式求值 ---
    if formula:
        var_defs = expression.get('variables', {})
        result_name = expression.get('result', '结果')

        # 提取数值
        numeric_vars = {}
        for k, v in variables.items():
            try:
                numeric_vars[k] = float(v)
            except (ValueError, TypeError):
                numeric_vars[k] = 0

        computed = None
        # I² × R × L 模式（线损，三变量含平方）
        if '²' in formula and len(numeric_vars) == 3:
            keys = list(numeric_vars.keys())
            computed = numeric_vars[keys[0]] ** 2 * numeric_vars[keys[1]] * numeric_vars[keys[2]]
        # (a - b) / c 模式（折旧公式等，三变量含减法和除法）
        elif '-' in formula and '/' in formula and len(numeric_vars) == 3:
            keys = list(numeric_vars.keys())
            computed = (numeric_vars[keys[0]] - numeric_vars[keys[1]]) / numeric_vars[keys[2]] if numeric_vars[keys[2]] != 0 else None
        # a / b × 100 模式（百分比计算，两变量）
        elif '/' in formula and ('×' in formula or '*' in formula) and '100' in formula and len(numeric_vars) == 2:
            vals = list(numeric_vars.values())
            computed = vals[0] / vals[1] * 100 if vals[1] != 0 else None
        # P = U × I（两变量乘法）
        elif '×' in formula and len(numeric_vars) == 2:
            vals = list(numeric_vars.values())
            computed = vals[0] * vals[1]
        # 通用两变量乘法
        elif len(numeric_vars) == 2:
            vals = list(numeric_vars.values())
            computed = vals[0] * vals[1]

        # 约束检查
        constraint = expression.get('constraint')
        constraint_result = None
        if constraint and computed is not None:
            try:
                parts = constraint.replace('≤', '<=').replace('≥', '>=').split()
                if len(parts) >= 3:
                    threshold = float(parts[-1])
                    op = parts[-2]
                    ops = {'<=': computed <= threshold, '>=': computed >= threshold,
                           '<': computed < threshold, '>': computed > threshold}
                    constraint_result = {
                        'satisfied': ops.get(op, True),
                        'constraint': constraint,
                        'actual': round(computed, 4),
                        'threshold': threshold,
                        'message': expression.get('message', '').replace('{value}', f'{computed:.1f}') if not ops.get(op, True) else '满足约束'
                    }
            except (ValueError, IndexError):
                pass

        return {
            'type': 'formula',
            'formula': formula,
            'input_values': numeric_vars,
            'result_name': result_name,
            'computed_value': round(computed, 4) if computed is not None else None,
            'unit': expression.get('unit', ''),
            'constraint_check': constraint_result,
            'method': expression.get('method'),
            'industry_standard': expression.get('industry_standard')
        }

    # --- THRESHOLD: 阈值检查 ---
    if 'field' in expression and 'operator' in expression:
        field = expression['field']
        operator = expression['operator']
        ref = expression.get('reference_field')
        tolerance = float(expression.get('tolerance', 0))

        actual = float(variables.get(field, variables.get('actual', 0)))
        threshold = float(variables.get(ref, variables.get('threshold', expression.get('value', 0))))
        if tolerance > 0:
            threshold = threshold * (1 + tolerance)

        ops = {'>': actual > threshold, '<': actual < threshold,
               '>=': actual >= threshold, '<=': actual <= threshold}
        triggered = ops.get(operator, False)

        return {
            'type': 'threshold',
            'triggered': triggered,
            'field': field,
            'actual_value': actual,
            'threshold': threshold,
            'tolerance': tolerance,
            'operator': operator,
            'message': expression.get('message', '') if triggered else '未触发'
        }

    # --- BUSINESS_RULE: 条件分支 ---
    condition = expression.get('condition', expression.get('trigger', ''))
    if condition:
        triggered = False
        for field, value in variables.items():
            if field in condition:
                try:
                    parts = condition.split()
                    for i, p in enumerate(parts):
                        if p in ('>', '<', '>=', '<=', '=', '=='):
                            threshold = float(parts[i + 1])
                            actual = float(value)
                            op = p if p != '=' else '=='
                            ops = {'>': actual > threshold, '<': actual < threshold,
                                   '>=': actual >= threshold, '<=': actual <= threshold,
                                   '==': actual == threshold}
                            triggered = ops.get(op, False)
                            break
                except (ValueError, IndexError):
                    pass

        then_action = expression.get('then', expression.get('action', ''))
        else_action = expression.get('else', '')

        return {
            'type': 'rule',
            'triggered': triggered,
            'condition': condition,
            'action': then_action if triggered else else_action,
            'side_effect': expression.get('side_effect')
        }

    return {'type': 'unknown', 'error': '无法识别的规则表达式格式'}


@olm_api.route('/api/olm/relation-rules/graph')
def api_relation_rules_graph():
    """返回关系规则图谱数据（ECharts 力导向图格式）"""
    if not is_db_available():
        return jsonify({'nodes': [], 'links': [], 'categories': [], 'source': 'unavailable'})

    try:
        rules = execute_query("SELECT * FROM object_relation_rules WHERE is_active = TRUE")
        if isinstance(rules, dict) and 'error' in rules:
            return jsonify({'nodes': [], 'links': [], 'error': rules['error']})

        objects = execute_query("SELECT object_code, object_name, data_domain FROM extracted_objects")
        obj_map = {}
        if isinstance(objects, list):
            for o in objects:
                obj_map[o['object_code']] = o.get('object_name', o['object_code'])

        # 收集涉及的对象
        involved = set()
        for r in rules:
            involved.add(r['source_object_code'])
            involved.add(r['target_object_code'])

        # 构建节点
        nodes = []
        for code in involved:
            nodes.append({
                'id': code,
                'name': obj_map.get(code, code.replace('OBJ_', '')),
                'symbolSize': 40,
                'category': 0
            })

        # 类别配色
        category_colors = {
            'PHYSICAL_FORMULA': {'name': '物理公式', 'color': '#3b82f6'},
            'BUSINESS_RULE': {'name': '业务规则', 'color': '#10b981'},
            'THRESHOLD': {'name': '阈值约束', 'color': '#ef4444'},
            'DERIVED_CALC': {'name': '派生计算', 'color': '#f59e0b'},
            'VALIDATION': {'name': '校验规则', 'color': '#8b5cf6'}
        }

        # 构建边
        links = []
        for r in rules:
            cat = r.get('rule_category', 'BUSINESS_RULE')
            expr_raw = r.get('expression', '{}')
            expr = json.loads(expr_raw) if isinstance(expr_raw, str) else expr_raw
            formula_text = expr.get('formula', expr.get('condition', expr.get('trigger', '')))

            links.append({
                'source': r['source_object_code'],
                'target': r['target_object_code'],
                'value': r['rule_name'],
                'rule_id': r['rule_id'],
                'rule_code': r['rule_code'],
                'rule_name': r['rule_name'],
                'relation_type': r.get('relation_type', ''),
                'rule_category': cat,
                'formula': formula_text,
                'description': r.get('description', ''),
                'severity': r.get('severity', 'INFO'),
                'lineStyle': {
                    'color': category_colors.get(cat, {}).get('color', '#999'),
                    'width': 3 if r.get('severity') == 'CRITICAL' else 2,
                    'type': 'dashed' if cat == 'THRESHOLD' else 'solid'
                }
            })

        categories = [{'name': v['name'], 'itemStyle': {'color': v['color']}}
                      for v in category_colors.values()]

        return jsonify({
            'nodes': nodes,
            'links': links,
            'categories': categories,
            'category_colors': category_colors,
            'total_rules': len(rules),
            'total_objects': len(nodes),
            'source': 'database'
        })
    except Exception as e:
        return jsonify({'nodes': [], 'links': [], 'error': str(e)})


# ============================================================================
# Phase 1: 对象名称可解释性 API
# ============================================================================

@olm_api.route('/api/olm/object-name-explanation/<object_code>')
def api_object_name_explanation(object_code):
    """获取对象命名的详细解释（含 Top-N 代表实体、聚类统计、重命名历史）"""
    if not is_db_available():
        return jsonify({'error': '数据库不可用'}), 503
    try:
        obj = execute_query(
            "SELECT * FROM extracted_objects WHERE object_code = %s", (object_code,))
        if not obj or isinstance(obj, dict):
            return jsonify({'error': '对象不存在'}), 404
        obj = obj[0]
        oid = obj['object_id']

        # Top-N 代表实体（按关联强度降序）
        top_entities = execute_query("""
            SELECT entity_name, entity_layer, relation_strength, match_method
            FROM object_entity_relations
            WHERE object_id = %s ORDER BY relation_strength DESC LIMIT 15
        """, (oid,))
        if isinstance(top_entities, dict):
            top_entities = []

        # 聚类统计
        stats = execute_query("""
            SELECT entity_layer, COUNT(*) as cnt,
                   ROUND(AVG(relation_strength), 4) as avg_strength
            FROM object_entity_relations WHERE object_id = %s
            GROUP BY entity_layer
        """, (oid,))
        if isinstance(stats, dict):
            stats = []

        # 重命名历史
        history = execute_query("""
            SELECT old_name, new_name, rename_source, rename_reason, renamed_by, created_at
            FROM object_name_history WHERE object_id = %s ORDER BY created_at DESC
        """, (oid,))
        if isinstance(history, dict):
            history = []

        # 关键词频率分析（从代表实体中提取高频词）
        entity_names = [e['entity_name'] for e in top_entities if e.get('entity_name')]
        word_freq = {}
        for name in entity_names:
            for seg in name.replace('信息', ' 信息').replace('管理', ' 管理').replace('数据', ' 数据').split():
                seg = seg.strip()
                if len(seg) >= 2:
                    word_freq[seg] = word_freq.get(seg, 0) + 1
        top_keywords = sorted(word_freq.items(), key=lambda x: -x[1])[:10]

        # 动态生成命名理由（如果 llm_reasoning 为空）
        reasoning = obj.get('llm_reasoning') or ''
        if not reasoning:
            total_rels = sum(s.get('cnt', 0) for s in stats)
            kw_text = '、'.join(f'「{k}」({v}次)' for k, v in top_keywords[:5])
            reasoning = (f"通过语义聚类分析，该聚类包含 {total_rels} 个实体关联。"
                        f"高频关键词: {kw_text}。"
                        f"代表性实体: {', '.join(entity_names[:5])}。"
                        f"基于关键词频率和语义聚合将该聚类命名为「{obj['object_name']}」。")

        return jsonify({
            'object_code': object_code,
            'object_name': obj['object_name'],
            'extraction_source': obj.get('extraction_source', ''),
            'extraction_confidence': float(obj.get('extraction_confidence', 0)),
            'llm_reasoning': reasoning,
            'top_entities': top_entities,
            'layer_stats': stats,
            'top_keywords': [{'word': k, 'count': v} for k, v in top_keywords],
            'rename_history': history,
            'cluster_size': obj.get('cluster_size', sum(s.get('cnt', 0) for s in stats)),
            'source': 'database'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@olm_api.route('/api/olm/objects/<object_code>/rename', methods=['POST'])
def api_rename_object(object_code):
    """重命名对象（含审计追踪）"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True)
        new_name = data.get('new_name', '').strip()
        reason = data.get('reason', '').strip()
        if not new_name:
            return jsonify({'success': False, 'error': '新名称不能为空'}), 400

        obj = execute_query(
            "SELECT object_id, object_name FROM extracted_objects WHERE object_code = %s",
            (object_code,))
        if not obj or isinstance(obj, dict):
            return jsonify({'success': False, 'error': '对象不存在'}), 404
        obj = obj[0]
        old_name = obj['object_name']
        if old_name == new_name:
            return jsonify({'success': False, 'error': '新旧名称相同'}), 400

        # 插入历史记录
        execute_query("""
            INSERT INTO object_name_history (object_id, old_name, new_name, rename_source, rename_reason, renamed_by)
            VALUES (%s, %s, %s, 'MANUAL', %s, %s)
        """, (obj['object_id'], old_name, new_name, reason or f'手动重命名: {old_name} → {new_name}',
              data.get('renamed_by', 'user')), fetch=False)

        # 更新对象名称
        execute_query(
            "UPDATE extracted_objects SET object_name = %s WHERE object_code = %s",
            (new_name, object_code), fetch=False)

        return jsonify({'success': True, 'old_name': old_name, 'new_name': new_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/objects/<object_code>/name-history')
def api_object_name_history(object_code):
    """查询对象重命名历史"""
    if not is_db_available():
        return jsonify([])
    try:
        obj = execute_query(
            "SELECT object_id FROM extracted_objects WHERE object_code = %s", (object_code,))
        if not obj or isinstance(obj, dict):
            return jsonify([])
        history = execute_query("""
            SELECT old_name, new_name, rename_source, rename_reason, renamed_by, created_at
            FROM object_name_history WHERE object_id = %s ORDER BY created_at DESC
        """, (obj[0]['object_id'],))
        return jsonify(history if isinstance(history, list) else [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Phase 2: 生命周期管理增强 API
# ============================================================================

@olm_api.route('/api/olm/lifecycle-templates')
def api_lifecycle_templates():
    """列出生命周期阶段模板"""
    obj_type = request.args.get('object_type', '')
    if not is_db_available():
        return jsonify([])
    try:
        sql = "SELECT * FROM lifecycle_stage_templates"
        params = []
        if obj_type:
            sql += " WHERE object_type = %s"
            params.append(obj_type)
        sql += " ORDER BY FIELD(lifecycle_stage, 'Planning','Design','Construction','Operation')"
        result = execute_query(sql, params or None)
        if isinstance(result, dict):
            return jsonify([])
        # Parse JSON fields
        for r in result:
            for field in ('required_attributes', 'optional_attributes', 'validation_rules', 'trigger_functions'):
                if isinstance(r.get(field), str):
                    try:
                        r[field] = json.loads(r[field])
                    except Exception:
                        pass
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@olm_api.route('/api/olm/lifecycle-templates', methods=['POST'])
def api_create_lifecycle_template():
    """创建或更新生命周期阶段模板"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True)
        obj_type = data.get('object_type', 'CORE')
        stage = data.get('lifecycle_stage')
        if not stage:
            return jsonify({'success': False, 'error': '缺少 lifecycle_stage'}), 400

        result = execute_query("""
            INSERT INTO lifecycle_stage_templates
            (object_type, lifecycle_stage, required_attributes, optional_attributes,
             validation_rules, trigger_functions, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                required_attributes = VALUES(required_attributes),
                optional_attributes = VALUES(optional_attributes),
                validation_rules = VALUES(validation_rules),
                trigger_functions = VALUES(trigger_functions),
                description = VALUES(description)
        """, (
            obj_type, stage,
            json.dumps(data.get('required_attributes', []), ensure_ascii=False),
            json.dumps(data.get('optional_attributes', []), ensure_ascii=False) if data.get('optional_attributes') else None,
            json.dumps(data.get('validation_rules', {}), ensure_ascii=False) if data.get('validation_rules') else None,
            json.dumps(data.get('trigger_functions', []), ensure_ascii=False) if data.get('trigger_functions') else None,
            data.get('description', '')
        ), fetch=False)

        return jsonify({'success': True, 'object_type': obj_type, 'stage': stage})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/object-lifecycle/<object_code>/validate', methods=['GET', 'POST'])
def api_validate_lifecycle(object_code):
    """验证对象是否满足当前阶段的模板要求"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        # 查对象及其类型
        obj = execute_query("""
            SELECT o.object_id, o.object_type FROM extracted_objects o
            WHERE o.object_code = %s
        """, (object_code,))
        if not obj or isinstance(obj, dict):
            return jsonify({'success': False, 'error': '对象不存在'}), 404
        obj = obj[0]

        # 查当前阶段
        current = execute_query("""
            SELECT lifecycle_stage, attributes_snapshot FROM object_lifecycle_history
            WHERE object_id = %s ORDER BY stage_entered_at DESC LIMIT 1
        """, (obj['object_id'],))
        if not current or isinstance(current, dict) or not current:
            return jsonify({'success': False, 'error': '对象无生命周期记录'}), 404
        cur_stage = current[0]['lifecycle_stage']
        snapshot = current[0].get('attributes_snapshot')
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except Exception:
                snapshot = {}
        if not snapshot:
            snapshot = {}

        # 查模板
        tmpl = execute_query("""
            SELECT required_attributes, optional_attributes, validation_rules
            FROM lifecycle_stage_templates
            WHERE object_type = %s AND lifecycle_stage = %s
        """, (obj['object_type'], cur_stage))

        if not tmpl or isinstance(tmpl, dict):
            return jsonify({
                'passed': True, 'stage': cur_stage,
                'message': '该阶段无模板定义，跳过验证'
            })
        tmpl = tmpl[0]
        required = tmpl['required_attributes']
        if isinstance(required, str):
            required = json.loads(required)

        # 检查必填属性
        missing = [attr for attr in required if attr not in snapshot]
        passed = len(missing) == 0
        filled = [attr for attr in required if attr in snapshot]

        return jsonify({
            'passed': passed,
            'stage': cur_stage,
            'object_code': object_code,
            'object_type': obj['object_type'],
            'required_total': len(required),
            'filled': filled,
            'missing': missing,
            'completion_pct': round(len(filled) / max(len(required), 1) * 100, 1),
            'attributes_snapshot': snapshot
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/lifecycle-batch-advance', methods=['POST'])
def api_lifecycle_batch_advance():
    """批量推进多对象到下一阶段"""
    STAGE_ORDER = ['Planning', 'Design', 'Construction', 'Operation']
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True)
        object_codes = data.get('object_codes', [])
        target_stage = data.get('target_stage')
        attrs = data.get('attributes_snapshot', {})
        notes = data.get('notes', '批量推进')

        if not object_codes or not target_stage:
            return jsonify({'success': False, 'error': '缺少 object_codes 或 target_stage'}), 400
        if target_stage not in STAGE_ORDER:
            return jsonify({'success': False, 'error': f'无效阶段: {target_stage}'}), 400

        results = []
        for code in object_codes:
            obj = execute_query(
                "SELECT object_id FROM extracted_objects WHERE object_code = %s", (code,))
            if not obj or isinstance(obj, dict):
                results.append({'object_code': code, 'success': False, 'error': '对象不存在'})
                continue
            oid = obj[0]['object_id']

            # 查当前阶段
            current = execute_query("""
                SELECT lifecycle_stage, history_id FROM object_lifecycle_history
                WHERE object_id = %s ORDER BY stage_entered_at DESC LIMIT 1
            """, (oid,))

            now_str = datetime.now().isoformat()
            if isinstance(current, list) and current:
                cur_stage = current[0]['lifecycle_stage']
                cur_idx = STAGE_ORDER.index(cur_stage) if cur_stage in STAGE_ORDER else -1
                new_idx = STAGE_ORDER.index(target_stage)
                if new_idx > cur_idx + 1:
                    results.append({'object_code': code, 'success': False,
                                   'error': f'不能从 {cur_stage} 跳到 {target_stage}'})
                    continue
                # 关闭当前阶段
                execute_query("""
                    UPDATE object_lifecycle_history SET stage_exited_at = %s
                    WHERE history_id = %s AND stage_exited_at IS NULL
                """, (now_str, current[0]['history_id']), fetch=False)

            attrs_json = json.dumps(attrs, ensure_ascii=False) if attrs else None
            hid = execute_query("""
                INSERT INTO object_lifecycle_history
                (object_id, lifecycle_stage, stage_entered_at, attributes_snapshot, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (oid, target_stage, now_str, attrs_json, notes), fetch=False)
            results.append({'object_code': code, 'success': True, 'history_id': hid, 'stage': target_stage})

        succeeded = sum(1 for r in results if r.get('success'))
        return jsonify({
            'success': True,
            'total': len(object_codes),
            'succeeded': succeeded,
            'failed': len(object_codes) - succeeded,
            'results': results
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Phase 3: 公式链 + EAV 集成 API
# ============================================================================

@olm_api.route('/api/olm/formula-chains')
def api_list_formula_chains():
    """列出公式链（含步骤和关联规则详情）"""
    if not is_db_available():
        return jsonify([])
    try:
        chains = execute_query("SELECT * FROM formula_chains ORDER BY chain_id")
        if isinstance(chains, dict):
            return jsonify([])
        for chain in chains:
            steps = execute_query("""
                SELECT s.step_id, s.step_order, s.rule_id, s.input_mapping,
                       r.rule_code, r.rule_name, r.source_object_code, r.target_object_code,
                       r.rule_category, r.expression, r.relation_type
                FROM formula_chain_steps s
                JOIN object_relation_rules r ON r.rule_id = s.rule_id
                WHERE s.chain_id = %s ORDER BY s.step_order
            """, (chain['chain_id'],))
            if isinstance(steps, dict):
                steps = []
            for st in steps:
                for field in ('expression', 'input_mapping'):
                    if isinstance(st.get(field), str):
                        try:
                            st[field] = json.loads(st[field])
                        except Exception:
                            pass
            chain['steps'] = steps
        return jsonify(chains)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@olm_api.route('/api/olm/formula-chains', methods=['POST'])
def api_create_formula_chain():
    """创建公式链"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True)
        chain_code = data.get('chain_code', '').strip()
        chain_name = data.get('chain_name', '').strip()
        if not chain_code or not chain_name:
            return jsonify({'success': False, 'error': '缺少 chain_code 或 chain_name'}), 400

        chain_id = execute_query("""
            INSERT INTO formula_chains (chain_code, chain_name, description, data_domain)
            VALUES (%s, %s, %s, %s)
        """, (chain_code, chain_name, data.get('description', ''),
              data.get('data_domain', '')), fetch=False)

        # 插入步骤
        steps = data.get('steps', [])
        for step in steps:
            execute_query("""
                INSERT INTO formula_chain_steps (chain_id, step_order, rule_id, input_mapping)
                VALUES (%s, %s, %s, %s)
            """, (chain_id, step.get('step_order', 1), step.get('rule_id'),
                  json.dumps(step.get('input_mapping', {}), ensure_ascii=False)), fetch=False)

        return jsonify({'success': True, 'chain_id': chain_id, 'steps_count': len(steps)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/formula-chains/<int:chain_id>/execute', methods=['POST'])
def api_execute_formula_chain(chain_id):
    """执行公式链（级联求值）"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True) or {}
        variables = data.get('variables', {})

        chain = execute_query("SELECT * FROM formula_chains WHERE chain_id = %s", (chain_id,))
        if not chain or isinstance(chain, dict):
            return jsonify({'success': False, 'error': '公式链不存在'}), 404
        chain = chain[0]

        steps = execute_query("""
            SELECT s.step_order, s.rule_id, s.input_mapping,
                   r.rule_code, r.rule_name, r.rule_category, r.expression,
                   r.source_object_code, r.target_object_code
            FROM formula_chain_steps s
            JOIN object_relation_rules r ON r.rule_id = s.rule_id
            WHERE s.chain_id = %s ORDER BY s.step_order
        """, (chain_id,))
        if isinstance(steps, dict):
            return jsonify({'success': False, 'error': '无法加载链步骤'}), 500

        step_results = []
        carry_vars = dict(variables)  # 级联传递的变量

        for step in steps:
            expr = step['expression']
            if isinstance(expr, str):
                try:
                    expr = json.loads(expr)
                except Exception:
                    expr = {}

            # 执行求值
            result = _evaluate_relation_rule(step['rule_category'], expr, carry_vars)
            result['step_order'] = step['step_order']
            result['rule_code'] = step['rule_code']
            result['rule_name'] = step['rule_name']
            result['source_object'] = step['source_object_code']
            result['target_object'] = step['target_object_code']

            # 将输出传入下一步
            if 'result_value' in result:
                carry_vars[f"step{step['step_order']}_result"] = result['result_value']
            if 'result_name' in result and result.get('result_value') is not None:
                carry_vars[result['result_name']] = result['result_value']

            step_results.append(result)

        alerts_triggered = [r for r in step_results if r.get('triggered')]
        return jsonify({
            'success': True,
            'chain_code': chain['chain_code'],
            'chain_name': chain['chain_name'],
            'steps': step_results,
            'final_variables': carry_vars,
            'alerts_triggered': len(alerts_triggered),
            'total_steps': len(steps)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _evaluate_relation_rule(category, expression, variables):
    """通用关系规则求值引擎"""
    try:
        if category == 'PHYSICAL_FORMULA':
            formula = expression.get('formula', '')
            var_defs = expression.get('variables', {})
            result_name = expression.get('result', '')

            # 简单公式求值
            result_value = None
            if '×' in formula or '*' in formula:
                operands = []
                for var_name in var_defs:
                    val = variables.get(var_name)
                    if val is not None:
                        operands.append(float(val))
                if operands:
                    result_value = 1
                    for op in operands:
                        result_value *= op
            elif '/' in formula and '-' in formula:
                # (a - b) / c pattern
                vals = [variables.get(k) for k in var_defs]
                if all(v is not None for v in vals):
                    vals = [float(v) for v in vals]
                    if len(vals) >= 3 and vals[2] != 0:
                        result_value = (vals[0] - vals[1]) / vals[2]
                    elif len(vals) == 2 and vals[1] != 0:
                        result_value = vals[0] / vals[1]
            elif '²' in formula:
                # I² × R × L pattern
                vals = [float(variables.get(k, 0)) for k in var_defs]
                if len(vals) >= 3:
                    result_value = vals[0] ** 2 * vals[1] * vals[2]

            return {
                'type': 'PHYSICAL_FORMULA',
                'formula': formula,
                'input_values': {k: variables.get(k) for k in var_defs},
                'result_name': result_name.split('(')[0] if result_name else 'result',
                'result_value': round(result_value, 4) if result_value is not None else None,
                'triggered': False
            }

        elif category == 'BUSINESS_RULE':
            condition = expression.get('condition', '')
            then_val = expression.get('then', '')
            else_val = expression.get('else', '')
            trigger = expression.get('trigger', '')

            # 简单条件评估
            triggered = False
            if condition and '>' in condition:
                parts = condition.split('>')
                if len(parts) == 2:
                    field = parts[0].strip()
                    threshold = float(parts[1].strip().replace('万', '0000').replace(',', ''))
                    actual = float(variables.get(field, 0))
                    triggered = actual > threshold

            return {
                'type': 'BUSINESS_RULE',
                'condition': condition or trigger,
                'triggered': triggered,
                'action': then_val if triggered else else_val,
                'result_value': 1 if triggered else 0
            }

        elif category == 'THRESHOLD':
            field = expression.get('field', '')
            operator = expression.get('operator', '>')
            ref_field = expression.get('reference_field', '')
            tolerance = float(expression.get('tolerance', 0))
            actual = float(variables.get(field, 0))
            reference = float(variables.get(ref_field, 0))

            ops = {'>': actual > reference * (1 + tolerance),
                   '<': actual < reference * (1 - tolerance),
                   '>=': actual >= reference, '<=': actual <= reference}
            triggered = ops.get(operator, False)
            pct = round((actual / reference - 1) * 100, 1) if reference else 0

            return {
                'type': 'THRESHOLD',
                'field': field,
                'actual': actual,
                'reference': reference,
                'tolerance': tolerance,
                'triggered': triggered,
                'percent_over': pct,
                'message': expression.get('message', '').replace('{percent}', str(abs(pct))),
                'result_value': actual
            }

        elif category == 'DERIVED_CALC':
            var_defs = expression.get('variables', {})
            result_name = expression.get('result', '')
            vals = [float(variables.get(k, 0)) for k in var_defs]
            result_value = None
            if len(vals) >= 2 and vals[1] != 0:
                result_value = round(vals[0] / vals[1] * 100, 1)
            return {
                'type': 'DERIVED_CALC',
                'formula': expression.get('formula', ''),
                'input_values': {k: variables.get(k) for k in var_defs},
                'result_name': result_name,
                'result_value': result_value,
                'triggered': False
            }

        return {'type': category, 'error': '未知规则类别'}
    except Exception as e:
        return {'type': category, 'error': str(e)}


@olm_api.route('/api/olm/relation-rules/evaluate-with-eav', methods=['POST'])
def api_evaluate_rule_with_eav():
    """用 EAV 真实数据求值关系规则"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True)
        rule_id = data.get('rule_id')
        entity_id = data.get('entity_id')

        rule = execute_query("SELECT * FROM object_relation_rules WHERE rule_id = %s", (rule_id,))
        if not rule or isinstance(rule, dict):
            return jsonify({'success': False, 'error': '规则不存在'}), 404
        rule = rule[0]
        expr = rule['expression']
        if isinstance(expr, str):
            expr = json.loads(expr)

        # 从 EAV 获取变量值
        eav_values = {}
        if entity_id:
            rows = execute_query("""
                SELECT a.attr_name, v.value_text, v.value_number
                FROM eav_values v
                JOIN eav_attributes a ON a.attr_id = v.attr_id
                WHERE v.entity_id = %s
            """, (entity_id,))
            if isinstance(rows, list):
                for row in rows:
                    val = row.get('value_number') if row.get('value_number') is not None else row.get('value_text')
                    eav_values[row['attr_name']] = val

        # 合并手动输入的变量
        manual_vars = data.get('variables', {})
        merged = {**eav_values, **manual_vars}

        result = _evaluate_relation_rule(rule['rule_category'], expr, merged)
        result['rule_code'] = rule['rule_code']
        result['rule_name'] = rule['rule_name']
        result['eav_values'] = eav_values
        result['merged_variables'] = merged

        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/mechanism-functions/<int:func_id>/link-rule', methods=['POST'])
def api_link_mechanism_to_rule(func_id):
    """关联机理函数与关系规则"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True)
        rule_id = data.get('rule_id')
        execute_query(
            "UPDATE mechanism_functions SET linked_rule_id = %s WHERE func_id = %s",
            (rule_id, func_id), fetch=False)
        return jsonify({'success': True, 'func_id': func_id, 'linked_rule_id': rule_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# 对象字段全景端点（Object Fields Panorama）
# ============================================================================

@olm_api.route('/api/olm/object-fields/<object_code>')
def api_object_fields(object_code):
    """获取对象的全部概念层实体（字段列表），按 data_subdomain 分组"""
    if is_db_available():
        try:
            query = """
                SELECT r.entity_name, r.entity_code, r.relation_strength,
                       r.data_subdomain, r.data_domain, r.source_file
                FROM object_entity_relations r
                JOIN extracted_objects o ON o.object_id = r.object_id
                WHERE o.object_code = %s AND r.entity_layer = 'CONCEPT'
                ORDER BY r.data_subdomain, r.entity_name
            """
            rows = execute_query(query, (object_code,))
            if isinstance(rows, list):
                groups = {}
                for r in rows:
                    grp = r.get('data_subdomain') or '其他'
                    if grp not in groups:
                        groups[grp] = []
                    groups[grp].append({
                        'name': r['entity_name'],
                        'code': r.get('entity_code', ''),
                        'strength': float(r.get('relation_strength', 0) or 0),
                        'source_file': r.get('source_file', '')
                    })
                return jsonify({
                    'object_code': object_code,
                    'total_fields': len(rows),
                    'fields_by_group': {k: v for k, v in sorted(groups.items())},
                    'source': 'database'
                })
        except Exception as e:
            print(f"[WARN] 对象字段查询失败: {e}")
    # JSON fallback
    return jsonify({'object_code': object_code, 'total_fields': 0, 'fields_by_group': {}, 'source': 'json_file'})


# ============================================================================
# 字段级血缘关系端点（Field Lineage）
# ============================================================================

@olm_api.route('/api/olm/field-lineage')
def api_field_lineage():
    """列出所有字段血缘关系（支持按 object_code 过滤）"""
    object_code = request.args.get('object_code', '')
    if is_db_available():
        try:
            query = "SELECT * FROM field_lineage WHERE is_active = TRUE"
            params = []
            if object_code:
                query += " AND target_object_code = %s"
                params.append(object_code)
            query += " ORDER BY lineage_code"
            result = execute_query(query, tuple(params) if params else None)
            if isinstance(result, list):
                for row in result:
                    if row.get('expression') and isinstance(row['expression'], str):
                        try:
                            row['expression'] = json.loads(row['expression'])
                        except Exception:
                            pass
                    if row.get('created_at') and hasattr(row['created_at'], 'isoformat'):
                        row['created_at'] = row['created_at'].isoformat()
                return jsonify({'lineage': result, 'total': len(result), 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 字段血缘查询失败: {e}")
    return jsonify({'lineage': [], 'total': 0, 'source': 'json_file'})


@olm_api.route('/api/olm/field-lineage', methods=['POST'])
def api_create_field_lineage():
    """创建字段血缘记录"""
    if not is_db_available():
        return jsonify({'success': False, 'error': '数据库不可用'}), 503
    try:
        data = request.get_json(force=True)
        required = ['lineage_code', 'lineage_name', 'target_object_code', 'target_field_name', 'expression']
        for f in required:
            if f not in data:
                return jsonify({'success': False, 'error': f'缺少必填字段: {f}'}), 400
        expr = data['expression'] if isinstance(data['expression'], str) else json.dumps(data['expression'], ensure_ascii=False)
        execute_query("""
            INSERT INTO field_lineage (lineage_code, lineage_name, target_object_code, target_field_name,
                expression, chain_id, rule_id, description, data_domain)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (data['lineage_code'], data['lineage_name'], data['target_object_code'],
              data['target_field_name'], expr,
              data.get('chain_id'), data.get('rule_id'),
              data.get('description', ''), data.get('data_domain', '')), fetch=False)
        return jsonify({'success': True, 'lineage_code': data['lineage_code']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@olm_api.route('/api/olm/field-lineage/trace/<object_code>/<path:field_name>')
def api_trace_field(object_code, field_name):
    """追踪某个字段的完整血缘链路"""
    if is_db_available():
        try:
            result = execute_query("""
                SELECT fl.*, o.object_name as target_object_name
                FROM field_lineage fl
                LEFT JOIN extracted_objects o ON o.object_code = fl.target_object_code
                WHERE fl.target_object_code = %s AND fl.target_field_name = %s AND fl.is_active = TRUE
            """, (object_code, field_name))
            if isinstance(result, list):
                for row in result:
                    if row.get('expression') and isinstance(row['expression'], str):
                        try:
                            row['expression'] = json.loads(row['expression'])
                        except Exception:
                            pass
                    if row.get('created_at') and hasattr(row['created_at'], 'isoformat'):
                        row['created_at'] = row['created_at'].isoformat()
                return jsonify({'lineage': result, 'object_code': object_code, 'field_name': field_name, 'source': 'database'})
        except Exception as e:
            print(f"[WARN] 字段血缘追踪失败: {e}")
    return jsonify({'lineage': [], 'object_code': object_code, 'field_name': field_name, 'source': 'json_file'})


# ============================================================================
# TP/AP 工作负载统计端点（HTAP 融合可视化）
# ============================================================================

@olm_api.route('/api/olm/workload-stats')
def api_workload_stats():
    """返回 TP/AP 工作负载统计 — 用于 HTAP 融合演示"""
    with _workload_lock:
        tp = _workload_counters['TP']
        ap = _workload_counters['AP']
        total = tp + ap
        return jsonify({
            'success': True,
            'tp_count': tp,
            'ap_count': ap,
            'total_count': total,
            'tp_ratio': round(tp / total * 100, 1) if total > 0 else 0,
            'ap_ratio': round(ap / total * 100, 1) if total > 0 else 0,
            'tp_avg_ms': round(_workload_counters['tp_total_ms'] / tp, 1) if tp > 0 else 0,
            'ap_avg_ms': round(_workload_counters['ap_total_ms'] / ap, 1) if ap > 0 else 0,
            'recent_ops': list(_workload_log),
        })
