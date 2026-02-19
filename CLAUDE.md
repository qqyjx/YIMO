# CLAUDE.md - AI Assistant Guide for YIMO

> This document provides context and guidelines for AI assistants working on the YIMO codebase.

## Project Overview

**YIMO** is an Object Extraction & Three-Tier Architecture Association System for smart grid data management (南方电网). The core concept is extracting highly abstract "objects" (like Project, Device, Asset) from data architecture documents and establishing associations with the three-tier architecture (Concept Entity, Logical Entity, Physical Entity).

### Problem Solved

Data architecture documents contain three layers of entities:
- **Concept Entity (概念实体)**: Business scenario layer (DA-01 sheets)
- **Logical Entity (逻辑实体)**: Interaction form layer (DA-02 sheets)
- **Physical Entity (物理实体)**: Database layer (DA-03 sheets)

YIMO extracts abstract "objects" from these entities and builds association relationships, enabling:
- Unified object model across different data domains (输配电, 集采, etc.)
- Traceable relationships between objects and three-tier entities
- Foundation for comparison with enterprise data center
- Penetrating business supervision (穿透式业务监管)

### Client Requirements (Key)

1. **Object extraction from three-tier architecture**: Automatically extract high-level "objects" (项目, 设备, 资产, etc.) from DA-01/02/03 Excel sheets
2. **Three-tier association visualization**: Frontend must show object-to-entity associations across concept/logical/physical layers
3. **Required object "项目" (Project)**: Must always be extracted; likely compared with enterprise data center
4. **Multi-domain support**: Currently 输配电 (power distribution) and 集采 (procurement) domains; more to be added (计划财务域, etc.)
5. **Penetrating traceability**: From financial settlement → project initiation → procurement contracts → field construction records
6. **Dynamic extensibility**: EAV model allows flexible attribute/entity additions without schema changes

### Core Components

1. **EAV Data Model** - Entity-Attribute-Value storage for heterogeneous data
2. **Semantic Clustering** - SBERT-based Chinese text clustering for object extraction
3. **LLM Object Naming** - DeepSeek API integration for cluster naming
4. **Web Visualization** - Flask app with object cards, relation panels, knowledge graphs, and Sankey diagrams
5. **JSON Fallback** - All APIs work without database by falling back to `outputs/extraction_*.json` files

---

## Codebase Structure

