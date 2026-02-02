#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对象抽取器 (Object Extractor) - 语义聚类版
=============================================
采用"自下而上"的归纳抽取方法：
1. 收集三层架构所有实体名称
2. SBERT向量化
3. 层次聚类（控制聚类数量~20个）
4. 大模型归纳命名每个聚类
5. 输出高度抽象的核心对象

算法流程：
实体名称收集 → SBERT向量化 → 语义聚类 → 大模型归纳命名 → 核心对象输出

作者: YIMO Team
日期: 2026-02
"""

import os
import re
import json
import hashlib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Optional, Tuple
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import numpy as np
import pymysql
from pymysql.cursors import DictCursor

# 可选依赖
try:
    from sentence_transformers import SentenceTransformer
    HAS_SBERT = True
except ImportError:
    HAS_SBERT = False
    print("[WARN] sentence-transformers not installed, semantic clustering disabled")

try:
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    print("[WARN] sklearn not installed, clustering disabled")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[WARN] requests not installed, LLM extraction disabled")

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    def tqdm(x, **kwargs):
        return x


# ============================================================
# 配置常量
# ============================================================

# 目标聚类数量（高度抽象的对象数量）
TARGET_CLUSTER_COUNT = 15  # 目标15个左右，最多不超过20个
MAX_CLUSTER_COUNT = 20

# SBERT模型（中文语义向量）
SBERT_MODEL_NAME = "shibing624/text2vec-base-chinese"

# 必须包含的对象（甲方明确要求）
REQUIRED_OBJECTS = ["项目"]


# ============================================================
# 数据类定义
# ============================================================

@dataclass
class ExtractedObject:
    """抽取的对象"""
    object_code: str
    object_name: str
    object_name_en: str = ""
    parent_object_code: Optional[str] = None
    object_type: str = "CORE"  # CORE, DERIVED, AUXILIARY
    description: str = ""
    extraction_source: str = "SEMANTIC_CLUSTER"  # 新增来源类型
    extraction_confidence: float = 0.0
    llm_reasoning: str = ""
    synonyms: List[str] = field(default_factory=list)
    key_attributes: List[str] = field(default_factory=list)
    cluster_id: int = -1  # 聚类ID
    cluster_size: int = 0  # 聚类大小
    sample_entities: List[str] = field(default_factory=list)  # 聚类样本实体


@dataclass
class EntityInfo:
    """实体信息"""
    name: str
    layer: str  # CONCEPT, LOGICAL, PHYSICAL
    code: str = ""
    data_domain: str = ""
    data_subdomain: str = ""
    source_file: str = ""
    source_sheet: str = ""
    source_row: int = 0


@dataclass
class EntityRelation:
    """对象与实体的关联关系"""
    object_code: str
    entity_layer: str  # CONCEPT, LOGICAL, PHYSICAL
    entity_name: str
    entity_code: str = ""
    relation_type: str = "CLUSTER"  # CLUSTER（来自同一聚类）
    relation_strength: float = 0.0
    match_method: str = "SEMANTIC_CLUSTER"
    semantic_similarity: float = 0.0
    data_domain: str = ""
    data_subdomain: str = ""
    source_file: str = ""
    source_sheet: str = ""
    source_row: int = 0


# ============================================================
# 数据读取器
# ============================================================

class DataArchitectureReader:
    """数据架构读取器"""

    def __init__(self, data_dir: str = "DATA"):
        self.data_dir = Path(data_dir)
        self.entities: List[EntityInfo] = []

    def read_all(self) -> List[EntityInfo]:
        """读取所有三层架构实体"""
        print("[INFO] 开始读取三层架构数据...")

        # 读取 2.xlsx - 数据架构
        data_file = self.data_dir / "2.xlsx"
        if data_file.exists():
            print(f"  读取 {data_file}...")
            self._read_concept_entities(data_file)
            self._read_logical_entities(data_file)
            self._read_physical_entities(data_file)

        # 统计
        concept_count = len([e for e in self.entities if e.layer == "CONCEPT"])
        logical_count = len([e for e in self.entities if e.layer == "LOGICAL"])
        physical_count = len([e for e in self.entities if e.layer == "PHYSICAL"])

        print(f"[INFO] 数据读取完成:")
        print(f"  - 概念实体: {concept_count} 条")
        print(f"  - 逻辑实体: {logical_count} 条")
        print(f"  - 物理实体: {physical_count} 条")
        print(f"  - 总计: {len(self.entities)} 条")

        return self.entities

    def _read_concept_entities(self, file_path: Path):
        """读取概念实体清单"""
        try:
            df = pd.read_excel(file_path, sheet_name='DA-01 数据实体清单-概念实体清单')
            seen = set()
            for idx, row in df.iterrows():
                name = str(row.get("概念实体", "")).strip()
                if name and name != "nan" and name not in seen:
                    seen.add(name)
                    self.entities.append(EntityInfo(
                        name=name,
                        layer="CONCEPT",
                        code=str(row.get("概念实体编号", "")).strip(),
                        data_domain=str(row.get("数据域", "")).strip(),
                        data_subdomain=str(row.get("数据子域", "")).strip(),
                        source_file=str(file_path.name),
                        source_sheet="DA-01 概念实体清单",
                        source_row=idx + 2
                    ))
        except Exception as e:
            print(f"[ERROR] 读取概念实体失败: {e}")

    def _read_logical_entities(self, file_path: Path):
        """读取逻辑实体清单"""
        try:
            df = pd.read_excel(file_path, sheet_name='DA-02 数据实体清单-逻辑实体清单')
            seen = set()
            for idx, row in df.iterrows():
                name = str(row.get("逻辑实体名称", "")).strip()
                if name and name != "nan" and name not in seen:
                    seen.add(name)
                    self.entities.append(EntityInfo(
                        name=name,
                        layer="LOGICAL",
                        code=str(row.get("逻辑实体编码", "")).strip(),
                        data_domain=str(row.get("数据域", "")).strip(),
                        source_file=str(file_path.name),
                        source_sheet="DA-02 逻辑实体清单",
                        source_row=idx + 2
                    ))
        except Exception as e:
            print(f"[ERROR] 读取逻辑实体失败: {e}")

    def _read_physical_entities(self, file_path: Path):
        """读取物理实体清单"""
        try:
            df = pd.read_excel(file_path, sheet_name='DA-03数据实体清单-物理实体清单')
            seen = set()
            for idx, row in df.iterrows():
                name = str(row.get("物理实体名称", "")).strip()
                if name and name != "nan" and name not in seen:
                    seen.add(name)
                    self.entities.append(EntityInfo(
                        name=name,
                        layer="PHYSICAL",
                        code=str(row.get("物理实体编码", "")).strip(),
                        data_domain=str(row.get("数据域", "")).strip(),
                        source_file=str(file_path.name),
                        source_sheet="DA-03 物理实体清单",
                        source_row=idx + 2
                    ))
        except Exception as e:
            print(f"[ERROR] 读取物理实体失败: {e}")


# ============================================================
# 语义聚类抽取器（核心算法）
# ============================================================

class SemanticClusterExtractor:
    """
    语义聚类抽取器

    算法流程：
    1. 收集所有唯一实体名称
    2. SBERT向量化
    3. 层次聚类（AgglomerativeClustering）
    4. 为每个聚类采样代表性实体
    5. 调用大模型归纳命名
    """

    def __init__(self,
                 target_clusters: int = TARGET_CLUSTER_COUNT,
                 max_clusters: int = MAX_CLUSTER_COUNT,
                 sbert_model: str = SBERT_MODEL_NAME):
        self.target_clusters = target_clusters
        self.max_clusters = max_clusters
        self.sbert_model_name = sbert_model
        self.sbert_model = None
        self.embeddings = None
        self.entity_names = []
        self.entity_map: Dict[str, List[EntityInfo]] = defaultdict(list)

    def extract(self, entities: List[EntityInfo]) -> Tuple[List[Dict], Dict[int, List[str]]]:
        """
        执行语义聚类抽取

        Returns:
            clusters: 聚类结果列表，每个元素包含 cluster_id, entities, centroid_entity
            cluster_entity_map: 聚类ID到实体名称列表的映射
        """
        print("[INFO] 开始语义聚类抽取...")

        # 1. 收集唯一实体名称
        self._collect_unique_names(entities)

        if len(self.entity_names) == 0:
            print("[WARN] 没有可用的实体名称")
            return [], {}

        # 2. SBERT向量化
        self._vectorize_entities()

        # 3. 层次聚类
        cluster_labels = self._hierarchical_clustering()

        # 4. 构建聚类结果
        clusters, cluster_entity_map = self._build_cluster_results(cluster_labels)

        print(f"[INFO] 聚类完成，共 {len(clusters)} 个聚类")
        return clusters, cluster_entity_map

    def _collect_unique_names(self, entities: List[EntityInfo]):
        """收集唯一的实体名称"""
        for entity in entities:
            name = entity.name
            if name and name not in self.entity_map:
                self.entity_names.append(name)
            self.entity_map[name].append(entity)

        print(f"  收集到 {len(self.entity_names)} 个唯一实体名称")

    def _vectorize_entities(self):
        """SBERT向量化"""
        if not HAS_SBERT:
            print("[ERROR] SBERT未安装，无法进行语义聚类")
            raise RuntimeError("sentence-transformers not installed")

        print(f"  加载SBERT模型: {self.sbert_model_name}...")
        try:
            self.sbert_model = SentenceTransformer(self.sbert_model_name)
        except Exception as e:
            print(f"  模型加载失败，尝试备选模型...")
            self.sbert_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

        print(f"  对 {len(self.entity_names)} 个实体名称进行向量化...")
        self.embeddings = self.sbert_model.encode(
            self.entity_names,
            show_progress_bar=HAS_TQDM,
            batch_size=64
        )
        print(f"  向量维度: {self.embeddings.shape}")

    def _hierarchical_clustering(self) -> np.ndarray:
        """层次聚类"""
        if not HAS_SKLEARN:
            print("[ERROR] sklearn未安装，无法进行聚类")
            raise RuntimeError("sklearn not installed")

        n_samples = len(self.entity_names)

        # 动态确定聚类数量
        # 如果实体数量少于目标聚类数，则调整
        n_clusters = min(self.target_clusters, max(5, n_samples // 10))
        n_clusters = min(n_clusters, self.max_clusters)

        print(f"  执行层次聚类 (n_clusters={n_clusters})...")

        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric='cosine',
            linkage='average'
        )
        labels = clustering.fit_predict(self.embeddings)

        # 统计每个聚类的大小
        cluster_sizes = Counter(labels)
        print(f"  聚类大小分布: {dict(sorted(cluster_sizes.items()))}")

        return labels

    def _build_cluster_results(self, labels: np.ndarray) -> Tuple[List[Dict], Dict[int, List[str]]]:
        """构建聚类结果"""
        cluster_entity_map: Dict[int, List[str]] = defaultdict(list)

        # 按聚类分组
        for idx, label in enumerate(labels):
            cluster_entity_map[int(label)].append(self.entity_names[idx])

        # 构建聚类信息
        clusters = []
        for cluster_id, entity_list in cluster_entity_map.items():
            # 计算聚类中心
            cluster_indices = [i for i, l in enumerate(labels) if l == cluster_id]
            cluster_embeddings = self.embeddings[cluster_indices]
            centroid = np.mean(cluster_embeddings, axis=0)

            # 找到最接近中心的实体作为代表
            similarities = cosine_similarity([centroid], cluster_embeddings)[0]
            centroid_idx = cluster_indices[np.argmax(similarities)]
            centroid_entity = self.entity_names[centroid_idx]

            # 采样代表性实体（用于LLM归纳）
            sample_size = min(20, len(entity_list))
            # 优先选择：最接近中心的 + 随机采样
            sorted_indices = np.argsort(-similarities)
            sample_entities = [self.entity_names[cluster_indices[i]] for i in sorted_indices[:sample_size]]

            clusters.append({
                "cluster_id": cluster_id,
                "size": len(entity_list),
                "centroid_entity": centroid_entity,
                "sample_entities": sample_entities,
                "all_entities": entity_list
            })

        # 按聚类大小排序
        clusters.sort(key=lambda x: x["size"], reverse=True)

        return clusters, dict(cluster_entity_map)


# ============================================================
# 大模型归纳命名器
# ============================================================

class LLMObjectNamer:
    """大模型归纳命名器"""

    def __init__(self, api_base: str = None, api_key: str = None, model: str = "deepseek-chat"):
        self.api_base = api_base or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model

    def name_clusters(self, clusters: List[Dict]) -> List[ExtractedObject]:
        """为每个聚类命名"""
        print("[INFO] 开始大模型归纳命名...")

        if not HAS_REQUESTS or not self.api_key:
            print("[WARN] 大模型API不可用，使用规则命名")
            return self._rule_based_naming(clusters)

        try:
            objects = self._llm_batch_naming(clusters)
            # 确保必须的对象存在
            objects = self._ensure_required_objects(objects, clusters)
            return objects
        except Exception as e:
            print(f"[ERROR] 大模型调用失败: {e}")
            return self._rule_based_naming(clusters)

    def _llm_batch_naming(self, clusters: List[Dict]) -> List[ExtractedObject]:
        """批量调用LLM为聚类命名"""
        # 构建prompt
        cluster_samples = []
        for i, cluster in enumerate(clusters):
            cluster_samples.append({
                "cluster_id": i,
                "size": cluster["size"],
                "sample_entities": cluster["sample_entities"][:15]  # 限制样本数量
            })

        prompt = f"""你是一个电力行业数据架构专家。我将给你{len(clusters)}个聚类，每个聚类包含一组语义相似的数据实体名称。

