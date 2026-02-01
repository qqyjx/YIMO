#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
穿透式查询引擎 - Penetration Query Engine
YIMO 对象生命周期管理器核心模块

功能：
1. 垂直穿透：从业务场景追溯到底层物理数据
2. 水平穿透：跨阶段追溯同一对象的演变
3. 斜向穿透：结合垂直和水平的复合查询
4. 全链路追溯：完整的业务追溯链
5. 财务域穿透监管：结算追溯到业务源头
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque

# 数据库连接
try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None

# SBERT语义匹配（复用现有模块）
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    SBERT_AVAILABLE = True
except ImportError:
    SBERT_AVAILABLE = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# 枚举和数据类
# ============================================================================

class EntityLayer(Enum):
    """实体层级"""
    CONCEPT = "concept"       # 概念实体（业务场景）
    LOGICAL = "logical"       # 逻辑实体（交互表单）
    PHYSICAL = "physical"     # 物理实体（客观实体）
    OBJECT = "object"         # 业务对象
    INSTANCE = "instance"     # 对象实例

class PenetrationDirection(Enum):
    """穿透方向"""
    UP = "up"                 # 向上穿透（物理→逻辑→概念）
    DOWN = "down"             # 向下穿透（概念→逻辑→物理）
    HORIZONTAL = "horizontal" # 水平穿透（同层级跨阶段）
    FULL = "full"             # 全链路

class LifecycleStage(Enum):
    """生命周期阶段"""
    PLANNING = "Planning"
    DESIGN = "Design"
    CONSTRUCTION = "Construction"
    OPERATION = "Operation"
    FINANCE = "Finance"

@dataclass
class PenetrationNode:
    """穿透节点"""
    layer: EntityLayer
    entity_code: str
    entity_name: str
    stage: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    source_reference: Optional[str] = None
    depth: int = 0

@dataclass
class PenetrationPath:
    """穿透路径"""
    nodes: List[PenetrationNode] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    total_depth: int = 0

@dataclass
class PenetrationResult:
    """穿透查询结果"""
    query_uid: str
    query_type: str
    start_layer: EntityLayer
    start_entity: str
    end_layer: Optional[EntityLayer] = None
    paths: List[PenetrationPath] = field(default_factory=list)
    result_count: int = 0
    execution_time_ms: int = 0
    summary: Dict[str, Any] = field(default_factory=dict)

# ============================================================================
# 穿透式查询引擎
# ============================================================================

