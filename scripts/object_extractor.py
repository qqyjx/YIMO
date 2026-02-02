#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对象抽取器 (Object Extractor)
==============================
从DATA表单（数据架构Excel）中抽取高度抽象的"对象"

核心功能：
1. 读取三层架构数据（概念实体、逻辑实体、物理实体）
2. 使用大模型（DeepSeek/GPT）进行对象识别和归类
3. 计算对象与三层架构实体的关联关系
4. 将结果写入MySQL数据库

作者: YIMO Team
日期: 2025-01
"""

import os
import re
import json
import hashlib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Optional, Tuple
from collections import Counter
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
    print("[WARN] sentence-transformers not installed, semantic matching disabled")

try:
    import jieba
    import jieba.analyse
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    print("[WARN] jieba not installed, using simple tokenization")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[WARN] requests not installed, LLM extraction disabled")


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
    extraction_source: str = "LLM"
    extraction_confidence: float = 0.0
    llm_reasoning: str = ""
    synonyms: List[str] = field(default_factory=list)
    key_attributes: List[str] = field(default_factory=list)


@dataclass
class EntityRelation:
    """对象与实体的关联关系"""
    object_code: str
    entity_layer: str  # CONCEPT, LOGICAL, PHYSICAL
    entity_name: str
    entity_code: str = ""
    relation_type: str = "DIRECT"  # DIRECT, INDIRECT, DERIVED
    relation_strength: float = 0.0
    match_method: str = "EXACT"  # EXACT, CONTAINS, SEMANTIC, LLM
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
        self.concept_entities: List[Dict] = []
        self.logical_entities: List[Dict] = []
        self.physical_entities: List[Dict] = []
        self.business_objects: List[Dict] = []

    def read_all(self) -> Dict[str, List[Dict]]:
        """读取所有数据架构表"""
        print("[INFO] 开始读取数据架构表...")

        # 读取 2.xlsx - 数据架构
        data_file = self.data_dir / "2.xlsx"
        if data_file.exists():
            print(f"  读取 {data_file}...")
            self._read_concept_entities(data_file)
            self._read_logical_entities(data_file)
            self._read_physical_entities(data_file)

        # 读取 1.xlsx - 业务架构（补充业务对象信息）
        ba_file = self.data_dir / "1.xlsx"
        if ba_file.exists():
            print(f"  读取 {ba_file}...")
            self._read_business_objects(ba_file)

        print(f"[INFO] 数据读取完成:")
        print(f"  - 概念实体: {len(self.concept_entities)} 条")
        print(f"  - 逻辑实体: {len(self.logical_entities)} 条")
        print(f"  - 物理实体: {len(self.physical_entities)} 条")
        print(f"  - 业务对象: {len(self.business_objects)} 条")

        return {
            "concept": self.concept_entities,
            "logical": self.logical_entities,
            "physical": self.physical_entities,
            "business": self.business_objects
        }

    def _read_concept_entities(self, file_path: Path):
        """读取概念实体清单"""
        try:
            df = pd.read_excel(file_path, sheet_name='DA-01 数据实体清单-概念实体清单')
            for idx, row in df.iterrows():
                self.concept_entities.append({
                    "entity_name": str(row.get("概念实体", "")).strip(),
                    "entity_code": str(row.get("概念实体编号", "")).strip(),
                    "business_object": str(row.get("业务对象", "")).strip(),
                    "data_domain": str(row.get("数据域", "")).strip(),
                    "data_subdomain": str(row.get("数据子域", "")).strip(),
                    "is_core": row.get("是否核心概念实体", "") == "是",
                    "data_classification": str(row.get("数据分类", "")).strip(),
                    "source_file": str(file_path.name),
                    "source_sheet": "DA-01 概念实体清单",
                    "source_row": idx + 2  # Excel行号从2开始（含表头）
                })
        except Exception as e:
            print(f"[ERROR] 读取概念实体失败: {e}")

    def _read_logical_entities(self, file_path: Path):
        """读取逻辑实体清单"""
        try:
            df = pd.read_excel(file_path, sheet_name='DA-02 数据实体清单-逻辑实体清单')
            # 只取唯一的逻辑实体（去重）
            seen = set()
            for idx, row in df.iterrows():
                entity_name = str(row.get("逻辑实体名称", "")).strip()
                if entity_name and entity_name not in seen:
                    seen.add(entity_name)
                    self.logical_entities.append({
                        "entity_name": entity_name,
                        "entity_code": str(row.get("逻辑实体编码", "")).strip(),
                        "concept_entity": str(row.get("概念实体", "")).strip(),
                        "data_domain": str(row.get("数据域", "")).strip(),
                        "source_file": str(file_path.name),
                        "source_sheet": "DA-02 逻辑实体清单",
                        "source_row": idx + 2
                    })
        except Exception as e:
            print(f"[ERROR] 读取逻辑实体失败: {e}")

    def _read_physical_entities(self, file_path: Path):
        """读取物理实体清单"""
        try:
            df = pd.read_excel(file_path, sheet_name='DA-03数据实体清单-物理实体清单')
            seen = set()
            for idx, row in df.iterrows():
                entity_name = str(row.get("物理实体名称", "")).strip()
                if entity_name and entity_name not in seen:
                    seen.add(entity_name)
                    self.physical_entities.append({
                        "entity_name": entity_name,
                        "entity_code": str(row.get("物理实体编码", "")).strip(),
                        "logical_entity": str(row.get("逻辑实体名称", "")).strip(),
                        "data_domain": str(row.get("数据域", "")).strip(),
                        "source_file": str(file_path.name),
                        "source_sheet": "DA-03 物理实体清单",
                        "source_row": idx + 2
                    })
        except Exception as e:
            print(f"[ERROR] 读取物理实体失败: {e}")

    def _read_business_objects(self, file_path: Path):
        """读取业务对象清单"""
        try:
            df = pd.read_excel(file_path, sheet_name='BA-04 业务对象清单')
            seen = set()
            for idx, row in df.iterrows():
                obj_name = str(row.get("业务对象名称 ", "") or row.get("业务对象名称", "")).strip()
                if obj_name and obj_name not in seen:
                    seen.add(obj_name)
                    self.business_objects.append({
                        "object_name": obj_name,
                        "process_name": str(row.get("操作级业务流程名称", "")).strip(),
                        "step_name": str(row.get("业务步骤", "")).strip(),
                        "object_type": str(row.get("对象类型（普通对象/核心对象）", "")).strip(),
                        "source_file": str(file_path.name),
                        "source_sheet": "BA-04 业务对象清单",
                        "source_row": idx + 2
                    })
        except Exception as e:
            print(f"[ERROR] 读取业务对象失败: {e}")


# ============================================================
# 候选对象识别器
# ============================================================

class CandidateObjectIdentifier:
    """候选对象识别器"""

    # 电网领域核心对象关键词（用于识别）
    DOMAIN_KEYWORDS = {
        "项目": ["项目", "工程", "建设", "施工", "可研", "设计", "验收"],
        "设备": ["设备", "变压器", "断路器", "线路", "开关", "电缆", "GIS", "主变"],
        "资产": ["资产", "固定资产", "在建工程", "折旧"],
        "合同": ["合同", "协议", "招标", "投标", "采购"],
        "人员": ["人员", "员工", "负责人", "经理", "班组"],
        "组织": ["组织", "部门", "单位", "公司", "项目部", "班组"],
        "文档": ["文档", "报告", "清单", "表单", "方案", "计划"],
        "流程": ["流程", "审批", "评审", "检查", "验收"],
        "物资": ["物资", "材料", "备品", "备件", "库存"],
        "任务": ["任务", "工单", "作业", "检修", "巡检"],
        "费用": ["费用", "成本", "预算", "结算", "支出"],
        "指标": ["指标", "KPI", "统计", "分析", "评价"]
    }

    def __init__(self, data: Dict[str, List[Dict]]):
        self.data = data
        self.entity_names: List[str] = []
        self.word_freq: Counter = Counter()

    def identify_candidates(self) -> Tuple[List[str], Dict[str, List[str]]]:
        """识别候选对象"""
        print("[INFO] 开始识别候选对象...")

        # 1. 收集所有实体名称
        self._collect_entity_names()

        # 2. 分词和词频统计
        self._analyze_word_frequency()

        # 3. 基于关键词匹配识别候选对象
        candidates = self._match_domain_keywords()

        print(f"[INFO] 识别到 {len(candidates)} 个候选对象类别")
        return list(candidates.keys()), candidates

    def _collect_entity_names(self):
        """收集所有实体名称"""
        for entity in self.data.get("concept", []):
            name = entity.get("entity_name", "")
            if name and name != "nan":
                self.entity_names.append(name)

        for entity in self.data.get("logical", []):
            name = entity.get("entity_name", "")
            if name and name != "nan":
                self.entity_names.append(name)

        for entity in self.data.get("physical", []):
            name = entity.get("entity_name", "")
            if name and name != "nan":
                self.entity_names.append(name)

        for obj in self.data.get("business", []):
            name = obj.get("object_name", "")
            if name and name != "nan":
                self.entity_names.append(name)

        print(f"  收集到 {len(self.entity_names)} 个实体名称")

    def _analyze_word_frequency(self):
        """分析词频"""
        if HAS_JIEBA:
            for name in self.entity_names:
                words = jieba.cut(name)
                for word in words:
                    if len(word) >= 2:
                        self.word_freq[word] += 1
        else:
            # 简单分词
            for name in self.entity_names:
                for kw_list in self.DOMAIN_KEYWORDS.values():
                    for kw in kw_list:
                        if kw in name:
                            self.word_freq[kw] += 1

        print(f"  词频统计完成，高频词（前20）:")
        for word, freq in self.word_freq.most_common(20):
            print(f"    {word}: {freq}")

    def _match_domain_keywords(self) -> Dict[str, List[str]]:
        """基于领域关键词匹配"""
        candidates = {}

        for obj_type, keywords in self.DOMAIN_KEYWORDS.items():
            matched_entities = []
            for name in self.entity_names:
                for kw in keywords:
                    if kw in name:
                        matched_entities.append(name)
                        break
            if matched_entities:
                candidates[obj_type] = list(set(matched_entities))[:100]  # 限制每类100个

        return candidates


# ============================================================
# 大模型对象抽取器
# ============================================================

class LLMObjectExtractor:
    """大模型对象抽取器"""

    def __init__(self, api_base: str = None, api_key: str = None, model: str = "deepseek-chat"):
        self.api_base = api_base or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model

    def extract_objects(self, entity_names: List[str], candidates: Dict[str, List[str]]) -> List[ExtractedObject]:
        """使用大模型抽取对象"""
        print("[INFO] 调用大模型进行对象抽取...")

        if not HAS_REQUESTS or not self.api_key:
            print("[WARN] 大模型API不可用，使用规则抽取")
            return self._rule_based_extraction(candidates)

        # 构造提示词
        prompt = self._build_prompt(entity_names, candidates)

        try:
            response = self._call_llm(prompt)
            objects = self._parse_llm_response(response)
            return objects
        except Exception as e:
            print(f"[ERROR] 大模型调用失败: {e}")
            return self._rule_based_extraction(candidates)

    def _build_prompt(self, entity_names: List[str], candidates: Dict[str, List[str]]) -> str:
        """构建提示词"""
        # 采样一些实体名称
        sample_entities = entity_names[:200] if len(entity_names) > 200 else entity_names

        prompt = f"""你是一个电力行业数据架构专家。请根据以下数据实体名称，抽取出高度抽象的核心"对象"。