请为每个聚类归纳出一个**高度抽象的对象名称**。

## 要求
1. 对象名称必须是高度抽象的概念，如"项目"、"设备"、"资产"、"人员"等
2. 不要使用具体的实体名称，如"变压器"、"断路器"等
3. 必须包含"项目"这个对象（这是甲方明确要求）
4. 每个对象需要给出中英文名称、简要描述和同义词

## 聚类数据
```json
{json.dumps(cluster_samples, ensure_ascii=False, indent=2)}
```

## 输出格式
请直接输出JSON数组，不要有其他内容：
```json
[
  {{
    "cluster_id": 0,
    "object_code": "OBJ_PROJECT",
    "object_name": "项目",
    "object_name_en": "Project",
    "object_type": "CORE",
    "description": "电网建设项目，包括输变电工程项目、配网工程项目等",
    "synonyms": ["工程", "建设项目"],
    "key_attributes": ["项目名称", "项目编号"],
    "confidence": 0.95,
    "reasoning": "该聚类包含大量项目相关实体如项目信息、工程进度信息等"
  }}
]
```
"""
        response = self._call_llm(prompt)
        return self._parse_llm_response(response, clusters)

    def _call_llm(self, prompt: str) -> str:
        """调用大模型API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的数据架构师，精通电力行业业务。请严格按照JSON格式输出。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4000
        }

        response = requests.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=data,
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _parse_llm_response(self, response: str, clusters: List[Dict]) -> List[ExtractedObject]:
        """解析大模型响应"""
        objects = []

        # 提取JSON部分
        json_match = re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            print("[WARN] 无法解析大模型响应")
            return self._rule_based_naming(clusters)

        try:
            data = json.loads(json_match.group())
            for item in data:
                cluster_id = item.get("cluster_id", -1)
                cluster = clusters[cluster_id] if 0 <= cluster_id < len(clusters) else None

                obj = ExtractedObject(
                    object_code=item.get("object_code", f"OBJ_{cluster_id}"),
                    object_name=item.get("object_name", ""),
                    object_name_en=item.get("object_name_en", ""),
                    object_type=item.get("object_type", "CORE"),
                    description=item.get("description", ""),
                    extraction_source="SEMANTIC_CLUSTER_LLM",
                    extraction_confidence=float(item.get("confidence", 0.8)),
                    llm_reasoning=item.get("reasoning", ""),
                    synonyms=item.get("synonyms", []),
                    key_attributes=item.get("key_attributes", []),
                    cluster_id=cluster_id,
                    cluster_size=cluster["size"] if cluster else 0,
                    sample_entities=cluster["sample_entities"][:10] if cluster else []
                )
                objects.append(obj)

        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON解析失败: {e}")
            return self._rule_based_naming(clusters)

        return objects

    def _ensure_required_objects(self, objects: List[ExtractedObject], clusters: List[Dict]) -> List[ExtractedObject]:
        """确保必须的对象存在"""
        object_names = {obj.object_name for obj in objects}

        for required in REQUIRED_OBJECTS:
            if required not in object_names:
                print(f"[INFO] 补充必须对象: {required}")
                # 找到最可能对应的聚类
                best_cluster = None
                best_score = 0
                for cluster in clusters:
                    score = sum(1 for e in cluster["sample_entities"] if required in e)
                    if score > best_score:
                        best_score = score
                        best_cluster = cluster

                objects.append(ExtractedObject(
                    object_code=f"OBJ_{required.upper()}",
                    object_name=required,
                    object_name_en=required.title(),
                    object_type="CORE",
                    description=f"核心对象：{required}",
                    extraction_source="REQUIRED",
                    extraction_confidence=1.0,
                    cluster_id=best_cluster["cluster_id"] if best_cluster else -1,
                    cluster_size=best_cluster["size"] if best_cluster else 0
                ))

        return objects

    def _rule_based_naming(self, clusters: List[Dict]) -> List[ExtractedObject]:
        """基于规则的命名（备选方案）"""
        print("[INFO] 使用规则进行聚类命名...")

        # 关键词到对象的映射
        keyword_object_map = {
            "项目": ("OBJ_PROJECT", "项目", "Project", "CORE", "电网建设项目"),
            "工程": ("OBJ_PROJECT", "项目", "Project", "CORE", "电网建设项目"),
            "设备": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备"),
            "变压器": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备"),
            "断路器": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备"),
            "资产": ("OBJ_ASSET", "资产", "Asset", "CORE", "固定资产"),
            "合同": ("OBJ_CONTRACT", "合同", "Contract", "CORE", "业务合同"),
            "人员": ("OBJ_PERSONNEL", "人员", "Personnel", "CORE", "相关人员"),
            "员工": ("OBJ_PERSONNEL", "人员", "Personnel", "CORE", "相关人员"),
            "组织": ("OBJ_ORGANIZATION", "组织", "Organization", "CORE", "组织机构"),
            "部门": ("OBJ_ORGANIZATION", "组织", "Organization", "CORE", "组织机构"),
            "文档": ("OBJ_DOCUMENT", "文档", "Document", "AUXILIARY", "业务文档"),
            "报告": ("OBJ_DOCUMENT", "文档", "Document", "AUXILIARY", "业务文档"),
            "任务": ("OBJ_TASK", "任务", "Task", "DERIVED", "工作任务"),
            "工单": ("OBJ_TASK", "任务", "Task", "DERIVED", "工作任务"),
            "物资": ("OBJ_MATERIAL", "物资", "Material", "CORE", "工程物资"),
            "材料": ("OBJ_MATERIAL", "物资", "Material", "CORE", "工程物资"),
            "费用": ("OBJ_COST", "费用", "Cost", "DERIVED", "费用成本"),
            "预算": ("OBJ_COST", "费用", "Cost", "DERIVED", "费用成本"),
            "指标": ("OBJ_METRIC", "指标", "Metric", "AUXILIARY", "业务指标"),
            "统计": ("OBJ_METRIC", "指标", "Metric", "AUXILIARY", "业务指标"),
            "流程": ("OBJ_PROCESS", "流程", "Process", "AUXILIARY", "业务流程"),
            "审批": ("OBJ_PROCESS", "流程", "Process", "AUXILIARY", "业务流程"),
            "系统": ("OBJ_SYSTEM", "系统", "System", "AUXILIARY", "信息系统"),
            "平台": ("OBJ_SYSTEM", "系统", "System", "AUXILIARY", "信息系统"),
            "标准": ("OBJ_STANDARD", "标准", "Standard", "AUXILIARY", "技术标准"),
            "规范": ("OBJ_STANDARD", "标准", "Standard", "AUXILIARY", "技术标准"),
        }

        objects = []
        used_codes = set()

        for cluster in clusters:
            # 统计聚类中各关键词的出现次数
            keyword_counts = Counter()
            for entity in cluster["sample_entities"]:
                for keyword in keyword_object_map:
                    if keyword in entity:
                        keyword_counts[keyword] += 1

            if keyword_counts:
                # 选择出现最多的关键词对应的对象
                top_keyword = keyword_counts.most_common(1)[0][0]
                obj_info = keyword_object_map[top_keyword]
                code, name, name_en, obj_type, desc = obj_info

                # 避免重复
                if code not in used_codes:
                    used_codes.add(code)
                    objects.append(ExtractedObject(
                        object_code=code,
                        object_name=name,
                        object_name_en=name_en,
                        object_type=obj_type,
                        description=desc,
                        extraction_source="SEMANTIC_CLUSTER_RULE",
                        extraction_confidence=0.7,
                        cluster_id=cluster["cluster_id"],
                        cluster_size=cluster["size"],
                        sample_entities=cluster["sample_entities"][:10]
                    ))
            else:
                # 无法识别的聚类，使用通用命名
                generic_code = f"OBJ_CLUSTER_{cluster['cluster_id']}"
                if generic_code not in used_codes:
                    used_codes.add(generic_code)
                    objects.append(ExtractedObject(
                        object_code=generic_code,
                        object_name=f"对象{cluster['cluster_id'] + 1}",
                        object_name_en=f"Object{cluster['cluster_id'] + 1}",
                        object_type="AUXILIARY",
                        description=f"自动聚类生成的对象，代表性实体：{cluster['centroid_entity']}",
                        extraction_source="SEMANTIC_CLUSTER_AUTO",
                        extraction_confidence=0.5,
                        cluster_id=cluster["cluster_id"],
                        cluster_size=cluster["size"],
                        sample_entities=cluster["sample_entities"][:10]
                    ))

        # 确保必须的对象存在
        return self._ensure_required_objects(objects, clusters)


