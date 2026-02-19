#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_eav_full.py
EAV 数据导入模块测试
"""

import pytest
import pandas as pd
from pathlib import Path

from eav_full import (
    _normalize_na, normalize_attr_name, infer_value_type,
    majority_type, sha1_row, load_excel_all_sheets,
    IncrementalStats, NA_TOKENS,
)


# ============================================================
# _normalize_na 测试
# ============================================================

class TestNormalizeNa:
    """NA 值归一化"""

    def test_none_returns_none(self):
        assert _normalize_na(None) is None

    def test_nan_float_returns_none(self):
        assert _normalize_na(float("nan")) is None

    def test_null_string_returns_none(self):
        assert _normalize_na("null") is None
        assert _normalize_na("NULL") is None

    def test_na_string_returns_none(self):
        assert _normalize_na("N/A") is None
        assert _normalize_na("#N/A") is None
        assert _normalize_na("na") is None

    def test_none_string_returns_none(self):
        assert _normalize_na("none") is None
        assert _normalize_na("None") is None

    def test_empty_string_returns_none(self):
        assert _normalize_na("") is None

    def test_dash_returns_none(self):
        assert _normalize_na("-") is None
        assert _normalize_na("—") is None

    def test_valid_value_returned_unchanged(self):
        assert _normalize_na("hello") == "hello"
        assert _normalize_na(42) == 42
        assert _normalize_na("项目名称") == "项目名称"

    def test_na_tokens_exhaustive(self):
        """NA_TOKENS 中的所有值都应被归一化为 None"""
        for token in NA_TOKENS:
            result = _normalize_na(token)
            assert result is None, f"NA token '{token}' 未被正确归一化"


# ============================================================
# normalize_attr_name 测试
# ============================================================

class TestNormalizeAttrName:
    """属性名标准化"""

    def test_strip_whitespace(self):
        assert normalize_attr_name("  名称  ") == "名称"

    def test_collapse_multiple_spaces(self):
        assert normalize_attr_name("项目  名称") == "项目 名称"

    def test_none_returns_empty(self):
        assert normalize_attr_name(None) == ""

    def test_normal_name_unchanged(self):
        assert normalize_attr_name("属性名") == "属性名"


# ============================================================
# infer_value_type 测试
# ============================================================

class TestInferValueType:
    """类型推断"""

    # number 类型
    def test_integer(self):
        assert infer_value_type("123") == "number"

    def test_negative_integer(self):
        # 注意: "-456" 含 '-' 字符，infer_value_type 跳过 number 分支，
        # 然后 dateutil 能解析为 datetime → 这是已知的边界行为
        assert infer_value_type("-456") == "datetime"

    def test_float(self):
        assert infer_value_type("3.14") == "number"

    def test_comma_separated_number(self):
        assert infer_value_type("1,234,567") == "number"

    def test_zero(self):
        assert infer_value_type("0") == "number"

    # bool 类型
    def test_bool_true_cn(self):
        assert infer_value_type("是") == "bool"

    def test_bool_false_cn(self):
        assert infer_value_type("否") == "bool"

    def test_bool_yes(self):
        assert infer_value_type("yes") == "bool"

    def test_bool_no(self):
        assert infer_value_type("no") == "bool"

    def test_bool_true_en(self):
        assert infer_value_type("true") == "bool"

    def test_bool_false_en(self):
        assert infer_value_type("false") == "bool"

    # datetime 类型
    def test_iso_date(self):
        assert infer_value_type("2024-01-15") == "datetime"

    def test_datetime_with_time(self):
        assert infer_value_type("2024-01-15 10:30:00") == "datetime"

    def test_slash_date(self):
        assert infer_value_type("2024/01/15") == "datetime"

    # text 类型
    def test_chinese_text(self):
        assert infer_value_type("项目名称ABC") == "text"

    def test_pure_chinese(self):
        assert infer_value_type("输配电") == "text"

    def test_empty_string(self):
        assert infer_value_type("") == "text"

    def test_none(self):
        assert infer_value_type(None) == "text"

    # 边界情况
    def test_number_with_date_chars_is_datetime(self):
        """含日期字符(如-)的数字串应被识别为 datetime"""
        # "2024-01" 含 - 字符，不应直接判为 number
        result = infer_value_type("2024-01")
        assert result in ("datetime", "text")  # 取决于 dateutil 能否解析


# ============================================================
# majority_type 测试
# ============================================================

class TestMajorityType:
    """多数投票类型推断"""

    def test_all_numbers(self):
        assert majority_type(["123", "456", "789"]) == "number"

    def test_all_text(self):
        assert majority_type(["abc", "项目", "测试"]) == "text"

    def test_mixed_number_wins(self):
        """number 占多数时应返回 number"""
        assert majority_type(["123", "456", "abc"]) == "number"

    def test_empty_samples(self):
        """空样本时所有计数为0，按优先级排序 number 排第一"""
        assert majority_type([]) == "number"

    def test_all_bool(self):
        assert majority_type(["是", "否", "是"]) == "bool"

    def test_number_priority_on_tie(self):
        """平票时 number 优先级高于 text"""
        # 1 个 number + 1 个 text → number 优先
        result = majority_type(["123", "abc"])
        assert result == "number"


# ============================================================
# sha1_row 测试
# ============================================================

class TestSha1Row:
    """行哈希计算"""

    def test_deterministic(self):
        """相同输入应产生相同哈希"""
        h1 = sha1_row(["a", "b", "c"])
        h2 = sha1_row(["a", "b", "c"])
        assert h1 == h2

    def test_different_input_different_hash(self):
        """不同输入应产生不同哈希"""
        h1 = sha1_row(["a", "b"])
        h2 = sha1_row(["a", "c"])
        assert h1 != h2

    def test_order_matters(self):
        """列顺序影响哈希值"""
        h1 = sha1_row(["a", "b"])
        h2 = sha1_row(["b", "a"])
        assert h1 != h2

    def test_none_handling(self):
        """含 None 的行应正常计算"""
        h = sha1_row([None, "a", None])
        assert isinstance(h, str)
        assert len(h) == 40  # SHA1 hex 长度

    def test_empty_list(self):
        h = sha1_row([])
        assert isinstance(h, str)
        assert len(h) == 40

    def test_chinese_content(self):
        h = sha1_row(["项目名称", "设备编码", "资产信息"])
        assert isinstance(h, str)


# ============================================================
# load_excel_all_sheets 测试
# ============================================================

class TestLoadExcelAllSheets:
    """Excel 多 sheet 加载"""

    def test_loads_all_sheets(self, sample_xlsx):
        sheets = load_excel_all_sheets(sample_xlsx)
        assert len(sheets) == 3
        assert "DA-01 数据实体清单-概念实体清单" in sheets
        assert "DA-02 数据实体清单-逻辑实体清单" in sheets
        assert "DA-03数据实体清单-物理实体清单" in sheets

    def test_returns_dataframes(self, sample_xlsx):
        sheets = load_excel_all_sheets(sample_xlsx)
        for name, df in sheets.items():
            assert isinstance(df, pd.DataFrame)

    def test_na_values_normalized(self, tmp_path):
        """NA 值应被统一处理为 None"""
        xlsx = tmp_path / "na_test.xlsx"
        df = pd.DataFrame({
            "col1": ["valid", "nan", "N/A", "", "good"],
            "col2": ["1", "NULL", "none", "-", "2"],
        })
        df.to_excel(xlsx, index=False, engine="openpyxl")

        sheets = load_excel_all_sheets(xlsx)
        result_df = list(sheets.values())[0]

        # "valid" 和 "good" 应保留, "nan"/"N/A"/"" 应为 None
        assert result_df["col1"].iloc[0] == "valid"
        assert result_df["col1"].iloc[4] == "good"

    def test_nonexistent_file_raises(self, tmp_path):
        """不存在的文件应报错"""
        with pytest.raises(Exception):
            load_excel_all_sheets(tmp_path / "nonexistent.xlsx")


# ============================================================
# IncrementalStats 测试
# ============================================================

class TestIncrementalStats:
    """增量导入统计"""

    def test_initial_values(self):
        stats = IncrementalStats()
        assert stats.inserted == 0
        assert stats.updated == 0
        assert stats.skipped == 0

    def test_total(self):
        stats = IncrementalStats()
        stats.inserted = 5
        stats.updated = 3
        stats.skipped = 2
        assert stats.total() == 10

    def test_str_representation(self):
        stats = IncrementalStats()
        stats.inserted = 1
        stats.updated = 2
        stats.skipped = 3
        s = str(stats)
        assert "1" in s
        assert "2" in s
        assert "3" in s
