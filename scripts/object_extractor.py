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
    via_concept_entity: str = ""  # 间接关联时的中间概念实体名称
    semantic_similarity: float = 0.0
    data_domain: str = ""
    data_subdomain: str = ""
    source_file: str = ""
    source_sheet: str = ""
    source_row: int = 0


# ============================================================
# 数据域配置
# ============================================================

# 数据域定义（可通过配置扩展）
# 所有域的Excel文件统一存放在DATA目录下
DOMAIN_CONFIG = {
    "shupeidian": {
        "name": "输配电",
        "files": ["1.xlsx", "2.xlsx", "3.xlsx"],  # 输配电域的三份Excel
        "sheet_config": {
            "concept": "DA-01 数据实体清单-概念实体清单",
            "logical": "DA-02 数据实体清单-逻辑实体清单",
            "physical": "DA-03数据实体清单-物理实体清单"
        }
    },
    "jicai": {
        "name": "计划财务",
        "files": [],  # 待配置：集采域的Excel文件
        "sheet_config": {
            "concept": "DA-01 数据实体清单-概念实体清单",
            "logical": "DA-02 数据实体清单-逻辑实体清单",
            "physical": "DA-03数据实体清单-物理实体清单"
        }
    },
    "yingxiao": {
        "name": "营销",
        "files": [],  # 待配置
        "sheet_config": {
            "concept": "DA-01 数据实体清单-概念实体清单",
            "logical": "DA-02 数据实体清单-逻辑实体清单",
            "physical": "DA-03数据实体清单-物理实体清单"
        }
    },
    "caiwu": {
        "name": "财务",
        "files": [],  # 待配置
        "sheet_config": {
            "concept": "DA-01 数据实体清单-概念实体清单",
            "logical": "DA-02 数据实体清单-逻辑实体清单",
            "physical": "DA-03数据实体清单-物理实体清单"
        }
    },
    "renliziyuan": {
        "name": "人力资源",
        "files": [],  # 待配置
        "sheet_config": {
            "concept": "DA-01 数据实体清单-概念实体清单",
            "logical": "DA-02 数据实体清单-逻辑实体清单",
            "physical": "DA-03数据实体清单-物理实体清单"
        }
    },
    "default": {
        "name": "默认",
        "files": ["2.xlsx"],  # 默认使用2.xlsx
        "sheet_config": {
            "concept": "DA-01 数据实体清单-概念实体清单",
            "logical": "DA-02 数据实体清单-逻辑实体清单",
            "physical": "DA-03数据实体清单-物理实体清单"
        }
    }
}


def get_domain_name(domain_code: str) -> str:
    """获取数据域的中文名称"""
    config = DOMAIN_CONFIG.get(domain_code, DOMAIN_CONFIG["default"])
    return config.get("name", domain_code)


# ============================================================
# 数据读取器
# ============================================================