```
YIMO/
├── scripts/                        # Core Python processing modules
│   ├── object_extractor.py        # Object extraction algorithm (SBERT + LLM, ~86KB)
│   ├── simple_extractor.py        # Keyword rule-based fallback extractor (no SBERT)
│   ├── eav_full.py                # Excel → EAV import (multi-sheet, auto-type detection)
│   ├── eav_csv.py                 # CSV → EAV import
│   ├── eav_semantic_dedupe.py     # SBERT semantic deduplication & canonicalization
│   ├── import_all.py              # Batch import coordinator
│   ├── check_db_semantic.py       # Database health checks
│   ├── run_sql_file.py            # SQL script executor utility
│   ├── create_normalized_view.sql # Aggregation view definitions
│   ├── generate-diagram.js        # Mermaid diagram renderer (Node.js)
│   ├── run_all_once.sh            # Batch processing script
│   ├── run_dedupe_full.sh         # Full semantic deduplication runner
│   └── watch_and_export_pdf.sh    # PDF export watcher
│
├── webapp/                         # Flask web application
│   ├── app.py                     # Main Flask app (RAG, DeepSeek proxy, domain discovery)
│   ├── olm_api.py                 # REST API Blueprint (~1550 lines, 20+ endpoints)
│   ├── requirements.txt           # Python web dependencies (pinned versions)
│   ├── .env.example               # Configuration template
│   ├── start_web.sh               # Service start script (auto-detects Python env)
│   ├── stop_web.sh                # Graceful service stop (SIGTERM → SIGKILL)
│   └── templates/                 # Jinja2 HTML templates
│       ├── 10.0.html              # Main dashboard (v10.0, ~81KB, full-featured UI)
│       ├── object_extraction.html # Object extraction interface (~32KB)
│       └── home.html              # Homepage fallback
│
├── mysql-local/                    # MySQL configuration
│   ├── bootstrap.sql              # Database schema init (~400 lines, 10 tables)
│   ├── my.cnf                     # MySQL config (port 3307, utf8mb4)
│   └── init_local_mysql.sh        # User-mode MySQL startup
│
├── DATA/                           # Data directory (per-domain subdirectories)
│   ├── shupeidian/                # 输配电域 (Power Distribution)
│   │   ├── 1.xlsx, 2.xlsx, 3.xlsx
│   └── jicai/                     # 集采域 (Procurement)
│       ├── 1.xlsx, 2.xlsx, 3.xlsx
│
├── outputs/                        # Extraction results (JSON fallback source)
│   ├── extraction_shupeidian.json # Power distribution results (~3.6MB)
│   ├── extraction_jicai.json      # Procurement results (~720KB)
│   └── semantic_dedupe_gpu_full/  # Deduplication artifacts
│
├── figures/                        # Architecture diagrams
│   ├── architecture/              # Mermaid (.mmd) + SVG renders
│   │   ├── object_extraction_algorithm.mmd
│   │   ├── data_flow.mmd/.svg
│   │   ├── lifecycle_ontology.mmd/.svg
│   │   └── tech_roadmap.mmd/.svg
│   └── plan/                      # Project roadmap
│       └── roadmap.mmd/.pdf/.html/.tex
│
├── doc/                            # Project documentation
│   ├── plan/plan.xlsx             # Project planning spreadsheet
│   └── requirement/               # Client requirements
│       ├── 0.md                   # Core requirements (穿透式监管, 对象管理器)
│       └── 1.md                   # Client clarifications (三层架构 = DA-01/02/03)
│
├── docs/                           # Academic documentation
│   └── paper_outline_计算机学报.md # Paper outline for journal submission
│
├── bat/                            # Windows SSH tunnel utilities
│   ├── mysql_tunnel_4090_start.bat
│   └── mysql_tunnel_4090_stop.bat
│
├── docker-compose.yml              # Docker orchestration (MySQL + Flask)
├── Dockerfile                      # Multi-stage Python 3.11-slim build
├── deploy.sh                       # Interactive deployment (~618 lines, multi-OS)
├── demo.sh                         # One-click demo launcher
├── docker-start.sh                 # Docker Compose wrapper with health checks
├── init.sh                         # Agent session environment verification
├── task.json                       # Structured task list (agent harness)
├── claude-progress.txt             # Agent session progress log
├── requirements.txt                # Root Python dependencies
└── .gitignore                      # Excludes venv, models, .env, dbdata, outputs
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.10+ (3.11 in Docker), Flask 3.0 |
| **Database** | MySQL 8.0 (InnoDB, UTF8MB4, port 3307) |
| **ML/AI** | SBERT (text2vec-base-chinese, 768-dim), scikit-learn |
| **Vector Search** | FAISS (faiss-cpu, IndexFlatIP for RAG) |
| **LLM** | DeepSeek API integration |
| **Frontend** | HTML5/Jinja2, CSS3, ECharts (knowledge graphs) |
| **DevOps** | Docker, Docker Compose, Bash |

### Key Dependencies

Root `requirements.txt`:
```
pandas>=2.0                # Data processing
openpyxl>=3.1              # Excel I/O
mysql-connector-python>=8.0 # MySQL driver (scripts)
tqdm>=4.66                 # Progress bars
flask>=3.0                 # Web framework
pymysql>=1.1               # MySQL driver (webapp)
python-dotenv>=1.0         # Environment config
requests>=2.31             # HTTP client
sentence-transformers>=2.2 # SBERT embeddings
numpy>=1.24                # Numerical computing
scikit-learn>=1.3          # Clustering algorithms
faiss-cpu>=1.7             # Vector search index
```

Webapp `requirements.txt` (pinned versions):
```
flask==3.0.3
pymysql==1.1.1
cryptography>=42.0
sqlalchemy==2.0.32
sentence-transformers==2.7.0
faiss-cpu==1.7.4
python-dotenv==1.0.1
requests==2.32.3
```

---

## Development Workflows

### Environment Setup

```bash
# Option 1: Docker (recommended)
./docker-start.sh