# ============================================================
# 关联关系构建器
# ============================================================

class ClusterRelationBuilder:
    """基于聚类的关联关系构建器"""

    def __init__(self,
                 objects: List[ExtractedObject],
                 entities: List[EntityInfo],
                 cluster_entity_map: Dict[int, List[str]]):
        self.objects = objects
        self.entities = entities
        self.cluster_entity_map = cluster_entity_map

        # 构建实体名称到实体信息的映射
        self.entity_info_map: Dict[str, List[EntityInfo]] = defaultdict(list)
        for entity in entities:
            self.entity_info_map[entity.name].append(entity)

    def build_relations(self) -> List[EntityRelation]:
        """构建对象与实体的关联关系"""
        print("[INFO] 开始构建关联关系...")

        relations = []

        for obj in self.objects:
            if obj.cluster_id < 0:
                continue

            # 获取该对象对应聚类的所有实体
            cluster_entities = self.cluster_entity_map.get(obj.cluster_id, [])

            for entity_name in cluster_entities:
                # 获取该实体的详细信息
                entity_infos = self.entity_info_map.get(entity_name, [])

                for entity_info in entity_infos:
                    # 计算关联强度（基于聚类内位置）
                    # 样本实体的强度更高
                    if entity_name in obj.sample_entities:
                        strength = 0.9
                    else:
                        strength = 0.7

                    relations.append(EntityRelation(
                        object_code=obj.object_code,
                        entity_layer=entity_info.layer,
                        entity_name=entity_name,
                        entity_code=entity_info.code,
                        relation_type="CLUSTER",
                        relation_strength=strength,
                        match_method="SEMANTIC_CLUSTER",
                        data_domain=entity_info.data_domain,
                        data_subdomain=entity_info.data_subdomain,
                        source_file=entity_info.source_file,
                        source_sheet=entity_info.source_sheet,
                        source_row=entity_info.source_row
                    ))

        print(f"[INFO] 构建完成，共 {len(relations)} 条关联关系")
        return relations


