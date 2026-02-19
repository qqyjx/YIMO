#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_olm_api.py
REST API 端点 + 机理函数求值测试
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from olm_api import (
    load_json_data, get_objects_from_json, get_relations_from_json,
    _evaluate_expression, _json_cache,
)


# ============================================================
# JSON 后备数据源测试
# ============================================================

class TestLoadJsonData:
    """JSON 文件加载"""

    def test_load_existing_file(self, sample_json_file):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        data = load_json_data("shupeidian")
        assert data["data_domain"] == "shupeidian"
        assert len(data["objects"]) == 2

    def test_load_nonexistent_domain(self, tmp_path):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = tmp_path

        data = load_json_data("nonexistent")
        assert data == {}

    def test_caching(self, sample_json_file):
        """第二次加载应使用缓存"""
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        data1 = load_json_data("shupeidian")
        data2 = load_json_data("shupeidian")
        assert data1 is data2  # 同一对象（缓存命中）


class TestGetObjectsFromJson:
    """从 JSON 获取对象列表"""

    def test_returns_object_list(self, sample_json_file):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        objects = get_objects_from_json("shupeidian")
        assert len(objects) == 2
        assert objects[0]["object_code"] == "OBJ_PROJECT"
        assert objects[1]["object_code"] == "OBJ_DEVICE"

    def test_object_has_required_fields(self, sample_json_file):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        objects = get_objects_from_json("shupeidian")
        required_fields = ["object_id", "object_code", "object_name", "object_type",
                           "data_domain", "stats"]
        for obj in objects:
            for field in required_fields:
                assert field in obj, f"缺少字段: {field}"

    def test_stats_computed_from_relations(self, sample_json_file):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        objects = get_objects_from_json("shupeidian")
        proj = objects[0]
        # stats 应从 objects 中的 stats 字段获取
        assert "concept" in proj["stats"]
        assert "logical" in proj["stats"]
        assert "physical" in proj["stats"]

    def test_empty_domain(self, tmp_path):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = tmp_path

        objects = get_objects_from_json("empty")
        assert objects == []


class TestGetRelationsFromJson:
    """从 JSON 获取关联"""

    def test_returns_three_layers(self, sample_json_file):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        rels = get_relations_from_json("OBJ_PROJECT", "shupeidian")
        assert "concept" in rels
        assert "logical" in rels
        assert "physical" in rels

    def test_concept_relations(self, sample_json_file):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        rels = get_relations_from_json("OBJ_PROJECT", "shupeidian")
        assert len(rels["concept"]) >= 1
        assert rels["concept"][0]["entity_name"] == "项目信息"

    def test_nonexistent_object(self, sample_json_file):
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        rels = get_relations_from_json("OBJ_NONEXISTENT", "shupeidian")
        assert rels["concept"] == []
        assert rels["logical"] == []
        assert rels["physical"] == []

    def test_logical_has_via_concept_entity(self, sample_json_file):
        """逻辑层关联应包含 via_concept_entity"""
        _json_cache.clear()
        import olm_api
        olm_api.OUTPUTS_DIR = sample_json_file.parent

        rels = get_relations_from_json("OBJ_PROJECT", "shupeidian")
        if rels["logical"]:
            assert "via_concept_entity" in rels["logical"][0]


# ============================================================
# 机理函数求值测试
# ============================================================

