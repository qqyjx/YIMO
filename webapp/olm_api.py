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
from flask import Blueprint, request, jsonify, render_template, Response

import pymysql
from pymysql.cursors import DictCursor

# 添加脚本目录到路径
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
sys.path.insert(0, SCRIPT_DIR)

# 创建 Blueprint
olm_api = Blueprint('olm_api', __name__)


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
    """对象抽取与三层架构关联页面"""
    return render_template('object_extraction.html')


# ============================================================================
# 抽取对象管理 API
# ============================================================================

@olm_api.route('/api/olm/extracted-objects')
def api_extracted_objects():
    """获取抽取的对象列表"""
    try:
        result = execute_query("""
            SELECT o.*,
                   (SELECT COUNT(*) FROM object_entity_relations r
                    WHERE r.object_id = o.object_id AND r.entity_layer = 'CONCEPT') as concept_count,
                   (SELECT COUNT(*) FROM object_entity_relations r
                    WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') as logical_count,
                   (SELECT COUNT(*) FROM object_entity_relations r
                    WHERE r.object_id = o.object_id AND r.entity_layer = 'PHYSICAL') as physical_count
            FROM extracted_objects o
            ORDER BY o.object_type, o.object_name
        """)

        if isinstance(result, dict) and 'error' in result:
            return jsonify({'objects': [], 'error': result['error']})

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

        return jsonify({'objects': objects, 'total': len(objects)})
    except Exception as e:
        return jsonify({'objects': [], 'error': str(e)})


@olm_api.route('/api/olm/object-relations/<object_code>')
def api_object_relations(object_code):
    """获取对象与三层架构的关联关系"""
    try:
        # 获取对象ID
        obj_result = execute_query(
            "SELECT object_id FROM extracted_objects WHERE object_code = %s",
            (object_code,)
        )

        if not obj_result or isinstance(obj_result, dict):
            return jsonify({'error': 'Object not found'}), 404

        object_id = obj_result[0]['object_id']

        # 获取各层关联
        concept_result = execute_query("""
            SELECT entity_name, entity_code, relation_strength, data_domain
            FROM object_entity_relations
            WHERE object_id = %s AND entity_layer = 'CONCEPT'
            ORDER BY relation_strength DESC
            LIMIT 50
        """, (object_id,))

        logical_result = execute_query("""
            SELECT entity_name, entity_code, relation_strength, data_domain
            FROM object_entity_relations
            WHERE object_id = %s AND entity_layer = 'LOGICAL'
            ORDER BY relation_strength DESC
            LIMIT 50
        """, (object_id,))

        physical_result = execute_query("""
            SELECT entity_name, entity_code, relation_strength, data_domain
            FROM object_entity_relations
            WHERE object_id = %s AND entity_layer = 'PHYSICAL'
            ORDER BY relation_strength DESC
            LIMIT 50
        """, (object_id,))

        return jsonify({
            'concept': concept_result if not isinstance(concept_result, dict) else [],
            'logical': logical_result if not isinstance(logical_result, dict) else [],
            'physical': physical_result if not isinstance(physical_result, dict) else []
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@olm_api.route('/api/olm/relation-stats')
def api_relation_stats():
    """获取对象关联统计"""
    try:
        result = execute_query("""
            SELECT * FROM v_object_relation_stats
            ORDER BY total_entity_count DESC
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
# 对象抽取执行 API
# ============================================================================

@olm_api.route('/api/olm/run-extraction', methods=['POST'])
def api_run_extraction():
    """执行对象抽取"""
    try:
        data = request.json or {}
        use_llm = data.get('use_llm', False)
        target_clusters = data.get('target_clusters', 15)

        # 导入抽取模块
        from object_extractor import SemanticObjectExtractionPipeline

        # 获取数据目录
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'DATA')

        # 配置数据库
        db_config = {
            'host': os.getenv("MYSQL_HOST", "127.0.0.1"),
            'port': int(os.getenv("MYSQL_PORT", "3307")),
            'user': os.getenv("MYSQL_USER", "eav_user"),
            'password': os.getenv("MYSQL_PASSWORD", "eavpass123"),
            'database': os.getenv("MYSQL_DB", "eav_db")
        }

        # 执行抽取
        pipeline = SemanticObjectExtractionPipeline(
            data_dir=data_dir,
            db_config=db_config,
            target_clusters=target_clusters
        )
        result = pipeline.run(use_llm=use_llm)

        return jsonify({
            'success': True,
            'objects_count': len(result.get('objects', [])),
            'relations_count': result.get('relations_count', 0),
            'clusters': result.get('clusters', [])
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
    """导出抽取的对象和关联关系"""
    try:
        # 获取对象
        objects = execute_query("""
            SELECT * FROM extracted_objects ORDER BY object_type, object_name
        """)

        # 获取关联关系
        relations = execute_query("""
            SELECT o.object_code, r.entity_layer, r.entity_name, r.entity_code,
                   r.relation_type, r.relation_strength, r.data_domain
            FROM object_entity_relations r
            JOIN extracted_objects o ON o.object_id = r.object_id
            ORDER BY o.object_code, r.entity_layer, r.relation_strength DESC
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
            'objects': objects if not isinstance(objects, dict) else [],
            'relations': relations if not isinstance(relations, dict) else []
        }

        return Response(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=extracted_objects.json'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# 对象管理 CRUD API
# ============================================================================

@olm_api.route('/api/olm/objects', methods=['POST'])
def api_create_object():
    """创建新对象"""
    try:
        data = request.json or {}

        object_code = data.get('object_code')
        object_name = data.get('object_name')

        if not object_code or not object_name:
            return jsonify({'error': 'Missing object_code or object_name'}), 400

        sql = """
            INSERT INTO extracted_objects
            (object_code, object_name, object_name_en, object_type, description,
             extraction_source, extraction_confidence, is_verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        result = execute_query(sql, (
            object_code,
            object_name,
            data.get('object_name_en', ''),
            data.get('object_type', 'CORE'),
            data.get('description', ''),
            'MANUAL',
            1.0,
            True
        ), fetch=False)

        if isinstance(result, dict) and 'error' in result:
            return jsonify(result), 500

        return jsonify({'success': True, 'object_id': result})
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
    """获取系统统计信息"""
    try:
        stats = {}

        # 对象统计
        result = execute_query("SELECT COUNT(*) as cnt FROM extracted_objects")
        stats['objects_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

        # 关联关系统计
        result = execute_query("SELECT COUNT(*) as cnt FROM object_entity_relations")
        stats['relations_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

        # 按层级统计关联
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
        result = execute_query("SELECT COUNT(*) as cnt FROM object_extraction_batches")
        stats['batches_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