class DataArchitectureReader:
    """数据架构读取器 - 支持多数据域"""

    def __init__(self, data_dir: str = "DATA", data_domain: str = "default",
                 excel_files: List[str] = None, domain_config: Dict = None):
        """
        初始化数据读取器

        Args:
            data_dir: 数据目录路径
            data_domain: 数据域编码
            excel_files: 指定的Excel文件列表（如果为None则自动查找）
            domain_config: 自定义域配置（覆盖默认配置）
        """
        self.data_dir = Path(data_dir)
        self.data_domain = data_domain
        self.excel_files = excel_files
        self.entities: List[EntityInfo] = []

        # 获取域配置
        self.config = domain_config or DOMAIN_CONFIG.get(data_domain, DOMAIN_CONFIG["default"])

    def read_all(self) -> List[EntityInfo]:
        """读取所有三层架构实体"""
        print(f"[INFO] 开始读取三层架构数据 (数据域: {self.data_domain})...")

        # 确定要读取的文件列表
        files_to_read = self._get_files_to_read()

        if not files_to_read:
            print(f"[WARN] 数据目录 {self.data_dir} 中未找到数据文件")
            return self.entities

        for data_file in files_to_read:
            print(f"  读取 {data_file}...")
            self._read_concept_entities(data_file)
            self._read_logical_entities(data_file)
            self._read_physical_entities(data_file)

        # 统计
        concept_count = len([e for e in self.entities if e.layer == "CONCEPT"])
        logical_count = len([e for e in self.entities if e.layer == "LOGICAL"])
        physical_count = len([e for e in self.entities if e.layer == "PHYSICAL"])

        print(f"[INFO] 数据读取完成 (域: {self.data_domain}):")
        print(f"  - 概念实体: {concept_count} 条")
        print(f"  - 逻辑实体: {logical_count} 条")
        print(f"  - 物理实体: {physical_count} 条")
        print(f"  - 总计: {len(self.entities)} 条")

        return self.entities

    def _get_files_to_read(self) -> List[Path]:
        """确定要读取的文件列表 - 支持域子目录结构"""
        files = []

        # 如果明确指定了文件列表（命令行参数或API调用）
        if self.excel_files:
            for f in self.excel_files:
                file_path = Path(f) if Path(f).is_absolute() else self.data_dir / f
                if file_path.exists():
                    files.append(file_path)
                else:
                    print(f"[WARN] 文件不存在: {file_path}")
            if files:
                files.sort(key=lambda x: x.name)
                return files

        # 优先检查域子目录 (DATA/<domain>/)
        domain_subdir = self.data_dir / self.data_domain
        if domain_subdir.exists() and domain_subdir.is_dir():
            files = list(domain_subdir.glob("*.xlsx"))
            if files:
                print(f"[INFO] 从域子目录读取: {domain_subdir}")
                files.sort(key=lambda x: x.name)
                return files

        # 降级：根据域配置获取文件列表
        config_files = self.config.get("files", [])

        if config_files:
            # 使用配置中指定的文件列表
            for f in config_files:
                file_path = self.data_dir / f
                if file_path.exists():
                    files.append(file_path)
                else:
                    print(f"[WARN] 配置文件不存在: {file_path}")
        else:
            # 没有配置文件列表，读取目录下所有xlsx文件
            files = list(self.data_dir.glob("*.xlsx"))
            print(f"[INFO] 数据域 {self.data_domain} 未配置文件列表，读取所有xlsx文件")

        # 排序以保证一致性
        files.sort(key=lambda x: x.name)
        return files

    @staticmethod
    def _read_excel_fallback(file_path: Path, sheet_name: str) -> pd.DataFrame:
        """当 openpyxl 因 custom.xml 过大崩溃时，用 zipfile + lxml 直接解析 xlsx"""
        import zipfile
        from lxml import etree

        NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        WB_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

        with zipfile.ZipFile(file_path) as z:
            # 1) 读 shared strings
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                tree = etree.parse(z.open("xl/sharedStrings.xml"), etree.XMLParser(huge_tree=True))
                for si in tree.findall(f"{{{NS}}}si"):
                    texts = si.itertext()
                    shared.append("".join(texts))

            # 2) 查找 sheet_name 对应的文件
            wb_tree = etree.parse(z.open("xl/workbook.xml"))
            sheet_map = {}
            for s in wb_tree.findall(f".//{{{WB_NS}}}sheet"):
                sheet_map[s.get("name")] = s.get("sheetId")

            if sheet_name not in sheet_map:
                raise ValueError(f"Worksheet named '{sheet_name}' not found")

            # workbook.xml 中的 sheetId 不直接对应文件名，需从 rels 获取
            rels_tree = etree.parse(z.open("xl/_rels/workbook.xml.rels"))
            rid_map = {}
            for rel in rels_tree.getroot():
                rid_map[rel.get("Id")] = rel.get("Target")

            # 找 rId
            rid = None
            for s in wb_tree.findall(f".//{{{WB_NS}}}sheet"):
                if s.get("name") == sheet_name:
                    rid = s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    break

            if not rid or rid not in rid_map:
                raise ValueError(f"Cannot resolve sheet file for '{sheet_name}'")

            sheet_file = "xl/" + rid_map[rid]

            # 3) 解析 sheet XML
            sheet_tree = etree.parse(z.open(sheet_file), etree.XMLParser(huge_tree=True))
            rows_data = []
            for row_el in sheet_tree.findall(f".//{{{NS}}}row"):
                row_dict = {}
                for cell in row_el.findall(f"{{{NS}}}c"):
                    ref = cell.get("r", "")  # e.g. "A1"
                    col_letter = "".join(c for c in ref if c.isalpha())
                    val_el = cell.find(f"{{{NS}}}v")
                    val = val_el.text if val_el is not None else ""
                    if cell.get("t") == "s" and val:
                        val = shared[int(val)] if int(val) < len(shared) else val
                    row_dict[col_letter] = val
                rows_data.append(row_dict)

            if not rows_data:
                return pd.DataFrame()

            # 第一行作为列名
            header = rows_data[0]
            col_map = {letter: name for letter, name in header.items()}
            data = []
            for row_dict in rows_data[1:]:
                named_row = {col_map.get(k, k): v for k, v in row_dict.items()}
                data.append(named_row)

            return pd.DataFrame(data)

    def _read_concept_entities(self, file_path: Path):
        """读取概念实体清单"""
        sheet_name = self.config.get("sheet_config", {}).get("concept", "DA-01 数据实体清单-概念实体清单")
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            seen = set()
            for idx, row in df.iterrows():
                name = str(row.get("概念实体", "")).strip()
                if name and name != "nan" and name not in seen:
                    seen.add(name)
                    # 优先使用Excel中的数据域，如果为空则使用配置的数据域
                    excel_domain = str(row.get("数据域", "")).strip()
                    domain = excel_domain if excel_domain and excel_domain != "nan" else self.data_domain
                    self.entities.append(EntityInfo(
                        name=name,
                        layer="CONCEPT",
                        code=str(row.get("概念实体编号", "")).strip(),
                        data_domain=domain,
                        data_subdomain=str(row.get("数据子域", "")).strip(),
                        source_file=str(file_path.name),
                        source_sheet=sheet_name,
                        source_row=idx + 2
                    ))
        except Exception as e:
            print(f"[WARN] pd.read_excel 读取概念实体失败 ({file_path.name}): {e}")
            try:
                print(f"[INFO] 尝试 fallback 解析 {file_path.name}...")
                df = self._read_excel_fallback(file_path, sheet_name)
                seen_fb = set()
                for idx, row in df.iterrows():
                    name = str(row.get("概念实体", "")).strip()
                    if name and name != "nan" and name != "" and name not in seen_fb:
                        seen_fb.add(name)
                        excel_domain = str(row.get("数据域", "")).strip()
                        domain = excel_domain if excel_domain and excel_domain != "nan" else self.data_domain
                        self.entities.append(EntityInfo(
                            name=name, layer="CONCEPT",
                            code=str(row.get("概念实体编号", "")).strip(),
                            data_domain=domain,
                            data_subdomain=str(row.get("数据子域", "")).strip(),
                            source_file=str(file_path.name),
                            source_sheet=sheet_name, source_row=idx + 2
                        ))
                print(f"[INFO] fallback 成功，读取到 {len(seen_fb)} 个概念实体")
            except Exception as e2:
                print(f"[ERROR] fallback 也失败 ({file_path.name}): {e2}")

    def _read_logical_entities(self, file_path: Path):
        """读取逻辑实体清单"""
        sheet_name = self.config.get("sheet_config", {}).get("logical", "DA-02 数据实体清单-逻辑实体清单")
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            seen = set()
            for idx, row in df.iterrows():
                name = str(row.get("逻辑实体名称", "")).strip()
                if name and name != "nan" and name not in seen:
                    seen.add(name)
                    excel_domain = str(row.get("数据域", "")).strip()
                    domain = excel_domain if excel_domain and excel_domain != "nan" else self.data_domain
                    self.entities.append(EntityInfo(
                        name=name,
                        layer="LOGICAL",
                        code=str(row.get("逻辑实体编码", "")).strip(),
                        data_domain=domain,
                        source_file=str(file_path.name),
                        source_sheet=sheet_name,
                        source_row=idx + 2
                    ))
        except Exception as e:
            print(f"[ERROR] 读取逻辑实体失败 ({file_path.name}): {e}")

    def read_concept_with_mapping(self) -> Tuple[List['EntityInfo'], Dict[str, List['EntityInfo']], Dict[str, List['EntityInfo']]]:
        """读取概念实体 + 构建概念→逻辑实体映射 + 逻辑→物理实体映射

        只用概念实体做聚类，逻辑实体通过映射间接关联，物理实体通过逻辑实体间接关联。

        Returns:
            concept_entities: 概念实体列表（用于聚类）
            concept_to_logical: {概念实体名称: [逻辑实体EntityInfo列表]}
            logical_to_physical: {逻辑实体名称: [物理实体EntityInfo列表]}
        """
        print(f"[INFO] 读取概念实体 + 概念→逻辑映射 + 逻辑→物理映射 (域: {self.data_domain})...")

        files_to_read = self._get_files_to_read()
        if not files_to_read:
            print(f"[WARN] 未找到数据文件")
            return [], {}, {}

        concept_to_logical: Dict[str, List[EntityInfo]] = defaultdict(list)
        logical_to_physical: Dict[str, List[EntityInfo]] = defaultdict(list)

        for data_file in files_to_read:
            print(f"  读取 {data_file}...")
            self._read_concept_entities(data_file)
            self._build_concept_logical_mapping(data_file, concept_to_logical)
            self._build_logical_physical_mapping(data_file, logical_to_physical)

        concept_entities = [e for e in self.entities if e.layer == "CONCEPT"]
        total_logical = sum(len(v) for v in concept_to_logical.values())
        total_physical = sum(len(v) for v in logical_to_physical.values())
        print(f"[INFO] 读取完成:")
        print(f"  - 概念实体: {len(concept_entities)} 个")
        print(f"  - 概念→逻辑映射: {len(concept_to_logical)} 个概念实体 → {total_logical} 个逻辑实体")
        print(f"  - 逻辑→物理映射: {len(logical_to_physical)} 个逻辑实体 → {total_physical} 个物理实体")

        return concept_entities, dict(concept_to_logical), dict(logical_to_physical)

    def _build_concept_logical_mapping(self, file_path: Path,
                                        mapping: Dict[str, List['EntityInfo']]):
        """从 DA-02 构建概念实体→逻辑实体映射"""
        sheet_name = self.config.get("sheet_config", {}).get("logical",
                     "DA-02 数据实体清单-逻辑实体清单")
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            seen: Set[Tuple[str, str]] = set()

            for idx, row in df.iterrows():
                concept_name = str(row.get("概念实体", "")).strip()
                logical_name = str(row.get("逻辑实体名称", "")).strip()

                if (not concept_name or concept_name == "nan"
                        or not logical_name or logical_name == "nan"):
                    continue

                key = (concept_name, logical_name)
                if key in seen:
                    continue
                seen.add(key)

                excel_domain = str(row.get("数据域", "")).strip()
                domain = excel_domain if excel_domain and excel_domain != "nan" else self.data_domain

                mapping[concept_name].append(EntityInfo(
                    name=logical_name,
                    layer="LOGICAL",
                    code=str(row.get("逻辑实体编码", "")).strip(),
                    data_domain=domain,
                    source_file=str(file_path.name),
                    source_sheet=sheet_name,
                    source_row=idx + 2
                ))
        except Exception as e:
            print(f"[WARN] pd.read_excel 构建概念→逻辑映射失败 ({file_path.name}): {e}")
            try:
                print(f"[INFO] 尝试 fallback 解析 DA-02 ({file_path.name})...")
                df = self._read_excel_fallback(file_path, sheet_name)
                seen_fb: Set[Tuple[str, str]] = set()
                count = 0
                for idx, row in df.iterrows():
                    concept_name = str(row.get("概念实体", "")).strip()
                    logical_name = str(row.get("逻辑实体名称", "")).strip()
                    if (not concept_name or concept_name == "nan"
                            or not logical_name or logical_name == "nan"):
                        continue
                    key = (concept_name, logical_name)
                    if key in seen_fb:
                        continue
                    seen_fb.add(key)
                    excel_domain = str(row.get("数据域", "")).strip()
                    domain = excel_domain if excel_domain and excel_domain != "nan" else self.data_domain
                    mapping[concept_name].append(EntityInfo(
                        name=logical_name, layer="LOGICAL",
                        code=str(row.get("逻辑实体编码", "")).strip(),
                        data_domain=domain,
                        data_subdomain=str(row.get("数据子域", "")).strip(),
                        source_file=str(file_path.name),
                        source_sheet=sheet_name, source_row=idx + 2
                    ))
                    count += 1
                print(f"[INFO] fallback 成功，构建 {len(set(k for k,_ in seen_fb))} 个概念→{count} 个逻辑映射")
            except Exception as e2:
                print(f"[ERROR] fallback 也失败 ({file_path.name}): {e2}")

    def _build_logical_physical_mapping(self, file_path: Path,
                                         mapping: Dict[str, List['EntityInfo']]):
        """从 DA-03 构建逻辑实体→物理实体映射"""
        sheet_name = self.config.get("sheet_config", {}).get("physical",
                     "DA-03数据实体清单-物理实体清单")
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            seen: Set[Tuple[str, str]] = set()

            for idx, row in df.iterrows():
                logical_name = str(row.get("逻辑实体名称", "")).strip()
                physical_name = str(row.get("物理实体名称", "")).strip()

                if (not logical_name or logical_name == "nan"
                        or not physical_name or physical_name == "nan"):
                    continue

                key = (logical_name, physical_name)
                if key in seen:
                    continue
                seen.add(key)

                excel_domain = str(row.get("数据域", "")).strip()
                domain = excel_domain if excel_domain and excel_domain != "nan" else self.data_domain

                mapping[logical_name].append(EntityInfo(
                    name=physical_name,
                    layer="PHYSICAL",
                    code=str(row.get("物理实体编码", "")).strip(),
                    data_domain=domain,
                    source_file=str(file_path.name),
                    source_sheet=sheet_name,
                    source_row=idx + 2
                ))
        except Exception as e:
            print(f"[WARN] 构建逻辑→物理映射失败 ({file_path.name}): {e}")

    def _read_physical_entities(self, file_path: Path):
        """读取物理实体清单"""
        sheet_name = self.config.get("sheet_config", {}).get("physical", "DA-03数据实体清单-物理实体清单")
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            seen = set()
            for idx, row in df.iterrows():
                name = str(row.get("物理实体名称", "")).strip()
                if name and name != "nan" and name not in seen:
                    seen.add(name)
                    excel_domain = str(row.get("数据域", "")).strip()
                    domain = excel_domain if excel_domain and excel_domain != "nan" else self.data_domain
                    self.entities.append(EntityInfo(
                        name=name,
                        layer="PHYSICAL",
                        code=str(row.get("物理实体编码", "")).strip(),
                        data_domain=domain,
                        source_file=str(file_path.name),
                        source_sheet=sheet_name,
                        source_row=idx + 2
                    ))
        except Exception as e:
            print(f"[ERROR] 读取物理实体失败 ({file_path.name}): {e}")


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
# 层级关联关系构建器（新模型）
# ============================================================

