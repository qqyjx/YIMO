#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_object_extractor.py
对象抽取核心算法测试
"""

import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock
from collections import defaultdict

from object_extractor import (
    ExtractedObject, EntityInfo, EntityRelation,
    DataArchitectureReader, LLMObjectNamer,
    ClusterRelationBuilder, HierarchicalRelationBuilder,
    SmallObjectHandler, BusinessObjectMatcher,
    get_domain_name, auto_discover_domains,
    REQUIRED_OBJECTS, DEFAULT_SHEET_CONFIG,
)


# ============================================================
# 数据类基础测试
# ============================================================

class TestDataClasses:
    """数据类创建和字段默认值"""

    def test_extracted_object_defaults(self):
        obj = ExtractedObject(object_code="OBJ_TEST", object_name="测试")
        assert obj.object_type == "CORE"
        assert obj.extraction_source == "SEMANTIC_CLUSTER"
        assert obj.extraction_confidence == 0.0
        assert obj.synonyms == []
        assert obj.cluster_id == -1

    def test_entity_info_creation(self):
        e = EntityInfo(name="项目信息", layer="CONCEPT", code="CE001",
                       data_domain="shupeidian")
        assert e.name == "项目信息"
        assert e.layer == "CONCEPT"

    def test_entity_relation_defaults(self):
        r = EntityRelation(object_code="OBJ_X", entity_layer="CONCEPT",
                           entity_name="测试实体")
        assert r.relation_type == "CLUSTER"
        assert r.relation_strength == 0.0
        assert r.via_concept_entity == ""


# ============================================================
# 工具函数测试
# ============================================================

class TestUtilFunctions:
    """工具函数"""

    def test_get_domain_name_known(self):
        assert get_domain_name("shupeidian") == "输配电"

    def test_get_domain_name_unknown(self):
        """未注册的域返回 default 配置的名称"""
        result = get_domain_name("unknown_domain")
        assert result == "默认"

    def test_auto_discover_domains_nonexistent_dir(self):
        result = auto_discover_domains("/nonexistent/path")
        assert result == {}

    def test_auto_discover_domains(self, sample_data_dir):
        result = auto_discover_domains(str(sample_data_dir))
        assert "shupeidian" in result
        assert "files" in result["shupeidian"]
        assert len(result["shupeidian"]["files"]) > 0

    def test_auto_discover_domains_ignores_non_xlsx(self, tmp_path):
        """没有 xlsx 文件的子目录不会被发现"""
        subdir = tmp_path / "empty_domain"
        subdir.mkdir()
        (subdir / "readme.txt").write_text("hello")
        result = auto_discover_domains(str(tmp_path))
        assert "empty_domain" not in result


# ============================================================
# DataArchitectureReader 测试
# ============================================================

class TestDataArchitectureReader:
    """数据架构读取器"""

    def test_read_all_from_domain_dir(self, sample_data_dir):
        """从标准域子目录读取三层实体"""
        reader = DataArchitectureReader(
            data_dir=str(sample_data_dir),
            data_domain="shupeidian"
        )
        entities = reader.read_all()

        assert len(entities) > 0

        # 三层都应该有数据
        layers = {e.layer for e in entities}
        assert "CONCEPT" in layers
        assert "LOGICAL" in layers
        assert "PHYSICAL" in layers

    def test_concept_entity_names(self, sample_data_dir):
        """验证概念实体名称正确读取"""
        reader = DataArchitectureReader(
            data_dir=str(sample_data_dir),
            data_domain="shupeidian"
        )
        entities = reader.read_all()
        concept_names = {e.name for e in entities if e.layer == "CONCEPT"}
        assert "项目信息" in concept_names
        assert "设备台账" in concept_names

    def test_logical_entity_names(self, sample_data_dir):
        """验证逻辑实体名称正确读取"""
        reader = DataArchitectureReader(
            data_dir=str(sample_data_dir),
            data_domain="shupeidian"
        )
        entities = reader.read_all()
        logical_names = {e.name for e in entities if e.layer == "LOGICAL"}
        assert "项目基本信息表" in logical_names
        assert "变压器台账" in logical_names

    def test_physical_entity_names(self, sample_data_dir):
        """验证物理实体名称正确读取"""
        reader = DataArchitectureReader(
            data_dir=str(sample_data_dir),
            data_domain="shupeidian"
        )
        entities = reader.read_all()
        physical_names = {e.name for e in entities if e.layer == "PHYSICAL"}
        assert "t_project_info" in physical_names

    def test_empty_data_dir(self, tmp_path):
        """空目录应返回空列表"""
        reader = DataArchitectureReader(
            data_dir=str(tmp_path),
            data_domain="empty"
        )
        entities = reader.read_all()
        assert entities == []

    def test_deduplication(self, tmp_path, sample_concept_df, sample_logical_df, sample_physical_df):
        """同名实体不应重复"""
        domain_dir = tmp_path / "testdomain"
        domain_dir.mkdir()

        # 写两个包含重复实体的 xlsx
        for fname in ["a.xlsx", "b.xlsx"]:
            xlsx = domain_dir / fname
            with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
                sample_concept_df.to_excel(w, sheet_name="DA-01 数据实体清单-概念实体清单", index=False)
                sample_logical_df.to_excel(w, sheet_name="DA-02 数据实体清单-逻辑实体清单", index=False)
                sample_physical_df.to_excel(w, sheet_name="DA-03数据实体清单-物理实体清单", index=False)

        reader = DataArchitectureReader(data_dir=str(tmp_path), data_domain="testdomain")
        entities = reader.read_all()

        # 同一文件内的去重（同名实体只出现一次/per file）
        # 但跨文件允许重复（因为 read_all 对每个文件独立去重）
        concept_names = [e.name for e in entities if e.layer == "CONCEPT"]
        # 5 个概念实体 × 2 个文件 = 10（每个文件内去重，但跨文件允许）
        assert len(concept_names) == 10

    def test_read_concept_with_mapping(self, sample_data_dir):
        """测试概念实体→逻辑实体→物理实体映射构建"""
        reader = DataArchitectureReader(
            data_dir=str(sample_data_dir),
            data_domain="shupeidian"
        )
        concepts, c2l, l2p = reader.read_concept_with_mapping()

        assert len(concepts) > 0
        # 概念实体 → 逻辑实体映射
        assert "项目信息" in c2l
        assert len(c2l["项目信息"]) == 2  # 项目基本信息表, 项目进度表
        # 逻辑实体 → 物理实体映射
        assert "项目基本信息表" in l2p
        assert l2p["项目基本信息表"][0].name == "t_project_info"

    def test_missing_sheet_handled_gracefully(self, tmp_path):
        """缺少 sheet 时不崩溃"""
        domain_dir = tmp_path / "partial"
        domain_dir.mkdir()
        xlsx = domain_dir / "1.xlsx"
        # 只写概念实体 sheet，缺逻辑和物理
        with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
            pd.DataFrame({"概念实体": ["测试"], "概念实体编号": ["T1"]}).to_excel(
                w, sheet_name="DA-01 数据实体清单-概念实体清单", index=False
            )

        reader = DataArchitectureReader(data_dir=str(tmp_path), data_domain="partial")
        entities = reader.read_all()
        # 只有概念实体
        assert all(e.layer == "CONCEPT" for e in entities)


# ============================================================
# LLMObjectNamer 测试
# ============================================================

class TestLLMObjectNamer:
    """大模型归纳命名器"""

    def _make_clusters(self):
        return [
            {"cluster_id": 0, "size": 10, "centroid_entity": "项目信息",
             "sample_entities": ["项目信息", "工程项目", "项目进度", "项目编号"]},
            {"cluster_id": 1, "size": 8, "centroid_entity": "变压器台账",
             "sample_entities": ["变压器台账", "断路器台账", "设备参数", "设备编码"]},
            {"cluster_id": 2, "size": 5, "centroid_entity": "审批流程记录",
             "sample_entities": ["审批流程记录", "流程状态", "审核意见"]},
        ]

    def test_rule_based_naming(self):
        """规则命名（无 LLM 时的回退方案）"""
        namer = LLMObjectNamer(api_key="")  # 无 API key
        clusters = self._make_clusters()
        objects = namer.name_clusters(clusters)

        assert len(objects) > 0
        codes = {o.object_code for o in objects}
        names = {o.object_name for o in objects}
        # 项目必须存在（REQUIRED_OBJECTS 保障）
        assert "项目" in names

    def test_ensure_required_objects_adds_missing(self):
        """缺少"项目"时应自动补充"""
        namer = LLMObjectNamer(api_key="")
        clusters = self._make_clusters()

        # 构造一个不含"项目"的对象列表
        objects = [
            ExtractedObject(object_code="OBJ_DEVICE", object_name="设备",
                            cluster_id=1, cluster_size=8),
        ]
        result = namer._ensure_required_objects(objects, clusters)

        names = {o.object_name for o in result}
        assert "项目" in names

    def test_ensure_required_objects_no_duplicate(self):
        """已存在"项目"时不应重复添加"""
        namer = LLMObjectNamer(api_key="")
        clusters = self._make_clusters()

        objects = [
            ExtractedObject(object_code="OBJ_PROJECT", object_name="项目",
                            cluster_id=0, cluster_size=10),
        ]
        result = namer._ensure_required_objects(objects, clusters)

        project_count = sum(1 for o in result if o.object_name == "项目")
        assert project_count == 1

    def test_name_from_cluster_content(self):
        """从聚类内容中提取对象名称"""
        cluster = {
            "cluster_id": 0, "size": 5, "centroid_entity": "合同信息",
            "sample_entities": ["合同信息", "合同明细", "合同编号", "合同金额"]
        }
        used_codes = set()
        name, name_en, code = LLMObjectNamer._name_from_cluster_content(cluster, used_codes)
        # 应该从高频子串中提取出"合同"
        assert "合同" in name

    def test_parse_llm_response_valid_json(self):
        """正确解析 LLM 返回的 JSON"""
        namer = LLMObjectNamer(api_key="fake")
        clusters = self._make_clusters()
        response = '''```json
[
    {"cluster_id": 0, "object_code": "OBJ_PROJECT", "object_name": "项目",
     "object_name_en": "Project", "object_type": "CORE",
     "description": "工程项目", "confidence": 0.95, "reasoning": "含项目相关实体"},
    {"cluster_id": 1, "object_code": "OBJ_DEVICE", "object_name": "设备",
     "object_name_en": "Device", "object_type": "CORE",
     "description": "电网设备", "confidence": 0.90, "reasoning": "含设备实体"}
]
```'''
        objects = namer._parse_llm_response(response, clusters)
        assert len(objects) == 2
        assert objects[0].object_name == "项目"
        assert objects[0].extraction_confidence == 0.95

    def test_parse_llm_response_invalid_json(self):
        """LLM 返回无效 JSON 时应回退到规则命名"""
        namer = LLMObjectNamer(api_key="fake")
        clusters = self._make_clusters()
        objects = namer._parse_llm_response("这不是JSON", clusters)
        # 应该回退到 rule_based_naming 并且包含"项目"
        names = {o.object_name for o in objects}
        assert "项目" in names


# ============================================================
# ClusterRelationBuilder 测试
# ============================================================

class TestClusterRelationBuilder:
    """基于聚类的关联构建器"""

    def test_build_relations_basic(self):
        """基本关联构建"""
        obj = ExtractedObject(
            object_code="OBJ_PROJECT", object_name="项目",
            cluster_id=0, cluster_size=3,
            sample_entities=["项目信息"]
        )
        entities = [
            EntityInfo(name="项目信息", layer="CONCEPT", code="CE001", data_domain="test"),
            EntityInfo(name="项目进度", layer="LOGICAL", code="LE001", data_domain="test"),
        ]
        cluster_map = {0: ["项目信息", "项目进度"]}

        builder = ClusterRelationBuilder([obj], entities, cluster_map)
        relations = builder.build_relations()

        assert len(relations) == 2
        concept_rels = [r for r in relations if r.entity_layer == "CONCEPT"]
        logical_rels = [r for r in relations if r.entity_layer == "LOGICAL"]
        assert len(concept_rels) == 1
        assert len(logical_rels) == 1

    def test_sample_entity_higher_strength(self):
        """样本实体的关联强度应为 0.9"""
        obj = ExtractedObject(
            object_code="OBJ_TEST", object_name="测试",
            cluster_id=0, cluster_size=2,
            sample_entities=["实体A"]
        )
        entities = [
            EntityInfo(name="实体A", layer="CONCEPT", data_domain="test"),
            EntityInfo(name="实体B", layer="CONCEPT", data_domain="test"),
        ]
        cluster_map = {0: ["实体A", "实体B"]}

        builder = ClusterRelationBuilder([obj], entities, cluster_map)
        relations = builder.build_relations()

        rel_a = [r for r in relations if r.entity_name == "实体A"][0]
        rel_b = [r for r in relations if r.entity_name == "实体B"][0]
        assert rel_a.relation_strength == 0.9
        assert rel_b.relation_strength == 0.7

    def test_skip_negative_cluster_id(self):
        """cluster_id < 0 的对象不产生关联"""
        obj = ExtractedObject(
            object_code="OBJ_ORPHAN", object_name="孤立",
            cluster_id=-1, cluster_size=0
        )
        builder = ClusterRelationBuilder([obj], [], {})
        relations = builder.build_relations()
        assert len(relations) == 0


# ============================================================
# HierarchicalRelationBuilder 测试
# ============================================================

class TestHierarchicalRelationBuilder:
    """层级关联构建器 — 三层穿透"""

    def _setup(self):
        obj = ExtractedObject(
            object_code="OBJ_PROJECT", object_name="项目",
            cluster_id=0, cluster_size=3,
            sample_entities=["项目信息"]
        )
        concept_entities = [
            EntityInfo(name="项目信息", layer="CONCEPT", code="CE001",
                       data_domain="test"),
        ]
        concept_to_logical = {
            "项目信息": [
                EntityInfo(name="项目基本信息表", layer="LOGICAL", code="LE001",
                           data_domain="test"),
            ]
        }
        logical_to_physical = {
            "项目基本信息表": [
                EntityInfo(name="t_project", layer="PHYSICAL", code="PE001",
                           data_domain="test"),
            ]
        }
        cluster_map = {0: ["项目信息"]}
        return obj, concept_entities, concept_to_logical, logical_to_physical, cluster_map

    def test_three_layer_penetration(self):
        """穿透式关联：对象 → 概念 → 逻辑 → 物理"""
        obj, concepts, c2l, l2p, cmap = self._setup()
        builder = HierarchicalRelationBuilder(
            [obj], cmap, concepts, c2l, l2p
        )
        relations = builder.build_relations()

        layers = {r.entity_layer for r in relations}
        assert layers == {"CONCEPT", "LOGICAL", "PHYSICAL"}

    def test_concept_relation_is_direct(self):
        """概念层关联类型应为 DIRECT"""
        obj, concepts, c2l, l2p, cmap = self._setup()
        builder = HierarchicalRelationBuilder([obj], cmap, concepts, c2l, l2p)
        relations = builder.build_relations()

        concept_rel = [r for r in relations if r.entity_layer == "CONCEPT"][0]
        assert concept_rel.relation_type == "DIRECT"
        assert concept_rel.relation_strength >= 0.8

    def test_logical_relation_is_indirect(self):
        """逻辑层关联类型应为 INDIRECT，且记录 via_concept_entity"""
        obj, concepts, c2l, l2p, cmap = self._setup()
        builder = HierarchicalRelationBuilder([obj], cmap, concepts, c2l, l2p)
        relations = builder.build_relations()

        logical_rel = [r for r in relations if r.entity_layer == "LOGICAL"][0]
        assert logical_rel.relation_type == "INDIRECT"
        assert logical_rel.via_concept_entity == "项目信息"
        assert logical_rel.relation_strength == 0.7

    def test_physical_relation_strength(self):
        """物理层关联强度应为 0.6"""
        obj, concepts, c2l, l2p, cmap = self._setup()
        builder = HierarchicalRelationBuilder([obj], cmap, concepts, c2l, l2p)
        relations = builder.build_relations()

        physical_rel = [r for r in relations if r.entity_layer == "PHYSICAL"][0]
        assert physical_rel.relation_strength == 0.6

    def test_empty_logical_mapping(self):
        """概念实体无逻辑映射时，只产生概念层关联"""
        obj, concepts, _, l2p, cmap = self._setup()
        builder = HierarchicalRelationBuilder(
            [obj], cmap, concepts,
            concept_to_logical={},  # 空映射
            logical_to_physical=l2p
        )
        relations = builder.build_relations()
        layers = {r.entity_layer for r in relations}
        assert layers == {"CONCEPT"}


# ============================================================
# SmallObjectHandler 测试
# ============================================================

class TestSmallObjectHandler:
    """小对象处理器"""

    def test_identify_small_objects(self):
        handler = SmallObjectHandler(min_entity_count=5)
        objects = [
            ExtractedObject(object_code="OBJ_BIG", object_name="大", cluster_size=10),
            ExtractedObject(object_code="OBJ_SMALL", object_name="小", cluster_size=2),
        ]
        small = handler.identify_small_objects(objects)
        assert len(small) == 1
        assert small[0].object_code == "OBJ_SMALL"

    def test_find_merge_target_text_overlap(self):
        """通过文本重叠找到合并目标"""
        handler = SmallObjectHandler(min_entity_count=3)
        small = ExtractedObject(
            object_code="OBJ_SMALL", object_name="小",
            cluster_size=1, sample_entities=["项目信息"]
        )
        big = ExtractedObject(
            object_code="OBJ_BIG", object_name="大",
            cluster_size=10, sample_entities=["项目信息", "项目进度"]
        )
        target = handler.find_merge_target(small, [big])
        assert target.object_code == "OBJ_BIG"

    def test_merge_objects_transfers_relations(self):
        """合并应将 source 的关联转移到 target（强度 ×0.9）"""
        handler = SmallObjectHandler()
        source = ExtractedObject(object_code="SRC", object_name="源")
        target = ExtractedObject(object_code="TGT", object_name="目标")
        relations = [
            EntityRelation(object_code="SRC", entity_layer="CONCEPT",
                           entity_name="实体A", relation_strength=1.0),
            EntityRelation(object_code="TGT", entity_layer="CONCEPT",
                           entity_name="实体B", relation_strength=0.8),
        ]
        result = handler.merge_objects(source, target, relations)
        # source 的关联应转移到 target
        tgt_rels = [r for r in result if r.object_code == "TGT"]
        assert len(tgt_rels) == 2
        transferred = [r for r in tgt_rels if r.entity_name == "实体A"][0]
        assert transferred.relation_strength == pytest.approx(0.9)  # 1.0 * 0.9
