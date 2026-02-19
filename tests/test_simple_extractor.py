#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_simple_extractor.py
关键词规则抽取器测试
"""

import pytest
import pandas as pd
from pathlib import Path

from simple_extractor import (
    ExtractedObject, EntityInfo, EntityRelation,
    KEYWORD_OBJECT_MAP, read_entities, extract_objects,
)


# ============================================================
# KEYWORD_OBJECT_MAP 测试
# ============================================================

class TestKeywordObjectMap:
    """关键词映射配置"""

    def test_required_keywords_present(self):
        """必须包含"项目"相关关键词"""
        assert "项目" in KEYWORD_OBJECT_MAP
        assert "工程" in KEYWORD_OBJECT_MAP

    def test_project_maps_to_obj_project(self):
        """项目关键词应映射到 OBJ_PROJECT"""
        code = KEYWORD_OBJECT_MAP["项目"][0]
        assert code == "OBJ_PROJECT"

    def test_synonyms_map_to_same_code(self):
        """同义词应映射到同一个对象编码"""
        assert KEYWORD_OBJECT_MAP["设备"][0] == KEYWORD_OBJECT_MAP["变压器"][0]
        assert KEYWORD_OBJECT_MAP["合同"][0] == "OBJ_CONTRACT"
        assert KEYWORD_OBJECT_MAP["人员"][0] == KEYWORD_OBJECT_MAP["员工"][0]
        assert KEYWORD_OBJECT_MAP["物资"][0] == KEYWORD_OBJECT_MAP["材料"][0]

    def test_all_entries_have_six_fields(self):
        """每个映射条目应有 6 个字段"""
        for keyword, entry in KEYWORD_OBJECT_MAP.items():
            assert len(entry) == 6, f"关键词 '{keyword}' 的映射条目应有6个字段，实际 {len(entry)}"


# ============================================================
# read_entities 测试
# ============================================================

class TestReadEntities:
    """实体数据读取"""

    def test_read_from_valid_dir(self, sample_data_dir):
        """从有效的数据目录读取实体"""
        domain_dir = sample_data_dir / "shupeidian"
        entities = read_entities(str(domain_dir), "shupeidian")

        assert len(entities) > 0
        layers = {e.layer for e in entities}
        assert "CONCEPT" in layers

    def test_read_from_nonexistent_dir(self, tmp_path):
        """不存在的目录应返回空列表"""
        entities = read_entities(str(tmp_path / "not_here"), "test")
        assert entities == []

    def test_read_from_empty_dir(self, tmp_path):
        """没有 xlsx 的目录应返回空列表"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        entities = read_entities(str(empty_dir), "test")
        assert entities == []

    def test_entity_has_correct_domain(self, sample_data_dir):
        """读取的实体应有正确的 data_domain"""
        domain_dir = sample_data_dir / "shupeidian"
        entities = read_entities(str(domain_dir), "shupeidian")
        # data_domain 来自 Excel 中的"数据域"列
        assert all(e.data_domain for e in entities)

    def test_nan_entities_filtered(self, tmp_path):
        """名称为 nan 或空的实体应被过滤"""
        test_dir = tmp_path / "nantest"
        test_dir.mkdir()
        df = pd.DataFrame({
            "概念实体": ["有效实体", "nan", "", None, "另一个有效实体"],
            "概念实体编码": ["C1", "C2", "C3", "C4", "C5"],
        })
        xlsx = test_dir / "test.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="DA-01 数据实体清单-概念实体清单", index=False)

        entities = read_entities(str(test_dir), "test")
        names = {e.name for e in entities}
        assert "有效实体" in names
        assert "另一个有效实体" in names
        assert "nan" not in names
        assert "" not in names


# ============================================================
# extract_objects 测试
# ============================================================

