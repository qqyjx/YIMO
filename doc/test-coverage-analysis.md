# YIMO 测试覆盖分析报告

> 分析日期: 2026-02-19

## 概述

YIMO 代码库目前 **没有任何自动化测试**。6个核心模块共计约 6,500 行代码、17 个类、120+ 个函数、45 个 API 端点，测试覆盖率为 **0%**。

没有测试框架（pytest/unittest）、没有测试配置文件、没有 CI/CD 流水线、没有测试依赖。

---

## 模块概览

| 模块 | 代码行数 | 类数量 | 函数数量 | API 端点 | 覆盖率 |
|------|---------|--------|---------|----------|--------|
| `scripts/object_extractor.py` | 2,164 | 12 | 50+ | — | 0% |
| `scripts/simple_extractor.py` | 321 | 3 | 3+ | — | 0% |
| `scripts/eav_full.py` | 655 | 1 | 15+ | — | 0% |
| `scripts/eav_semantic_dedupe.py` | 676 | 1 | 10+ | — | 0% |
| `webapp/app.py` | 357 | 0 | 7 | 7 | 0% |
| `webapp/olm_api.py` | 2,254 | 0 | 38+ | 38 | 0% |

---

## 关键测试缺口分析

### 1. 对象抽取核心算法 (`scripts/object_extractor.py`) — 风险: 极高

这是系统最核心的模块，2,164 行代码，12 个类，完全没有测试。

**应优先测试的区域：**

| 组件 | 测试类型 | 优先级 | 原因 |
|------|---------|--------|------|
| `DataArchitectureReader` — Excel DA-01/02/03 解析 | 单元测试 | P0 | 输入数据解析是整个流水线的入口，sheet 名称匹配、列映射、编码处理都需要验证 |
| `SemanticClusterExtractor` — SBERT 聚类 | 单元测试 + 集成测试 | P0 | 聚类结果的质量直接影响抽取结果；需验证向量化、距离计算、聚类数量控制 |
| `HierarchicalRelationBuilder` — 三层关联构建 | 单元测试 | P0 | 客户核心需求（概念→逻辑→物理 穿透式关联），relation_strength 计算逻辑需要验证 |
| `_ensure_required_objects()` — "项目"必须存在保障 | 单元测试 | P0 | 甲方硬性要求，如果回归失败后果严重 |
| `LLMObjectNamer` — DeepSeek API 调用 | 单元测试 (mock) | P1 | 需验证 API 超时/失败的回退逻辑、prompt 构造、响应解析 |
| `DatabaseWriter` — MySQL 写入 | 集成测试 | P1 | 需验证事务完整性、upsert 语义、外键约束 |
| `SemanticObjectExtractionPipeline.run()` — 流水线编排 | 端到端测试 | P1 | 验证完整的 数据读取→向量化→聚类→命名→关联构建→输出 流程 |
| SBERT 可选依赖的优雅降级 | 单元测试 | P2 | try/except 导入逻辑需确保在无 SBERT 环境下不崩溃 |

**具体测试建议：**

```python
# test_object_extractor.py

class TestDataArchitectureReader:
    """测试 Excel 数据读取"""
    def test_read_standard_sheets(self):
        """DA-01/02/03 标准 sheet 名称应正确识别"""
    def test_read_with_missing_sheets(self):
        """缺少某个 sheet 时应优雅处理而非崩溃"""
    def test_normalize_column_names(self):
        """列名含空格、特殊字符时应正确归一化"""
    def test_empty_sheet_handling(self):
        """空 sheet 应返回空列表而非异常"""
    def test_encoding_variants(self):
        """GBK/UTF-8 BOM 编码的文件应能正确读取"""

class TestSemanticClusterExtractor:
    """测试语义聚类"""
    def test_cluster_count_matches_target(self):
        """聚类数量应接近 TARGET_CLUSTER_COUNT"""
    def test_identical_entities_same_cluster(self):
        """语义相同的实体应归入同一聚类"""
    def test_dissimilar_entities_different_clusters(self):
        """语义无关的实体应归入不同聚类"""
    def test_empty_input_handling(self):
        """空输入应返回空结果"""
    def test_single_entity_input(self):
        """单个实体输入应产生 1 个聚类"""

class TestHierarchicalRelationBuilder:
    """测试三层关联构建"""
    def test_direct_relation_strength(self):
        """直接关联的 strength 应为 0.9"""
    def test_cluster_member_strength(self):
        """聚类成员的 strength 应为 0.7"""
    def test_all_three_layers_covered(self):
        """每个对象应有 CONCEPT/LOGICAL/PHYSICAL 三层关联"""
    def test_via_concept_entity_penetration(self):
        """穿透式关联应正确从概念实体追溯到物理实体"""

class TestEnsureRequiredObjects:
    """测试"项目"必须存在保障"""
    def test_project_object_always_present(self):
        """无论聚类结果如何，"项目"对象必须在输出中"""
    def test_project_not_duplicated_if_already_exists(self):
        """如果聚类已包含"项目"，不应重复添加"""
```

