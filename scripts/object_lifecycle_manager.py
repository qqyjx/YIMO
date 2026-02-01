#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对象生命周期管理器 - Object Lifecycle Manager (OLM)
YIMO 一模到底核心模块

功能：
1. 三层本体模型管理（概念实体、逻辑实体、物理实体）
2. 业务对象抽取与管理
3. 机理函数系统（业务规则、物理公式）
4. 穿透式查询引擎
5. 时态建模（生命周期阶段属性管理）

保留与现有EAV库和SBERT相似度匹配的集成
"""

import os
import sys
import json
import uuid
import hashlib
import logging
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum

import pandas as pd
import numpy as np

# 数据库连接
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None

# SBERT语义编码（复用现有模块）
try:
    from sentence_transformers import SentenceTransformer
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
# 数据类定义
# ============================================================================

class EntityLayer(Enum):
    """实体层级枚举"""
    CONCEPT = "concept"      # 概念实体（业务场景层）
    LOGICAL = "logical"      # 逻辑实体（交互表单层）
    PHYSICAL = "physical"    # 物理实体（客观实体层）

class ObjectType(Enum):
    """业务对象类型枚举"""
    PROJECT = "project"          # 项目
    ASSET = "asset"              # 资产/设备
    CONTRACT = "contract"        # 合同
    INVOICE = "invoice"          # 发票
    MATERIAL = "material"        # 物资
    PERSONNEL = "personnel"      # 人员
    ORGANIZATION = "organization" # 组织
    DOCUMENT = "document"        # 文档
    PROCESS = "process"          # 流程
    OTHER = "other"              # 其他

class FunctionType(Enum):
    """机理函数类型枚举"""
    PHYSICAL = "physical"        # 物理公式（如P=UI）
    BUSINESS = "business"        # 业务规则
    VALIDATION = "validation"    # 校验规则
    CALCULATION = "calculation"  # 计算规则
    TRANSFORMATION = "transformation" # 转换规则
    ROUTING = "routing"          # 路由规则

class LifecycleStage(Enum):
    """生命周期阶段枚举"""
    PLANNING = "Planning"        # 规划阶段
    DESIGN = "Design"            # 设计阶段
    CONSTRUCTION = "Construction" # 建设阶段
    OPERATION = "Operation"      # 运维阶段
    FINANCE = "Finance"          # 财务阶段

@dataclass
class ConceptEntity:
    """概念实体数据类"""
    entity_code: str
    entity_name: str
    data_domain: Optional[str] = None
    data_subdomain: Optional[str] = None
    business_object_code: Optional[str] = None
    business_object_name: Optional[str] = None
    is_core: bool = False
    data_classification: Optional[str] = None
    usage_scope: Optional[str] = None
    data_owner: Optional[str] = None
    description: Optional[str] = None
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None

@dataclass
class LogicalEntity:
    """逻辑实体数据类"""
    entity_code: str
    entity_name: str
    concept_entity_code: Optional[str] = None
    data_domain: Optional[str] = None
    data_item: Optional[str] = None
    business_object_code: Optional[str] = None
    business_object_name: Optional[str] = None
    description: Optional[str] = None
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None

@dataclass
class PhysicalEntity:
    """物理实体数据类"""
    entity_code: str
    entity_name: str
    logical_entity_code: Optional[str] = None
    data_domain: Optional[str] = None
    table_schema: Optional[str] = None
    table_name: Optional[str] = None
    description: Optional[str] = None
    fields: List[Dict[str, Any]] = field(default_factory=list)
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None

@dataclass
class BusinessObject:
    """业务对象数据类"""
    object_code: str
    object_name: str
    object_type: ObjectType = ObjectType.OTHER
    object_category: Optional[str] = None
    parent_object_code: Optional[str] = None
    description: Optional[str] = None
    data_items: List[str] = field(default_factory=list)
    business_constraints: List[str] = field(default_factory=list)
    is_core_object: bool = False
    source_process: Optional[str] = None
    source_step: Optional[str] = None
    related_concept_entities: List[str] = field(default_factory=list)
    related_logical_entities: List[str] = field(default_factory=list)
    related_physical_entities: List[str] = field(default_factory=list)

@dataclass
class MechanismFunction:
    """机理函数数据类"""
    function_code: str
    function_name: str
    function_type: FunctionType = FunctionType.BUSINESS
    category: Optional[str] = None
    description: Optional[str] = None
    formula_expression: Optional[str] = None
    formula_latex: Optional[str] = None
    input_parameters: List[Dict[str, Any]] = field(default_factory=list)
    output_parameters: List[Dict[str, Any]] = field(default_factory=list)
    python_code: Optional[str] = None
    applicable_objects: List[str] = field(default_factory=list)
    applicable_stages: List[str] = field(default_factory=list)
    preconditions: List[Dict[str, Any]] = field(default_factory=list)
    postconditions: List[Dict[str, Any]] = field(default_factory=list)
    is_active: bool = True

@dataclass
class BusinessRule:
    """业务规则数据类"""
    rule_code: str
    rule_name: str
    rule_type: str = "judgment"
    rule_description: Optional[str] = None
    rule_details: List[str] = field(default_factory=list)
    rule_elements: List[Dict[str, Any]] = field(default_factory=list)
    element_logic: str = "and"
    result_value: Optional[str] = None
    is_digitized: bool = False
    supported_processes: List[str] = field(default_factory=list)
    supported_steps: List[str] = field(default_factory=list)
    severity: str = "warning"

# ============================================================================
# 数据库连接管理
# ============================================================================

class DatabaseManager:
    """数据库连接管理器"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 3307,
        user: str = "eav_user",
        password: str = "eavpass123",
        database: str = "eav_db"
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None

    def connect(self) -> bool:
        """建立数据库连接"""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci',
                autocommit=False
            )
            logger.info(f"数据库连接成功: {self.host}:{self.port}/{self.database}")
            return True
        except MySQLError as e:
            logger.error(f"数据库连接失败: {e}")
            return False

    def disconnect(self):
        """关闭数据库连接"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("数据库连接已关闭")

    def execute(self, sql: str, params: tuple = None, fetch: bool = False) -> Any:
        """执行SQL语句"""
        cursor = self.connection.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            if fetch:
                return cursor.fetchall()
            self.connection.commit()
            return cursor.lastrowid
        except MySQLError as e:
            self.connection.rollback()
            logger.error(f"SQL执行失败: {e}\nSQL: {sql}")
            raise
        finally:
            cursor.close()

    def execute_many(self, sql: str, params_list: List[tuple]) -> int:
        """批量执行SQL语句"""
        cursor = self.connection.cursor()
        try:
            cursor.executemany(sql, params_list)
            self.connection.commit()
            return cursor.rowcount
        except MySQLError as e:
            self.connection.rollback()
            logger.error(f"批量SQL执行失败: {e}")
            raise
        finally:
            cursor.close()

# ============================================================================
# 语义编码器（复用SBERT）
# ============================================================================

class SemanticEncoder:
    """语义编码器 - 复用现有SBERT模块"""

    def __init__(self, model_name: str = "shibing624/text2vec-base-chinese"):
        self.model_name = model_name
        self.model = None
        self.embedding_dim = 768

    def load_model(self):
        """加载SBERT模型"""
        if not SBERT_AVAILABLE:
            logger.warning("SBERT不可用，语义编码功能将被禁用")
            return False

        try:
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"SBERT模型加载成功: {self.model_name}")
            return True
        except Exception as e:
            logger.error(f"SBERT模型加载失败: {e}")
            return False

    def encode(self, texts: Union[str, List[str]], normalize: bool = True) -> np.ndarray:
        """编码文本为向量"""
        if self.model is None:
            raise RuntimeError("SBERT模型未加载")

        if isinstance(texts, str):
            texts = [texts]

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=len(texts) > 100
        )
        return embeddings

    def compute_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的语义相似度"""
        embeddings = self.encode([text1, text2])
        similarity = np.dot(embeddings[0], embeddings[1])
        return float(similarity)

    def find_similar(
        self,
        query: str,
        candidates: List[str],
        top_k: int = 5,
        threshold: float = 0.5
    ) -> List[Tuple[int, str, float]]:
        """查找相似文本"""
        if not candidates:
            return []

        query_emb = self.encode(query)[0]
        cand_embs = self.encode(candidates)

        similarities = np.dot(cand_embs, query_emb)

        # 筛选超过阈值的
        valid_indices = np.where(similarities >= threshold)[0]

        # 按相似度排序
        sorted_indices = valid_indices[np.argsort(similarities[valid_indices])[::-1]]

        results = []
        for idx in sorted_indices[:top_k]:
            results.append((int(idx), candidates[idx], float(similarities[idx])))

        return results