class PenetrationQueryEngine:
    """穿透式查询引擎"""

    # 层级顺序（从上到下）
    LAYER_ORDER = [
        EntityLayer.CONCEPT,
        EntityLayer.LOGICAL,
        EntityLayer.PHYSICAL
    ]

    # 层级对应的表名
    LAYER_TABLES = {
        EntityLayer.CONCEPT: 'ontology_concept_entities',
        EntityLayer.LOGICAL: 'ontology_logical_entities',
        EntityLayer.PHYSICAL: 'ontology_physical_entities',
        EntityLayer.OBJECT: 'business_objects',
        EntityLayer.INSTANCE: 'object_instances'
    }

    def __init__(self, db_connection=None, encoder=None):
        self.db = db_connection
        self.encoder = encoder
        self.query_cache = {}

    def _get_cursor(self):
        """获取数据库游标"""
        if self.db:
            return self.db.cursor(dictionary=True)
        return None

    def _execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        """执行查询"""
        cursor = self._get_cursor()
        if not cursor:
            return []

        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            return []
        finally:
            cursor.close()

    # ========================================================================
    # 垂直穿透
    # ========================================================================

    def trace_up(
        self,
        start_layer: EntityLayer,
        entity_code: str,
        max_depth: int = 10
    ) -> PenetrationResult:
        """
        向上穿透：从底层追溯到上层
        例：物理实体 -> 逻辑实体 -> 概念实体
        """
        start_time = datetime.now()
        query_uid = str(uuid.uuid4())

        result = PenetrationResult(
            query_uid=query_uid,
            query_type="trace_up",
            start_layer=start_layer,
            start_entity=entity_code
        )

        # 获取起始实体
        start_node = self._get_entity_node(start_layer, entity_code)
        if not start_node:
            result.summary = {'error': f'未找到实体: {entity_code}'}
            return result

        # 使用BFS向上穿透
        visited = set()
        queue = deque([(start_node, [start_node])])
        all_paths = []

        while queue and len(all_paths) < 100:  # 限制路径数量
            current_node, current_path = queue.popleft()

            if current_node.entity_code in visited:
                continue
            visited.add(current_node.entity_code)

            # 如果到达概念层，记录路径
            if current_node.layer == EntityLayer.CONCEPT:
                path = PenetrationPath(
                    nodes=current_path,
                    total_depth=len(current_path)
                )
                all_paths.append(path)
                continue

            # 查找上层关联
            upper_nodes = self._find_upper_relations(current_node)
            for upper_node in upper_nodes:
                if upper_node.entity_code not in visited:
                    new_path = current_path + [upper_node]
                    queue.append((upper_node, new_path))

        result.paths = all_paths
        result.result_count = len(all_paths)
        result.end_layer = EntityLayer.CONCEPT
        result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # 生成摘要
        result.summary = {
            'start_entity': start_node.entity_name,
            'total_paths': len(all_paths),
            'max_depth': max(p.total_depth for p in all_paths) if all_paths else 0,
            'concept_entities': list(set(
                p.nodes[-1].entity_name for p in all_paths if p.nodes
            ))
        }

        return result

    def trace_down(
        self,
        start_layer: EntityLayer,
        entity_code: str,
        max_depth: int = 10
    ) -> PenetrationResult:
        """
        向下穿透：从上层追溯到底层
        例：概念实体 -> 逻辑实体 -> 物理实体
        """
        start_time = datetime.now()
        query_uid = str(uuid.uuid4())

        result = PenetrationResult(
            query_uid=query_uid,
            query_type="trace_down",
            start_layer=start_layer,
            start_entity=entity_code
        )

        # 获取起始实体
        start_node = self._get_entity_node(start_layer, entity_code)
        if not start_node:
            result.summary = {'error': f'未找到实体: {entity_code}'}
            return result

        # 使用BFS向下穿透
        visited = set()
        queue = deque([(start_node, [start_node])])
        all_paths = []

        while queue and len(all_paths) < 100:
            current_node, current_path = queue.popleft()

            if current_node.entity_code in visited:
                continue
            visited.add(current_node.entity_code)

            # 如果到达物理层，记录路径
            if current_node.layer == EntityLayer.PHYSICAL:
                path = PenetrationPath(
                    nodes=current_path,
                    total_depth=len(current_path)
                )
                all_paths.append(path)
                continue

            # 查找下层关联
            lower_nodes = self._find_lower_relations(current_node)
            for lower_node in lower_nodes:
                if lower_node.entity_code not in visited:
                    new_path = current_path + [lower_node]
                    queue.append((lower_node, new_path))

        result.paths = all_paths
        result.result_count = len(all_paths)
        result.end_layer = EntityLayer.PHYSICAL
        result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # 生成摘要
        result.summary = {
            'start_entity': start_node.entity_name,
            'total_paths': len(all_paths),
            'max_depth': max(p.total_depth for p in all_paths) if all_paths else 0,
            'physical_entities': list(set(
                p.nodes[-1].entity_name for p in all_paths if p.nodes
            ))
        }

        return result

    # ========================================================================
    # 水平穿透（跨生命周期阶段）
    # ========================================================================

    def trace_horizontal(
        self,
        object_code: str,
        from_stage: Optional[str] = None,
        to_stage: Optional[str] = None
    ) -> PenetrationResult:
        """
        水平穿透：追溯同一对象在不同生命周期阶段的演变
        """
        start_time = datetime.now()
        query_uid = str(uuid.uuid4())

        result = PenetrationResult(
            query_uid=query_uid,
            query_type="trace_horizontal",
            start_layer=EntityLayer.OBJECT,
            start_entity=object_code
        )

        # 查询对象实例及其时态属性
        sql = """
            SELECT oi.instance_uid, oi.instance_name, oi.current_stage,
                   oi.golden_attributes, oi.global_asset_uid,
                   ota.lifecycle_stage, ota.attribute_name, ota.attribute_value,
                   ota.effective_from, ota.effective_to
            FROM object_instances oi
            LEFT JOIN object_temporal_attributes ota ON oi.instance_uid = ota.instance_uid
            WHERE oi.object_code = %s
            ORDER BY ota.lifecycle_stage, ota.effective_from
        """
        rows = self._execute_query(sql, (object_code,))

        if not rows:
            result.summary = {'error': f'未找到对象实例: {object_code}'}
            return result

        # 按实例和阶段组织数据
        stage_data = {}
        instances = {}

        for row in rows:
            instance_uid = row['instance_uid']
            stage = row.get('lifecycle_stage') or row.get('current_stage')

            if instance_uid not in instances:
                instances[instance_uid] = {
                    'instance_uid': instance_uid,
                    'instance_name': row['instance_name'],
                    'current_stage': row['current_stage'],
                    'global_asset_uid': row['global_asset_uid']
                }

            if stage:
                if stage not in stage_data:
                    stage_data[stage] = []

                if row.get('attribute_name'):
                    stage_data[stage].append({
                        'instance_uid': instance_uid,
                        'attribute_name': row['attribute_name'],
                        'attribute_value': row['attribute_value'],
                        'effective_from': str(row['effective_from']) if row.get('effective_from') else None,
                        'effective_to': str(row['effective_to']) if row.get('effective_to') else None
                    })

        # 构建生命周期路径
        stage_order = ['Planning', 'Design', 'Construction', 'Operation', 'Finance']
        lifecycle_path = []

        for stage in stage_order:
            if stage in stage_data or (from_stage and to_stage):
                node = PenetrationNode(
                    layer=EntityLayer.INSTANCE,
                    entity_code=object_code,
                    entity_name=f"{object_code}@{stage}",
                    stage=stage,
                    attributes={'temporal_data': stage_data.get(stage, [])}
                )
                lifecycle_path.append(node)

        if lifecycle_path:
            path = PenetrationPath(
                nodes=lifecycle_path,
                total_depth=len(lifecycle_path)
            )
            result.paths = [path]
            result.result_count = 1

        result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        result.summary = {
            'object_code': object_code,
            'instances': list(instances.values()),
            'stages_found': list(stage_data.keys()),
            'total_attributes': sum(len(v) for v in stage_data.values())
        }

        return result

    # ========================================================================
    # 全链路穿透（财务域应用）
    # ========================================================================

    def trace_full_chain(
        self,
        settlement_uid: str
    ) -> PenetrationResult:
        """
        全链路穿透：从财务结算单据追溯到完整业务链
        财务结算 -> 项目 -> 合同 -> 采购 -> 施工 -> 资产
        """
        start_time = datetime.now()
        query_uid = str(uuid.uuid4())

        result = PenetrationResult(
            query_uid=query_uid,
            query_type="full_chain",
            start_layer=EntityLayer.INSTANCE,
            start_entity=settlement_uid
        )

        # 查询结算追溯记录
        sql = """
            SELECT * FROM finance_settlement_traces
            WHERE settlement_uid = %s
        """
        traces = self._execute_query(sql, (settlement_uid,))

        if not traces:
            # 如果没有预先建立的追溯记录，尝试动态构建
            result.summary = {'warning': '无预建追溯链，尝试动态构建'}
            return self._build_dynamic_trace_chain(settlement_uid, result)

        trace = traces[0]

        # 构建追溯链节点
        chain_nodes = []

        # 1. 财务结算节点
        settlement_node = PenetrationNode(
            layer=EntityLayer.INSTANCE,
            entity_code=settlement_uid,
            entity_name=f"结算单据 {settlement_uid[:8]}",
            stage="Finance",
            attributes={
                'settlement_type': trace.get('settlement_type'),
                'settlement_amount': float(trace['settlement_amount']) if trace.get('settlement_amount') else 0,
                'settlement_date': str(trace['settlement_date']) if trace.get('settlement_date') else None
            },
            depth=0
        )
        chain_nodes.append(settlement_node)

        # 2. 项目节点
        if trace.get('project_instance_uid'):
            project_node = PenetrationNode(
                layer=EntityLayer.INSTANCE,
                entity_code=trace['project_instance_uid'],
                entity_name=f"项目 {trace['project_instance_uid'][:8]}",
                stage="Planning",
                source_reference=trace.get('feasibility_reference'),
                depth=1
            )
            chain_nodes.append(project_node)

        # 3. 合同节点
        if trace.get('contract_instance_uid'):
            contract_node = PenetrationNode(
                layer=EntityLayer.INSTANCE,
                entity_code=trace['contract_instance_uid'],
                entity_name=f"合同 {trace['contract_instance_uid'][:8]}",
                stage="Construction",
                source_reference=trace.get('procurement_reference'),
                depth=2
            )
            chain_nodes.append(contract_node)

        # 4. 资产节点
        if trace.get('asset_instance_uid'):
            asset_node = PenetrationNode(
                layer=EntityLayer.INSTANCE,
                entity_code=trace['asset_instance_uid'],
                entity_name=f"资产 {trace['asset_instance_uid'][:8]}",
                stage="Operation",
                source_reference=trace.get('construction_reference'),
                depth=3
            )
            chain_nodes.append(asset_node)

        # 构建路径
        path = PenetrationPath(
            nodes=chain_nodes,
            total_depth=len(chain_nodes),
            relations=json.loads(trace['trace_chain']) if trace.get('trace_chain') else []
        )

        result.paths = [path]
        result.result_count = 1
        result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        result.summary = {
            'settlement_uid': settlement_uid,
            'settlement_amount': float(trace['settlement_amount']) if trace.get('settlement_amount') else 0,
            'chain_length': len(chain_nodes),
            'validation_status': trace.get('validation_status', 'pending'),
            'linked_entities': {
                'project': trace.get('project_instance_uid'),
                'contract': trace.get('contract_instance_uid'),
                'asset': trace.get('asset_instance_uid')
            }
        }

        return result

    def _build_dynamic_trace_chain(
        self,
        settlement_uid: str,
        result: PenetrationResult
    ) -> PenetrationResult:
        """动态构建追溯链（当没有预建链时）"""
        # 尝试从对象实例表查找关联
        sql = """
            SELECT * FROM object_instances
            WHERE instance_uid = %s OR external_ids LIKE %s
        """
        instances = self._execute_query(sql, (settlement_uid, f'%{settlement_uid}%'))

        if instances:
            instance = instances[0]
            # 简单构建一个单节点路径
            node = PenetrationNode(
                layer=EntityLayer.INSTANCE,
                entity_code=instance['instance_uid'],
                entity_name=instance.get('instance_name', settlement_uid),
                stage=instance.get('current_stage'),
                attributes=json.loads(instance['golden_attributes']) if instance.get('golden_attributes') else {}
            )
            path = PenetrationPath(nodes=[node], total_depth=1)
            result.paths = [path]
            result.result_count = 1

        result.summary['dynamic_build'] = True
        return result

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _get_entity_node(
        self,
        layer: EntityLayer,
        entity_code: str
    ) -> Optional[PenetrationNode]:
        """获取实体节点"""
        table_name = self.LAYER_TABLES.get(layer)
        if not table_name:
            return None

        sql = f"SELECT * FROM {table_name} WHERE entity_code = %s LIMIT 1"
        rows = self._execute_query(sql, (entity_code,))

        if not rows:
            return None

        row = rows[0]
        return PenetrationNode(
            layer=layer,
            entity_code=entity_code,
            entity_name=row.get('entity_name', entity_code),
            attributes={k: v for k, v in row.items() if k not in ['id', 'created_at', 'updated_at', 'embedding_vector']}
        )

    def _find_upper_relations(self, node: PenetrationNode) -> List[PenetrationNode]:
        """查找上层关联实体"""
        upper_nodes = []

        if node.layer == EntityLayer.PHYSICAL:
            # 物理 -> 逻辑
            logical_code = node.attributes.get('logical_entity_code')
            if logical_code:
                upper_node = self._get_entity_node(EntityLayer.LOGICAL, logical_code)
                if upper_node:
                    upper_nodes.append(upper_node)

            # 通过关系表查找
            sql = """
                SELECT target_entity_code FROM ontology_layer_relations
                WHERE source_layer = 'physical' AND source_entity_code = %s
                  AND target_layer = 'logical'
            """
            rows = self._execute_query(sql, (node.entity_code,))
            for row in rows:
                upper_node = self._get_entity_node(EntityLayer.LOGICAL, row['target_entity_code'])
                if upper_node and upper_node.entity_code not in [n.entity_code for n in upper_nodes]:
                    upper_nodes.append(upper_node)

        elif node.layer == EntityLayer.LOGICAL:
            # 逻辑 -> 概念
            concept_code = node.attributes.get('concept_entity_code')
            if concept_code:
                upper_node = self._get_entity_node(EntityLayer.CONCEPT, concept_code)
                if upper_node:
                    upper_nodes.append(upper_node)

            # 通过关系表查找
            sql = """
                SELECT target_entity_code FROM ontology_layer_relations
                WHERE source_layer = 'logical' AND source_entity_code = %s
                  AND target_layer = 'concept'
            """
            rows = self._execute_query(sql, (node.entity_code,))
            for row in rows:
                upper_node = self._get_entity_node(EntityLayer.CONCEPT, row['target_entity_code'])
                if upper_node and upper_node.entity_code not in [n.entity_code for n in upper_nodes]:
                    upper_nodes.append(upper_node)

        return upper_nodes

    def _find_lower_relations(self, node: PenetrationNode) -> List[PenetrationNode]:
        """查找下层关联实体"""
        lower_nodes = []

        if node.layer == EntityLayer.CONCEPT:
            # 概念 -> 逻辑
            sql = """
                SELECT entity_code, entity_name FROM ontology_logical_entities
                WHERE concept_entity_code = %s
            """
            rows = self._execute_query(sql, (node.entity_code,))
            for row in rows:
                lower_node = self._get_entity_node(EntityLayer.LOGICAL, row['entity_code'])
                if lower_node:
                    lower_nodes.append(lower_node)

        elif node.layer == EntityLayer.LOGICAL:
            # 逻辑 -> 物理
            sql = """
                SELECT entity_code, entity_name FROM ontology_physical_entities
                WHERE logical_entity_code = %s
            """
            rows = self._execute_query(sql, (node.entity_code,))
            for row in rows:
                lower_node = self._get_entity_node(EntityLayer.PHYSICAL, row['entity_code'])
                if lower_node:
                    lower_nodes.append(lower_node)

        return lower_nodes

    # ========================================================================
    # 语义穿透（结合SBERT）
    # ========================================================================

    def semantic_trace(
        self,
        query_text: str,
        target_layer: EntityLayer = None,
        top_k: int = 5,
        threshold: float = 0.5
    ) -> PenetrationResult:
        """
        语义穿透：基于语义相似度查找关联实体
        """
        start_time = datetime.now()
        query_uid = str(uuid.uuid4())

        result = PenetrationResult(
            query_uid=query_uid,
            query_type="semantic_trace",
            start_layer=EntityLayer.CONCEPT,
            start_entity=query_text[:50]
        )

        if not self.encoder:
            result.summary = {'error': 'SBERT编码器不可用'}
            return result

        try:
            # 编码查询文本
            query_embedding = self.encoder.encode(query_text)
            if isinstance(query_embedding, list):
                query_embedding = query_embedding[0]

            # 在各层级搜索
            all_matches = []
            layers_to_search = [target_layer] if target_layer else [
                EntityLayer.CONCEPT, EntityLayer.LOGICAL, EntityLayer.PHYSICAL
            ]

            for layer in layers_to_search:
                table_name = self.LAYER_TABLES.get(layer)
                if not table_name:
                    continue

                # 获取所有实体的向量
                sql = f"""
                    SELECT entity_code, entity_name, embedding_vector
                    FROM {table_name}
                    WHERE embedding_vector IS NOT NULL
                    LIMIT 1000
                """
                rows = self._execute_query(sql)

                for row in rows:
                    if row.get('embedding_vector'):
                        try:
                            import numpy as np
                            entity_embedding = np.frombuffer(row['embedding_vector'], dtype=np.float32)

                            # 计算余弦相似度
                            similarity = np.dot(query_embedding, entity_embedding) / (
                                np.linalg.norm(query_embedding) * np.linalg.norm(entity_embedding) + 1e-8
                            )

                            if similarity >= threshold:
                                all_matches.append({
                                    'layer': layer,
                                    'entity_code': row['entity_code'],
                                    'entity_name': row['entity_name'],
                                    'similarity': float(similarity)
                                })
                        except Exception as e:
                            logger.warning(f"向量计算失败: {e}")

            # 按相似度排序
            all_matches.sort(key=lambda x: x['similarity'], reverse=True)
            top_matches = all_matches[:top_k]

            # 构建路径
            for match in top_matches:
                node = PenetrationNode(
                    layer=match['layer'],
                    entity_code=match['entity_code'],
                    entity_name=match['entity_name'],
                    attributes={'similarity': match['similarity']}
                )
                path = PenetrationPath(nodes=[node], total_depth=1)
                result.paths.append(path)

            result.result_count = len(result.paths)
            result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            result.summary = {
                'query_text': query_text[:100],
                'matches_found': len(all_matches),
                'top_matches': top_matches
            }

        except Exception as e:
            logger.error(f"语义穿透失败: {e}")
            result.summary = {'error': str(e)}

        return result

    # ========================================================================
    # 记录查询日志
    # ========================================================================

    def log_query(self, result: PenetrationResult, queried_by: str = None):
        """记录穿透查询日志"""
        if not self.db:
            return

        try:
            cursor = self.db.cursor()
            sql = """
                INSERT INTO penetration_queries
                (query_uid, query_type, start_layer, start_entity_id,
                 end_layer, result_count, result_summary,
                 execution_time_ms, queried_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                result.query_uid,
                result.query_type,
                result.start_layer.value if result.start_layer else None,
                result.start_entity,
                result.end_layer.value if result.end_layer else None,
                result.result_count,
                json.dumps(result.summary, ensure_ascii=False, default=str),
                result.execution_time_ms,
                queried_by
            ))
            self.db.commit()
            cursor.close()
            logger.info(f"穿透查询已记录: {result.query_uid}")

        except Exception as e:
            logger.error(f"记录查询日志失败: {e}")

    # ========================================================================
    # 结果序列化
    # ========================================================================

    def result_to_dict(self, result: PenetrationResult) -> Dict:
        """将结果转换为字典"""
        return {
            'query_uid': result.query_uid,
            'query_type': result.query_type,
            'start_layer': result.start_layer.value if result.start_layer else None,
            'start_entity': result.start_entity,
            'end_layer': result.end_layer.value if result.end_layer else None,
            'result_count': result.result_count,
            'execution_time_ms': result.execution_time_ms,
            'summary': result.summary,
            'paths': [
                {
                    'nodes': [
                        {
                            'layer': n.layer.value,
                            'entity_code': n.entity_code,
                            'entity_name': n.entity_name,
                            'stage': n.stage,
                            'depth': n.depth
                        }
                        for n in path.nodes
                    ],
                    'total_depth': path.total_depth
                }
                for path in result.paths
            ]
        }

# ============================================================================
# 主入口
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='穿透式查询引擎')
    parser.add_argument('--action', choices=['up', 'down', 'horizontal', 'full', 'semantic'],
                       required=True, help='穿透类型')
    parser.add_argument('--entity', type=str, help='起始实体编码')
    parser.add_argument('--layer', choices=['concept', 'logical', 'physical'],
                       help='起始层级')
    parser.add_argument('--query', type=str, help='语义查询文本')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='MySQL主机')
    parser.add_argument('--port', type=int, default=3307, help='MySQL端口')
    parser.add_argument('--user', type=str, default='eav_user', help='MySQL用户')
    parser.add_argument('--password', type=str, default='eavpass123', help='MySQL密码')
    parser.add_argument('--database', type=str, default='eav_db', help='MySQL数据库')

    args = parser.parse_args()

    # 连接数据库
    try:
        db = mysql.connector.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database
        )
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        db = None

    # 初始化引擎
    engine = PenetrationQueryEngine(db)

    # 执行查询
    if args.action == 'up':
        if not args.entity or not args.layer:
            print("向上穿透需要 --entity 和 --layer 参数")
            return
        layer = EntityLayer(args.layer)
        result = engine.trace_up(layer, args.entity)

    elif args.action == 'down':
        if not args.entity or not args.layer:
            print("向下穿透需要 --entity 和 --layer 参数")
            return
        layer = EntityLayer(args.layer)
        result = engine.trace_down(layer, args.entity)

    elif args.action == 'horizontal':
        if not args.entity:
            print("水平穿透需要 --entity 参数")
            return
        result = engine.trace_horizontal(args.entity)

    elif args.action == 'full':
        if not args.entity:
            print("全链路穿透需要 --entity 参数（结算单据UID）")
            return
        result = engine.trace_full_chain(args.entity)

    elif args.action == 'semantic':
        if not args.query:
            print("语义穿透需要 --query 参数")
            return
        # 加载SBERT
        if SBERT_AVAILABLE:
            from sentence_transformers import SentenceTransformer
            encoder = SentenceTransformer('shibing624/text2vec-base-chinese')
            engine.encoder = encoder
        result = engine.semantic_trace(args.query)

    # 输出结果
    print("\n=== 穿透查询结果 ===\n")
    result_dict = engine.result_to_dict(result)
    print(json.dumps(result_dict, ensure_ascii=False, indent=2))

    if db:
        db.close()

if __name__ == '__main__':
    main()