## 背景
这些数据来自电网企业的数据架构，包含概念实体、逻辑实体和物理实体。
我们需要从中抽取出核心的业务对象（如"项目"、"设备"、"资产"等），这些对象是高度抽象的概念。

## 实体名称样本（共{len(entity_names)}个）
{json.dumps(sample_entities[:100], ensure_ascii=False, indent=2)}

## 候选对象及其匹配的实体数量
{json.dumps({k: len(v) for k, v in candidates.items()}, ensure_ascii=False, indent=2)}

## 要求
1. 必须包含"项目"这个核心对象
2. 抽取8-15个核心对象
3. 每个对象需要给出：
   - object_code: 对象编码（如 OBJ_PROJECT）
   - object_name: 中文名称
   - object_name_en: 英文名称
   - object_type: CORE（核心）/ DERIVED（派生）/ AUXILIARY（辅助）
   - description: 简要描述
   - synonyms: 同义词列表
   - key_attributes: 关键属性列表
   - confidence: 置信度（0-1）
   - reasoning: 抽取理由

## 输出格式
请直接输出JSON数组，不要有其他内容：
```json
[
  {{
    "object_code": "OBJ_PROJECT",
    "object_name": "项目",
    "object_name_en": "Project",
    "object_type": "CORE",
    "description": "电网建设项目...",
    "synonyms": ["工程", "建设项目"],
    "key_attributes": ["项目名称", "项目编号", "建设单位"],
    "confidence": 0.95,
    "reasoning": "..."
  }}
]
```
"""
        return prompt

    def _call_llm(self, prompt: str) -> str:
        """调用大模型API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的数据架构师，精通电力行业业务。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4000
        }

        response = requests.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _parse_llm_response(self, response: str) -> List[ExtractedObject]:
        """解析大模型响应"""
        objects = []

        # 提取JSON部分
        json_match = re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            print("[WARN] 无法解析大模型响应，使用规则抽取")
            return []

        try:
            data = json.loads(json_match.group())
            for item in data:
                obj = ExtractedObject(
                    object_code=item.get("object_code", ""),
                    object_name=item.get("object_name", ""),
                    object_name_en=item.get("object_name_en", ""),
                    object_type=item.get("object_type", "CORE"),
                    description=item.get("description", ""),
                    extraction_source="LLM",
                    extraction_confidence=float(item.get("confidence", 0.8)),
                    llm_reasoning=item.get("reasoning", ""),
                    synonyms=item.get("synonyms", []),
                    key_attributes=item.get("key_attributes", [])
                )
                objects.append(obj)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON解析失败: {e}")

        return objects

    def _rule_based_extraction(self, candidates: Dict[str, List[str]]) -> List[ExtractedObject]:
        """基于规则的对象抽取（备选方案）"""
        print("[INFO] 使用规则进行对象抽取...")

        predefined_objects = [
            ExtractedObject("OBJ_PROJECT", "项目", "Project", object_type="CORE",
                          description="电网建设项目，包括输变电工程项目、配网工程项目等",
                          extraction_source="RULE", extraction_confidence=1.0,
                          synonyms=["工程", "建设项目", "输变电工程"],
                          key_attributes=["项目名称", "项目编号", "建设单位", "投资金额"]),

            ExtractedObject("OBJ_DEVICE", "设备", "Device", object_type="CORE",
                          description="电网设备，包括变压器、断路器、线路等",
                          extraction_source="RULE", extraction_confidence=1.0,
                          synonyms=["电气设备", "主设备", "一次设备"],
                          key_attributes=["设备名称", "设备编号", "设备类型", "电压等级"]),

            ExtractedObject("OBJ_ASSET", "资产", "Asset", object_type="CORE",
                          description="固定资产，包括设备资产、房屋资产等",
                          extraction_source="RULE", extraction_confidence=1.0,
                          synonyms=["固定资产", "在建工程"],
                          key_attributes=["资产名称", "资产编号", "资产原值", "净值"]),

            ExtractedObject("OBJ_CONTRACT", "合同", "Contract", object_type="CORE",
                          description="各类业务合同",
                          extraction_source="RULE", extraction_confidence=0.95,
                          synonyms=["协议", "框架合同"],
                          key_attributes=["合同名称", "合同编号", "合同金额", "签订日期"]),

            ExtractedObject("OBJ_PERSONNEL", "人员", "Personnel", object_type="CORE",
                          description="相关人员",
                          extraction_source="RULE", extraction_confidence=0.9,
                          synonyms=["员工", "工作人员", "负责人"],
                          key_attributes=["姓名", "工号", "部门", "岗位"]),

            ExtractedObject("OBJ_ORGANIZATION", "组织", "Organization", object_type="CORE",
                          description="组织机构",
                          extraction_source="RULE", extraction_confidence=0.95,
                          synonyms=["部门", "单位", "公司", "项目部"],
                          key_attributes=["组织名称", "组织编码", "上级组织"]),

            ExtractedObject("OBJ_DOCUMENT", "文档", "Document", object_type="AUXILIARY",
                          description="各类业务文档",
                          extraction_source="RULE", extraction_confidence=0.85,
                          synonyms=["报告", "清单", "表单", "方案"],
                          key_attributes=["文档名称", "文档类型", "创建时间"]),

            ExtractedObject("OBJ_TASK", "任务", "Task", object_type="DERIVED",
                          description="工作任务",
                          extraction_source="RULE", extraction_confidence=0.85,
                          synonyms=["工单", "作业", "检修任务", "巡检任务"],
                          key_attributes=["任务名称", "任务类型", "执行人", "状态"]),

            ExtractedObject("OBJ_MATERIAL", "物资", "Material", object_type="CORE",
                          description="工程物资",
                          extraction_source="RULE", extraction_confidence=0.9,
                          synonyms=["材料", "备品备件", "库存物资"],
                          key_attributes=["物资名称", "物资编码", "规格型号", "数量"]),

            ExtractedObject("OBJ_COST", "费用", "Cost", object_type="DERIVED",
                          description="费用成本",
                          extraction_source="RULE", extraction_confidence=0.85,
                          synonyms=["成本", "预算", "结算"],
                          key_attributes=["费用名称", "费用类型", "金额", "发生日期"]),
        ]

        return predefined_objects