# Option 2: Interactive local deployment (multi-OS, progress bars)
./deploy.sh

# Option 3: Quick demo
./demo.sh
```

### Running the Web Application

```bash
# Start service (auto-detects venv/conda/system Python)
cd webapp && ./start_web.sh

# Manual start with venv
source venv/bin/activate
cd webapp && python app.py

# Stop service
cd webapp && ./stop_web.sh

# Verify health
curl http://localhost:5000/health
```

### Object Extraction

```bash
# Full extraction (SBERT + LLM, no database write)
python scripts/object_extractor.py \
    --data-dir DATA \
    --target-clusters 15 \
    --no-db \
    --output outputs/extraction_result.json

# With LLM naming + database write
python scripts/object_extractor.py \
    --data-dir DATA \
    --target-clusters 15 \
    --use-llm \
    --db-host localhost \
    --db-port 3307 \
    --db-name eav_db

# Lightweight keyword-based extraction (no SBERT required)
python scripts/simple_extractor.py \
    --data-dir DATA \
    --output outputs/extraction_simple.json
```

### Data Import

```bash
# Import Excel to EAV (multi-sheet, auto-type detection)
python scripts/eav_full.py --excel ./DATA/shupeidian/2.xlsx

# Import CSV
python scripts/eav_csv.py --csv ./data.csv --db eav_db

# Batch import all domains
python scripts/import_all.py

