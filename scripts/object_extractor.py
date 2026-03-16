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

# 统一的工作表配置（所有域共用同一套算法和sheet名称）
DEFAULT_SHEET_CONFIG = {
    "concept": "DA-01 数据实体清单-概念实体清单",
    "logical": "DA-02 数据实体清单-逻辑实体清单",
    "physical": "DA-03数据实体清单-物理实体清单",
    "ba04": "BA-04 业务对象清单"
}

# 数据域定义（文件列表为空时自动从 DATA/<domain>/ 子目录发现）
DOMAIN_CONFIG = {
    "shupeidian": {
        "name": "输配电",
        "files": ["1.xlsx", "2.xlsx", "3.xlsx"],
        "sheet_config": DEFAULT_SHEET_CONFIG,
        "ba04_file": "1.xlsx"
    },
    "jicai": {
        "name": "计划财务",
        "files": ["1.xlsx", "2.xlsx", "3.xlsx"],
        "sheet_config": DEFAULT_SHEET_CONFIG,
        "ba04_file": "2.xlsx"
    },
    "default": {
        "name": "默认",
        "files": [],  # 空列表 = 自动发现
        "sheet_config": DEFAULT_SHEET_CONFIG,
    }
}

# 小对象合并阈值（聚类实体数低于此值的对象将自动合并到最近的大对象）
SMALL_OBJECT_THRESHOLD = 5

# 垃圾名称检测模式（匹配这些模式的对象名称会被强制标记为待合并）
import re
GARBAGE_NAME_PATTERNS = [
    re.compile(r'^[A-Za-z]{1,4}$'),           # 纯英文 1-4 字符（如 WH, AB, IT）
    re.compile(r'^[\u4e00-\u9fff]{1}$'),       # 单个中文字符
    re.compile(r'^[\u4e00-\u9fff]{2}$'),       # 两个中文字符（如 发放、主配、价信、填报、授权、日常、可再）
    re.compile(r'^\d+$'),                       # 纯数字
    re.compile(r'^[A-Za-z\d_-]{1,3}$'),        # 英文+数字 1-3 字符
]

def is_garbage_name(name: str) -> bool:
    """检测对象名称是否为低质量的垃圾名称。

    电力行业有大量合法的 2 字术语（计划、线路、监督、班站等），
    白名单覆盖常见业务概念，避免误判。
    """
    if not name:
        return True
    # 电力行业 + 通用业务领域的合法 2-4 字对象名称白名单
    KNOWN_GOOD_NAMES = {
        # 通用核心对象
        "项目", "设备", "资产", "合同", "人员", "物资", "文档",
        "指标", "系统", "任务", "预算", "票据", "报表", "审计",
        "组织", "流程", "标准", "规则", "模型", "方案", "目标",
        # 电力行业术语
        "线路", "电缆", "变压", "开关", "母线", "电容", "电抗",
        "配电", "输电", "变电", "用电", "发电", "调度", "运维",
        "巡检", "检修", "试验", "缺陷", "故障", "停电", "送电",
        "负荷", "功率", "电压", "电流", "频率", "谐波", "损耗",
        "台账", "运行", "监控", "测量", "保护", "接地", "绝缘",
        # 管理业务术语
        "计划", "监督", "班站", "考核", "评价", "培训", "安全",
        "采购", "仓储", "供应", "结算", "付款", "发票", "费用",
        "预警", "分析", "统计", "汇总", "核算", "拨款", "成本",
        "招标", "投标", "履约", "验收", "决算", "审价", "造价",
    }
    if name in KNOWN_GOOD_NAMES:
        return False
    return any(p.match(name) for p in GARBAGE_NAME_PATTERNS)


def get_domain_name(domain_code: str) -> str:
    """获取数据域的中文名称"""
    config = DOMAIN_CONFIG.get(domain_code, DOMAIN_CONFIG["default"])
    return config.get("name", domain_code)


