#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对象生命周期管理器 API - Object Lifecycle Manager API
YIMO 对象管理器 Web API 模块

功能：
1. 三层本体管理 API
2. 业务对象管理 API
3. 机理函数调用 API
4. 穿透式查询 API
5. 财务域监管 API
"""

import os
import sys
import json
import uuid
from datetime import datetime
from functools import lru_cache
from flask import Blueprint, request, jsonify, render_template

import pymysql
from pymysql.cursors import DictCursor

# 添加脚本目录到路径
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
sys.path.insert(0, SCRIPT_DIR)

# 导入核心模块
try:
    from mechanism_function_engine import (
        MechanismFunctionEngine,
        BusinessRuleEngine,
        FinanceSupervisionEngine
    )
    MECHANISM_ENGINE_AVAILABLE = True
except ImportError:
    MECHANISM_ENGINE_AVAILABLE = False

try:
    from penetration_query_engine import (
        PenetrationQueryEngine,
        EntityLayer,
        PenetrationDirection
    )
    PENETRATION_ENGINE_AVAILABLE = True
except ImportError:
    PENETRATION_ENGINE_AVAILABLE = False

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

@olm_api.route('/olm')
def olm_page():
    """对象生命周期管理器主页面"""
    return render_template('object_lifecycle_manager.html')

@olm_api.route('/olm/finance')
def olm_finance_page():
    """财务域穿透监管页面"""
    return render_template('finance_supervision.html')

# ============================================================================
# 三层本体 API
# ============================================================================

@olm_api.route('/api/olm/ontology/stats')
def api_ontology_stats():
    """获取三层本体统计信息"""
    stats = {}

    # 概念实体统计
    result = execute_query("SELECT COUNT(*) as cnt FROM ontology_concept_entities")
    stats['concept_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

    # 逻辑实体统计
    result = execute_query("SELECT COUNT(*) as cnt FROM ontology_logical_entities")
    stats['logical_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

    # 物理实体统计
    result = execute_query("SELECT COUNT(*) as cnt FROM ontology_physical_entities")
    stats['physical_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

    # 关联关系统计
    result = execute_query("SELECT COUNT(*) as cnt FROM ontology_layer_relations")
    stats['relation_count'] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

    # 按数据域统计概念实体
    result = execute_query("""
        SELECT data_domain, COUNT(*) as cnt
        FROM ontology_concept_entities
        WHERE data_domain IS NOT NULL
        GROUP BY data_domain
        ORDER BY cnt DESC
        LIMIT 10
    """)
    stats['concept_by_domain'] = result if result and not isinstance(result, dict) else []

    return jsonify(stats)

@olm_api.route('/api/olm/ontology/concept')
def api_ontology_concept():
    """获取概念实体列表"""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    domain = request.args.get('domain')
    search = request.args.get('search')

    sql = "SELECT * FROM ontology_concept_entities WHERE 1=1"
    params = []

    if domain:
        sql += " AND data_domain = %s"
        params.append(domain)

    if search:
        sql += " AND (entity_name LIKE %s OR entity_code LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])

    sql += " ORDER BY is_core DESC, id LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    result = execute_query(sql, tuple(params))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    # 处理日期时间
    for row in result:
        for key in ['created_at', 'updated_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
        # 移除二进制向量
        if 'embedding_vector' in row:
            row['embedding_vector'] = None

    return jsonify({'entities': result, 'count': len(result)})

@olm_api.route('/api/olm/ontology/logical')
def api_ontology_logical():
    """获取逻辑实体列表"""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    concept_code = request.args.get('concept_code')
    search = request.args.get('search')

    sql = "SELECT * FROM ontology_logical_entities WHERE 1=1"
    params = []

    if concept_code:
        sql += " AND concept_entity_code = %s"
        params.append(concept_code)

    if search:
        sql += " AND (entity_name LIKE %s OR entity_code LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])

    sql += " ORDER BY id LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    result = execute_query(sql, tuple(params))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        for key in ['created_at', 'updated_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
        if 'embedding_vector' in row:
            row['embedding_vector'] = None

    return jsonify({'entities': result, 'count': len(result)})

@olm_api.route('/api/olm/ontology/logical/<entity_code>/attributes')
def api_logical_attributes(entity_code):
    """获取逻辑实体的属性列表"""
    result = execute_query("""
        SELECT * FROM ontology_logical_attributes
        WHERE logical_entity_code = %s
        ORDER BY is_primary_key DESC, id
    """, (entity_code,))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    return jsonify({'attributes': result, 'count': len(result)})

@olm_api.route('/api/olm/ontology/physical')
def api_ontology_physical():
    """获取物理实体列表"""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    logical_code = request.args.get('logical_code')
    search = request.args.get('search')

    sql = "SELECT * FROM ontology_physical_entities WHERE 1=1"
    params = []

    if logical_code:
        sql += " AND logical_entity_code = %s"
        params.append(logical_code)

    if search:
        sql += " AND (entity_name LIKE %s OR entity_code LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])

    sql += " ORDER BY id LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    result = execute_query(sql, tuple(params))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        for key in ['created_at', 'updated_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
        if 'embedding_vector' in row:
            row['embedding_vector'] = None

    return jsonify({'entities': result, 'count': len(result)})

@olm_api.route('/api/olm/ontology/relations')
def api_ontology_relations():
    """获取实体间关联关系"""
    source_layer = request.args.get('source_layer')
    source_code = request.args.get('source_code')
    target_layer = request.args.get('target_layer')

    sql = "SELECT * FROM ontology_layer_relations WHERE 1=1"
    params = []

    if source_layer:
        sql += " AND source_layer = %s"
        params.append(source_layer)

    if source_code:
        sql += " AND source_entity_code = %s"
        params.append(source_code)

    if target_layer:
        sql += " AND target_layer = %s"
        params.append(target_layer)

    sql += " ORDER BY relation_strength DESC LIMIT 500"

    result = execute_query(sql, tuple(params))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    return jsonify({'relations': result, 'count': len(result)})

# ============================================================================
# 业务对象 API
# ============================================================================

@olm_api.route('/api/olm/objects')
def api_business_objects():
    """获取业务对象列表"""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    object_type = request.args.get('type')
    search = request.args.get('search')

    sql = "SELECT * FROM business_objects WHERE 1=1"
    params = []

    if object_type:
        sql += " AND object_type = %s"
        params.append(object_type)

    if search:
        sql += " AND (object_name LIKE %s OR object_code LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])

    sql += " ORDER BY is_core_object DESC, id LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    result = execute_query(sql, tuple(params))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        for key in ['created_at', 'updated_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
        # 解析JSON字段
        for json_key in ['data_items', 'business_constraints', 'related_concept_entities', 'related_logical_entities', 'related_physical_entities']:
            if row.get(json_key) and isinstance(row[json_key], str):
                try:
                    row[json_key] = json.loads(row[json_key])
                except:
                    pass
        if 'embedding_vector' in row:
            row['embedding_vector'] = None

    return jsonify({'objects': result, 'count': len(result)})

@olm_api.route('/api/olm/objects/<object_code>')
def api_business_object_detail(object_code):
    """获取业务对象详情"""
    result = execute_query("""
        SELECT * FROM business_objects WHERE object_code = %s
    """, (object_code,))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    if not result:
        return jsonify({'error': 'Object not found'}), 404

    obj = result[0]

    # 解析JSON字段
    for json_key in ['data_items', 'business_constraints', 'related_concept_entities', 'related_logical_entities', 'related_physical_entities']:
        if obj.get(json_key) and isinstance(obj[json_key], str):
            try:
                obj[json_key] = json.loads(obj[json_key])
            except:
                pass

    # 获取关联的实例
    instances = execute_query("""
        SELECT * FROM object_instances WHERE object_code = %s LIMIT 100
    """, (object_code,))

    if not isinstance(instances, dict):
        for inst in instances:
            if inst.get('golden_attributes') and isinstance(inst['golden_attributes'], str):
                try:
                    inst['golden_attributes'] = json.loads(inst['golden_attributes'])
                except:
                    pass
            for key in ['created_at', 'updated_at']:
                if inst.get(key):
                    inst[key] = inst[key].isoformat() if hasattr(inst[key], 'isoformat') else str(inst[key])
        obj['instances'] = instances
    else:
        obj['instances'] = []

    return jsonify(obj)

@olm_api.route('/api/olm/objects/<object_code>/instances')
def api_object_instances(object_code):
    """获取业务对象的实例列表"""
    result = execute_query("""
        SELECT * FROM object_instances WHERE object_code = %s
        ORDER BY current_stage, status LIMIT 500
    """, (object_code,))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        if row.get('golden_attributes') and isinstance(row['golden_attributes'], str):
            try:
                row['golden_attributes'] = json.loads(row['golden_attributes'])
            except:
                pass
        for key in ['created_at', 'updated_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])

    return jsonify({'instances': result, 'count': len(result)})

# ============================================================================
# 业务规则 API
# ============================================================================

@olm_api.route('/api/olm/rules')
def api_business_rules():
    """获取业务规则列表"""
    limit = int(request.args.get('limit', 100))
    rule_type = request.args.get('type')
    is_digitized = request.args.get('digitized')

    sql = "SELECT * FROM business_rules WHERE is_active = 1"
    params = []

    if rule_type:
        sql += " AND rule_type = %s"
        params.append(rule_type)

    if is_digitized is not None:
        sql += " AND is_digitized = %s"
        params.append(1 if is_digitized.lower() == 'true' else 0)

    sql += " ORDER BY id LIMIT %s"
    params.append(limit)

    result = execute_query(sql, tuple(params))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        for json_key in ['rule_details', 'rule_elements', 'supported_processes', 'supported_steps']:
            if row.get(json_key) and isinstance(row[json_key], str):
                try:
                    row[json_key] = json.loads(row[json_key])
                except:
                    pass
        for key in ['created_at', 'updated_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])

    return jsonify({'rules': result, 'count': len(result)})

# ============================================================================
# 机理函数 API
# ============================================================================

@olm_api.route('/api/olm/functions')
def api_mechanism_functions():
    """获取机理函数列表"""
    if not MECHANISM_ENGINE_AVAILABLE:
        return jsonify({'error': 'Mechanism engine not available', 'functions': []})

    engine = MechanismFunctionEngine()
    functions = engine.get_formula_list()

    return jsonify({'functions': functions, 'count': len(functions)})

@olm_api.route('/api/olm/functions/execute', methods=['POST'])
def api_execute_function():
    """执行机理函数"""
    if not MECHANISM_ENGINE_AVAILABLE:
        return jsonify({'error': 'Mechanism engine not available'}), 503

    data = request.json or {}
    function_code = data.get('code')
    parameters = data.get('parameters', {})

    if not function_code:
        return jsonify({'error': 'Missing function code'}), 400

    engine = MechanismFunctionEngine()
    result = engine.execute_formula(function_code, parameters)

    return jsonify({
        'success': result.success,
        'result': result.result,
        'message': result.message,
        'execution_time_ms': result.execution_time_ms
    })

@olm_api.route('/api/olm/functions/expression', methods=['POST'])
def api_evaluate_expression():
    """执行数学表达式"""
    if not MECHANISM_ENGINE_AVAILABLE:
        return jsonify({'error': 'Mechanism engine not available'}), 503

    data = request.json or {}
    expression = data.get('expression')
    variables = data.get('variables', {})

    if not expression:
        return jsonify({'error': 'Missing expression'}), 400

    engine = MechanismFunctionEngine()
    result = engine.execute_expression(expression, variables)

    return jsonify({
        'success': result.success,
        'result': result.result,
        'message': result.message,
        'execution_time_ms': result.execution_time_ms
    })

# ============================================================================
# 穿透式查询 API
# ============================================================================

@olm_api.route('/api/olm/penetration/up', methods=['POST'])
def api_penetration_up():
    """向上穿透查询"""
    if not PENETRATION_ENGINE_AVAILABLE:
        return jsonify({'error': 'Penetration engine not available'}), 503

    data = request.json or {}
    layer = data.get('layer')
    entity_code = data.get('entity_code')

    if not layer or not entity_code:
        return jsonify({'error': 'Missing layer or entity_code'}), 400

    try:
        conn = get_conn()
        engine = PenetrationQueryEngine(conn)
        layer_enum = EntityLayer(layer)
        result = engine.trace_up(layer_enum, entity_code)
        conn.close()

        return jsonify(engine.result_to_dict(result))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@olm_api.route('/api/olm/penetration/down', methods=['POST'])
def api_penetration_down():
    """向下穿透查询"""
    if not PENETRATION_ENGINE_AVAILABLE:
        return jsonify({'error': 'Penetration engine not available'}), 503

    data = request.json or {}
    layer = data.get('layer')
    entity_code = data.get('entity_code')

    if not layer or not entity_code:
        return jsonify({'error': 'Missing layer or entity_code'}), 400

    try:
        conn = get_conn()
        engine = PenetrationQueryEngine(conn)
        layer_enum = EntityLayer(layer)
        result = engine.trace_down(layer_enum, entity_code)
        conn.close()

        return jsonify(engine.result_to_dict(result))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@olm_api.route('/api/olm/penetration/horizontal', methods=['POST'])
def api_penetration_horizontal():
    """水平穿透查询（跨生命周期阶段）"""
    if not PENETRATION_ENGINE_AVAILABLE:
        return jsonify({'error': 'Penetration engine not available'}), 503

    data = request.json or {}
    object_code = data.get('object_code')

    if not object_code:
        return jsonify({'error': 'Missing object_code'}), 400

    try:
        conn = get_conn()
        engine = PenetrationQueryEngine(conn)
        result = engine.trace_horizontal(object_code)
        conn.close()

        return jsonify(engine.result_to_dict(result))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@olm_api.route('/api/olm/penetration/full', methods=['POST'])
def api_penetration_full():
    """全链路穿透查询"""
    if not PENETRATION_ENGINE_AVAILABLE:
        return jsonify({'error': 'Penetration engine not available'}), 503

    data = request.json or {}
    settlement_uid = data.get('settlement_uid')

    if not settlement_uid:
        return jsonify({'error': 'Missing settlement_uid'}), 400

    try:
        conn = get_conn()
        engine = PenetrationQueryEngine(conn)
        result = engine.trace_full_chain(settlement_uid)
        conn.close()

        return jsonify(engine.result_to_dict(result))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# 财务域监管 API
# ============================================================================

@olm_api.route('/api/olm/finance/redlines')
def api_finance_redlines():
    """获取财务审计红线列表"""
    result = execute_query("""
        SELECT * FROM finance_audit_redlines WHERE is_active = 1
        ORDER BY severity DESC, id
    """)

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        for json_key in ['applicable_objects', 'trigger_action', 'threshold_range']:
            if row.get(json_key) and isinstance(row[json_key], str):
                try:
                    row[json_key] = json.loads(row[json_key])
                except:
                    pass

    return jsonify({'redlines': result, 'count': len(result)})

@olm_api.route('/api/olm/finance/check-redline', methods=['POST'])
def api_check_redline():
    """检查财务审计红线"""
    if not MECHANISM_ENGINE_AVAILABLE:
        return jsonify({'error': 'Mechanism engine not available'}), 503

    data = request.json or {}
    redline_code = data.get('redline_code')
    value = data.get('value')

    if not redline_code or value is None:
        return jsonify({'error': 'Missing redline_code or value'}), 400

    try:
        conn = get_conn()
        engine = BusinessRuleEngine(conn)
        engine.load_redlines_from_db()
        result = engine.check_redline(redline_code, value)
        conn.close()

        return jsonify({
            'rule_code': result.rule_code,
            'status': result.status.value,
            'message': result.message,
            'current_value': result.current_value,
            'expected_value': result.expected_value,
            'triggered_actions': result.triggered_actions
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@olm_api.route('/api/olm/finance/validate-settlement', methods=['POST'])
def api_validate_settlement():
    """验证财务结算单据"""
    if not MECHANISM_ENGINE_AVAILABLE:
        return jsonify({'error': 'Mechanism engine not available'}), 503

    data = request.json or {}

    try:
        conn = get_conn()
        engine = FinanceSupervisionEngine(conn)
        result = engine.validate_settlement(data)
        conn.close()

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@olm_api.route('/api/olm/finance/alerts')
def api_finance_alerts():
    """获取财务预警列表"""
    status = request.args.get('status', 'open')
    limit = int(request.args.get('limit', 100))

    sql = """
        SELECT * FROM finance_alerts
        WHERE status = %s
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'error' THEN 2
                WHEN 'warning' THEN 3
                ELSE 4
            END,
            created_at DESC
        LIMIT %s
    """
    result = execute_query(sql, (status, limit))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        if row.get('trace_info') and isinstance(row['trace_info'], str):
            try:
                row['trace_info'] = json.loads(row['trace_info'])
            except:
                pass
        for key in ['created_at', 'handled_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])

    return jsonify({'alerts': result, 'count': len(result)})

@olm_api.route('/api/olm/finance/settlements')
def api_finance_settlements():
    """获取财务结算追溯列表"""
    limit = int(request.args.get('limit', 100))
    status = request.args.get('status')

    sql = "SELECT * FROM finance_settlement_traces WHERE 1=1"
    params = []

    if status:
        sql += " AND validation_status = %s"
        params.append(status)

    sql += " ORDER BY settlement_date DESC LIMIT %s"
    params.append(limit)

    result = execute_query(sql, tuple(params))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    for row in result:
        for json_key in ['trace_chain', 'validation_details']:
            if row.get(json_key) and isinstance(row[json_key], str):
                try:
                    row[json_key] = json.loads(row[json_key])
                except:
                    pass
        for key in ['settlement_date', 'created_at', 'updated_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])

    return jsonify({'settlements': result, 'count': len(result)})

# ============================================================================
# 时态属性 API
# ============================================================================

@olm_api.route('/api/olm/temporal/<instance_uid>')
def api_temporal_attributes(instance_uid):
    """获取对象实例的时态属性"""
    result = execute_query("""
        SELECT * FROM object_temporal_attributes
        WHERE instance_uid = %s
        ORDER BY lifecycle_stage, attribute_name, effective_from DESC
    """, (instance_uid,))

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    # 按阶段组织
    stages = {}
    for row in result:
        stage = row['lifecycle_stage']
        if stage not in stages:
            stages[stage] = []

        for key in ['effective_from', 'effective_to', 'value_datetime', 'created_at']:
            if row.get(key):
                row[key] = row[key].isoformat() if hasattr(row[key], 'isoformat') else str(row[key])
        if row.get('value_json') and isinstance(row['value_json'], str):
            try:
                row['value_json'] = json.loads(row['value_json'])
            except:
                pass

        stages[stage].append(row)

    return jsonify({'instance_uid': instance_uid, 'stages': stages})

# ============================================================================
# 导入/同步 API
# ============================================================================

@olm_api.route('/api/olm/import/status')
def api_import_status():
    """获取数据导入状态"""
    stats = {}

    tables = [
        ('ontology_concept_entities', 'concept'),
        ('ontology_logical_entities', 'logical'),
        ('ontology_physical_entities', 'physical'),
        ('business_objects', 'objects'),
        ('business_rules', 'rules'),
        ('object_instances', 'instances')
    ]

    for table, key in tables:
        result = execute_query(f"SELECT COUNT(*) as cnt FROM {table}")
        stats[key] = result[0]['cnt'] if result and not isinstance(result, dict) else 0

    return jsonify(stats)
