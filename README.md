# YIMO — 对象抽取与三层架构关联系统

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)](https://mysql.com)
[![ECharts](https://img.shields.io/badge/ECharts-5.0-AA344D?logo=apacheecharts&logoColor=white)](https://echarts.apache.org/)
[![Tests](https://img.shields.io/badge/Tests-146_passing-brightgreen)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

> 智能电网数据架构对象抽取与三层架构关联可视化平台（南方电网 China Southern Power Grid）

从企业数据架构文档（DA-01/02/03 Excel）中 **自动抽取** 高度抽象的业务"对象"（项目、设备、资产、合同等），建立与三层架构（概念实体→逻辑实体→物理实体）的穿透式关联关系，提供多维可视化与智能治理能力。

---

## 系统架构

```mermaid
graph TB
    subgraph 数据源
        E1["📋 DA-01<br/>概念实体清单"]
        E2["📋 DA-02<br/>逻辑实体清单"]
        E3["📋 DA-03<br/>物理实体清单"]
    end

    subgraph 对象抽取引擎
        SBERT["🧠 SBERT 向量化<br/>text2vec-base-chinese 768维"]
        CLUSTER["📊 层次聚类<br/>AgglomerativeClustering"]
        LLM["🤖 DeepSeek LLM<br/>归纳命名"]
        DEDUP["🔄 去重 & 合并<br/>垃圾名称过滤"]
    end

    subgraph 对象管理层
        OBJ["🎯 抽取对象<br/>项目/设备/资产/合同"]
        REL["🔗 三层关联<br/>CONCEPT→LOGICAL→PHYSICAL"]
        LC["⏳ 生命周期<br/>Planning→Operation→Finance"]
        MF["⚡ 机理函数<br/>阈值/公式/规则"]
    end

    subgraph 可视化 & API
        KG["🕸️ 知识图谱<br/>ECharts 力导向"]
        SANKEY["📊 Sankey 流向图"]
        GOV["📋 治理看板"]
        API["🔌 42 REST 端点"]
    end

    E1 & E2 & E3 --> SBERT --> CLUSTER --> LLM --> DEDUP --> OBJ
    OBJ --> REL --> KG & SANKEY
    OBJ --> LC --> GOV
    OBJ --> MF --> GOV
    REL & LC & MF --> API
```

> 📐 详细架构设计：[doc/系统架构设计-飞书版.md](doc/系统架构设计-飞书版.md) | 产品设计与 Palantir 对标：[doc/product-design.md](doc/product-design.md) | [doc/palantir-对标方案-飞书版.md](doc/palantir-对标方案-飞书版.md)

## 对象抽取算法

```mermaid
flowchart LR
    A["📥 读取 Excel<br/>DA-01/02/03"] --> B["📝 收集概念实体<br/>+ 映射关系"]
    B --> C["🧠 SBERT 编码<br/>768维向量"]
    C --> D["📊 层次聚类<br/>自适应聚类数"]
    D --> E{"🤖 DeepSeek<br/>API 可用?"}
    E -->|是| F["LLM 归纳命名"]
    E -->|否| G["规则命名"]
    F & G --> H["🔄 去重清洗<br/>垃圾名过滤<br/>小对象合并"]
    H --> I["🔗 构建三层关联<br/>概念→逻辑→物理"]
    I --> J["💾 输出<br/>JSON / MySQL"]

    style E fill:#fef3c7,stroke:#f59e0b
    style F fill:#dbeafe,stroke:#3b82f6
    style H fill:#fce7f3,stroke:#ec4899
```

## 三层架构关联模型

```mermaid
graph TB
    subgraph 对象层
        P["🎯 项目<br/>OBJ_PROJECT"]
        D["🎯 设备<br/>OBJ_DEVICE"]
        A["🎯 资产<br/>OBJ_ASSET"]
    end

    subgraph 概念实体层 DA-01
        C1["项目信息"]
        C2["工程进度信息"]
        C3["设备台账信息"]
        C4["资产卡片信息"]
    end

    subgraph 逻辑实体层 DA-02
        L1["项目立项表"]
        L2["进度报告表"]
        L3["设备巡检记录"]
        L4["资产折旧表"]
    end

    subgraph 物理实体层 DA-03
        PH1["t_project_init"]
        PH2["t_progress_report"]
        PH3["t_device_inspect"]
        PH4["t_asset_deprec"]
    end

    P -->|"DIRECT 0.9"| C1 & C2
    D -->|"DIRECT 0.8"| C3
    A -->|"DIRECT 0.8"| C4
    C1 -->|"穿透"| L1
    C2 -->|"穿透"| L2
    C3 -->|"穿透"| L3
    C4 -->|"穿透"| L4
    L1 --> PH1
    L2 --> PH2
    L3 --> PH3
    L4 --> PH4

    style P fill:#6366f1,color:#fff
    style D fill:#6366f1,color:#fff
    style A fill:#6366f1,color:#fff
    style C1 fill:#818cf8,color:#fff
    style C2 fill:#818cf8,color:#fff
    style C3 fill:#818cf8,color:#fff
    style C4 fill:#818cf8,color:#fff
    style L1 fill:#10b981,color:#fff
    style L2 fill:#10b981,color:#fff
    style L3 fill:#10b981,color:#fff
    style L4 fill:#10b981,color:#fff
    style PH1 fill:#f59e0b,color:#fff
    style PH2 fill:#f59e0b,color:#fff
    style PH3 fill:#f59e0b,color:#fff
    style PH4 fill:#f59e0b,color:#fff
```

## 数据流

```mermaid
graph LR
    EXCEL["📋 Excel 文件<br/>DA-01/02/03"] -->|"eav_full.py"| EAV[("💾 EAV 表<br/>MySQL 3307")]
    EXCEL -->|"object_extractor.py"| JSON["📄 extraction_*.json"]
    JSON --> API["🔌 42 REST 端点<br/>olm_api.py"]
    EAV --> API
    API --> UI["🖥️ v10.0 仪表盘"]
    UI --> G1["🕸️ 三层知识图谱"]
    UI --> G2["📊 Sankey 流向图"]
    UI --> G3["📋 治理看板"]
    UI --> G4["⚡ 预警面板"]

    style API fill:#3b82f6,color:#fff
    style UI fill:#6366f1,color:#fff
```

## 核心功能

| 功能 | 说明 |
|------|------|
| **对象自动抽取** | SBERT 语义聚类 + DeepSeek LLM 归纳命名，自动从三层实体中提炼业务对象 |
| **三层知识图谱** | ECharts 力导向图，对象→概念→逻辑→物理 四层穿透可视化 |
| **Sankey 流向图** | 对象→概念→逻辑实体的数据流向展示 |
| **穿透式溯源** | 从财务结算→项目立项→采购合同→现场施工的全链路追踪 |
| **机理函数** | 自定义业务规则（阈值/公式/规则），如合同额度>300万走审计路径 |
| **风险预警** | 基于机理函数自动触发预警，支持多级别预警管理 |
| **数据治理看板** | 完整性、缺陷率、跨域对比等 8 项治理指标 |
| **多域管理** | 输配电、计划财务等多数据域独立管理与切换 |
| **RAG 智能问答** | FAISS 向量检索 + DeepSeek 生成式回答 |
| **EAV 动态存储** | Entity-Attribute-Value 模型，灵活扩展属性无需改表 |

## 快速开始

```bash
# 一键启动（推荐）
bash start.sh

# 访问主界面
open http://localhost:5000/

# 对象抽取（DeepSeek API Key 存在时自动使用 LLM 命名）
python scripts/object_extractor.py --data-dir DATA --data-domain shupeidian --no-db -o outputs/extraction_shupeidian.json

# 强制使用规则命名（无需 API Key）
python scripts/object_extractor.py --no-llm --data-dir DATA --data-domain jicai --no-db -o outputs/extraction_jicai.json
```

## 系统启停

```bash
bash start.sh              # 启动（MySQL 检查 → venv 激活 → Flask → 健康检查）
bash start.sh --stop       # 停止
bash start.sh --restart    # 重启
bash start.sh --status     # 查看状态
bash start.sh --port 8080  # 指定端口
bash start.sh --extract    # 启动前先运行对象抽取
```

## 数据目录

```
DATA/
├── shupeidian/     # 输配电域（3 个 Excel，~26MB）
└── jicai/          # 计划财务域（3 个 Excel，~11MB）
```

每个 Excel 文件需包含标准化工作表：
- `DA-01 数据实体清单-概念实体清单`（概念实体 → 业务场景层）
- `DA-02 数据实体清单-逻辑实体清单`（逻辑实体 → 交互表单层）
- `DA-03数据实体清单-物理实体清单`（物理实体 → 数据库层）

## API 接口

### 对象管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/olm/extracted-objects` | GET | 获取对象列表（支持域过滤） |
| `/api/olm/object-relations/<code>` | GET | 对象的三层实体关联 |
| `/api/olm/run-extraction` | POST | 执行对象抽取 |
| `/api/olm/merge-objects` | POST | 合并对象 |
| `/api/olm/cross-domain-duplicates` | GET | 跨域重复对象检测 |

### 可视化

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/olm/graph-data-three-tier` | GET | 三层架构知识图谱（支持深度 2/3/4 层） |
| `/api/olm/graph-data-global` | GET | 全局知识图谱 |
| `/api/olm/sankey-data` | GET | Sankey 流向图数据 |

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
| `/api/olm/governance/metrics` | GET | 治理指标（完整性/缺陷/覆盖率） |
| `/api/olm/governance/defects` | GET | 缺陷报告 |
| `/api/olm/governance/domain-comparison` | GET | 跨域对比 |

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3.10+, Flask 3.0 |
| **数据库** | MySQL 8.0 (InnoDB, UTF8MB4, port 3307) |
| **ML/AI** | SBERT (text2vec-base-chinese, 768维), scikit-learn |
| **向量检索** | FAISS (IndexFlatIP, RAG) |
| **LLM** | DeepSeek API（自动检测 API Key，支持离线规则回退） |
| **前端** | HTML5/Jinja2, CSS3, ECharts 5.0 |
| **部署** | Docker, Docker Compose, Bash |

## 项目结构

```
YIMO/
├── start.sh                       # 一键启停管理
├── scripts/
│   ├── object_extractor.py        # 核心：SBERT + LLM 语义聚类抽取
│   ├── simple_extractor.py        # 轻量：规则抽取（无 SBERT 依赖）
│   ├── eav_full.py                # Excel → EAV 导入
│   └── eav_semantic_dedupe.py     # SBERT 语义去重
├── webapp/
│   ├── app.py                     # Flask 应用（RAG, DeepSeek 代理）
│   ├── olm_api.py                 # REST API（42+ 端点）
│   └── templates/10.0.html        # v10.0 全功能仪表盘
├── tests/                         # pytest 测试套件（146 测试）
├── DATA/                          # 数据域目录（Excel 文件）
├── outputs/                       # 抽取结果 JSON
├── mysql-local/                   # MySQL Schema（19 表 + 4 视图）
├── doc/
│   ├── product-design.md          # 产品设计文档
│   └── requirement/               # 甲方需求文档
├── docker-compose.yml             # Docker 编排
└── Dockerfile                     # 多阶段构建
```

## 数据库设计

```mermaid
erDiagram
    extracted_objects ||--o{ object_entity_relations : "has"
    extracted_objects ||--o{ object_lifecycle_history : "tracks"
    extracted_objects ||--o{ object_synonyms : "aliases"
    mechanism_functions ||--o{ alert_records : "triggers"
    traceability_chains ||--o{ traceability_chain_nodes : "contains"

    extracted_objects {
        int object_id PK
        varchar object_code UK
        varchar object_name
        enum object_type "CORE/DERIVED/AUXILIARY"
        varchar data_domain
    }

    object_entity_relations {
        bigint relation_id PK
        int object_id FK
        enum entity_layer "CONCEPT/LOGICAL/PHYSICAL"
        varchar entity_name
        decimal relation_strength "0-1"
        enum match_method "EXACT/SEMANTIC/LLM"
    }

    eav_entities {
        bigint entity_id PK
        int dataset_id FK
        varchar source_identifier
    }

    eav_values {
        bigint value_id PK
        bigint entity_id FK
        int attribute_id FK
        text value_text
    }
```

## 部署方式

```bash
# 方式 1: 本地启动（推荐）
bash start.sh

# 方式 2: Docker Compose
docker compose up -d

# 方式 3: 交互式部署（多 OS 支持）
bash deploy.sh
```

## 测试

```bash
source venv/bin/activate
pytest tests/ -v    # 146 个测试（EAV 51 + 抽取 33 + API 45 + 简化 17）
```

## 配置

```bash
# .env 文件（可选）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_DB=eav_db
MYSQL_USER=eav_user
MYSQL_PASSWORD=eavpass123
DEEPSEEK_API_KEY=your_api_key        # 设置后自动启用 LLM 命名
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
```

## License

MIT