class TestEvaluateExpression:
    """_evaluate_expression 机理函数求值引擎"""

    # --- THRESHOLD 类型 ---

    def test_threshold_greater_than_triggered(self):
        expr = {"type": "THRESHOLD", "field": "金额", "operator": ">",
                "value": 300, "message": "超过300万红线"}
        result = _evaluate_expression(expr, {"金额": 500})
        assert result["triggered"] is True
        assert result["actual_value"] == 500.0
        assert result["threshold"] == 300.0
        assert "红线" in result["message"]

    def test_threshold_greater_than_not_triggered(self):
        expr = {"type": "THRESHOLD", "field": "金额", "operator": ">", "value": 300}
        result = _evaluate_expression(expr, {"金额": 100})
        assert result["triggered"] is False

    def test_threshold_less_than(self):
        expr = {"type": "THRESHOLD", "field": "质量", "operator": "<", "value": 60}
        result = _evaluate_expression(expr, {"质量": 50})
        assert result["triggered"] is True

    def test_threshold_equal(self):
        expr = {"type": "THRESHOLD", "field": "x", "operator": "==", "value": 10}
        assert _evaluate_expression(expr, {"x": 10})["triggered"] is True
        assert _evaluate_expression(expr, {"x": 11})["triggered"] is False

    def test_threshold_not_equal(self):
        expr = {"type": "THRESHOLD", "field": "x", "operator": "!=", "value": 10}
        assert _evaluate_expression(expr, {"x": 11})["triggered"] is True
        assert _evaluate_expression(expr, {"x": 10})["triggered"] is False

    def test_threshold_gte(self):
        expr = {"type": "THRESHOLD", "field": "x", "operator": ">=", "value": 100}
        assert _evaluate_expression(expr, {"x": 100})["triggered"] is True
        assert _evaluate_expression(expr, {"x": 99})["triggered"] is False

    def test_threshold_lte(self):
        expr = {"type": "THRESHOLD", "field": "x", "operator": "<=", "value": 100}
        assert _evaluate_expression(expr, {"x": 100})["triggered"] is True
        assert _evaluate_expression(expr, {"x": 101})["triggered"] is False

    def test_threshold_missing_field_defaults_to_zero(self):
        """输入中缺少字段时默认为 0"""
        expr = {"type": "THRESHOLD", "field": "金额", "operator": ">", "value": 300}
        result = _evaluate_expression(expr, {})
        assert result["actual_value"] == 0.0
        assert result["triggered"] is False

    # --- FORMULA 类型 ---

    def test_formula_multiplication(self):
        expr = {"type": "FORMULA", "variables": ["电压", "电流"],
                "expression": "功率 = 电压 * 电流", "result": "功率", "unit": "W"}
        result = _evaluate_expression(expr, {"电压": 220, "电流": 10})
        assert result["computed_value"] == pytest.approx(2200.0)
        assert result["unit"] == "W"

    def test_formula_addition(self):
        expr = {"type": "FORMULA", "variables": ["A", "B"],
                "expression": "总计 = A + B", "result": "总计"}
        result = _evaluate_expression(expr, {"A": 100, "B": 200})
        assert result["computed_value"] == pytest.approx(300.0)

    def test_formula_subtraction(self):
        expr = {"type": "FORMULA", "variables": ["收入", "支出"],
                "expression": "利润 = 收入 - 支出", "result": "利润"}
        result = _evaluate_expression(expr, {"收入": 1000, "支出": 600})
        assert result["computed_value"] == pytest.approx(400.0)

    def test_formula_division(self):
        expr = {"type": "FORMULA", "variables": ["总量", "数量"],
                "expression": "均值 = 总量 / 数量", "result": "均值"}
        result = _evaluate_expression(expr, {"总量": 100, "数量": 4})
        assert result["computed_value"] == pytest.approx(25.0)

    def test_formula_division_by_zero(self):
        """除以零应返回 None 而非报错"""
        expr = {"type": "FORMULA", "variables": ["A", "B"],
                "expression": "C = A / B", "result": "C"}
        result = _evaluate_expression(expr, {"A": 100, "B": 0})
        assert result["computed_value"] is None

    def test_formula_missing_variable_defaults_to_zero(self):
        expr = {"type": "FORMULA", "variables": ["A", "B"],
                "expression": "C = A * B", "result": "C"}
        result = _evaluate_expression(expr, {"A": 5})  # B 缺失
        assert result["computed_value"] == pytest.approx(0.0)  # 5 * 0

    # --- RULE 类型 ---

    def test_rule_condition_triggered(self):
        expr = {"type": "RULE",
                "condition": "金额 > 300",
                "then": "走审批路径A",
                "else": "走审批路径B"}
        result = _evaluate_expression(expr, {"金额": 500})
        assert result["triggered"] is True
        assert result["action"] == "走审批路径A"

    def test_rule_condition_not_triggered(self):
        expr = {"type": "RULE",
                "condition": "金额 > 300",
                "then": "走审批路径A",
                "else": "走审批路径B"}
        result = _evaluate_expression(expr, {"金额": 100})
        assert result["triggered"] is False
        assert result["action"] == "走审批路径B"

    # --- 未知类型 ---

    def test_unknown_type_returns_dict(self):
        """未知表达式类型不应崩溃"""
        expr = {"type": "UNKNOWN"}
        result = _evaluate_expression(expr, {})
        # 返回值取决于实现，但不应抛异常
        assert isinstance(result, (dict, type(None)))