class TestExtractObjects:
    """基于关键词的对象抽取"""

    def _make_entities(self):
        """创建一组测试实体"""
        return [
            EntityInfo(name="项目信息", layer="CONCEPT", data_domain="test"),
            EntityInfo(name="项目进度表", layer="LOGICAL", data_domain="test"),
            EntityInfo(name="设备台账", layer="CONCEPT", data_domain="test"),
            EntityInfo(name="变压器信息表", layer="LOGICAL", data_domain="test"),
            EntityInfo(name="合同明细", layer="CONCEPT", data_domain="test"),
            EntityInfo(name="费用统计", layer="CONCEPT", data_domain="test"),
            EntityInfo(name="审批流程", layer="LOGICAL", data_domain="test"),
        ]

    def test_extracts_known_objects(self):
        """应抽取出关键词匹配的对象"""
        entities = self._make_entities()
        objects, relations = extract_objects(entities)

        codes = {o.object_code for o in objects}
        assert "OBJ_PROJECT" in codes  # 项目
        assert "OBJ_DEVICE" in codes   # 设备 (变压器→设备)
        assert "OBJ_CONTRACT" in codes  # 合同

    def test_returns_relations(self):
        """应返回对象→实体关联"""
        entities = self._make_entities()
        objects, relations = extract_objects(entities)

        assert len(relations) > 0
        # 每条关联都有 object_code 和 entity_name
        for r in relations:
            assert r.object_code
            assert r.entity_name

    def test_relation_strength_is_0_8(self):
        """关联强度应固定为 0.8"""
        entities = self._make_entities()
        _, relations = extract_objects(entities)
        for r in relations:
            assert r.relation_strength == 0.8

    def test_empty_entities(self):
        """空实体列表应返回空结果"""
        objects, relations = extract_objects([])
        assert objects == []
        assert relations == []

    def test_no_keyword_match(self):
        """无关键词匹配的实体不应产生对象"""
        entities = [
            EntityInfo(name="随机名称XYZ", layer="CONCEPT", data_domain="test"),
        ]
        objects, relations = extract_objects(entities)
        assert objects == []

    def test_objects_sorted_by_entity_count(self):
        """对象应按关联实体数量降序排列"""
        entities = [
            EntityInfo(name="项目信息1", layer="CONCEPT", data_domain="t"),
            EntityInfo(name="项目信息2", layer="LOGICAL", data_domain="t"),
            EntityInfo(name="项目信息3", layer="PHYSICAL", data_domain="t"),
            EntityInfo(name="设备台账", layer="CONCEPT", data_domain="t"),
        ]
        objects, _ = extract_objects(entities)

        if len(objects) >= 2:
            # 项目有3个实体，设备有1个，项目应排在前面
            assert objects[0].stats["total"] >= objects[1].stats["total"]

    def test_stats_per_layer(self):
        """stats 应包含每层的实体数量"""
        entities = [
            EntityInfo(name="项目信息", layer="CONCEPT", data_domain="t"),
            EntityInfo(name="项目进度表", layer="LOGICAL", data_domain="t"),
            EntityInfo(name="项目物理表", layer="PHYSICAL", data_domain="t"),
        ]
        objects, _ = extract_objects(entities)
        proj = [o for o in objects if o.object_code == "OBJ_PROJECT"][0]
        assert proj.stats["concept"] >= 1
        assert proj.stats["logical"] >= 1
        assert proj.stats["physical"] >= 1

    def test_synonyms_aggregate_to_same_object(self):
        """同义词关键词应聚合到同一个对象"""
        entities = [
            EntityInfo(name="设备台账", layer="CONCEPT", data_domain="t"),
            EntityInfo(name="变压器信息", layer="CONCEPT", data_domain="t"),
            EntityInfo(name="断路器参数", layer="CONCEPT", data_domain="t"),
        ]
        objects, _ = extract_objects(entities)
        # 设备/变压器/断路器都应映射到 OBJ_DEVICE
        device_objs = [o for o in objects if o.object_code == "OBJ_DEVICE"]
        assert len(device_objs) == 1
        assert device_objs[0].stats["total"] == 3
