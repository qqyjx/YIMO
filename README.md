# YIMO - 对象抽取与三层架构关联系统

> 智能电网数据架构对象抽取与三层架构关联可视化平台（南方电网）

从数据架构文档（DA-01/02/03 Excel）中自动抽取高度抽象的"对象"（项目、设备、资产、合同等），建立与三层架构（概念实体→逻辑实体→物理实体）的关联关系，提供知识图谱、Sankey 流向图、穿透式溯源等多维可视化能力。

## 功能特性

- **对象自动抽取** — SBERT 语义聚类 + DeepSeek LLM 归纳命名，从三层实体中提炼核心业务对象
- **三层关联可视化** — 对象卡片 → 概念/逻辑/物理实体关联面板，支持强度排序与高亮
- **知识图谱** — ECharts 力导向图，支持单对象子图与全局拓扑两种视图
- **Sankey 流向图** — 对象→概念→逻辑实体的数据流向展示
- **多域管理** — 输配电、计划财务等多数据域独立管理与切换
- **穿透式溯源** — 从财务结算→项目立项→采购合同→现场施工记录的业务链追踪
- **机理函数与预警** — 自定义业务规则（如合同额度阈值），触发风险预警
- **数据治理看板** — 完整性、缺陷率、跨域对比等治理指标
- **RAG 智能问答** — FAISS 向量检索 + DeepSeek 生成式回答
- **EAV 动态存储** — Entity-Attribute-Value 模型，灵活扩展属性无需改表

## 快速开始

```bash
# 一键启动（推荐）— 自动检查 MySQL、启动 Flask、健康检查
bash start.sh

# 访问
# 主页:     http://localhost:5000/
# 对象管理: http://localhost:5000/extraction
```

## 系统启停

```bash
bash start.sh              # 启动（MySQL 检查 → venv 激活 → Flask → 健康检查）
bash start.sh --stop       # 停止服务
bash start.sh --restart    # 重启（改完代码后用）
bash start.sh --status     # 查看状态（MySQL + Flask + 健康检查）
bash start.sh --port 8080  # 指定端口
bash start.sh --extract    # 启动前先运行对象抽取
```

启动流程：
1. 检测 MySQL (port 3307)，未运行则自动启动
2. 显示数据库摘要（对象数 / 关联数 / EAV 实体数 / EAV 值数）
3. 自动检测 Python 环境（venv → conda → system python3）
4. 后台启动 Flask，PID 管理 + 日志记录
5. 健康检查通过后输出访问地址

## 核心概念

**三层架构**：

| 层级 | 说明 | 数据来源 |
|------|------|----------|
| 概念实体 | 业务场景层 | DA-01 概念实体清单 |
| 逻辑实体 | 交互表单层 | DA-02 逻辑实体清单 |
| 物理实体 | 数据库层 | DA-03 物理实体清单 |

**对象**：从三层架构实体中抽取的高度抽象概念（项目、设备、资产、合同等），是跨层关联的核心枢纽。

## 数据目录

```
DATA/
├── shupeidian/     # 输配电域（3 个 Excel 文件）
└── jicai/          # 计划财务域（3 个 Excel 文件）
```

每个 Excel 文件需包含工作表：
- `DA-01 数据实体清单-概念实体清单`
- `DA-02 数据实体清单-逻辑实体清单`
- `DA-03数据实体清单-物理实体清单`

## 抽取算法

采用 **语义聚类 + LLM 归纳命名** 的自下而上归纳方法：

```
实体名称收集 → SBERT 向量化 → 层次聚类 → LLM 归纳命名 → 对象输出
```

| 组件 | 技术 |
|------|------|
| 嵌入模型 | `shibing624/text2vec-base-chinese`（768 维） |
| 聚类算法 | AgglomerativeClustering（余弦距离） |
| LLM 命名 | DeepSeek API（可选） |
| 关联强度 | 样本实体 0.9，其他成员 0.7 |

## 数据源机制

系统采用 **数据库优先 + JSON 回退** 的双数据源架构：

- **数据库可用**：从 MySQL 实时查询（22 个对象 / 13,000+ 关联 / 235,000+ EAV 实体）
- **数据库不可用**：自动回退到 `outputs/extraction_<domain>.json`
- 通过 `/api/olm/export-objects` 可将数据库数据导出为 JSON

## 项目结构