# Semantic deduplication
bash scripts/run_dedupe_full.sh
```

---

## Database Architecture

### Configuration

Default connection (WSL2-compatible):
```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307          # Port 3307 to avoid WSL2 conflicts
MYSQL_DB=eav_db
MYSQL_USER=eav_user
MYSQL_PASSWORD=eavpass123
TABLE_PREFIX=eav
```

### Core EAV Tables

| Table | Purpose |
|-------|---------|
| `eav_datasets` | Dataset metadata (name, source_file, imported_at) |
| `eav_entities` | Entity instances (row records) |
| `eav_attributes` | Attribute definitions (name, data_type, ord_index) |
| `eav_values` | Actual values (value_text, value_number, value_datetime, value_bool) |

### Semantic Tables

| Table | Purpose |
|-------|---------|
| `eav_semantic_canon` | Canonical values (cluster representatives) |
| `eav_semantic_mapping` | Original → canonical text mappings |
| `semantic_fingerprints` | Vector embeddings (768-dim SBERT) |

### Object Extraction Tables

| Table | Purpose |
|-------|---------|
| `extracted_objects` | Core objects (object_code, object_name, object_type, data_domain) |
| `object_synonyms` | Object synonyms/aliases |
| `object_attribute_definitions` | Object attribute definitions |
| `object_entity_relations` | **Object to Three-Tier Entity Relations (Core)** |
| `object_extraction_batches` | Extraction batch records |

### Object-Entity Relation Table Structure

```sql
CREATE TABLE object_entity_relations (
    relation_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    object_id INT NOT NULL,
    entity_layer ENUM('CONCEPT', 'LOGICAL', 'PHYSICAL'),  -- Three-tier layer
    entity_name VARCHAR(512),                              -- Entity name
    entity_code VARCHAR(256),                              -- Entity code
    relation_type ENUM('DIRECT', 'INDIRECT', 'DERIVED', 'CLUSTER'),
    relation_strength DECIMAL(5,4),                        -- 0-1 strength
    match_method ENUM('EXACT', 'CONTAINS', 'SEMANTIC', 'LLM', 'SEMANTIC_CLUSTER'),
    data_domain VARCHAR(128),                              -- Data domain
    source_file VARCHAR(256),                              -- Source file
    FOREIGN KEY (object_id) REFERENCES extracted_objects(object_id)
);
```

---

## Coding Conventions

### Python Style

- Python 3.10+ required (type hints encouraged)
- Use `logging` module for output, not print statements in production code
- Scripts support CLI arguments via `argparse`
- Database connections use `pymysql` with context managers
- Configuration via environment variables or `.env` files
- Dataclasses for data structures (`ExtractedObject`, `EntityRelation`, etc.)
- Graceful dependency imports with try/except for optional packages (SBERT, FAISS)

### File Organization

- Core processing logic: `scripts/` directory
- Web application: `webapp/` directory
- SQL initialization: `mysql-local/bootstrap.sql`
- Configuration templates: `.env.example` files
- Extraction outputs: `outputs/` directory (JSON files)
- Client requirements: `doc/requirement/` directory

### Error Handling

- Scripts should fail gracefully with informative error messages
- Database operations should use transactions where appropriate
- Long-running operations use `tqdm` for progress indication
- All API endpoints implement database-first with JSON fallback strategy

### Naming Conventions

- Python files: `snake_case.py`
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Database tables: `snake_case` with `eav_` prefix for EAV tables
- Object codes: `OBJ_PROJECT`, `OBJ_ASSET` (UPPER_SNAKE_CASE with `OBJ_` prefix)
- Data domains: `snake_case` directory names (`shupeidian`, `jicai`)

---

## API Endpoints

### Web Application Routes (app.py)

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main dashboard (v10.0, auto-scans DATA/ for domains) |
| `/health` | GET | Health check (returns JSON with FAISS/DB status) |
| `/extraction` | GET | Redirect to dashboard |
| `/api/domains` | GET | Auto-discover data domains in DATA/ directory |
| `/dataset/<dsid>/attributes` | GET | EAV attribute listing for a dataset |
| `/deepseek/chat` | POST | DeepSeek API proxy endpoint |
| `/rag/query` | POST | RAG semantic query (FAISS + sentence-transformers) |

### Object Extraction API (olm_api.py)

#### Object CRUD
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/olm/extracted-objects` | GET | List all/filtered objects with layer stats |
| `/api/olm/objects` | POST | Create new object |
| `/api/olm/objects/<code>` | PUT | Update object |
| `/api/olm/objects/<code>` | DELETE | Delete object |
| `/api/olm/export-objects` | GET | Export objects to JSON |

#### Relations & Architecture
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/olm/object-relations/<code>` | GET | Object's three-tier relations (concept/logical/physical) |
| `/api/olm/relation-stats` | GET | Relation statistics overview |
| `/api/olm/object-business-objects/<code>` | GET | BA-04 business object mapping |
| `/api/olm/search-entities` | GET | Entity name search across layers |

#### Visualization Data
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/olm/graph-data/<code>` | GET | Single object knowledge graph (ECharts format) |
| `/api/olm/graph-data-global` | GET | Global knowledge graph |
| `/api/olm/sankey-data` | GET | Sankey flow diagram (objects → concepts → layers) |
| `/api/olm/granularity-report` | GET | Cluster size analysis report |