---

### 2. REST API 端点 (`webapp/olm_api.py`) — 风险: 高

2,254 行代码，38 个端点，零测试。这是前端唯一的数据来源。

**应优先测试的区域：**

| 端点类别 | 端点数量 | 测试类型 | 优先级 | 原因 |
|---------|---------|---------|--------|------|
| 对象 CRUD (`/api/olm/objects`, `/api/olm/extracted-objects`) | 6 | 单元测试 + 集成测试 | P0 | 核心数据操作，错误直接影响用户 |
| 数据库→JSON 回退策略 | 所有端点 | 单元测试 | P0 | 每个端点的 `is_db_available()` 分支都需要独立验证 |
| 可视化数据 (`/api/olm/graph-data`, `/api/olm/sankey-data`) | 4 | 单元测试 | P1 | ECharts/Sankey 数据格式错误会导致前端白屏 |
| 机理函数评估 (`/api/olm/mechanism-functions/evaluate`) | 1 | 单元测试 | P1 | 表达式求值逻辑复杂，THRESHOLD/FORMULA/RULE 三种类型各有边界条件 |
| 告警规则检查 (`/api/olm/alerts/run-check`) | 1 | 集成测试 | P1 | 遍历 EAV 数据触发检查，需验证误报/漏报 |
| 生命周期 + 溯源链路 | 7 | 单元测试 | P2 | Phase 2-3 功能，数据一致性需验证 |

**具体测试建议：**

```python
# test_olm_api.py

class TestExtractedObjectsAPI:
    """测试对象查询端点"""
    def test_list_objects_with_db(self):
        """数据库可用时应返回数据库数据"""
    def test_list_objects_json_fallback(self):
        """数据库不可用时应回退到 JSON 文件"""
    def test_list_objects_filter_by_domain(self):
        """domain 参数应正确过滤数据"""
    def test_list_objects_empty_result(self):
        """无数据时应返回空列表而非 500"""

class TestDatabaseJsonFallback:
    """测试所有端点的数据库/JSON 双源策略"""
    def test_each_endpoint_has_fallback(self):
        """遍历所有端点，验证 JSON 回退分支"""
    def test_json_and_db_data_format_consistent(self):
        """JSON 和数据库返回的数据格式应一致"""

class TestMechanismFunctionEvaluation:
    """测试机理函数评估"""
    def test_threshold_greater_than(self):
        """THRESHOLD > 比较应正确触发"""
    def test_threshold_boundary_value(self):
        """边界值（等于阈值）应按 operator 正确判断"""
    def test_formula_multiplication(self):
        """FORMULA 乘法应正确计算"""
    def test_formula_division_by_zero(self):
        """FORMULA 除以零应安全处理"""
    def test_rule_condition_evaluation(self):
        """RULE 条件判断应正确匹配"""
    def test_invalid_expression_type(self):
        """未知类型应返回错误而非崩溃"""

class TestAlertRunCheck:
    """测试告警规则检查"""
    def test_threshold_violation_creates_alert(self):
        """超阈值应创建告警记录"""
    def test_no_violation_no_alert(self):
        """未超阈值不应创建告警"""
    def test_inactive_function_skipped(self):
        """is_active=False 的函数应跳过"""
```

---

### 3. EAV 数据导入 (`scripts/eav_full.py`) — 风险: 高

655 行代码，负责 Excel→MySQL 的 EAV 数据导入。数据导入的正确性直接影响下游所有分析。

**应优先测试的区域：**

