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

    result = []
    for idx, obj in enumerate(objects, start=1):
        obj_code = obj.get('object_code', '')
        result.append({
            'object_id': idx,
            'object_code': obj_code,
            'object_name': obj.get('object_name', ''),
            'object_name_en': obj.get('object_name_en', ''),
            'object_type': obj.get('object_type', 'CORE'),
            'data_domain': domain or data.get('data_domain', 'shupeidian'),
            'description': obj.get('description', ''),
            'stats': obj.get('stats') or stats_map.get(obj_code, {'concept': 0, 'logical': 0, 'physical': 0})
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
                        'physical': row.pop('physical_count', 0)
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