# ============================================================
# 关联关系构建器
# ============================================================

class RelationBuilder:
    """关联关系构建器"""

    def __init__(self, objects: List[ExtractedObject], data: Dict[str, List[Dict]]):
        self.objects = objects
        self.data = data
        self.relations: List[EntityRelation] = []
        self.sbert_model = None

        if HAS_SBERT:
            try:
                print("[INFO] 加载SBERT模型...")
                self.sbert_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            except Exception as e:
                print(f"[WARN] SBERT模型加载失败: {e}")

    def build_relations(self) -> List[EntityRelation]:
        """构建对象与实体的关联关系"""
        print("[INFO] 开始构建关联关系...")

        # 为每个对象构建关联
        for obj in self.objects:
            # 1. 概念实体关联
            self._build_concept_relations(obj)

            # 2. 逻辑实体关联
            self._build_logical_relations(obj)

            # 3. 物理实体关联
            self._build_physical_relations(obj)

        print(f"[INFO] 构建完成，共 {len(self.relations)} 条关联关系")
        return self.relations

    def _build_concept_relations(self, obj: ExtractedObject):
        """构建与概念实体的关联"""
        keywords = [obj.object_name] + obj.synonyms

        for entity in self.data.get("concept", []):
            entity_name = entity.get("entity_name", "")
            if not entity_name or entity_name == "nan":
                continue

            match_method, strength = self._calculate_match(keywords, entity_name)
            if strength > 0.3:  # 阈值
                self.relations.append(EntityRelation(
                    object_code=obj.object_code,
                    entity_layer="CONCEPT",
                    entity_name=entity_name,
                    entity_code=entity.get("entity_code", ""),
                    relation_type="DIRECT" if strength > 0.7 else "INDIRECT",
                    relation_strength=strength,
                    match_method=match_method,
                    data_domain=entity.get("data_domain", ""),
                    data_subdomain=entity.get("data_subdomain", ""),
                    source_file=entity.get("source_file", ""),
                    source_sheet=entity.get("source_sheet", ""),
                    source_row=entity.get("source_row", 0)
                ))

    def _build_logical_relations(self, obj: ExtractedObject):
        """构建与逻辑实体的关联"""
        keywords = [obj.object_name] + obj.synonyms

        for entity in self.data.get("logical", []):
            entity_name = entity.get("entity_name", "")
            if not entity_name or entity_name == "nan":
                continue

            match_method, strength = self._calculate_match(keywords, entity_name)
            if strength > 0.3:
                self.relations.append(EntityRelation(
                    object_code=obj.object_code,
                    entity_layer="LOGICAL",
                    entity_name=entity_name,
                    entity_code=entity.get("entity_code", ""),
                    relation_type="DIRECT" if strength > 0.7 else "INDIRECT",
                    relation_strength=strength,
                    match_method=match_method,
                    data_domain=entity.get("data_domain", ""),
                    source_file=entity.get("source_file", ""),
                    source_sheet=entity.get("source_sheet", ""),
                    source_row=entity.get("source_row", 0)
                ))

    def _build_physical_relations(self, obj: ExtractedObject):
        """构建与物理实体的关联"""
        keywords = [obj.object_name] + obj.synonyms

        for entity in self.data.get("physical", []):
            entity_name = entity.get("entity_name", "")
            if not entity_name or entity_name == "nan":
                continue

            match_method, strength = self._calculate_match(keywords, entity_name)
            if strength > 0.3:
                self.relations.append(EntityRelation(
                    object_code=obj.object_code,
                    entity_layer="PHYSICAL",
                    entity_name=entity_name,
                    entity_code=entity.get("entity_code", ""),
                    relation_type="DIRECT" if strength > 0.7 else "INDIRECT",
                    relation_strength=strength,
                    match_method=match_method,
                    data_domain=entity.get("data_domain", ""),
                    source_file=entity.get("source_file", ""),
                    source_sheet=entity.get("source_sheet", ""),
                    source_row=entity.get("source_row", 0)
                ))

    def _calculate_match(self, keywords: List[str], entity_name: str) -> Tuple[str, float]:
        """计算匹配强度"""
        # 1. 精确匹配
        for kw in keywords:
            if kw == entity_name:
                return "EXACT", 1.0

        # 2. 包含匹配
        for kw in keywords:
            if kw in entity_name:
                # 根据关键词在实体名称中的比例计算强度
                strength = len(kw) / len(entity_name)
                return "CONTAINS", min(0.9, strength + 0.3)

        # 3. 语义匹配（如果SBERT可用）
        if self.sbert_model:
            try:
                kw_text = " ".join(keywords)
                embeddings = self.sbert_model.encode([kw_text, entity_name])
                similarity = float(np.dot(embeddings[0], embeddings[1]) /
                                 (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])))
                if similarity > 0.5:
                    return "SEMANTIC", similarity
            except Exception:
                pass

        return "NONE", 0.0


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
                        # 插入或更新对象
                        sql = """
                        INSERT INTO extracted_objects
                        (object_code, object_name, object_name_en, object_type, description,
                         extraction_source, extraction_confidence, llm_reasoning, is_verified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        object_name = VALUES(object_name),
                        description = VALUES(description),
                        extraction_confidence = VALUES(extraction_confidence)
                        """
                        cursor.execute(sql, (
                            obj.object_code, obj.object_name, obj.object_name_en,
                            obj.object_type, obj.description, obj.extraction_source,
                            obj.extraction_confidence, obj.llm_reasoning, False
                        ))

                        # 获取对象ID
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
        batch_code = f"BATCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

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