def auto_discover_domains(data_dir: str = "DATA") -> Dict[str, Dict]:
    """自动发现 DATA/ 下的所有数据域子目录

    任何包含 .xlsx 文件的子目录都视为一个数据域。
    如果域未在 DOMAIN_CONFIG 中注册，则使用 default 配置。
    """
    data_path = Path(data_dir)
    discovered = {}
    if not data_path.exists():
        return discovered

    for subdir in sorted(data_path.iterdir()):
        if not subdir.is_dir():
            continue
        xlsx_files = sorted(subdir.glob("*.xlsx"))
        if not xlsx_files:
            continue
        domain_code = subdir.name
        config = DOMAIN_CONFIG.get(domain_code, {
            "name": domain_code,
            "files": [f.name for f in xlsx_files],
            "sheet_config": DEFAULT_SHEET_CONFIG,
        })
        # 如果域配置中 files 为空，自动填充
        if not config.get("files"):
            config["files"] = [f.name for f in xlsx_files]
        discovered[domain_code] = config
    return discovered


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
                    # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                    domain = self.data_domain
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
                        # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                        domain = self.data_domain
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
                    # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                    domain = self.data_domain
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

        # 如果物理实体映射为空（源数据缺失），从逻辑实体推断物理实体
        if total_physical == 0 and total_logical > 0:
            print(f"[WARN] DA-03 物理实体数据为空，从逻辑实体推断物理实体...")
            logical_to_physical = self._infer_physical_from_logical(
                concept_to_logical, logical_to_physical
            )
            total_physical = sum(len(v) for v in logical_to_physical.values())
            print(f"[INFO] 推断完成: {len(logical_to_physical)} 个逻辑实体 → {total_physical} 个物理实体")

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

                # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                domain = self.data_domain

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
                    # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                    domain = self.data_domain
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
            count = 0

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

                # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                domain = self.data_domain

                mapping[logical_name].append(EntityInfo(
                    name=physical_name,
                    layer="PHYSICAL",
                    code=str(row.get("物理实体编码", "")).strip(),
                    data_domain=domain,
                    source_file=str(file_path.name),
                    source_sheet=sheet_name,
                    source_row=idx + 2
                ))
                count += 1

            if count > 0:
                print(f"    逻辑→物理映射: {len(seen)} 对 ({file_path.name})")
        except Exception as e:
            print(f"[WARN] pd.read_excel 构建逻辑→物理映射失败 ({file_path.name}): {e}")
            try:
                print(f"[INFO] 尝试 fallback 解析 DA-03 ({file_path.name})...")
                df = self._read_excel_fallback(file_path, sheet_name)
                seen_fb: Set[Tuple[str, str]] = set()
                count = 0
                for idx, row in df.iterrows():
                    logical_name = str(row.get("逻辑实体名称", "")).strip()
                    physical_name = str(row.get("物理实体名称", "")).strip()
                    if (not logical_name or logical_name == "nan"
                            or not physical_name or physical_name == "nan"):
                        continue
                    key = (logical_name, physical_name)
                    if key in seen_fb:
                        continue
                    seen_fb.add(key)
                    # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                    domain = self.data_domain
                    mapping[logical_name].append(EntityInfo(
                        name=physical_name, layer="PHYSICAL",
                        code=str(row.get("物理实体编码", "")).strip(),
                        data_domain=domain,
                        source_file=str(file_path.name),
                        source_sheet=sheet_name, source_row=idx + 2
                    ))
                    count += 1
                print(f"[INFO] fallback 成功，构建 {len(set(k for k,_ in seen_fb))} 个逻辑→{count} 个物理映射")
            except Exception as e2:
                print(f"[WARN] fallback 也失败 ({file_path.name}): {e2}")

    def _infer_physical_from_logical(self,
                                     concept_to_logical: Dict[str, List['EntityInfo']],
                                     logical_to_physical: Dict[str, List['EntityInfo']]) -> Dict[str, List['EntityInfo']]:
        """当 DA-03 数据为空时，从逻辑实体推断物理实体

        策略：每个逻辑实体生成一个同名的推断物理实体，
        标记 match_method 为 INFERRED，relation_strength 较低。
        这样保证三层关联链路完整，前端可以展示。
        """
        inferred = defaultdict(list)
        seen = set()
        for concept_name, logical_list in concept_to_logical.items():
            for le in logical_list:
                if le.name in seen:
                    continue
                seen.add(le.name)
                # 用逻辑实体名称生成推断的物理实体
                inferred[le.name].append(EntityInfo(
                    name=f"{le.name}（推断）",
                    layer="PHYSICAL",
                    code=f"INFERRED_{le.code}" if le.code else "",
                    data_domain=le.data_domain,
                    data_subdomain=le.data_subdomain,
                    source_file=le.source_file,
                    source_sheet="INFERRED_FROM_DA02",
                    source_row=le.source_row
                ))
        # 合并已有映射（如果有的话）
        for k, v in logical_to_physical.items():
            if k in inferred:
                inferred[k].extend(v)
            else:
                inferred[k] = v
        return dict(inferred)

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
                    # data_domain 统一使用 CLI 传入的域编码，不读 Excel 中文名
                    domain = self.data_domain
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

    def read_business_objects_from_ba04(self) -> List[str]:
        """从 BA-04 业务对象清单读取唯一业务对象名称列表

        BA-04 sheet 存在于每个域的特定 Excel 文件中（由 ba04_file 配置指定）。
        列名"业务对象名称"或"业务对象名称 "（可能有尾部空格），用 strip 统一。
        """
        sheet_name = self.config.get("sheet_config", {}).get("ba04", "BA-04 业务对象清单")
        ba04_file = self.config.get("ba04_file")

        # 确定 BA-04 所在文件
        files_to_try = []
        if ba04_file:
            domain_subdir = self.data_dir / self.data_domain
            if domain_subdir.exists():
                files_to_try.append(domain_subdir / ba04_file)
            files_to_try.append(self.data_dir / ba04_file)
        else:
            files_to_try = self._get_files_to_read()

        business_objects = set()
        for file_path in files_to_try:
            if not file_path.exists():
                continue
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                # 列名可能是"业务对象名称"或"业务对象名称 "（带空格）
                col_name = None
                for c in df.columns:
                    if c.strip() == "业务对象名称":
                        col_name = c
                        break
                if col_name is None:
                    continue
                for val in df[col_name].dropna():
                    name = str(val).strip()
                    if name and name != "nan":
                        business_objects.add(name)
                print(f"[INFO] 从 {file_path.name}/{sheet_name} 读取到 {len(business_objects)} 个唯一业务对象")
                break  # 找到就停
            except Exception as e:
                print(f"[WARN] 读取 BA-04 失败 ({file_path.name}): {e}")

        return sorted(business_objects)

    def build_biz_object_to_concept_mapping(self) -> Dict[str, List[str]]:
        """从 DA-01 的"业务对象"列构建 业务对象→概念实体 映射

        DA-01 中每行有"业务对象"和"概念实体"两列，构成多对多映射。
        返回: {业务对象名称: [概念实体名称列表]}
        """
        sheet_name = self.config.get("sheet_config", {}).get("concept",
                     "DA-01 数据实体清单-概念实体清单")
        files_to_read = self._get_files_to_read()

        mapping: Dict[str, List[str]] = defaultdict(list)
        seen: Set[Tuple[str, str]] = set()

        for file_path in files_to_read:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if "业务对象" not in df.columns or "概念实体" not in df.columns:
                    continue
                for _, row in df.iterrows():
                    biz_obj = str(row.get("业务对象", "")).strip()
                    concept = str(row.get("概念实体", "")).strip()
                    if (not biz_obj or biz_obj == "nan"
                            or not concept or concept == "nan"):
                        continue
                    key = (biz_obj, concept)
                    if key not in seen:
                        seen.add(key)
                        mapping[biz_obj].append(concept)
            except Exception as e:
                print(f"[WARN] 构建业务对象→概念实体映射失败 ({file_path.name}): {e}")

        print(f"[INFO] 业务对象→概念实体映射: {len(mapping)} 个业务对象 → {sum(len(v) for v in mapping.values())} 个概念实体")
        return dict(mapping)


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

        # 5. 拆分超大聚类（占比 >50% 的聚类进行二次聚类）
        clusters, cluster_entity_map = self._split_oversized_clusters(
            clusters, cluster_entity_map, cluster_labels
        )

        print(f"[INFO] 聚类完成，共 {len(clusters)} 个聚类")
        return clusters, cluster_entity_map

    def _split_oversized_clusters(self, clusters: List[Dict],
                                   cluster_entity_map: Dict[int, List[str]],
                                   original_labels: np.ndarray
                                   ) -> Tuple[List[Dict], Dict[int, List[str]]]:
        """递归拆分占比超过 40% 的超大聚类，防止单个对象吞噬绝大多数实体。

        使用 40% 阈值而非 50%，确保拆分后的子聚类也不会过度主导。
        最多递归 3 层防止无限拆分。
        """
        total_entities = sum(c["size"] for c in clusters)
        if total_entities == 0:
            return clusters, cluster_entity_map

        name_to_idx = {n: i for i, n in enumerate(self.entity_names)}
        next_cluster_id = max(c["cluster_id"] for c in clusters) + 1

        def split_recursive(cluster_list, entity_map, depth=0, max_depth=3):
            nonlocal next_cluster_id
            if depth >= max_depth:
                return cluster_list, entity_map

            threshold = total_entities * 0.4
            oversized = [c for c in cluster_list if c["size"] > threshold]
            if not oversized:
                return cluster_list, entity_map

            result_clusters = [c for c in cluster_list if c["size"] <= threshold]
            result_map = {cid: ents for cid, ents in entity_map.items()
                          if any(c["cluster_id"] == cid for c in result_clusters)}

            for big_cluster in oversized:
                cid = big_cluster["cluster_id"]
                entity_list = entity_map[cid]
                n_sub = max(3, min(5, len(entity_list) // 50))
                print(f"[INFO] {'  ' * depth}拆分超大聚类 {cid} ({big_cluster['size']} 个实体, "
                      f"占比 {big_cluster['size']/total_entities*100:.1f}%) → {n_sub} 个子聚类")

                sub_indices = [name_to_idx[e] for e in entity_list if e in name_to_idx]
                if len(sub_indices) < n_sub:
                    result_clusters.append(big_cluster)
                    result_map[cid] = entity_list
                    continue

                sub_embeddings = self.embeddings[sub_indices]
                sub_names = [self.entity_names[i] for i in sub_indices]

                sub_clustering = AgglomerativeClustering(
                    n_clusters=n_sub, metric='cosine', linkage='average'
                )
                sub_labels = sub_clustering.fit_predict(sub_embeddings)

                sub_map_local: Dict[int, List[str]] = defaultdict(list)
                for idx, label in enumerate(sub_labels):
                    sub_map_local[int(label)].append(sub_names[idx])

                new_sub_clusters = []
                for sub_id, sub_entity_list in sub_map_local.items():
                    new_cid = next_cluster_id
                    next_cluster_id += 1

                    sub_idx_list = [name_to_idx[e] for e in sub_entity_list if e in name_to_idx]
                    sub_emb = self.embeddings[sub_idx_list]
                    centroid = np.mean(sub_emb, axis=0)
                    sims = cosine_similarity([centroid], sub_emb)[0]
                    centroid_entity = sub_entity_list[np.argmax(sims)]

                    sample_size = min(20, len(sub_entity_list))
                    sorted_idx = np.argsort(-sims)
                    sample_entities = [sub_entity_list[i] for i in sorted_idx[:sample_size]]

                    sc = {
                        "cluster_id": new_cid,
                        "size": len(sub_entity_list),
                        "centroid_entity": centroid_entity,
                        "sample_entities": sample_entities,
                        "all_entities": sub_entity_list
                    }
                    new_sub_clusters.append(sc)
                    result_map[new_cid] = sub_entity_list
                    print(f"[INFO] {'  ' * depth}  子聚类 {new_cid}: {len(sub_entity_list)} 个实体, "
                          f"代表: {centroid_entity}")

                result_clusters.extend(new_sub_clusters)

            # 递归检查新生成的子聚类是否仍然超大
            result_clusters, result_map = split_recursive(result_clusters, result_map, depth + 1, max_depth)
            result_clusters.sort(key=lambda x: x["size"], reverse=True)
            return result_clusters, result_map

        return split_recursive(clusters, cluster_entity_map)

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

        # 自适应聚类数量：每 20 个实体约 1 个聚类，范围 [5, 20]
        # 避免过多聚类导致大量 cluster_size=1 的碎片对象
        adaptive_count = max(5, min(20, n_samples // 20))
        n_clusters = min(self.target_clusters or adaptive_count, max(5, n_samples // 10))
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
            # 后命名语义去重：合并语义相近的对象和待合并对象
            objects = self._deduplicate_named_objects(objects)
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

    @staticmethod
    def _name_from_cluster_content(cluster: Dict, used_codes: set) -> Tuple[str, str, str]:
        """从聚类内容中提取最具代表性的短词作为对象名

        分析聚类的 centroid_entity 和 sample_entities，
        提取最常见的 2 字词作为对象名，避免"对象N"。
        """
        centroid = cluster.get("centroid_entity", "")
        samples = cluster.get("sample_entities", [])

        # 提取所有实体名中出现的 2-4 字常见子串
        word_counts = Counter()
        all_names = [centroid] + samples
        for name in all_names:
            if not name:
                continue
            # 提取 2 字和 3 字子串
            for length in (2, 3):
                for i in range(len(name) - length + 1):
                    word = name[i:i+length]
                    # 过滤掉纯数字、含标点的
                    if any(c in word for c in "0123456789-_()（）、，。 "):
                        continue
                    word_counts[word] += 1

        # 排除已被使用的关键词
        existing_names = {"信息", "数据", "管理", "记录", "清单", "明细", "编码", "名称", "类型", "状态"}

        # 质量门槛：最佳候选子串出现次数 >= 3 才创建独立对象
        MIN_NAME_FREQUENCY = 3

        if word_counts:
            for word, count in word_counts.most_common(20):
                if word in existing_names:
                    continue
                # 垃圾名称检测：即使频率足够，低质量名称也标记为待合并
                if is_garbage_name(word):
                    continue
                if count < MIN_NAME_FREQUENCY:
                    # 出现次数不足，标记为待合并（返回特殊前缀）
                    code = f"OBJ__PENDING_MERGE_{cluster.get('cluster_id', 0)}"
                    return word, word, code
                code = f"OBJ_{word}"
                if code not in used_codes:
                    return word, word, code

        # 最终回退：标记为待合并
        cid = cluster.get("cluster_id", 0)
        centroid_label = centroid[:4] if centroid and len(centroid) >= 4 else f"聚类{cid + 1}"
        return centroid_label, centroid_label, f"OBJ__PENDING_MERGE_{cid}"

    # 必需对象的标准编码映射（避免中文 upper() 问题）
    REQUIRED_OBJECT_CODE_MAP = {
        "项目": ("OBJ_PROJECT", "Project"),
        "设备": ("OBJ_DEVICE", "Device"),
        "资产": ("OBJ_ASSET", "Asset"),
    }

    def _ensure_required_objects(self, objects: List[ExtractedObject], clusters: List[Dict]) -> List[ExtractedObject]:
        """确保必须的对象存在（不重复已有对象的聚类）"""
        object_names = {obj.object_name for obj in objects}
        used_cluster_ids = {obj.cluster_id for obj in objects if obj.cluster_id >= 0}

        for required in REQUIRED_OBJECTS:
            if required not in object_names:
                print(f"[INFO] 补充必须对象: {required}")
                # 找到最可能对应且未被占用的聚类
                best_cluster = None
                best_score = 0
                for cluster in clusters:
                    if cluster["cluster_id"] in used_cluster_ids:
                        continue
                    score = sum(1 for e in cluster["sample_entities"] if required in e)
                    if score > best_score:
                        best_score = score
                        best_cluster = cluster

                # 如果所有聚类都被占用，不分配聚类ID（避免与其他对象重复）
                cid = best_cluster["cluster_id"] if best_cluster else -1
                csize = best_cluster["size"] if best_cluster else 0
                if cid >= 0:
                    used_cluster_ids.add(cid)

                # 使用标准编码映射
                code_info = self.REQUIRED_OBJECT_CODE_MAP.get(required)
                obj_code = code_info[0] if code_info else f"OBJ_{required}"
                obj_name_en = code_info[1] if code_info else required.title()

                objects.append(ExtractedObject(
                    object_code=obj_code,
                    object_name=required,
                    object_name_en=obj_name_en,
                    object_type="CORE",
                    description=f"核心对象：{required}",
                    extraction_source="REQUIRED",
                    extraction_confidence=1.0,
                    cluster_id=cid,
                    cluster_size=csize
                ))

        return objects

    def _deduplicate_named_objects(self, objects: List[ExtractedObject]) -> List[ExtractedObject]:
        """后命名语义去重：合并语义相近对象和待合并（PENDING_MERGE）对象

        策略：
        1. 先处理 _PENDING_MERGE_ 对象：找到语义最近的正常对象合并进去
        2. 再检查正常对象间的语义重复（名称/同义词交叉）
        """
        if len(objects) <= 1:
            return objects

        # 分离正常对象和待合并对象
        normal = [o for o in objects if "_PENDING_MERGE_" not in o.object_code]
        pending = [o for o in objects if "_PENDING_MERGE_" in o.object_code]

        if pending:
            print(f"[INFO] 后命名去重：{len(pending)} 个待合并对象需处理")

        # 步骤1：将待合并对象合并到语义最近的正常对象
        for p_obj in pending:
            if not normal:
                break
            # 用 sample_entities 关键词重叠度找最佳目标
            best_target, best_score = None, 0
            p_keywords = set()
            for e in p_obj.sample_entities:
                for length in (2, 3):
                    for i in range(len(e) - length + 1):
                        p_keywords.add(e[i:i+length])

            for n_obj in normal:
                n_keywords = set()
                for e in n_obj.sample_entities:
                    for length in (2, 3):
                        for i in range(len(e) - length + 1):
                            n_keywords.add(e[i:i+length])
                overlap = len(p_keywords & n_keywords)
                if overlap > best_score:
                    best_score, best_target = overlap, n_obj

            # 当关键词重叠为0时，回退到最长公共子串匹配
            if best_score == 0 and normal:
                p_text = " ".join(p_obj.sample_entities)
                best_lcs, best_target = 0, normal[0]
                for n_obj in normal:
                    n_text = " ".join(n_obj.sample_entities)
                    # 计算实体名称中共享的任意3字子串数
                    shared_chars = sum(1 for c in set(p_text) if c in n_text)
                    if shared_chars > best_lcs:
                        best_lcs, best_target = shared_chars, n_obj

            if best_target:
                # 合并 sample_entities
                merged_samples = list(set(best_target.sample_entities + p_obj.sample_entities))
                best_target.sample_entities = merged_samples[:20]
                best_target.cluster_size = max(best_target.cluster_size,
                                               best_target.cluster_size + p_obj.cluster_size)
                print(f"  待合并 '{p_obj.object_name}' → 合入 '{best_target.object_name}'")

        # 步骤1.5：检查正常对象中的垃圾名称，降级为待合并
        garbage_from_normal = []
        remaining_normal = []
        for obj in normal:
            if is_garbage_name(obj.object_name) and obj.object_name not in set(REQUIRED_OBJECTS):
                garbage_from_normal.append(obj)
            else:
                remaining_normal.append(obj)
        if garbage_from_normal:
            print(f"[INFO] 检测到 {len(garbage_from_normal)} 个垃圾名称对象，降级合并:")
            for g_obj in garbage_from_normal:
                if not remaining_normal:
                    remaining_normal.append(g_obj)
                    continue
                # 找最大的正常对象合并
                target = max(remaining_normal, key=lambda o: o.cluster_size)
                merged_samples = list(set(target.sample_entities + g_obj.sample_entities))
                target.sample_entities = merged_samples[:20]
                target.cluster_size += g_obj.cluster_size
                print(f"  垃圾名称 '{g_obj.object_name}' → 合入 '{target.object_name}'")
        normal = remaining_normal

        # 步骤2：检查正常对象间的语义重复（名称完全相同或名称出现在对方同义词中）
        to_remove = set()
        for i, obj_a in enumerate(normal):
            if i in to_remove:
                continue
            for j in range(i + 1, len(normal)):
                if j in to_remove:
                    continue
                obj_b = normal[j]

                # 检查名称相同
                name_match = (obj_a.object_name == obj_b.object_name)

                # 检查同义词交叉
                synonyms_a = set(getattr(obj_a, 'synonyms', []) or [])
                synonyms_b = set(getattr(obj_b, 'synonyms', []) or [])
                cross_match = (obj_a.object_name in synonyms_b or
                               obj_b.object_name in synonyms_a)

                if name_match or cross_match:
                    # 合并小→大
                    if obj_a.cluster_size >= obj_b.cluster_size:
                        keeper, victim, victim_idx = obj_a, obj_b, j
                    else:
                        keeper, victim, victim_idx = obj_b, obj_a, i
                    keeper.cluster_size += victim.cluster_size
                    merged = list(set(keeper.sample_entities + victim.sample_entities))
                    keeper.sample_entities = merged[:20]
                    to_remove.add(victim_idx)
                    print(f"  语义重复 '{victim.object_name}' → 合入 '{keeper.object_name}'")

        result = [o for i, o in enumerate(normal) if i not in to_remove]
        removed_count = len(objects) - len(result)
        if removed_count > 0:
            print(f"[INFO] 后命名去重完成：去除 {removed_count} 个对象，剩余 {len(result)} 个")
        return result

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
            # ---- 扩展映射：减少垃圾名回退 ----
            "票据": ("OBJ_VOUCHER", "票据", "Voucher", "AUXILIARY", "财务票据凭证"),
            "凭证": ("OBJ_VOUCHER", "票据", "Voucher", "AUXILIARY", "财务票据凭证"),
            "发票": ("OBJ_VOUCHER", "票据", "Voucher", "AUXILIARY", "财务票据凭证"),
            "监督": ("OBJ_AUDIT", "监督", "Audit", "AUXILIARY", "监督稽查"),
            "稽查": ("OBJ_AUDIT", "监督", "Audit", "AUXILIARY", "监督稽查"),
            "检查": ("OBJ_AUDIT", "监督", "Audit", "AUXILIARY", "监督稽查"),
            "发电": ("OBJ_GENERATION", "发电", "Generation", "CORE", "发电生产"),
            "电站": ("OBJ_GENERATION", "发电", "Generation", "CORE", "发电生产"),
            "机组": ("OBJ_GENERATION", "发电", "Generation", "CORE", "发电生产"),
            "线路": ("OBJ_LINE", "线路", "Line", "CORE", "输配电线路"),
            "电缆": ("OBJ_LINE", "线路", "Line", "CORE", "输配电线路"),
            "杆塔": ("OBJ_LINE", "线路", "Line", "CORE", "输配电线路"),
            "班组": ("OBJ_TEAM", "班站", "Team", "AUXILIARY", "班组站所"),
            "班站": ("OBJ_TEAM", "班站", "Team", "AUXILIARY", "班组站所"),
            "供电所": ("OBJ_TEAM", "班站", "Team", "AUXILIARY", "班组站所"),
            "授权": ("OBJ_PROCESS", "流程", "Process", "AUXILIARY", "业务流程"),
            "权限": ("OBJ_PROCESS", "流程", "Process", "AUXILIARY", "业务流程"),
            "计划": ("OBJ_PLAN", "计划", "Plan", "AUXILIARY", "业务计划"),
            "方案": ("OBJ_PLAN", "计划", "Plan", "AUXILIARY", "业务计划"),
            "配网": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备"),
            "主网": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备"),
            "台账": ("OBJ_LEDGER", "台账", "Ledger", "AUXILIARY", "设备资产台账"),
            "缺陷": ("OBJ_DEFECT", "缺陷", "Defect", "AUXILIARY", "缺陷故障"),
            "故障": ("OBJ_DEFECT", "缺陷", "Defect", "AUXILIARY", "缺陷故障"),
            "结算": ("OBJ_COST", "费用", "Cost", "DERIVED", "费用成本"),
            "付款": ("OBJ_COST", "费用", "Cost", "DERIVED", "费用成本"),
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
                # 无法通过关键词识别的聚类，从聚类内容中提取最有代表性的词作为名称
                obj_name, obj_name_en, obj_code = self._name_from_cluster_content(
                    cluster, used_codes
                )
                if obj_code not in used_codes:
                    used_codes.add(obj_code)
                    objects.append(ExtractedObject(
                        object_code=obj_code,
                        object_name=obj_name,
                        object_name_en=obj_name_en,
                        object_type="AUXILIARY",
                        description=f"语义聚类对象，代表性实体：{cluster['centroid_entity']}",
                        extraction_source="SEMANTIC_CLUSTER_AUTO",
                        extraction_confidence=0.5,
                        cluster_id=cluster["cluster_id"],
                        cluster_size=cluster["size"],
                        sample_entities=cluster["sample_entities"][:10]
                    ))

        # 确保必须的对象存在
        objects = self._ensure_required_objects(objects, clusters)
        # 后命名语义去重
        objects = self._deduplicate_named_objects(objects)
        return objects


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
# BA-04 业务对象桥接匹配器
# ============================================================

class BusinessObjectMatcher:
    """通过 BA-04 业务对象做桥梁，将抽取对象与三层实体关联

    匹配路径: 抽取对象 → (语义匹配) → 业务对象 → (DA-01映射) → 概念实体 → 逻辑实体 → 物理实体
    """

    def __init__(self,
                 biz_obj_to_concept: Dict[str, List[str]],
                 concept_to_logical: Dict[str, List[EntityInfo]],
                 logical_to_physical: Dict[str, List[EntityInfo]],
                 concept_info_map: Dict[str, EntityInfo]):
        self.biz_obj_to_concept = biz_obj_to_concept
        self.concept_to_logical = concept_to_logical
        self.logical_to_physical = logical_to_physical
        self.concept_info_map = concept_info_map

    def match_objects(self, extracted_objects: List[ExtractedObject],
                      business_objects: List[str]) -> Dict[str, List[Tuple[str, float]]]:
        """将抽取对象与业务对象匹配

        策略: 用抽取对象的 sample_entities 与业务对象名称做精确/模糊匹配。
        每个抽取对象的 sample_entities 是聚类中最具代表性的概念实体名称，
        而 DA-01 中"业务对象"列的值就是概念实体的上层分组名。

        Returns: {object_code: [(business_object_name, match_score), ...]}
        """
        print(f"[INFO] 开始 BA-04 业务对象匹配... ({len(extracted_objects)} 个对象 × {len(business_objects)} 个业务对象)")

        # 构建概念实体→业务对象的反向索引
        concept_to_biz: Dict[str, List[str]] = defaultdict(list)
        for biz_name, concepts in self.biz_obj_to_concept.items():
            for c in concepts:
                concept_to_biz[c].append(biz_name)

        matches: Dict[str, List[Tuple[str, float]]] = {}
        for obj in extracted_objects:
            obj_matches: Dict[str, float] = {}

            # 通过聚类中的概念实体找到对应的业务对象
            for entity_name in obj.sample_entities:
                for biz_name in concept_to_biz.get(entity_name, []):
                    # 越多概念实体指向同一个业务对象，匹配分越高
                    obj_matches[biz_name] = obj_matches.get(biz_name, 0) + 1.0

            if obj_matches:
                # 归一化分数
                max_score = max(obj_matches.values())
                sorted_matches = sorted(
                    [(name, score / max_score) for name, score in obj_matches.items()],
                    key=lambda x: -x[1]
                )
                matches[obj.object_code] = sorted_matches
            else:
                matches[obj.object_code] = []

        matched_count = sum(1 for v in matches.values() if v)
        total_biz_matched = sum(len(v) for v in matches.values())
        print(f"[INFO] BA-04 匹配完成: {matched_count}/{len(extracted_objects)} 个对象找到匹配, 共匹配 {total_biz_matched} 个业务对象")
        return matches

    def build_bridged_relations(self,
                                matches: Dict[str, List[Tuple[str, float]]],
                                existing_relations: List[EntityRelation]) -> List[EntityRelation]:
        """通过 BA-04 业务对象桥梁构建补充关联

        只添加现有聚类关联中未覆盖的实体关联，避免重复。
        """
        # 构建已有关联集合（用于去重）
        existing_keys: Set[Tuple[str, str, str]] = set()
        for r in existing_relations:
            existing_keys.add((r.object_code, r.entity_layer, r.entity_name))

        new_relations: List[EntityRelation] = []

        for obj_code, biz_matches in matches.items():
            for biz_name, match_score in biz_matches:
                # 通过业务对象→概念实体映射
                concepts = self.biz_obj_to_concept.get(biz_name, [])
                for concept_name in concepts:
                    concept_info = self.concept_info_map.get(concept_name)
                    if not concept_info:
                        continue

                    # 概念层关联（如果不在已有关联中）
                    key_c = (obj_code, "CONCEPT", concept_name)
                    if key_c not in existing_keys:
                        existing_keys.add(key_c)
                        new_relations.append(EntityRelation(
                            object_code=obj_code,
                            entity_layer="CONCEPT",
                            entity_name=concept_name,
                            entity_code=concept_info.code,
                            relation_type="INDIRECT",
                            relation_strength=round(0.75 * match_score, 4),
                            match_method="BA04_BRIDGE",
                            via_concept_entity=biz_name,
                            data_domain=concept_info.data_domain,
                            data_subdomain=concept_info.data_subdomain,
                            source_file=concept_info.source_file,
                            source_sheet=concept_info.source_sheet,
                            source_row=concept_info.source_row
                        ))

                    # 逻辑层关联
                    for le in self.concept_to_logical.get(concept_name, []):
                        key_l = (obj_code, "LOGICAL", le.name)
                        if key_l not in existing_keys:
                            existing_keys.add(key_l)
                            new_relations.append(EntityRelation(
                                object_code=obj_code,
                                entity_layer="LOGICAL",
                                entity_name=le.name,
                                entity_code=le.code,
                                relation_type="INDIRECT",
                                relation_strength=round(0.55 * match_score, 4),
                                match_method="BA04_BRIDGE",
                                via_concept_entity=concept_name,
                                data_domain=le.data_domain,
                                data_subdomain=le.data_subdomain,
                                source_file=le.source_file,
                                source_sheet=le.source_sheet,
                                source_row=le.source_row
                            ))

                    # 物理层关联
                    for le in self.concept_to_logical.get(concept_name, []):
                        for pe in self.logical_to_physical.get(le.name, []):
                            key_p = (obj_code, "PHYSICAL", pe.name)
                            if key_p not in existing_keys:
                                existing_keys.add(key_p)
                                new_relations.append(EntityRelation(
                                    object_code=obj_code,
                                    entity_layer="PHYSICAL",
                                    entity_name=pe.name,
                                    entity_code=pe.code,
                                    relation_type="INDIRECT",
                                    relation_strength=round(0.45 * match_score, 4),
                                    match_method="BA04_BRIDGE",
                                    via_concept_entity=le.name,
                                    data_domain=pe.data_domain,
                                    data_subdomain=pe.data_subdomain,
                                    source_file=pe.source_file,
                                    source_sheet=pe.source_sheet,
                                    source_row=pe.source_row
                                ))

        if new_relations:
            c_new = len([r for r in new_relations if r.entity_layer == "CONCEPT"])
            l_new = len([r for r in new_relations if r.entity_layer == "LOGICAL"])
            p_new = len([r for r in new_relations if r.entity_layer == "PHYSICAL"])
            print(f"[INFO] BA-04 桥接新增关联:")
            print(f"  - 概念实体: +{c_new} 条")
            print(f"  - 逻辑实体: +{l_new} 条")
            print(f"  - 物理实体: +{p_new} 条")
        else:
            print(f"[INFO] BA-04 桥接未产生新增关联（已被聚类关联覆盖）")

        return new_relations


# ============================================================
# 小对象处理器
# ============================================================

class SmallObjectHandler:
    """识别和处理实体数量过少的对象"""

    def __init__(self, min_entity_count: int = 3):
        self.min_entity_count = min_entity_count

    def identify_small_objects(self, objects: List[ExtractedObject]) -> List[ExtractedObject]:
        """识别聚类大小低于阈值的对象"""
        small = [o for o in objects if o.cluster_size < self.min_entity_count]
        if small:
            print(f"[INFO] 发现 {len(small)} 个小对象 (cluster_size < {self.min_entity_count}):")
            for o in small:
                print(f"  - {o.object_code} ({o.object_name}): {o.cluster_size} 个实体")
        return small

    def find_merge_target(self, small_obj: ExtractedObject,
                          other_objects: List[ExtractedObject],
                          embeddings: np.ndarray = None,
                          entity_names: List[str] = None) -> Optional[ExtractedObject]:
        """找到与小对象语义最相近的大对象作为合并目标

        如果有 SBERT embeddings，用余弦相似度找最近的大聚类。
        否则用 sample_entities 的文本重叠度。
        """
        candidates = [o for o in other_objects
                      if o.object_code != small_obj.object_code
                      and o.cluster_size >= self.min_entity_count]
        if not candidates:
            return None

        if embeddings is not None and entity_names is not None and HAS_SKLEARN:
            # 用 SBERT embeddings 计算聚类中心相似度
            name_to_idx = {n: i for i, n in enumerate(entity_names)}
            small_indices = [name_to_idx[e] for e in small_obj.sample_entities if e in name_to_idx]
            if not small_indices:
                return candidates[0]

            small_center = np.mean(embeddings[small_indices], axis=0, keepdims=True)
            best_sim, best_target = -1, None
            for cand in candidates:
                cand_indices = [name_to_idx[e] for e in cand.sample_entities if e in name_to_idx]
                if not cand_indices:
                    continue
                cand_center = np.mean(embeddings[cand_indices], axis=0, keepdims=True)
                sim = cosine_similarity(small_center, cand_center)[0][0]
                if sim > best_sim:
                    best_sim, best_target = sim, cand
            return best_target
        else:
            # 文本重叠度 fallback
            small_set = set(small_obj.sample_entities)
            best_overlap, best_target = 0, None
            for cand in candidates:
                overlap = len(small_set & set(cand.sample_entities))
                if overlap > best_overlap:
                    best_overlap, best_target = overlap, cand
            return best_target or candidates[0]

    def merge_objects(self, source: ExtractedObject, target: ExtractedObject,
                      relations: List[EntityRelation]) -> List[EntityRelation]:
        """将 source 对象的关联合并到 target 对象，返回更新后的关联列表"""
        updated = []
        for r in relations:
            if r.object_code == source.object_code:
                # 将 source 的关联转移到 target
                updated.append(EntityRelation(
                    object_code=target.object_code,
                    entity_layer=r.entity_layer,
                    entity_name=r.entity_name,
                    entity_code=r.entity_code,
                    relation_type=r.relation_type,
                    relation_strength=r.relation_strength * 0.9,
                    match_method=r.match_method,
                    via_concept_entity=r.via_concept_entity,
                    data_domain=r.data_domain,
                    data_subdomain=r.data_subdomain,
                    source_file=r.source_file,
                    source_sheet=r.source_sheet,
                    source_row=r.source_row
                ))
            else:
                updated.append(r)
        # 去重
        seen: Set[Tuple[str, str, str]] = set()
        deduped = []
        for r in updated:
            key = (r.object_code, r.entity_layer, r.entity_name)
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped


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
                 data_domain: str = "default", excel_files: List[str] = None,
                 min_cluster_size: int = SMALL_OBJECT_THRESHOLD):
        """
        初始化流水线

        Args:
            data_dir: 数据目录路径
            db_config: 数据库配置
            target_clusters: 目标聚类数量
            data_domain: 数据域编码
            excel_files: 指定的Excel文件列表（覆盖域配置）
            min_cluster_size: 小对象合并阈值
        """
        self.data_dir = data_dir
        self.db_config = db_config or {}
        self.target_clusters = target_clusters
        self.data_domain = data_domain
        self.data_domain_name = get_domain_name(data_domain)
        self.excel_files = excel_files
        self.min_cluster_size = min_cluster_size

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

        # 4.5 BA-04 业务对象桥接关联（补充聚类关联覆盖不到的实体）
        biz_obj_matches = {}
        biz_obj_to_concept = {}
        concept_info_map = {ce.name: ce for ce in concept_entities}
        try:
            business_objects = reader.read_business_objects_from_ba04()
            biz_obj_to_concept = reader.build_biz_object_to_concept_mapping()
            if business_objects and biz_obj_to_concept:
                matcher = BusinessObjectMatcher(
                    biz_obj_to_concept, concept_to_logical, logical_to_physical, concept_info_map
                )
                biz_obj_matches = matcher.match_objects(objects, business_objects)
                bridged_relations = matcher.build_bridged_relations(biz_obj_matches, relations)
                if bridged_relations:
                    relations.extend(bridged_relations)
        except Exception as e:
            print(f"[WARN] BA-04 桥接关联失败: {e}")

        # 4.6 补充关联不足的必需对象（通过概念实体名称匹配）
        # 如果"项目"等必需对象无关联或聚类过小（<10），用名称/关键词在概念实体中搜索补充
        for obj in objects:
            if obj.object_name not in REQUIRED_OBJECTS:
                continue
            obj_rels = [r for r in relations if r.object_code == obj.object_code]
            if obj_rels and obj.cluster_size >= 10:
                continue  # 关联充足，跳过
            reason = "无关联" if not obj_rels else f"聚类过小(cluster_size={obj.cluster_size})"
            print(f"[INFO] 为必需对象 {obj.object_name} 补充关联（{reason}，通过概念实体名称匹配）...")
            # 先尝试通过 biz_obj_to_concept 找
            matched_concepts = biz_obj_to_concept.get(obj.object_name, [])
            if not matched_concepts:
                # 退化：在概念实体名称中模糊搜索
                matched_concepts = [ce.name for ce in concept_entities if obj.object_name in ce.name]
            if not matched_concepts:
                # 进一步退化：扩展关键词匹配（覆盖同义词和关联词）
                REQUIRED_OBJECT_KEYWORDS = {
                    "项目": ["工程", "建设", "立项", "竣工", "验收", "施工", "投资", "预算", "决算", "招标", "投标", "合同"],
                    "设备": ["装置", "终端", "传感器", "开关", "变压器", "电缆", "母线"],
                    "资产": ["固定资产", "在建工程", "折旧", "台账", "卡片"],
                }
                keywords = REQUIRED_OBJECT_KEYWORDS.get(obj.object_name, [])
                if keywords:
                    matched_concepts = [
                        ce.name for ce in concept_entities
                        if any(kw in ce.name for kw in keywords)
                    ]
                    if matched_concepts:
                        print(f"  通过扩展关键词匹配到 {len(matched_concepts)} 个概念实体")
            if matched_concepts:
                existing_keys = {(r.object_code, r.entity_layer, r.entity_name) for r in relations}
                new_count = 0
                for cname in matched_concepts[:30]:
                    ci = concept_info_map.get(cname)
                    if not ci:
                        continue
                    key_c = (obj.object_code, "CONCEPT", cname)
                    if key_c not in existing_keys:
                        existing_keys.add(key_c)
                        relations.append(EntityRelation(
                            object_code=obj.object_code, entity_layer="CONCEPT",
                            entity_name=cname, entity_code=ci.code,
                            relation_type="DIRECT", relation_strength=0.8,
                            match_method="NAME_MATCH", data_domain=ci.data_domain,
                            source_file=ci.source_file, source_sheet=ci.source_sheet
                        ))
                        new_count += 1
                    for le in concept_to_logical.get(cname, []):
                        key_l = (obj.object_code, "LOGICAL", le.name)
                        if key_l not in existing_keys:
                            existing_keys.add(key_l)
                            relations.append(EntityRelation(
                                object_code=obj.object_code, entity_layer="LOGICAL",
                                entity_name=le.name, entity_code=le.code,
                                relation_type="INDIRECT", relation_strength=0.65,
                                match_method="NAME_MATCH", via_concept_entity=cname,
                                data_domain=le.data_domain, source_file=le.source_file
                            ))
                        for pe in logical_to_physical.get(le.name, []):
                            key_p = (obj.object_code, "PHYSICAL", pe.name)
                            if key_p not in existing_keys:
                                existing_keys.add(key_p)
                                relations.append(EntityRelation(
                                    object_code=obj.object_code, entity_layer="PHYSICAL",
                                    entity_name=pe.name, entity_code=pe.code,
                                    relation_type="INDIRECT", relation_strength=0.5,
                                    match_method="NAME_MATCH", via_concept_entity=le.name,
                                    data_domain=pe.data_domain, source_file=pe.source_file
                                ))
                print(f"  补充了 {new_count} 个概念实体关联及其下级逻辑/物理实体")
                # 同步更新对象的 cluster_size 和 sample_entities（修复空壳/过小对象）
                if obj.cluster_size < 10 and new_count > 0:
                    obj.cluster_size = max(obj.cluster_size, len(matched_concepts))
                    obj.sample_entities = list(set(obj.sample_entities + matched_concepts[:20]))[:20]
                    print(f"  同步更新 {obj.object_name} 的 cluster_size={obj.cluster_size}")
            else:
                print(f"[WARN] 未找到与 {obj.object_name} 匹配的概念实体")

        # 5. 自动处理小对象（合并到最近的大对象，但保留必需对象）
        # 必需对象（如"项目"）不会被合并，即使cluster_size很小
        required_names = set(REQUIRED_OBJECTS)
        handler = SmallObjectHandler(min_entity_count=self.min_cluster_size)
        small_objects = handler.identify_small_objects(objects)
        # 从小对象列表中排除必需对象
        mergeable_small = [o for o in small_objects if o.object_name not in required_names]
        protected_small = [o for o in small_objects if o.object_name in required_names]
        if protected_small:
            print(f"[INFO] 保留 {len(protected_small)} 个必需小对象（不合并）: {[o.object_name for o in protected_small]}")
        if mergeable_small:
            print(f"\n[INFO] 开始自动合并 {len(mergeable_small)} 个小对象...")
            embeddings = extractor.embeddings
            entity_names = extractor.entity_names
            merged_codes = set()
            for small_obj in mergeable_small:
                target = handler.find_merge_target(small_obj, objects, embeddings, entity_names)
                if target:
                    print(f"  合并: {small_obj.object_name}({small_obj.cluster_size}个实体) → {target.object_name}({target.cluster_size}个实体)")
                    relations = handler.merge_objects(small_obj, target, relations)
                    merged_codes.add(small_obj.object_code)
                    target.cluster_size += small_obj.cluster_size
                    target.sample_entities = list(set(target.sample_entities + small_obj.sample_entities))
            objects = [o for o in objects if o.object_code not in merged_codes]
            print(f"[INFO] 合并完成，剩余 {len(objects)} 个对象")

        # 6. 统计
        stats = self._compute_stats(objects, relations)
        print("\n[INFO] 关联关系统计:")
        for obj_code, obj_stats in stats.items():
            print(f"  {obj_code}:")
            print(f"    概念实体: {obj_stats['concept']} | 逻辑实体: {obj_stats['logical']} | 物理实体: {obj_stats['physical']}")

        # 7. 写入数据库（支持数据域）
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
            "relations": [asdict(r) for r in relations],
            "relations_count": len(relations),
            "stats": stats,
            "biz_obj_matches": {k: [(name, round(score, 4)) for name, score in v[:20]]
                                for k, v in biz_obj_matches.items()},
            "data_domain": self.data_domain,
            "data_domain_name": self.data_domain_name
        }

    def _compute_stats(self, objects: List[ExtractedObject], relations: List[EntityRelation]) -> Dict:
        """计算统计信息"""
        stats = {}
        for obj in objects:
            obj_rels = [r for r in relations if r.object_code == obj.object_code]
            cluster_rels = [r for r in obj_rels if r.match_method == "SEMANTIC_CLUSTER"]
            bridge_rels = [r for r in obj_rels if r.match_method == "BA04_BRIDGE"]
            stats[obj.object_code] = {
                "object_name": obj.object_name,
                "cluster_id": obj.cluster_id,
                "cluster_size": obj.cluster_size,
                "concept": len([r for r in obj_rels if r.entity_layer == "CONCEPT"]),
                "logical": len([r for r in obj_rels if r.entity_layer == "LOGICAL"]),
                "physical": len([r for r in obj_rels if r.entity_layer == "PHYSICAL"]),
                "total": len(obj_rels),
                "cluster_relations": len(cluster_rels),
                "bridge_relations": len(bridge_rels)
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
    parser.add_argument("--use-llm", action="store_true", default=None,
                        help="使用大模型命名（默认：当 DEEPSEEK_API_KEY 存在时自动启用）")
    parser.add_argument("--no-llm", action="store_true", help="强制禁用大模型命名，仅使用规则")
    parser.add_argument("--no-db", action="store_true", help="不写入数据库")
    parser.add_argument("--output", "-o", default=None, help="输出JSON文件路径")
    parser.add_argument("--min-cluster-size", type=int, default=SMALL_OBJECT_THRESHOLD, help="小对象合并阈值(低于此值的对象自动合并)")
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

    # 自动检测 LLM：当 DEEPSEEK_API_KEY 存在时默认启用，除非 --no-llm
    if args.no_llm:
        use_llm = False
    elif args.use_llm:
        use_llm = True
    else:
        use_llm = bool(os.getenv("DEEPSEEK_API_KEY", ""))
        if use_llm:
            print("[INFO] 检测到 DEEPSEEK_API_KEY，自动启用 LLM 命名（使用 --no-llm 可禁用）")

    pipeline = SemanticObjectExtractionPipeline(
        data_dir=args.data_dir,
        db_config=db_config,
        target_clusters=args.target_clusters,
        data_domain=args.data_domain,
        excel_files=args.excel_files,
        min_cluster_size=args.min_cluster_size
    )
    result = pipeline.run(use_llm=use_llm)

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