#### Management & Analytics
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/olm/run-extraction` | POST | Execute object extraction pipeline |
| `/api/olm/batches` | GET | List extraction batches |
| `/api/olm/stats` | GET | System statistics |
| `/api/olm/domain-stats` | GET | Per-domain statistics |
| `/api/olm/summary` | GET | Dashboard summary (all metrics combined) |
| `/api/olm/small-objects` | GET | Low-cardinality objects with merge suggestions |
| `/api/olm/merge-objects` | POST | Merge two objects together |

#### Data Source Strategy

All endpoints implement **database-first with JSON fallback**:
1. Try MySQL (`extracted_objects` + `object_entity_relations` tables)
2. If MySQL unavailable → load from `outputs/extraction_<domain>.json`

This allows the frontend to work even without a running database.

---

## Object Extraction Algorithm

### Overview

The algorithm uses a **bottom-up inductive extraction** approach:

```
Entity Collection → SBERT Vectorization → Semantic Clustering → LLM Naming → Object Output
```

### Algorithm Steps

1. **Data Collection**: Read three-tier architecture data from Excel (DA-01, DA-02, DA-03 sheets)
2. **SBERT Vectorization**: Encode entity names using `shibing624/text2vec-base-chinese` (768-dim)
3. **Hierarchical Clustering**: Use `AgglomerativeClustering` with cosine distance (~15 clusters)
4. **LLM Naming**: Call DeepSeek API to name each cluster with an abstract object name
5. **Relation Building**: Build object-entity relations based on cluster membership

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TARGET_CLUSTER_COUNT` | 15 | Target number of clusters |
| `MAX_CLUSTER_COUNT` | 20 | Maximum clusters |
| `SBERT_MODEL_NAME` | text2vec-base-chinese | Embedding model |
| `REQUIRED_OBJECTS` | ["项目"] | Objects that must exist |

### Relation Strength

- Sample entities (top-20 in cluster): `strength = 0.9`
- Other cluster members: `strength = 0.7`

### Fallback Extractor

`simple_extractor.py` provides keyword-rule-based extraction without SBERT dependency, useful for environments where the ML model cannot be loaded.

---

## Data Domains

Data is organized by business domain under `DATA/`:

| Domain | Directory | Description | Files |
|--------|-----------|-------------|-------|
| 输配电 | `DATA/shupeidian/` | Power Distribution | 3 Excel files (~26MB total) |
| 集采 | `DATA/jicai/` | Procurement | 3 Excel files (~11MB total) |

Each Excel file contains standardized sheet names:
- `DA-01 数据实体清单-概念实体清单` (Concept Entities)
- `DA-02 数据实体清单-逻辑实体清单` (Logical Entities)
- `DA-03数据实体清单-物理实体清单` (Physical Entities)

Extraction outputs are stored in `outputs/extraction_<domain>.json`.

---

## Testing & Verification

### Health Checks

```bash
# Service health
curl http://localhost:5000/health

# Database validation
python scripts/check_db_semantic.py
```

### Common Verification Steps

1. Check web service: `curl http://localhost:5000/health`
2. Verify database connection: `python scripts/check_db_semantic.py`
3. Test data import: `python scripts/eav_full.py --excel ./DATA/shupeidian/2.xlsx`
4. Test object extraction: `python scripts/object_extractor.py --no-db --output test.json`
5. Verify JSON fallback: Ensure `outputs/extraction_shupeidian.json` and `outputs/extraction_jicai.json` exist

### Environment Verification (Agent Sessions)

```bash
bash init.sh  # Checks Python, project structure, DB, SBERT, git, data files
```

---

## Git Workflow

### Branch Naming

- Feature branches: `feature/<description>`
- Bug fixes: `fix/<description>`
- Claude/AI branches: `claude/<description>-<session-id>`

### Commit Messages

- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`
- Include context for changes
- Reference issue numbers when applicable

### Files to Never Commit

- `.env` files (use `.env.example` as template)
- `venv/` directories
- `__pycache__/` directories
- Large data files (`*.xlsx`, `*.csv` in `dataset/`)
- Model files (`models/`, `*.bin`, `*.safetensors`)
- Database data (`mysql-local/dbdata/`)
- Log and PID files (`*.log`, `*.pid`)

---

## Important Notes for AI Assistants

1. **Language**: The codebase primarily uses Chinese. **AI assistants must output in Chinese** when interacting with users. This includes:
   - All conversation responses must be in Chinese
   - Commit messages should include Chinese descriptions
   - User-facing strings and documentation use Chinese
   - Data content and attribute names are in Chinese
   - Comments in many files are in Chinese
   - Client requirement documents (`doc/requirement/`) are in Chinese

2. **Database Port**: Default is 3307 (not 3306) to avoid WSL2 conflicts

3. **Three-Tier Architecture** (maps to Excel sheet naming):
   - Concept Entity (概念实体) → DA-01 sheet → Business scenario layer
   - Logical Entity (逻辑实体) → DA-02 sheet → Interaction form layer
   - Physical Entity (物理实体) → DA-03 sheet → Database layer

4. **Required Object**: "项目" (Project) must always be extracted per client requirement

5. **Embedding Model**: Uses `shibing624/text2vec-base-chinese` (768 dimensions)

6. **Object Types**:
   - `CORE`: Core objects (Project, Device, Asset)
   - `DERIVED`: Derived objects (Task, Cost)
   - `AUXILIARY`: Auxiliary objects (Document, Process)

7. **JSON Fallback**: All API endpoints must support database-unavailable scenarios by falling back to `outputs/extraction_*.json` files

8. **Multi-Domain Architecture**: Data is organized per-domain under `DATA/`. The webapp auto-discovers domains via `/api/domains`. New domains can be added by creating a new subdirectory with Excel files following the DA-01/02/03 sheet naming convention.

9. **Client Requirements**: Stored in `doc/requirement/0.md` (core requirements) and `doc/requirement/1.md` (clarifications). The client is 南方电网 (China Southern Power Grid).

10. **Frontend Style**: v10.0 dashboard style should be preserved. Old "统一本体" (unified ontology) features were removed per client request; current focus is purely on object extraction + three-tier association.

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| MySQL connection refused | Check port 3307, verify MySQL is running |
| Import encoding errors | Ensure files are UTF-8 encoded |
| Web service won't start | Check if port 5000 is in use: `fuser 5000/tcp` |
| Empty extraction results | Verify `DATA/<domain>/` exists with DA-01/02/03 sheets |
| Missing model files | Models download automatically on first run (~400MB) |
| API returns empty data | Check `outputs/extraction_<domain>.json` exists (JSON fallback) |
| SBERT not available | Use `simple_extractor.py` as fallback |

### Log Locations

- Web app logs: `webapp/webapp.log`
- Web app PID: `webapp/webapp.pid`
- Docker logs: `docker compose logs -f`

---

*Last updated: 2026-02-19*

---

## Long-Running Agent Workflow

本项目使用 agent harness 实现跨 session 持续工作。状态文件：
- `task.json` — 结构化任务列表（JSON，防误改）
- `claude-progress.txt` — session 日志
- `init.sh` — 环境验证脚本

### Session 启动（每次必须执行）

1. `bash init.sh` — 验证环境
2. `tail -80 claude-progress.txt` — 读上次进度
3. `git log --oneline -20` — 读 git 历史
4. 解析 task.json → 选最高优先级的可执行任务
5. 向用户报告选定任务，开始执行

### 任务执行

- 按 task.steps 逐步执行，不跳步
- 所有 task.verification 通过才能标记 completed
- 用 Conventional Commits 提交（feat/fix/docs/chore）

### 障碍处理

- 记录到 progress.txt（OBSTACLE-ID）
- 记录到 task.json notes
- 不标记为 completed
- 切换到下一可用任务

### task.json 修改规则

可改：`status`, `completed_at`, `session_id`, `notes`
禁改：`id`, `title`, `steps`, `verification`, `blocked_by`, `priority`

### 命令映射

| 任务类别 | 命令 |
|---------|------|
| assessment | 环境验证 + 代码审计 |
| development | 功能开发 |
| testing | 功能测试 |
| review | 代码审查 |
| documentation | 文档与部署 |