```
YIMO/
├── start.sh                       # 一键启停管理脚本
├── scripts/
│   ├── object_extractor.py        # 语义聚类对象抽取（核心，SBERT + LLM）
│   ├── simple_extractor.py        # 规则抽取（无 SBERT 依赖）
│   ├── eav_full.py                # Excel → EAV 导入
│   ├── eav_semantic_dedupe.py     # SBERT 语义去重
│   └── import_all.py              # 批量导入协调器
├── webapp/
│   ├── app.py                     # Flask 应用（RAG、DeepSeek 代理、域发现）
│   ├── olm_api.py                 # REST API（42 个端点，2700+ 行）
│   └── templates/
│       ├── 10.0.html              # 主界面（v10.0，全功能仪表盘）
│       └── object_extraction.html # 对象抽取管理界面
├── tests/                         # 测试套件（146 个测试）
├── DATA/                          # 数据域目录
├── outputs/                       # 抽取结果 JSON
├── mysql-local/                   # MySQL 配置与 Schema（19 表 + 4 视图）
├── docker-compose.yml             # Docker 编排（MySQL + Flask）
└── Dockerfile                     # 多阶段构建（Python 3.11-slim）
```

## API 接口

### 对象管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/olm/extracted-objects` | GET | 获取对象列表 |
| `/api/olm/object-relations/<code>` | GET | 对象关联的三层实体 |
| `/api/olm/objects` | POST | 创建对象 |
| `/api/olm/objects/<code>` | PUT/DELETE | 更新/删除对象 |
| `/api/olm/run-extraction` | POST | 执行对象抽取 |
| `/api/olm/export-objects` | GET | 导出为 JSON |
| `/api/olm/merge-objects` | POST | 合并对象 |

### 可视化与分析

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/olm/graph-data/<code>` | GET | 单对象知识图谱数据 |
| `/api/olm/graph-data-global` | GET | 全局知识图谱 |
| `/api/olm/sankey-data` | GET | Sankey 流向图数据 |
| `/api/olm/search-entities` | GET | 实体搜索 |
| `/api/olm/stats` | GET | 系统统计 |
| `/api/olm/domain-stats` | GET | 域级统计 |
| `/api/olm/summary` | GET | 综合摘要 |

### 生命周期与溯源

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/olm/object-lifecycle/<code>` | GET/POST | 对象生命周期 |
| `/api/olm/traceability-chains` | GET/POST | 穿透式溯源链 |
| `/api/olm/trace-object/<code>` | GET | 对象溯源追踪 |

### 机理函数与预警

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/olm/mechanism-functions` | GET/POST | 机理函数管理 |
| `/api/olm/mechanism-functions/evaluate` | POST | 规则求值 |
| `/api/olm/alerts` | GET | 预警列表 |
| `/api/olm/alerts/run-check` | POST | 触发预警检查 |

### 数据治理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/olm/governance/metrics` | GET | 治理指标 |
| `/api/olm/governance/completeness` | GET | 完整性报告 |
| `/api/olm/governance/defects` | GET | 缺陷报告 |
| `/api/olm/governance/domain-comparison` | GET | 跨域对比 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+, Flask 3.0 |
| 数据库 | MySQL 8.0 (InnoDB, UTF8MB4, port 3307) |
| ML/AI | SBERT (text2vec-base-chinese), scikit-learn |
| 向量检索 | FAISS (IndexFlatIP, 用于 RAG) |
| LLM | DeepSeek API |
| 前端 | HTML5/Jinja2, CSS3, ECharts |
| 部署 | Docker, Docker Compose |

## 数据库结构

### EAV 核心表

| 表名 | 说明 |
|------|------|
| `eav_datasets` | 数据集元信息 |
| `eav_entities` | 实体（每行数据） |
| `eav_attributes` | 属性定义 |
| `eav_values` | 值存储 |

### 对象与关联

| 表名 | 说明 |
|------|------|
| `extracted_objects` | 抽取的核心对象 |
| `object_synonyms` | 对象同义词 |
| `object_entity_relations` | 对象↔三层实体关联（核心） |
| `object_extraction_batches` | 抽取批次记录 |

### 语义相似度

| 表名 | 说明 |
|------|------|
| `eav_semantic_canon` | 规范值（SBERT 聚类代表文本） |
| `eav_semantic_mapping` | 原始值 → 规范值映射 |

## 配置

### 环境变量

```bash
# 数据库（可选，无数据库时自动使用 JSON 回退）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_DB=eav_db
MYSQL_USER=eav_user
MYSQL_PASSWORD=eavpass123

# LLM（用于对象命名和 RAG 问答）
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
```

### 对象抽取参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--target-clusters` | 15 | 目标聚类数量 |
| `--use-llm` | False | 使用 DeepSeek LLM 归纳命名 |
| `--no-db` | False | 不写入数据库，输出到 JSON |
| `--output` | None | 输出 JSON 文件路径 |

## 部署方式

```bash
# 方式 1: 本地启动（推荐）
bash start.sh

# 方式 2: Docker Compose
docker compose up -d

# 方式 3: 交互式部署（多操作系统支持）
bash deploy.sh
```

## 测试

```bash
source venv/bin/activate
pytest tests/ -v    # 146 个测试（EAV 51 + 抽取 33 + API 45 + 简化 17）
```

## License

MIT
