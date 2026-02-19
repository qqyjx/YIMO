#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享 fixtures — 所有测试文件都可以使用这里定义的 fixtures。
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pandas as pd

# 把项目根目录加入 sys.path，方便导入 scripts/ 和 webapp/ 下的模块
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))
sys.path.insert(0, str(ROOT_DIR / "webapp"))


# ============================================================
# 测试用 Excel 数据 fixtures
# ============================================================

@pytest.fixture
def sample_concept_df():
    """模拟 DA-01 概念实体清单 DataFrame"""
    return pd.DataFrame({
        "概念实体": ["项目信息", "设备台账", "合同信息", "资产信息", "人员信息"],
        "概念实体编号": ["CE001", "CE002", "CE003", "CE004", "CE005"],
        "数据域": ["输配电", "输配电", "输配电", "输配电", "输配电"],
        "数据子域": ["项目管理", "设备管理", "合同管理", "资产管理", "人员管理"],
    })


@pytest.fixture
def sample_logical_df():
    """模拟 DA-02 逻辑实体清单 DataFrame"""
    return pd.DataFrame({
        "概念实体": ["项目信息", "项目信息", "设备台账", "设备台账", "合同信息"],
        "逻辑实体名称": ["项目基本信息表", "项目进度表", "变压器台账", "断路器台账", "合同明细表"],
        "逻辑实体编码": ["LE001", "LE002", "LE003", "LE004", "LE005"],
        "数据域": ["输配电", "输配电", "输配电", "输配电", "输配电"],
    })


@pytest.fixture
def sample_physical_df():
    """模拟 DA-03 物理实体清单 DataFrame"""
    return pd.DataFrame({
        "逻辑实体名称": ["项目基本信息表", "项目进度表", "变压器台账"],
        "物理实体名称": ["t_project_info", "t_project_progress", "t_transformer"],
        "物理实体编码": ["PE001", "PE002", "PE003"],
        "数据域": ["输配电", "输配电", "输配电"],
    })


@pytest.fixture
def sample_xlsx(tmp_path, sample_concept_df, sample_logical_df, sample_physical_df):
    """创建一个临时的测试 Excel 文件，包含三个标准 sheet"""
    xlsx_path = tmp_path / "test_data.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        sample_concept_df.to_excel(writer, sheet_name="DA-01 数据实体清单-概念实体清单", index=False)
        sample_logical_df.to_excel(writer, sheet_name="DA-02 数据实体清单-逻辑实体清单", index=False)
        sample_physical_df.to_excel(writer, sheet_name="DA-03数据实体清单-物理实体清单", index=False)
    return xlsx_path


@pytest.fixture
def sample_data_dir(tmp_path, sample_xlsx):
    """创建一个模拟的 DATA/shupeidian/ 目录结构"""
    domain_dir = tmp_path / "shupeidian"
    domain_dir.mkdir()
    # 复制测试 xlsx 到域目录
    import shutil
    shutil.copy(sample_xlsx, domain_dir / "1.xlsx")
    return tmp_path


# ============================================================
# 抽取结果 JSON fixtures
# ============================================================

@pytest.fixture
def sample_extraction_json():
    """模拟 extraction_shupeidian.json 的结构"""
    return {
        "data_domain": "shupeidian",
        "data_domain_name": "输配电",
        "extraction_time": "2026-02-19T10:00:00",
        "entity_stats": {
            "concept": 5,
            "logical": 5,
            "physical": 3,
            "total": 13,
        },
        "objects": [
            {
                "object_code": "OBJ_PROJECT",
                "object_name": "项目",
                "object_name_en": "Project",
                "object_type": "CORE",
                "description": "电网建设项目",
                "cluster_size": 10,
                "sample_entities": ["项目信息", "项目进度"],
                "stats": {"concept": 2, "logical": 3, "physical": 2},
            },
            {
                "object_code": "OBJ_DEVICE",
                "object_name": "设备",
                "object_name_en": "Device",
                "object_type": "CORE",
                "description": "电网设备",
                "cluster_size": 8,
                "sample_entities": ["设备台账", "变压器"],
                "stats": {"concept": 1, "logical": 2, "physical": 1},
            },
        ],
        "relations": [
            {"object_code": "OBJ_PROJECT", "entity_layer": "CONCEPT", "entity_name": "项目信息",
             "entity_code": "CE001", "relation_type": "CLUSTER", "relation_strength": 0.9,
             "data_domain": "shupeidian"},
            {"object_code": "OBJ_PROJECT", "entity_layer": "LOGICAL", "entity_name": "项目基本信息表",
             "entity_code": "LE001", "relation_type": "CLUSTER", "relation_strength": 0.8,
             "via_concept_entity": "项目信息", "data_domain": "shupeidian"},
            {"object_code": "OBJ_PROJECT", "entity_layer": "PHYSICAL", "entity_name": "t_project_info",
             "entity_code": "PE001", "relation_type": "CLUSTER", "relation_strength": 0.7,
             "data_domain": "shupeidian"},
            {"object_code": "OBJ_DEVICE", "entity_layer": "CONCEPT", "entity_name": "设备台账",
             "entity_code": "CE002", "relation_type": "CLUSTER", "relation_strength": 0.9,
             "data_domain": "shupeidian"},
        ],
        "biz_obj_matches": {
            "OBJ_PROJECT": [["项目管理业务对象", 0.85]],
        },
    }


@pytest.fixture
def sample_json_file(tmp_path, sample_extraction_json):
    """把 sample_extraction_json 写入临时文件"""
    json_path = tmp_path / "extraction_shupeidian.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sample_extraction_json, f, ensure_ascii=False)
    return json_path


# ============================================================
# Flask test client fixture
# ============================================================

@pytest.fixture
def flask_app(tmp_path, sample_json_file):
    """创建一个用于测试的 Flask 应用实例"""
    # 设置环境变量，指向不存在的数据库（强制走 JSON 回退）
    os.environ["MYSQL_HOST"] = "127.0.0.1"
    os.environ["MYSQL_PORT"] = "9999"  # 不存在的端口，强制 JSON fallback

    from app import app

    # 让 olm_api 使用测试 JSON 文件目录
    import olm_api as olm_module
    olm_module.OUTPUTS_DIR = tmp_path
    olm_module._json_cache.clear()

    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(flask_app):
    """Flask test client"""
    return flask_app.test_client()