class HierarchicalRelationBuilder:
    """层级关联关系构建器

    正确的关系模型：
    - 对象 → 概念实体：DIRECT（来自聚类归属）
    - 对象 → 逻辑实体：INDIRECT（通过概念实体间接关联）
    - 逻辑实体和对象没有直接关系，通过概念实体产生关系
    """

    def __init__(self,
                 objects: List[ExtractedObject],
                 cluster_entity_map: Dict[int, List[str]],
                 concept_entities: List[EntityInfo],
                 concept_to_logical: Dict[str, List[EntityInfo]],
                 logical_to_physical: Dict[str, List[EntityInfo]] = None):
        self.objects = objects
        self.cluster_entity_map = cluster_entity_map
        self.concept_to_logical = concept_to_logical
        self.logical_to_physical = logical_to_physical or {}

        # 构建概念实体名称 → EntityInfo 的映射
        self.concept_info_map: Dict[str, EntityInfo] = {}
        for ce in concept_entities:
            if ce.name not in self.concept_info_map:
                self.concept_info_map[ce.name] = ce

    def build_relations(self) -> List[EntityRelation]:
        """构建层级关联关系"""
        print("[INFO] 开始构建层级关联关系...")

        relations = []

        for obj in self.objects:
            if obj.cluster_id < 0:
                continue

            # 获取该对象对应聚类中的概念实体名称
            cluster_concepts = self.cluster_entity_map.get(obj.cluster_id, [])

            for concept_name in cluster_concepts:
                concept_info = self.concept_info_map.get(concept_name)
                if not concept_info:
                    continue

                # DIRECT: 对象 → 概念实体
                strength = 0.9 if concept_name in obj.sample_entities else 0.8
                relations.append(EntityRelation(
                    object_code=obj.object_code,
                    entity_layer="CONCEPT",
                    entity_name=concept_name,
                    entity_code=concept_info.code,
                    relation_type="DIRECT",
                    relation_strength=strength,
                    match_method="SEMANTIC_CLUSTER",
                    via_concept_entity="",
                    data_domain=concept_info.data_domain,
                    data_subdomain=concept_info.data_subdomain,
                    source_file=concept_info.source_file,
                    source_sheet=concept_info.source_sheet,
                    source_row=concept_info.source_row
                ))

                # INDIRECT: 对象 → 逻辑实体（通过该概念实体）
                logical_entities = self.concept_to_logical.get(concept_name, [])
                for le in logical_entities:
                    relations.append(EntityRelation(
                        object_code=obj.object_code,
                        entity_layer="LOGICAL",
                        entity_name=le.name,
                        entity_code=le.code,
                        relation_type="INDIRECT",
                        relation_strength=0.7,
                        match_method="SEMANTIC_CLUSTER",
                        via_concept_entity=concept_name,
                        data_domain=le.data_domain,
                        data_subdomain=le.data_subdomain,
                        source_file=le.source_file,
                        source_sheet=le.source_sheet,
                        source_row=le.source_row
                    ))

                    # INDIRECT: 对象 → 物理实体（通过逻辑实体间接关联）
                    physical_entities = self.logical_to_physical.get(le.name, [])
                    for pe in physical_entities:
                        relations.append(EntityRelation(
                            object_code=obj.object_code,
                            entity_layer="PHYSICAL",
                            entity_name=pe.name,
                            entity_code=pe.code,
                            relation_type="INDIRECT",
                            relation_strength=0.6,
                            match_method="SEMANTIC_CLUSTER",
                            via_concept_entity=le.name,
                            data_domain=pe.data_domain,
                            data_subdomain=pe.data_subdomain,
                            source_file=pe.source_file,
                            source_sheet=pe.source_sheet,
                            source_row=pe.source_row
                        ))

        concept_count = len([r for r in relations if r.entity_layer == "CONCEPT"])
        logical_count = len([r for r in relations if r.entity_layer == "LOGICAL"])
        physical_count = len([r for r in relations if r.entity_layer == "PHYSICAL"])
        print(f"[INFO] 层级关联构建完成:")
        print(f"  - 对象→概念实体 (DIRECT): {concept_count} 条")
        print(f"  - 对象→逻辑实体 (INDIRECT): {logical_count} 条")
        print(f"  - 对象→物理实体 (INDIRECT): {physical_count} 条")
        print(f"  - 总计: {len(relations)} 条")
        return relations