# ============================================================================
# 三层本体导入器
# ============================================================================

class OntologyImporter:
    """三层本体导入器 - 从Excel导入概念实体、逻辑实体、物理实体"""

    # Excel列映射配置
    CONCEPT_COLUMNS = {
        'entity_code': '概念实体编号',
        'entity_name': '概念实体',
        'data_domain': '数据域',
        'data_subdomain': '数据子域',
        'business_object_code': '业务对象编号',
        'business_object_name': '业务对象',
        'is_core': '是否核心概念实体',
        'data_classification': '数据分类',
        'usage_scope': '使用范围',
        'data_owner': '数据Owner'
    }

    LOGICAL_COLUMNS = {
        'entity_code': '逻辑实体编码',
        'entity_name': '逻辑实体名称',
        'concept_entity_code': '概念实体编号',
        'data_domain': '数据域',
        'data_item': '数据项',
        'business_object_code': '业务对象编号',
        'business_object_name': '业务对象名称',
        'attribute_name': '属性名',
        'attribute_code': '属性代码',
        'attribute_comment': '注释',
        'data_type': '数据类型',
        'is_primary_key': '是否业务主键',
        'is_foreign_key': '是否外键',
        'is_not_null': '是否非空',
        'default_value': '默认值',
        'data_security_class': '数据安全分类',
        'data_security_level': '数据安全等级',
        'build_status': '建设状态-现状'
    }

    PHYSICAL_COLUMNS = {
        'entity_code': '物理实体编码',
        'entity_name': '物理实体名称',
        'logical_entity_code': '逻辑实体编码',
        'data_domain': '数据域',
        'field_name': '字段名称',
        'field_code': '字段代码',
        'field_comment': '注释',
        'data_type': '数据类型',
        'is_primary_key': '是否业务主键',
        'is_foreign_key': '是否外键',
        'is_not_null': '是否非空',
        'default_value': '默认值',
        'build_status': '建设状态-现状'
    }

    def __init__(self, db: DatabaseManager, encoder: Optional[SemanticEncoder] = None):
        self.db = db
        self.encoder = encoder
        self.stats = {
            'concept': {'imported': 0, 'skipped': 0, 'errors': 0},
            'logical': {'imported': 0, 'skipped': 0, 'errors': 0},
            'physical': {'imported': 0, 'skipped': 0, 'errors': 0},
            'relations': {'imported': 0, 'skipped': 0, 'errors': 0}
        }

    def _find_column(self, df: pd.DataFrame, target_name: str) -> Optional[str]:
        """模糊匹配查找列名"""
        # 精确匹配
        if target_name in df.columns:
            return target_name

        # 模糊匹配（包含关键词）
        for col in df.columns:
            if target_name in str(col):
                return col

        return None

    def _generate_code(self, prefix: str, name: str) -> str:
        """生成实体编号"""
        hash_str = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
        return f"{prefix}_{hash_str}".upper()

    def _parse_bool(self, value: Any) -> bool:
        """解析布尔值"""
        if pd.isna(value):
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ('是', 'yes', 'true', '1', 'y')
        return bool(value)

    def import_concept_entities(
        self,
        excel_path: str,
        sheet_name: str = 'DA-01 数据实体清单-概念实体清单'
    ) -> int:
        """导入概念实体"""
        logger.info(f"开始导入概念实体: {excel_path} -> {sheet_name}")

        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            logger.error(f"读取Excel失败: {e}")
            return 0

        # 映射列名
        col_map = {}
        for key, cn_name in self.CONCEPT_COLUMNS.items():
            found_col = self._find_column(df, cn_name)
            if found_col:
                col_map[key] = found_col

        logger.info(f"列映射: {col_map}")

        # 去重（按实体名称）
        name_col = col_map.get('entity_name')
        if not name_col:
            logger.error("未找到概念实体名称列")
            return 0

        df = df.drop_duplicates(subset=[name_col], keep='first')
        df = df[df[name_col].notna()]

        count = 0
        for idx, row in df.iterrows():
            try:
                entity_name = str(row.get(name_col, '')).strip()
                if not entity_name:
                    continue

                # 生成或获取编号
                code_col = col_map.get('entity_code')
                entity_code = str(row.get(code_col, '')).strip() if code_col and pd.notna(row.get(code_col)) else None
                if not entity_code:
                    entity_code = self._generate_code('CE', entity_name)

                # 构建实体对象
                entity = ConceptEntity(
                    entity_code=entity_code,
                    entity_name=entity_name,
                    data_domain=str(row.get(col_map.get('data_domain', ''), '')).strip() or None,
                    data_subdomain=str(row.get(col_map.get('data_subdomain', ''), '')).strip() or None,
                    business_object_code=str(row.get(col_map.get('business_object_code', ''), '')).strip() or None,
                    business_object_name=str(row.get(col_map.get('business_object_name', ''), '')).strip() or None,
                    is_core=self._parse_bool(row.get(col_map.get('is_core', ''))),
                    data_classification=str(row.get(col_map.get('data_classification', ''), '')).strip() or None,
                    usage_scope=str(row.get(col_map.get('usage_scope', ''), '')).strip() or None,
                    data_owner=str(row.get(col_map.get('data_owner', ''), '')).strip() or None,
                    source_file=os.path.basename(excel_path),
                    source_sheet=sheet_name,
                    source_row=int(idx) + 2  # Excel行号从1开始，加上标题行
                )

                # 生成语义向量
                embedding_blob = None
                if self.encoder and self.encoder.model:
                    try:
                        text = f"{entity_name} {entity.data_domain or ''} {entity.business_object_name or ''}"
                        embedding = self.encoder.encode(text)[0]
                        embedding_blob = embedding.tobytes()
                    except Exception as e:
                        logger.warning(f"生成语义向量失败: {e}")

                # 插入数据库
                sql = """
                    INSERT INTO ontology_concept_entities
                    (entity_code, entity_name, data_domain, data_subdomain,
                     business_object_code, business_object_name, is_core,
                     data_classification, usage_scope, data_owner,
                     source_file, source_sheet, source_row, embedding_vector)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    entity_name = VALUES(entity_name),
                    data_domain = VALUES(data_domain),
                    updated_at = CURRENT_TIMESTAMP(6)
                """
                self.db.execute(sql, (
                    entity.entity_code, entity.entity_name, entity.data_domain,
                    entity.data_subdomain, entity.business_object_code,
                    entity.business_object_name, entity.is_core,
                    entity.data_classification, entity.usage_scope, entity.data_owner,
                    entity.source_file, entity.source_sheet, entity.source_row,
                    embedding_blob
                ))
                count += 1
                self.stats['concept']['imported'] += 1

            except Exception as e:
                logger.warning(f"导入概念实体失败 (行 {idx}): {e}")
                self.stats['concept']['errors'] += 1

        logger.info(f"概念实体导入完成: {count} 条")
        return count

    def import_logical_entities(
        self,
        excel_path: str,
        sheet_name: str = 'DA-02 数据实体清单-逻辑实体清单'
    ) -> int:
        """导入逻辑实体"""
        logger.info(f"开始导入逻辑实体: {excel_path} -> {sheet_name}")

        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            logger.error(f"读取Excel失败: {e}")
            return 0

        # 映射列名
        col_map = {}
        for key, cn_name in self.LOGICAL_COLUMNS.items():
            found_col = self._find_column(df, cn_name)
            if found_col:
                col_map[key] = found_col

        logger.info(f"列映射: {col_map}")

        # 按逻辑实体编码分组
        code_col = col_map.get('entity_code')
        name_col = col_map.get('entity_name')

        if not code_col and not name_col:
            logger.error("未找到逻辑实体编码或名称列")
            return 0

        # 分组处理逻辑实体及其属性
        entity_dict = {}
        for idx, row in df.iterrows():
            entity_code = str(row.get(code_col, '')).strip() if code_col else None
            entity_name = str(row.get(name_col, '')).strip() if name_col else None

            if not entity_code and not entity_name:
                continue

            if not entity_code:
                entity_code = self._generate_code('LE', entity_name)

            if entity_code not in entity_dict:
                entity_dict[entity_code] = {
                    'entity_code': entity_code,
                    'entity_name': entity_name,
                    'concept_entity_code': str(row.get(col_map.get('concept_entity_code', ''), '')).strip() or None,
                    'data_domain': str(row.get(col_map.get('data_domain', ''), '')).strip() or None,
                    'data_item': str(row.get(col_map.get('data_item', ''), '')).strip() or None,
                    'business_object_code': str(row.get(col_map.get('business_object_code', ''), '')).strip() or None,
                    'business_object_name': str(row.get(col_map.get('business_object_name', ''), '')).strip() or None,
                    'source_file': os.path.basename(excel_path),
                    'source_sheet': sheet_name,
                    'source_row': int(idx) + 2,
                    'attributes': []
                }

            # 添加属性
            attr_name = str(row.get(col_map.get('attribute_name', ''), '')).strip()
            if attr_name:
                entity_dict[entity_code]['attributes'].append({
                    'attribute_name': attr_name,
                    'attribute_code': str(row.get(col_map.get('attribute_code', ''), '')).strip() or None,
                    'attribute_comment': str(row.get(col_map.get('attribute_comment', ''), '')).strip() or None,
                    'data_type': str(row.get(col_map.get('data_type', ''), '')).strip() or None,
                    'is_primary_key': self._parse_bool(row.get(col_map.get('is_primary_key', ''))),
                    'is_foreign_key': self._parse_bool(row.get(col_map.get('is_foreign_key', ''))),
                    'is_not_null': self._parse_bool(row.get(col_map.get('is_not_null', ''))),
                    'default_value': str(row.get(col_map.get('default_value', ''), '')).strip() or None,
                    'data_security_class': str(row.get(col_map.get('data_security_class', ''), '')).strip() or None,
                    'data_security_level': str(row.get(col_map.get('data_security_level', ''), '')).strip() or None,
                    'build_status': str(row.get(col_map.get('build_status', ''), '')).strip() or None
                })

        # 插入逻辑实体
        count = 0
        for entity_code, entity_data in entity_dict.items():
            try:
                # 生成语义向量
                embedding_blob = None
                if self.encoder and self.encoder.model:
                    try:
                        text = f"{entity_data['entity_name']} {entity_data['data_domain'] or ''}"
                        embedding = self.encoder.encode(text)[0]
                        embedding_blob = embedding.tobytes()
                    except Exception as e:
                        logger.warning(f"生成语义向量失败: {e}")

                # 插入逻辑实体
                sql = """
                    INSERT INTO ontology_logical_entities
                    (entity_code, entity_name, concept_entity_code, data_domain,
                     data_item, business_object_code, business_object_name,
                     source_file, source_sheet, source_row, embedding_vector)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    entity_name = VALUES(entity_name),
                    concept_entity_code = VALUES(concept_entity_code),
                    updated_at = CURRENT_TIMESTAMP(6)
                """
                self.db.execute(sql, (
                    entity_data['entity_code'], entity_data['entity_name'],
                    entity_data['concept_entity_code'], entity_data['data_domain'],
                    entity_data['data_item'], entity_data['business_object_code'],
                    entity_data['business_object_name'], entity_data['source_file'],
                    entity_data['source_sheet'], entity_data['source_row'],
                    embedding_blob
                ))

                # 插入属性
                for attr in entity_data['attributes']:
                    attr_sql = """
                        INSERT INTO ontology_logical_attributes
                        (logical_entity_code, attribute_name, attribute_code,
                         attribute_comment, data_type, is_primary_key, is_foreign_key,
                         is_not_null, default_value, data_security_class,
                         data_security_level, build_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        attribute_comment = VALUES(attribute_comment)
                    """
                    self.db.execute(attr_sql, (
                        entity_code, attr['attribute_name'], attr['attribute_code'],
                        attr['attribute_comment'], attr['data_type'],
                        attr['is_primary_key'], attr['is_foreign_key'],
                        attr['is_not_null'], attr['default_value'],
                        attr['data_security_class'], attr['data_security_level'],
                        attr['build_status']
                    ))

                count += 1
                self.stats['logical']['imported'] += 1

            except Exception as e:
                logger.warning(f"导入逻辑实体失败 ({entity_code}): {e}")
                self.stats['logical']['errors'] += 1

        logger.info(f"逻辑实体导入完成: {count} 条")
        return count

    def import_physical_entities(
        self,
        excel_path: str,
        sheet_name: str = 'DA-03数据实体清单-物理实体清单'
    ) -> int:
        """导入物理实体"""
        logger.info(f"开始导入物理实体: {excel_path} -> {sheet_name}")

        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            logger.error(f"读取Excel失败: {e}")
            return 0

        if df.empty:
            logger.warning("物理实体表为空，跳过导入")
            return 0

        # 类似逻辑实体的处理逻辑
        col_map = {}
        for key, cn_name in self.PHYSICAL_COLUMNS.items():
            found_col = self._find_column(df, cn_name)
            if found_col:
                col_map[key] = found_col

        logger.info(f"列映射: {col_map}")

        code_col = col_map.get('entity_code')
        name_col = col_map.get('entity_name')

        if not code_col and not name_col:
            logger.warning("未找到物理实体编码或名称列")
            return 0

        # 分组处理
        entity_dict = {}
        for idx, row in df.iterrows():
            entity_code = str(row.get(code_col, '')).strip() if code_col else None
            entity_name = str(row.get(name_col, '')).strip() if name_col else None

            if not entity_code and not entity_name:
                continue

            if not entity_code:
                entity_code = self._generate_code('PE', entity_name)

            if entity_code not in entity_dict:
                entity_dict[entity_code] = {
                    'entity_code': entity_code,
                    'entity_name': entity_name,
                    'logical_entity_code': str(row.get(col_map.get('logical_entity_code', ''), '')).strip() or None,
                    'data_domain': str(row.get(col_map.get('data_domain', ''), '')).strip() or None,
                    'source_file': os.path.basename(excel_path),
                    'source_sheet': sheet_name,
                    'source_row': int(idx) + 2,
                    'fields': []
                }

            # 添加字段
            field_name = str(row.get(col_map.get('field_name', ''), '')).strip()
            if field_name:
                entity_dict[entity_code]['fields'].append({
                    'field_name': field_name,
                    'field_code': str(row.get(col_map.get('field_code', ''), '')).strip() or None,
                    'field_comment': str(row.get(col_map.get('field_comment', ''), '')).strip() or None,
                    'data_type': str(row.get(col_map.get('data_type', ''), '')).strip() or None,
                    'is_primary_key': self._parse_bool(row.get(col_map.get('is_primary_key', ''))),
                    'is_foreign_key': self._parse_bool(row.get(col_map.get('is_foreign_key', ''))),
                    'is_not_null': self._parse_bool(row.get(col_map.get('is_not_null', ''))),
                    'default_value': str(row.get(col_map.get('default_value', ''), '')).strip() or None,
                    'build_status': str(row.get(col_map.get('build_status', ''), '')).strip() or None
                })

        # 插入物理实体
        count = 0
        for entity_code, entity_data in entity_dict.items():
            try:
                # 生成语义向量
                embedding_blob = None
                if self.encoder and self.encoder.model:
                    try:
                        text = f"{entity_data['entity_name']} {entity_data['data_domain'] or ''}"
                        embedding = self.encoder.encode(text)[0]
                        embedding_blob = embedding.tobytes()
                    except:
                        pass

                # 插入物理实体
                sql = """
                    INSERT INTO ontology_physical_entities
                    (entity_code, entity_name, logical_entity_code, data_domain,
                     source_file, source_sheet, source_row, embedding_vector)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    entity_name = VALUES(entity_name),
                    logical_entity_code = VALUES(logical_entity_code),
                    updated_at = CURRENT_TIMESTAMP(6)
                """
                self.db.execute(sql, (
                    entity_data['entity_code'], entity_data['entity_name'],
                    entity_data['logical_entity_code'], entity_data['data_domain'],
                    entity_data['source_file'], entity_data['source_sheet'],
                    entity_data['source_row'], embedding_blob
                ))

                # 插入字段
                for field in entity_data['fields']:
                    field_sql = """
                        INSERT INTO ontology_physical_fields
                        (physical_entity_code, field_name, field_code,
                         field_comment, data_type, is_primary_key, is_foreign_key,
                         is_not_null, default_value, build_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    self.db.execute(field_sql, (
                        entity_code, field['field_name'], field['field_code'],
                        field['field_comment'], field['data_type'],
                        field['is_primary_key'], field['is_foreign_key'],
                        field['is_not_null'], field['default_value'],
                        field['build_status']
                    ))

                count += 1
                self.stats['physical']['imported'] += 1

            except Exception as e:
                logger.warning(f"导入物理实体失败 ({entity_code}): {e}")
                self.stats['physical']['errors'] += 1

        logger.info(f"物理实体导入完成: {count} 条")
        return count

    def build_layer_relations(self) -> int:
        """构建三层实体间的关联关系"""
        logger.info("开始构建三层实体关联关系...")
        count = 0

        # 概念实体 -> 逻辑实体（通过概念实体编号）
        sql = """
            INSERT IGNORE INTO ontology_layer_relations
            (source_layer, source_entity_code, target_layer, target_entity_code,
             relation_type, relation_strength, mapping_method)
            SELECT 'concept', ce.entity_code, 'logical', le.entity_code,
                   'derive', 1.0, 'rule'
            FROM ontology_concept_entities ce
            JOIN ontology_logical_entities le ON le.concept_entity_code = ce.entity_code
        """
        result = self.db.execute(sql)
        count += result if result else 0

        # 逻辑实体 -> 物理实体（通过逻辑实体编码）
        sql = """
            INSERT IGNORE INTO ontology_layer_relations
            (source_layer, source_entity_code, target_layer, target_entity_code,
             relation_type, relation_strength, mapping_method)
            SELECT 'logical', le.entity_code, 'physical', pe.entity_code,
                   'implement', 1.0, 'rule'
            FROM ontology_logical_entities le
            JOIN ontology_physical_entities pe ON pe.logical_entity_code = le.entity_code
        """
        result = self.db.execute(sql)
        count += result if result else 0

        self.stats['relations']['imported'] = count
        logger.info(f"三层实体关联关系构建完成: {count} 条")
        return count

    def import_all(self, excel_path: str) -> Dict[str, int]:
        """导入所有三层实体"""
        results = {
            'concept': self.import_concept_entities(excel_path),
            'logical': self.import_logical_entities(excel_path),
            'physical': self.import_physical_entities(excel_path),
            'relations': self.build_layer_relations()
        }
        return results

# ============================================================================
# 业务对象抽取器
# ============================================================================

class BusinessObjectExtractor:
    """业务对象抽取器 - 从三层实体和业务流程中抽取核心业务对象"""

    # 对象类型关键词映射
    OBJECT_TYPE_KEYWORDS = {
        ObjectType.PROJECT: ['项目', '工程', '立项', '可研'],
        ObjectType.ASSET: ['设备', '资产', '变压器', '开关', '线路', '电缆'],
        ObjectType.CONTRACT: ['合同', '协议', '契约'],
        ObjectType.INVOICE: ['发票', '票据', '账单'],
        ObjectType.MATERIAL: ['物资', '材料', '器材', '备品'],
        ObjectType.PERSONNEL: ['人员', '员工', '用户', '角色'],
        ObjectType.ORGANIZATION: ['组织', '部门', '单位', '公司'],
        ObjectType.DOCUMENT: ['文档', '报告', '记录', '档案'],
        ObjectType.PROCESS: ['流程', '审批', '工单']
    }

    def __init__(self, db: DatabaseManager, encoder: Optional[SemanticEncoder] = None):
        self.db = db
        self.encoder = encoder

    def _infer_object_type(self, name: str) -> ObjectType:
        """根据名称推断对象类型"""
        for obj_type, keywords in self.OBJECT_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name:
                    return obj_type
        return ObjectType.OTHER

    def extract_from_excel(
        self,
        excel_path: str,
        sheet_name: str = 'BA-04 业务对象清单'
    ) -> int:
        """从Excel导入业务对象"""
        logger.info(f"开始抽取业务对象: {excel_path} -> {sheet_name}")

        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            logger.error(f"读取Excel失败: {e}")
            return 0

        # 列映射
        col_map = {
            'process_name': None,
            'step_code': None,
            'step_name': None,
            'object_code': None,
            'object_name': None,
            'data_item': None,
            'constraint': None,
            'object_type': None
        }

        for col in df.columns:
            col_lower = str(col).lower()
            if '流程' in col and '名称' in col:
                col_map['process_name'] = col
            elif '步骤编号' in col:
                col_map['step_code'] = col
            elif '步骤' in col and '编号' not in col:
                col_map['step_name'] = col
            elif '对象编号' in col:
                col_map['object_code'] = col
            elif '对象名称' in col or '业务对象名称' in col:
                col_map['object_name'] = col
            elif '数据项' in col:
                col_map['data_item'] = col
            elif '约束' in col:
                col_map['constraint'] = col
            elif '对象类型' in col:
                col_map['object_type'] = col

        # 按对象名称分组
        name_col = col_map['object_name']
        if not name_col:
            logger.error("未找到业务对象名称列")
            return 0

        object_dict = {}
        for idx, row in df.iterrows():
            obj_name = str(row.get(name_col, '')).strip()
            if not obj_name or pd.isna(row.get(name_col)):
                continue

            if obj_name not in object_dict:
                # 推断对象类型
                obj_type = self._infer_object_type(obj_name)

                # 判断是否核心对象
                type_col = col_map['object_type']
                is_core = False
                if type_col and pd.notna(row.get(type_col)):
                    is_core = '核心' in str(row.get(type_col))

                object_dict[obj_name] = {
                    'object_name': obj_name,
                    'object_type': obj_type,
                    'is_core': is_core,
                    'data_items': set(),
                    'constraints': set(),
                    'processes': set(),
                    'steps': set()
                }

            # 收集数据项
            if col_map['data_item'] and pd.notna(row.get(col_map['data_item'])):
                object_dict[obj_name]['data_items'].add(str(row.get(col_map['data_item'])))

            # 收集约束
            if col_map['constraint'] and pd.notna(row.get(col_map['constraint'])):
                object_dict[obj_name]['constraints'].add(str(row.get(col_map['constraint'])))

            # 收集关联流程
            if col_map['process_name'] and pd.notna(row.get(col_map['process_name'])):
                object_dict[obj_name]['processes'].add(str(row.get(col_map['process_name'])))

            # 收集关联步骤
            if col_map['step_name'] and pd.notna(row.get(col_map['step_name'])):
                object_dict[obj_name]['steps'].add(str(row.get(col_map['step_name'])))

        # 插入数据库
        count = 0
        for obj_name, obj_data in object_dict.items():
            try:
                # 生成编号
                obj_code = self._generate_code('BO', obj_name)

                # 生成语义向量
                embedding_blob = None
                if self.encoder and self.encoder.model:
                    try:
                        text = f"{obj_name} {' '.join(obj_data['data_items'])}"
                        embedding = self.encoder.encode(text)[0]
                        embedding_blob = embedding.tobytes()
                    except:
                        pass

                sql = """
                    INSERT INTO business_objects
                    (object_code, object_name, object_type, is_core_object,
                     data_items, business_constraints, source_process, source_step,
                     embedding_vector)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    object_name = VALUES(object_name),
                    data_items = VALUES(data_items),
                    updated_at = CURRENT_TIMESTAMP(6)
                """
                self.db.execute(sql, (
                    obj_code,
                    obj_name,
                    obj_data['object_type'].value,
                    obj_data['is_core'],
                    json.dumps(list(obj_data['data_items']), ensure_ascii=False),
                    json.dumps(list(obj_data['constraints']), ensure_ascii=False),
                    ', '.join(obj_data['processes']) if obj_data['processes'] else None,
                    ', '.join(obj_data['steps']) if obj_data['steps'] else None,
                    embedding_blob
                ))
                count += 1

            except Exception as e:
                logger.warning(f"插入业务对象失败 ({obj_name}): {e}")

        logger.info(f"业务对象抽取完成: {count} 条")
        return count

    def _generate_code(self, prefix: str, name: str) -> str:
        """生成编号"""
        hash_str = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
        return f"{prefix}_{hash_str}".upper()

    def link_to_entities(self) -> int:
        """建立业务对象与三层实体的关联"""
        logger.info("开始建立业务对象与三层实体的关联...")

        # 获取所有业务对象
        objects = self.db.execute(
            "SELECT object_code, object_name FROM business_objects",
            fetch=True
        )

        if not objects:
            return 0

        count = 0
        for obj in objects:
            obj_code = obj['object_code']
            obj_name = obj['object_name']

            # 查找关联的概念实体（按业务对象名称匹配）
            concept_entities = self.db.execute(
                """
                SELECT entity_code FROM ontology_concept_entities
                WHERE business_object_name LIKE %s OR entity_name LIKE %s
                """,
                (f'%{obj_name}%', f'%{obj_name}%'),
                fetch=True
            )

            # 查找关联的逻辑实体
            logical_entities = self.db.execute(
                """
                SELECT entity_code FROM ontology_logical_entities
                WHERE business_object_name LIKE %s OR entity_name LIKE %s
                """,
                (f'%{obj_name}%', f'%{obj_name}%'),
                fetch=True
            )

            # 更新业务对象的关联实体列表
            if concept_entities or logical_entities:
                update_sql = """
                    UPDATE business_objects
                    SET related_concept_entities = %s,
                        related_logical_entities = %s,
                        updated_at = CURRENT_TIMESTAMP(6)
                    WHERE object_code = %s
                """
                self.db.execute(update_sql, (
                    json.dumps([e['entity_code'] for e in concept_entities], ensure_ascii=False) if concept_entities else None,
                    json.dumps([e['entity_code'] for e in logical_entities], ensure_ascii=False) if logical_entities else None,
                    obj_code
                ))
                count += 1

        logger.info(f"业务对象关联建立完成: {count} 条")
        return count

# ============================================================================
# 业务规则导入器
# ============================================================================

class BusinessRuleImporter:
    """业务规则导入器 - 从企业架构文档导入业务规则"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def import_from_excel(
        self,
        excel_path: str,
        sheet_name: str = 'BA-07 业务规则清单'
    ) -> int:
        """从Excel导入业务规则"""
        logger.info(f"开始导入业务规则: {excel_path} -> {sheet_name}")

        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name, skiprows=1)  # 跳过说明行
        except Exception as e:
            logger.error(f"读取Excel失败: {e}")
            return 0

        # 列映射
        col_map = {}
        for col in df.columns:
            col_str = str(col)
            if '规则编号' in col_str:
                col_map['rule_code'] = col
            elif '规则名称' in col_str:
                col_map['rule_name'] = col
            elif '规则描述' in col_str:
                col_map['rule_description'] = col
            elif '已实现数字化' in col_str:
                col_map['is_digitized'] = col
            elif '规则分类' in col_str:
                col_map['rule_type'] = col
            elif '规则细则' in col_str:
                col_map['rule_details'] = col
            elif '规则要素' in col_str and '逻辑' not in col_str:
                col_map['rule_elements'] = col
            elif '要素逻辑' in col_str:
                col_map['element_logic'] = col
            elif '结果值' in col_str:
                col_map['result_value'] = col
            elif '支撑的业务流程' in col_str and '编号' not in col_str:
                col_map['supported_processes'] = col
            elif '支撑的业务步骤' in col_str and '编号' not in col_str:
                col_map['supported_steps'] = col

        count = 0
        for idx, row in df.iterrows():
            try:
                rule_name = str(row.get(col_map.get('rule_name', ''), '')).strip()
                if not rule_name or '说明' in rule_name:
                    continue

                # 生成编号
                rule_code = str(row.get(col_map.get('rule_code', ''), '')).strip()
                if not rule_code or pd.isna(row.get(col_map.get('rule_code', ''))):
                    rule_code = f"BR_{hashlib.md5(rule_name.encode()).hexdigest()[:8]}".upper()

                # 解析规则类型
                rule_type_raw = str(row.get(col_map.get('rule_type', ''), '')).strip()
                rule_type_map = {
                    '定义规则': 'definition',
                    '判断规则': 'judgment',
                    '计算规则': 'calculation',
                    '推论规则': 'inference',
                    '约束规则': 'constraint',
                    '授权规则': 'authorization'
                }
                rule_type = rule_type_map.get(rule_type_raw, 'judgment')

                # 解析是否数字化
                is_digitized_raw = str(row.get(col_map.get('is_digitized', ''), '')).strip()
                is_digitized = is_digitized_raw.lower() in ('是', 'yes', 'true', '1')

                # 解析要素逻辑
                element_logic_raw = str(row.get(col_map.get('element_logic', ''), '')).strip().lower()
                element_logic = 'and' if 'and' in element_logic_raw else ('or' if 'or' in element_logic_raw else 'and')

                sql = """
                    INSERT INTO business_rules
                    (rule_code, rule_name, rule_type, rule_description,
                     rule_details, rule_elements, element_logic, result_value,
                     is_digitized, supported_processes, supported_steps,
                     source_file, source_sheet, source_row)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    rule_name = VALUES(rule_name),
                    rule_description = VALUES(rule_description),
                    updated_at = CURRENT_TIMESTAMP(6)
                """
                self.db.execute(sql, (
                    rule_code,
                    rule_name,
                    rule_type,
                    str(row.get(col_map.get('rule_description', ''), '')).strip() or None,
                    json.dumps([str(row.get(col_map.get('rule_details', ''), '')).strip()], ensure_ascii=False) if col_map.get('rule_details') else None,
                    json.dumps([{'name': str(row.get(col_map.get('rule_elements', ''), '')).strip()}], ensure_ascii=False) if col_map.get('rule_elements') else None,
                    element_logic,
                    str(row.get(col_map.get('result_value', ''), '')).strip() or None,
                    is_digitized,
                    json.dumps([str(row.get(col_map.get('supported_processes', ''), '')).strip()], ensure_ascii=False) if col_map.get('supported_processes') else None,
                    json.dumps([str(row.get(col_map.get('supported_steps', ''), '')).strip()], ensure_ascii=False) if col_map.get('supported_steps') else None,
                    os.path.basename(excel_path),
                    sheet_name,
                    int(idx) + 3  # 跳过说明行和标题行
                ))
                count += 1

            except Exception as e:
                logger.warning(f"导入业务规则失败 (行 {idx}): {e}")

        logger.info(f"业务规则导入完成: {count} 条")
        return count

# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='对象生命周期管理器 - Object Lifecycle Manager')
    parser.add_argument('--action', choices=['import', 'extract', 'link', 'all'],
                       default='all', help='执行动作')
    parser.add_argument('--excel', type=str, help='Excel数据文件路径')
    parser.add_argument('--data-dir', type=str, default='./DATA', help='数据目录')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='MySQL主机')
    parser.add_argument('--port', type=int, default=3307, help='MySQL端口')
    parser.add_argument('--user', type=str, default='eav_user', help='MySQL用户')
    parser.add_argument('--password', type=str, default='eavpass123', help='MySQL密码')
    parser.add_argument('--database', type=str, default='eav_db', help='MySQL数据库')
    parser.add_argument('--no-sbert', action='store_true', help='禁用SBERT语义编码')

    args = parser.parse_args()

    # 初始化数据库连接
    db = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database
    )

    if not db.connect():
        logger.error("数据库连接失败，退出")
        sys.exit(1)

    # 初始化语义编码器
    encoder = None
    if not args.no_sbert and SBERT_AVAILABLE:
        encoder = SemanticEncoder()
        encoder.load_model()

    try:
        # 确定Excel文件
        excel_files = []
        if args.excel:
            excel_files = [args.excel]
        else:
            # 扫描数据目录
            data_dir = args.data_dir
            if os.path.isdir(data_dir):
                for f in os.listdir(data_dir):
                    if f.endswith('.xlsx') and not f.startswith('~'):
                        excel_files.append(os.path.join(data_dir, f))

        if not excel_files:
            logger.error("未找到Excel数据文件")
            sys.exit(1)

        logger.info(f"找到 {len(excel_files)} 个Excel文件")

        # 执行动作
        if args.action in ['import', 'all']:
            importer = OntologyImporter(db, encoder)
            for excel_file in excel_files:
                logger.info(f"处理文件: {excel_file}")
                # 尝试导入三层实体（从2.xlsx）
                if '2.xlsx' in excel_file or '2.' in excel_file:
                    importer.import_all(excel_file)

        if args.action in ['extract', 'all']:
            extractor = BusinessObjectExtractor(db, encoder)
            rule_importer = BusinessRuleImporter(db)
            for excel_file in excel_files:
                # 尝试导入业务对象和规则（从1.xlsx）
                if '1.xlsx' in excel_file or '1.' in excel_file:
                    extractor.extract_from_excel(excel_file)
                    rule_importer.import_from_excel(excel_file)

        if args.action in ['link', 'all']:
            extractor = BusinessObjectExtractor(db, encoder)
            extractor.link_to_entities()

        logger.info("对象生命周期管理器执行完成")

    finally:
        db.disconnect()

if __name__ == '__main__':
    main()