# ============================================================
# 数据库写入器
# ============================================================

class DatabaseWriter:
    """数据库写入器"""

    def __init__(self, host: str = "localhost", port: int = 3307,
                 user: str = "root", password: str = "", database: str = "yimo"):
        self.db_config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "charset": "utf8mb4"
        }

    def write_objects(self, objects: List[ExtractedObject], batch_id: int) -> Dict[str, int]:
        """写入对象到数据库"""
        object_ids = {}

        with pymysql.connect(**self.db_config) as conn:
            with conn.cursor() as cursor:
                for obj in objects:
                    try:
                        sql = """
                        INSERT INTO extracted_objects
                        (object_code, object_name, object_name_en, object_type, description,
                         extraction_source, extraction_confidence, llm_reasoning, is_verified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        object_name = VALUES(object_name),
                        description = VALUES(description),
                        extraction_source = VALUES(extraction_source),
                        extraction_confidence = VALUES(extraction_confidence),
                        llm_reasoning = VALUES(llm_reasoning)
                        """
                        cursor.execute(sql, (
                            obj.object_code, obj.object_name, obj.object_name_en,
                            obj.object_type, obj.description, obj.extraction_source,
                            obj.extraction_confidence, obj.llm_reasoning, False
                        ))

                        cursor.execute("SELECT object_id FROM extracted_objects WHERE object_code = %s",
                                     (obj.object_code,))
                        result = cursor.fetchone()
                        if result:
                            object_ids[obj.object_code] = result[0]

                            # 插入同义词
                            for synonym in obj.synonyms:
                                cursor.execute("""
                                INSERT IGNORE INTO object_synonyms (object_id, synonym, source)
                                VALUES (%s, %s, %s)
                                """, (result[0], synonym, obj.extraction_source))

                            # 记录批次关联
                            cursor.execute("""
                            INSERT IGNORE INTO object_batch_mapping (object_id, batch_id)
                            VALUES (%s, %s)
                            """, (result[0], batch_id))

                    except Exception as e:
                        print(f"[ERROR] 写入对象 {obj.object_code} 失败: {e}")

                conn.commit()

        print(f"[INFO] 成功写入 {len(object_ids)} 个对象")
        return object_ids

    def write_relations(self, relations: List[EntityRelation], object_ids: Dict[str, int]):
        """写入关联关系到数据库"""
        count = 0

        with pymysql.connect(**self.db_config) as conn:
            with conn.cursor() as cursor:
                # 清空旧的关联关系
                for object_id in object_ids.values():
                    cursor.execute("DELETE FROM object_entity_relations WHERE object_id = %s", (object_id,))

                for rel in relations:
                    object_id = object_ids.get(rel.object_code)
                    if not object_id:
                        continue

                    try:
                        sql = """
                        INSERT INTO object_entity_relations
                        (object_id, entity_layer, entity_name, entity_code, relation_type,
                         relation_strength, match_method, data_domain, data_subdomain,
                         source_file, source_sheet, source_row)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql, (
                            object_id, rel.entity_layer, rel.entity_name, rel.entity_code,
                            rel.relation_type, rel.relation_strength, rel.match_method,
                            rel.data_domain, rel.data_subdomain, rel.source_file,
                            rel.source_sheet, rel.source_row
                        ))
                        count += 1
                    except Exception as e:
                        print(f"[ERROR] 写入关联失败: {e}")

                conn.commit()

        print(f"[INFO] 成功写入 {count} 条关联关系")
        return count

    def create_batch(self, source_files: List[str], llm_model: str = "") -> int:
        """创建抽取批次"""
        batch_code = f"SEMANTIC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with pymysql.connect(**self.db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                INSERT INTO object_extraction_batches
                (batch_code, source_files, llm_model, status)
                VALUES (%s, %s, %s, 'RUNNING')
                """, (batch_code, json.dumps(source_files), llm_model))
                conn.commit()
                return cursor.lastrowid

    def update_batch(self, batch_id: int, objects_count: int, relations_count: int, status: str = "COMPLETED"):
        """更新批次状态"""
        with pymysql.connect(**self.db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                UPDATE object_extraction_batches
                SET total_objects_extracted = %s, total_relations_created = %s, status = %s
                WHERE batch_id = %s
                """, (objects_count, relations_count, status, batch_id))
                conn.commit()


# ============================================================
# 主执行流程
# ============================================================

class SemanticObjectExtractionPipeline:
    """语义聚类对象抽取流水线"""

    def __init__(self, data_dir: str = "DATA", db_config: Dict = None,
                 target_clusters: int = TARGET_CLUSTER_COUNT):
        self.data_dir = data_dir
        self.db_config = db_config or {}
        self.target_clusters = target_clusters

    def run(self, use_llm: bool = True) -> Dict:
        """执行抽取流水线"""
        print("=" * 60)
        print("语义聚类对象抽取流水线启动")
        print("=" * 60)
        print(f"算法：自下而上的归纳抽取")
        print(f"目标聚类数：{self.target_clusters}")
        print()

        # 1. 读取三层架构数据
        reader = DataArchitectureReader(self.data_dir)
        entities = reader.read_all()

        if not entities:
            print("[ERROR] 没有读取到任何实体数据")
            return {"objects": [], "relations_count": 0, "stats": {}}

        # 2. 语义聚类
        extractor = SemanticClusterExtractor(target_clusters=self.target_clusters)
        clusters, cluster_entity_map = extractor.extract(entities)

        print(f"\n[INFO] 聚类结果预览:")
        for cluster in clusters[:5]:
            print(f"  聚类{cluster['cluster_id']}: {cluster['size']}个实体, 代表: {cluster['centroid_entity']}")
            print(f"    样本: {cluster['sample_entities'][:5]}")

        # 3. 大模型归纳命名
        namer = LLMObjectNamer()
        if use_llm:
            objects = namer.name_clusters(clusters)
        else:
            objects = namer._rule_based_naming(clusters)

        print(f"\n[INFO] 抽取到 {len(objects)} 个核心对象:")
        for obj in objects:
            print(f"  - {obj.object_code}: {obj.object_name} ({obj.object_type}) [聚类{obj.cluster_id}, {obj.cluster_size}个实体]")

        # 4. 构建关联关系
        builder = ClusterRelationBuilder(objects, entities, cluster_entity_map)
        relations = builder.build_relations()

        # 5. 统计
        stats = self._compute_stats(objects, relations)
        print("\n[INFO] 关联关系统计:")
        for obj_code, obj_stats in stats.items():
            print(f"  {obj_code}:")
            print(f"    概念实体: {obj_stats['concept']} | 逻辑实体: {obj_stats['logical']} | 物理实体: {obj_stats['physical']}")

        # 6. 写入数据库
        if self.db_config:
            try:
                writer = DatabaseWriter(**self.db_config)
                source_files = [f for f in os.listdir(self.data_dir) if f.endswith('.xlsx')]
                batch_id = writer.create_batch(source_files, "deepseek-chat")
                object_ids = writer.write_objects(objects, batch_id)
                rel_count = writer.write_relations(relations, object_ids)
                writer.update_batch(batch_id, len(objects), rel_count)
            except Exception as e:
                print(f"[ERROR] 数据库写入失败: {e}")

        return {
            "objects": [asdict(o) for o in objects],
            "clusters": [{k: v for k, v in c.items() if k != "all_entities"} for c in clusters],
            "relations_count": len(relations),
            "stats": stats
        }

    def _compute_stats(self, objects: List[ExtractedObject], relations: List[EntityRelation]) -> Dict:
        """计算统计信息"""
        stats = {}
        for obj in objects:
            obj_rels = [r for r in relations if r.object_code == obj.object_code]
            stats[obj.object_code] = {
                "object_name": obj.object_name,
                "cluster_id": obj.cluster_id,
                "cluster_size": obj.cluster_size,
                "concept": len([r for r in obj_rels if r.entity_layer == "CONCEPT"]),
                "logical": len([r for r in obj_rels if r.entity_layer == "LOGICAL"]),
                "physical": len([r for r in obj_rels if r.entity_layer == "PHYSICAL"]),
                "total": len(obj_rels)
            }
        return stats


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="语义聚类对象抽取器")
    parser.add_argument("--data-dir", default="DATA", help="数据目录")
    parser.add_argument("--target-clusters", type=int, default=TARGET_CLUSTER_COUNT, help="目标聚类数量")
    parser.add_argument("--db-host", default="localhost", help="数据库主机")
    parser.add_argument("--db-port", type=int, default=3307, help="数据库端口")
    parser.add_argument("--db-user", default="root", help="数据库用户")
    parser.add_argument("--db-password", default="", help="数据库密码")
    parser.add_argument("--db-name", default="yimo", help="数据库名称")
    parser.add_argument("--use-llm", action="store_true", help="使用大模型命名")
    parser.add_argument("--no-db", action="store_true", help="不写入数据库")
    parser.add_argument("--output", "-o", default=None, help="输出JSON文件路径")

    args = parser.parse_args()

    db_config = None
    if not args.no_db:
        db_config = {
            "host": args.db_host,
            "port": args.db_port,
            "user": args.db_user,
            "password": args.db_password,
            "database": args.db_name
        }

    pipeline = SemanticObjectExtractionPipeline(
        args.data_dir,
        db_config,
        target_clusters=args.target_clusters
    )
    result = pipeline.run(use_llm=args.use_llm)

    # 输出JSON结果
    print("\n" + "=" * 60)
    print("抽取结果摘要")
    print("=" * 60)
    print(f"核心对象数量: {len(result['objects'])}")
    print(f"关联关系数量: {result['relations_count']}")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")