class ObjectExtractionPipeline:
    """对象抽取流水线"""

    def __init__(self, data_dir: str = "DATA", db_config: Dict = None):
        self.data_dir = data_dir
        self.db_config = db_config or {}

    def run(self, use_llm: bool = True) -> Dict:
        """执行抽取流水线"""
        print("=" * 60)
        print("对象抽取流水线启动")
        print("=" * 60)

        # 1. 读取数据
        reader = DataArchitectureReader(self.data_dir)
        data = reader.read_all()

        # 2. 识别候选对象
        identifier = CandidateObjectIdentifier(data)
        candidate_names, candidates = identifier.identify_candidates()

        # 3. 大模型/规则抽取对象
        extractor = LLMObjectExtractor()
        objects = extractor.extract_objects(identifier.entity_names, candidates)

        print(f"\n[INFO] 抽取到 {len(objects)} 个对象:")
        for obj in objects:
            print(f"  - {obj.object_code}: {obj.object_name} ({obj.object_type})")

        # 4. 构建关联关系
        builder = RelationBuilder(objects, data)
        relations = builder.build_relations()

        # 5. 统计关联关系
        stats = self._compute_stats(objects, relations)
        print("\n[INFO] 关联关系统计:")
        for obj_code, obj_stats in stats.items():
            print(f"  {obj_code}:")
            print(f"    概念实体: {obj_stats['concept']} | 逻辑实体: {obj_stats['logical']} | 物理实体: {obj_stats['physical']}")

        # 6. 写入数据库（如果配置了）
        if self.db_config:
            try:
                writer = DatabaseWriter(**self.db_config)
                batch_id = writer.create_batch([f for f in os.listdir(self.data_dir) if f.endswith('.xlsx')])
                object_ids = writer.write_objects(objects, batch_id)
                rel_count = writer.write_relations(relations, object_ids)
                writer.update_batch(batch_id, len(objects), rel_count)
            except Exception as e:
                print(f"[ERROR] 数据库写入失败: {e}")

        return {
            "objects": [asdict(o) for o in objects],
            "relations_count": len(relations),
            "stats": stats
        }

    def _compute_stats(self, objects: List[ExtractedObject], relations: List[EntityRelation]) -> Dict:
        """计算统计信息"""
        stats = {}
        for obj in objects:
            obj_rels = [r for r in relations if r.object_code == obj.object_code]
            stats[obj.object_code] = {
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

    parser = argparse.ArgumentParser(description="对象抽取器")
    parser.add_argument("--data-dir", default="DATA", help="数据目录")
    parser.add_argument("--db-host", default="localhost", help="数据库主机")
    parser.add_argument("--db-port", type=int, default=3307, help="数据库端口")
    parser.add_argument("--db-user", default="root", help="数据库用户")
    parser.add_argument("--db-password", default="", help="数据库密码")
    parser.add_argument("--db-name", default="yimo", help="数据库名称")
    parser.add_argument("--use-llm", action="store_true", help="使用大模型抽取")
    parser.add_argument("--no-db", action="store_true", help="不写入数据库")

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

    pipeline = ObjectExtractionPipeline(args.data_dir, db_config)
    result = pipeline.run(use_llm=args.use_llm)

    # 输出JSON结果
    print("\n" + "=" * 60)
    print("抽取结果 (JSON)")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