# ============================================================
# Flask API 端点测试
# ============================================================

class TestAPIEndpoints:
    """REST API 端点（JSON fallback 模式）"""

    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_extracted_objects_endpoint(self, client):
        resp = client.get("/api/olm/extracted-objects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "objects" in data
        assert "total" in data
        assert data["source"] == "json_file"

    def test_extracted_objects_with_domain(self, client):
        resp = client.get("/api/olm/extracted-objects?domain=shupeidian")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["objects"]) == 2

    def test_object_relations_endpoint(self, client):
        resp = client.get("/api/olm/object-relations/OBJ_PROJECT")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "concept" in data
        assert "logical" in data
        assert "physical" in data
        assert data["source"] == "json_file"

    def test_object_relations_has_data(self, client):
        resp = client.get("/api/olm/object-relations/OBJ_PROJECT")
        data = resp.get_json()
        assert len(data["concept"]) >= 1

    def test_object_relations_nonexistent_object(self, client):
        resp = client.get("/api/olm/object-relations/OBJ_NONEXISTENT")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["concept"] == []

    def test_export_objects_endpoint(self, client):
        resp = client.get("/api/olm/export-objects")
        assert resp.status_code == 200

    def test_sankey_data_endpoint(self, client):
        resp = client.get("/api/olm/sankey-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data
        assert "links" in data

    def test_summary_endpoint(self, client):
        resp = client.get("/api/olm/summary")
        assert resp.status_code == 200

    def test_stats_endpoint(self, client):
        resp = client.get("/api/olm/stats")
        assert resp.status_code == 200

    def test_graph_data_endpoint(self, client):
        resp = client.get("/api/olm/graph-data/OBJ_PROJECT")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data
        assert "links" in data

    def test_search_entities_endpoint(self, client):
        resp = client.get("/api/olm/search-entities?q=项目")
        assert resp.status_code == 200

    def test_mechanism_functions_presets(self, client):
        resp = client.get("/api/olm/mechanism-functions/presets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "presets" in data
        assert len(data["presets"]) >= 3

    def test_evaluate_function_endpoint(self, client):
        """通过 API 调用机理函数评估"""
        resp = client.post("/api/olm/mechanism-functions/evaluate",
                           json={
                               "expression": {
                                   "type": "THRESHOLD",
                                   "field": "金额",
                                   "operator": ">",
                                   "value": 300,
                                   "message": "超限",
                               },
                               "input_values": {"金额": 500},
                           })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["result"]["triggered"] is True

    def test_evaluate_function_missing_expression(self, client):
        """缺少 expression 应返回 400"""
        resp = client.post("/api/olm/mechanism-functions/evaluate",
                           json={"input_values": {}})
        assert resp.status_code == 400

    def test_api_domains(self, client):
        """域发现端点"""
        resp = client.get("/api/domains")
        assert resp.status_code == 200

    def test_granularity_report(self, client):
        resp = client.get("/api/olm/granularity-report")
        assert resp.status_code == 200