| 组件 | 测试类型 | 优先级 | 原因 |
|------|---------|--------|------|
| `infer_value_type()` — 类型推断 | 单元测试 | P0 | datetime/number/bool/text 的推断规则复杂，误判会导致数据丢失 |
| `sha1_row()` — 行哈希 | 单元测试 | P0 | 增量导入的去重依赖此函数，错误会导致重复或遗漏 |
| `insert_value()` — EAV 值写入 | 集成测试 | P1 | 需验证 value_text/value_number/value_datetime/value_bool 四列的正确映射 |
| `load_excel_all_sheets()` — 多 sheet 加载 | 单元测试 | P1 | 需验证 sheet 筛选、跳过空 sheet、列名归一化 |
| `upsert_dataset()` / `upsert_attribute()` — 幂等写入 | 集成测试 | P2 | 需验证重复导入不会产生重复记录 |

**具体测试建议：**

```python
# test_eav_full.py

class TestInferValueType:
    """测试类型推断"""
    def test_integer_string(self):
        assert infer_value_type("123") == "number"
    def test_float_string(self):
        assert infer_value_type("3.14") == "number"
    def test_date_string(self):
        assert infer_value_type("2024-01-15") == "datetime"
    def test_chinese_date_string(self):
        assert infer_value_type("2024年1月15日") == "datetime"
    def test_boolean_string(self):
        assert infer_value_type("是") == "bool"
    def test_mixed_text(self):
        assert infer_value_type("项目名称ABC") == "text"
    def test_empty_string(self):
        """空字符串的类型推断行为"""
    def test_nan_value(self):
        """NaN/None 值的处理"""

class TestSha1Row:
    """测试行哈希计算"""
    def test_deterministic(self):
        """相同输入应产生相同哈希"""
    def test_order_sensitive(self):
        """不同列顺序应产生不同哈希"""
    def test_null_handling(self):
        """含 None 的行应正确处理"""
```

---

### 4. 关键字规则抽取器 (`scripts/simple_extractor.py`) — 风险: 中

321 行代码，作为 SBERT 不可用时的回退方案。

**应优先测试的区域：**

| 组件 | 测试类型 | 优先级 | 原因 |
|------|---------|--------|------|
| `KEYWORD_OBJECT_MAP` 关键字匹配 | 单元测试 | P1 | 验证 20+ 关键词规则是否正确命中 |
| `extract_objects()` — 分类逻辑 | 单元测试 | P1 | 验证同一实体不会被多个规则重复分配 |
| `read_entities()` — 多域数据读取 | 单元测试 | P2 | 验证 shupeidian/jicai 等域的正确读取 |

---

### 5. 语义去重 (`scripts/eav_semantic_dedupe.py`) — 风险: 中

676 行代码，SBERT 驱动的语义去重。

**应优先测试的区域：**

| 组件 | 测试类型 | 优先级 | 原因 |
|------|---------|--------|------|
| `cluster_by_threshold()` — 聚类 | 单元测试 | P1 | 阈值 0.86 的合理性需要用已知数据验证 |
| `choose_canonical()` — 规范值选择 | 单元测试 | P1 | 选择频率最高的值作为规范值的策略需验证 |
| `embed_texts()` — 向量化 | 集成测试 | P2 | 批量向量化的 GPU/CPU 回退逻辑 |

---

### 6. Flask 应用 (`webapp/app.py`) — 风险: 中

357 行代码，7 个路由。

**应优先测试的区域：**

| 组件 | 测试类型 | 优先级 | 原因 |
|------|---------|--------|------|
| `/health` 健康检查 | 单元测试 | P1 | 监控和部署依赖此端点，应验证各种故障场景的返回值 |
| `/api/domains` 域发现 | 单元测试 | P1 | DATA/ 目录扫描逻辑需验证空目录、权限等边界 |
| `/rag/query` RAG 查询 | 集成测试 | P2 | FAISS 索引构建和语义搜索逻辑 |
| `/deepseek/chat` LLM 代理 | 单元测试 (mock) | P2 | 超时、API 密钥缺失、速率限制等场景 |

---

## 安全相关测试缺口

审查代码发现以下安全相关区域缺少测试：