# ============================================================
# 数据库写入器
# ============================================================

class DatabaseWriter:
    """数据库写入器 - 支持多数据域"""

    def __init__(self, host: str = "127.0.0.1", port: int = 3307,
                 user: str = "eav_user", password: str = "eavpass123", database: str = "eav_db",
                 data_domain: str = "default"):
        self.db_config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "charset": "utf8mb4"
        }
        self.data_domain = data_domain
        self.data_domain_name = get_domain_name(data_domain)

    def write_objects(self, objects: List[ExtractedObject], batch_id: int) -> Dict[str, int]:
        """写入对象到数据库（支持数据域）"""
        object_ids = {}

        with pymysql.connect(**self.db_config) as conn:
            with conn.cursor() as cursor:
                # 清理该域的旧数据（先删关联再删对象）
                print(f"[INFO] 清理域 {self.data_domain} 的旧数据...")
                cursor.execute("""
                    DELETE r FROM object_entity_relations r
                    JOIN extracted_objects o ON r.object_id = o.object_id
                    WHERE o.data_domain = %s
                """, (self.data_domain,))
                cursor.execute("""
                    DELETE FROM object_synonyms WHERE object_id IN
                    (SELECT object_id FROM extracted_objects WHERE data_domain = %s)
                """, (self.data_domain,))
                cursor.execute(
                    "DELETE FROM extracted_objects WHERE data_domain = %s",
                    (self.data_domain,)
                )
                conn.commit()
                print(f"[INFO] 旧数据清理完成")

                for obj in objects:
                    try:
                        # 对象编码需要加上域前缀以支持多域唯一性
                        domain_object_code = f"{obj.object_code}_{self.data_domain}" if self.data_domain != "default" else obj.object_code

                        sql = """
                        INSERT INTO extracted_objects
                        (object_code, object_name, object_name_en, object_type, data_domain,
                         description, extraction_source, extraction_confidence, llm_reasoning, is_verified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        object_name = VALUES(object_name),
                        description = VALUES(description),
                        extraction_source = VALUES(extraction_source),
                        extraction_confidence = VALUES(extraction_confidence),
                        llm_reasoning = VALUES(llm_reasoning)
                        """
                        cursor.execute(sql, (
                            domain_object_code, obj.object_name, obj.object_name_en,
                            obj.object_type, self.data_domain, obj.description, obj.extraction_source,
                            obj.extraction_confidence, obj.llm_reasoning, False
                        ))

                        # 查询时使用域限定
                        cursor.execute(
                            "SELECT object_id FROM extracted_objects WHERE object_code = %s AND data_domain = %s",
                            (domain_object_code, self.data_domain)
                        )
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

        print(f"[INFO] 成功写入 {len(object_ids)} 个对象 (域: {self.data_domain})")
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
                         relation_strength, match_method, via_concept_entity,
                         data_domain, data_subdomain, source_file, source_sheet, source_row)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql, (
                            object_id, rel.entity_layer, rel.entity_name, rel.entity_code,
                            rel.relation_type, rel.relation_strength, rel.match_method,
                            rel.via_concept_entity or None,
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
        """创建抽取批次（支持数据域）"""
        batch_code = f"SEMANTIC_{self.data_domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with pymysql.connect(**self.db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                INSERT INTO object_extraction_batches
                (batch_code, data_domain, data_domain_name, source_files, llm_model, status)
                VALUES (%s, %s, %s, %s, %s, 'RUNNING')
                """, (batch_code, self.data_domain, self.data_domain_name, json.dumps(source_files), llm_model))
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
    """语义聚类对象抽取流水线 - 支持多数据域"""

    def __init__(self, data_dir: str = "DATA", db_config: Dict = None,
                 target_clusters: int = TARGET_CLUSTER_COUNT,
                 data_domain: str = "default", excel_files: List[str] = None):
        """
        初始化流水线

        Args:
            data_dir: 数据目录路径
            db_config: 数据库配置
            target_clusters: 目标聚类数量
            data_domain: 数据域编码
            excel_files: 指定的Excel文件列表（覆盖域配置）
        """
        self.data_dir = data_dir
        self.db_config = db_config or {}
        self.target_clusters = target_clusters
        self.data_domain = data_domain
        self.data_domain_name = get_domain_name(data_domain)
        self.excel_files = excel_files

    def run(self, use_llm: bool = True) -> Dict:
        """执行抽取流水线"""
        print("=" * 60)
        print("语义聚类对象抽取流水线启动")
        print("=" * 60)
        print(f"算法：自下而上的归纳抽取")
        print(f"数据域：{self.data_domain} ({self.data_domain_name})")
        print(f"目标聚类数：{self.target_clusters}")
        print()

        # 1. 读取概念实体 + 概念→逻辑映射 + 逻辑→物理映射（只用概念实体聚类）
        reader = DataArchitectureReader(
            data_dir=self.data_dir,
            data_domain=self.data_domain,
            excel_files=self.excel_files
        )
        concept_entities, concept_to_logical, logical_to_physical = reader.read_concept_with_mapping()

        if not concept_entities:
            print("[ERROR] 没有读取到概念实体数据")
            return {"objects": [], "relations_count": 0, "stats": {}, "data_domain": self.data_domain}

        # 2. 只对概念实体做语义聚类
        extractor = SemanticClusterExtractor(target_clusters=self.target_clusters)
        clusters, cluster_entity_map = extractor.extract(concept_entities)

        print(f"\n[INFO] 聚类结果预览 (仅概念实体):")
        for cluster in clusters[:5]:
            print(f"  聚类{cluster['cluster_id']}: {cluster['size']}个概念实体, 代表: {cluster['centroid_entity']}")
            print(f"    样本: {cluster['sample_entities'][:5]}")

        # 3. 大模型归纳命名
        namer = LLMObjectNamer()
        if use_llm:
            objects = namer.name_clusters(clusters)
        else:
            objects = namer._rule_based_naming(clusters)

        print(f"\n[INFO] 抽取到 {len(objects)} 个核心对象:")
        for obj in objects:
            print(f"  - {obj.object_code}: {obj.object_name} ({obj.object_type}) [聚类{obj.cluster_id}, {obj.cluster_size}个概念实体]")

        # 4. 构建层级关联关系（对象→概念实体 DIRECT, 对象→逻辑实体 INDIRECT, 对象→物理实体 INDIRECT）
        builder = HierarchicalRelationBuilder(
            objects, cluster_entity_map, concept_entities, concept_to_logical, logical_to_physical
        )
        relations = builder.build_relations()

        # 5. 统计
        stats = self._compute_stats(objects, relations)
        print("\n[INFO] 关联关系统计:")
        for obj_code, obj_stats in stats.items():
            print(f"  {obj_code}:")
            print(f"    概念实体: {obj_stats['concept']} | 逻辑实体: {obj_stats['logical']} | 物理实体: {obj_stats['physical']}")

        # 6. 写入数据库（支持数据域）
        if self.db_config:
            try:
                # 传递data_domain到DatabaseWriter
                db_config_with_domain = {**self.db_config, "data_domain": self.data_domain}
                writer = DatabaseWriter(**db_config_with_domain)

                # 获取实际读取的文件列表
                source_files = self.excel_files or [f for f in os.listdir(self.data_dir) if f.endswith('.xlsx')]
                batch_id = writer.create_batch(source_files, "deepseek-chat")
                object_ids = writer.write_objects(objects, batch_id)
                rel_count = writer.write_relations(relations, object_ids)
                writer.update_batch(batch_id, len(objects), rel_count)
            except Exception as e:
                print(f"[ERROR] 数据库写入失败: {e}")

        return {
            "objects": [asdict(o) for o in objects],
            "clusters": [{k: v for k, v in c.items() if k != "all_entities"} for c in clusters],
            "relations": [asdict(r) for r in relations],  # 添加关联关系
            "relations_count": len(relations),
            "stats": stats,
            "data_domain": self.data_domain,
            "data_domain_name": self.data_domain_name
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
                "concept": len([r for r in obj_rels if r.entity_layer == "CONCEPT" and r.relation_type == "DIRECT"]),
                "logical": len([r for r in obj_rels if r.entity_layer == "LOGICAL" and r.relation_type == "INDIRECT"]),
                "physical": len([r for r in obj_rels if r.entity_layer == "PHYSICAL"]),
                "total": len(obj_rels)
            }
        return stats


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="语义聚类对象抽取器 - 支持多数据域")
    parser.add_argument("--data-dir", default="DATA", help="数据目录")
    parser.add_argument("--data-domain", default="default", help="数据域编码 (如 shupeidian, jicai)")
    parser.add_argument("--excel-files", nargs="+", default=None, help="指定要读取的Excel文件列表 (覆盖域配置)")
    parser.add_argument("--target-clusters", type=int, default=TARGET_CLUSTER_COUNT, help="目标聚类数量")
    parser.add_argument("--db-host", default="127.0.0.1", help="数据库主机")
    parser.add_argument("--db-port", type=int, default=3307, help="数据库端口")
    parser.add_argument("--db-user", default="eav_user", help="数据库用户")
    parser.add_argument("--db-password", default="eavpass123", help="数据库密码")
    parser.add_argument("--db-name", default="eav_db", help="数据库名称")
    parser.add_argument("--use-llm", action="store_true", help="使用大模型命名")
    parser.add_argument("--no-db", action="store_true", help="不写入数据库")
    parser.add_argument("--output", "-o", default=None, help="输出JSON文件路径")
    parser.add_argument("--list-domains", action="store_true", help="列出所有可用的数据域配置")

    args = parser.parse_args()

    # 列出可用的数据域
    if args.list_domains:
        print("可用的数据域配置:")
        print("-" * 50)
        for code, config in DOMAIN_CONFIG.items():
            files = config.get("files", [])
            files_str = ", ".join(files) if files else "(未配置文件)"
            print(f"  {code:15s} | {config['name']:10s} | {files_str}")
        exit(0)

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
        data_dir=args.data_dir,
        db_config=db_config,
        target_clusters=args.target_clusters,
        data_domain=args.data_domain,
        excel_files=args.excel_files
    )
    result = pipeline.run(use_llm=args.use_llm)

    # 输出JSON结果
    print("\n" + "=" * 60)
    print("抽取结果摘要")
    print("=" * 60)
    print(f"数据域: {result.get('data_domain', 'default')} ({result.get('data_domain_name', '')})")
    print(f"核心对象数量: {len(result['objects'])}")
    print(f"关联关系数量: {result['relations_count']}")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")