| 区域 | 风险 | 说明 |
|------|------|------|
| `_evaluate_expression()` 表达式求值 | 中 | 虽然未使用 `eval()`，但 RULE 类型中的字符串条件匹配逻辑需验证注入可能性 |
| SQL 查询构建 | 中 | `olm_api.py` 中的 `execute_query` 使用参数化查询（好），但动态 UPDATE SET 拼接需审查 |
| `/deepseek/chat` 代理端点 | 中 | 需验证不会将内部配置（API key）泄露给前端 |
| JSON 反序列化 | 低 | `json.loads()` 用于数据库中存储的 expression 字段，需确保格式异常不会导致崩溃 |

---

## 建议的测试基础设施

### 目录结构

```
tests/
├── conftest.py                   # 共享 fixtures (Flask test client, mock DB, 测试数据)
├── fixtures/
│   ├── sample_da01.xlsx          # 最小化的测试 Excel (DA-01 sheet)
│   ├── sample_da02.xlsx          # 最小化的测试 Excel (DA-02 sheet)
│   ├── sample_da03.xlsx          # 最小化的测试 Excel (DA-03 sheet)
│   ├── extraction_test.json      # 测试用抽取结果 JSON
│   └── mock_entities.json        # 预构造的实体数据
├── unit/
│   ├── test_object_extractor.py  # 对象抽取算法测试
│   ├── test_simple_extractor.py  # 关键字抽取器测试
│   ├── test_eav_full.py          # EAV 导入测试
│   ├── test_eav_dedupe.py        # 语义去重测试
│   └── test_evaluate.py          # 机理函数求值测试
├── api/
│   ├── test_olm_api.py           # OLM API 端点测试
│   ├── test_app_routes.py        # Flask 路由测试
│   └── test_fallback.py          # 数据库/JSON 回退策略测试
└── integration/
    ├── test_extraction_pipeline.py  # 端到端抽取流水线
    └── test_eav_import.py           # Excel→MySQL 导入流程
```

### 依赖项（添加到 requirements.txt）

```
pytest>=7.0
pytest-cov>=4.0
pytest-flask>=1.3
pytest-mock>=3.10
factory-boy>=3.3       # 可选：测试数据工厂
```

### pytest 配置（pyproject.toml）

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: 单元测试（无外部依赖）",
    "api: API 端点测试（需要 Flask test client）",
    "integration: 集成测试（需要 MySQL）",
    "slow: 慢速测试（SBERT 模型加载等）",
]
addopts = "--tb=short -q"

[tool.coverage.run]
source = ["scripts", "webapp"]
omit = ["*/tests/*", "*/fixtures/*"]

[tool.coverage.report]
fail_under = 50
show_missing = true
```

---

## 实施优先级总结

### P0 — 必须立即实施（核心业务逻辑）

1. **对象抽取算法正确性** — `DataArchitectureReader`, `SemanticClusterExtractor`, `HierarchicalRelationBuilder`
2. **"项目"必须存在保障** — `_ensure_required_objects()`
3. **API 端点基础功能** — 对象 CRUD 的 200/400/404/500 响应
4. **数据库/JSON 回退策略** — 每个端点的双源数据一致性
5. **EAV 类型推断** — `infer_value_type()` 的正确性

### P1 — 应尽快实施（数据完整性 + 可视化）

6. **机理函数求值** — THRESHOLD/FORMULA/RULE 三种类型的边界条件
7. **告警规则检查** — 误报/漏报验证
8. **可视化数据格式** — ECharts/Sankey 数据结构验证
9. **LLM API 调用** — 超时/回退/响应解析
10. **EAV 行哈希与幂等导入** — `sha1_row()` + upsert

### P2 — 逐步补充（健壮性 + 可维护性）

11. **关键字规则匹配** — `simple_extractor.py` 的覆盖率
12. **语义去重** — 聚类阈值合理性
13. **Flask 路由** — 健康检查、域发现、RAG 查询
14. **安全测试** — SQL 注入、API key 泄露、表达式注入
15. **性能测试** — 大规模数据集（>200k 实体）的处理能力

---

## 覆盖率目标

| 阶段 | 覆盖率目标 | 范围 |
|------|-----------|------|
| Phase 1（P0 完成后） | ≥50% | 核心算法 + API 端点 |
| Phase 2（P1 完成后） | ≥70% | 含数据导入 + 求值引擎 |
| Phase 3（P2 完成后） | ≥85% | 全模块覆盖 |
