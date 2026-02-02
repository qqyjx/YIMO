# CLAUDE.md - AI Assistant Guide for YIMO

> This document provides context and guidelines for AI assistants working on the YIMO codebase.

## Project Overview

**YIMO** is an Object Extraction & Three-Tier Architecture Association System for smart grid data management. The core concept is extracting highly abstract "objects" (like Project, Device, Asset) from data architecture documents and establishing associations with the three-tier architecture (Concept Entity, Logical Entity, Physical Entity).

### Problem Solved

Data architecture documents contain three layers of entities:
- **Concept Entity (概念实体)**: Business scenario layer
- **Logical Entity (逻辑实体)**: Interaction form layer
- **Physical Entity (物理实体)**: Database layer

YIMO extracts abstract "objects" from these entities and builds association relationships, enabling:
- Unified object model across different data domains
- Traceable relationships between objects and three-tier entities
- Foundation for comparison with enterprise data center

### Core Components

1. **EAV Data Model** - Entity-Attribute-Value storage for heterogeneous data
2. **Semantic Clustering** - SBERT-based Chinese text clustering for object extraction
3. **LLM Object Naming** - DeepSeek/GPT integration for cluster naming
4. **Web Visualization** - Flask app with object cards and relation panels

---

## Codebase Structure

```
YIMO/
├── scripts/                    # Core Python processing modules
│   ├── object_extractor.py    # Object extraction algorithm (SBERT + LLM)
│   ├── eav_full.py            # Excel → EAV import (multi-sheet)
│   ├── eav_csv.py             # CSV → EAV import
│   ├── eav_semantic_dedupe.py # SBERT semantic deduplication
│   ├── import_all.py          # Batch import
│   └── check_db_semantic.py   # Database health checks
│
├── webapp/                     # Flask web application
│   ├── app.py                 # Main Flask app + RAG interface
│   ├── olm_api.py             # REST API Blueprint for Object Extraction
│   ├── requirements.txt       # Python web dependencies
│   ├── .env.example           # Configuration template
│   ├── start_web.sh           # Service start script
│   ├── stop_web.sh            # Service stop script
│   └── templates/             # Jinja2 HTML templates
│       ├── 10.0.html          # Main dashboard (v10.0)
│       ├── object_extraction.html
│       └── home.html
│
├── mysql-local/               # MySQL configuration
│   ├── bootstrap.sql          # Database initialization
│   ├── my.cnf                 # MySQL config
│   └── init_local_mysql.sh    # Local MySQL setup
│
├── DATA/                      # Data directory
│   ├── 1.xlsx, 2.xlsx, 3.xlsx # Data architecture files
│   └── (future: 计划财务域等)  # Additional domain data
│
├── figures/                   # Architecture diagrams (Mermaid)
│   └── architecture/
│       └── object_extraction_algorithm.mmd
│
├── docker-compose.yml         # Docker orchestration
├── Dockerfile                 # Multi-stage container build
├── deploy.sh                  # Interactive deployment script
└── requirements.txt           # Root Python dependencies
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.10+, Flask 3.0 |
| **Database** | MySQL 8.0 (InnoDB, UTF8MB4) |
| **ML/AI** | SBERT (text2vec-base-chinese), scikit-learn |
| **LLM** | Deepseek API integration |
| **Frontend** | HTML5/Jinja2, CSS3 |
| **DevOps** | Docker, Docker Compose, Bash |

### Key Dependencies

```
flask>=3.0.3               # Web framework
pymysql>=1.1.1             # MySQL driver
sentence-transformers>=2.7 # SBERT embeddings
scikit-learn>=1.3          # Clustering algorithms
pandas>=2.0                # Data processing
openpyxl>=3.1              # Excel I/O
python-dotenv>=1.0.1       # Environment config
requests>=2.32.3           # HTTP client
```

---

## Development Workflows

### Environment Setup

```bash
# Option 1: Docker (recommended)
./docker-start.sh

# Option 2: Local development
./deploy.sh
```

### Running the Web Application

```bash
# Start service
cd webapp && ./start_web.sh

# Manual start with venv
source venv/bin/activate
cd webapp && python app.py

# Verify health
curl http://localhost:5000/health
```

### Object Extraction

```bash
# Command line extraction (no LLM)
python scripts/object_extractor.py \
    --data-dir DATA \
    --target-clusters 15 \
    --no-db \
    --output result.json

# With LLM naming
python scripts/object_extractor.py \
    --data-dir DATA \
    --target-clusters 15 \
    --use-llm \
    --db-host localhost \
    --db-port 3307 \
    --db-name eav_db
```

### Data Import

```bash
# Import Excel to EAV
python scripts/eav_full.py --excel ./DATA/2.xlsx

# Import CSV
python scripts/eav_csv.py --csv ./data.csv --db eav_db
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
| `extracted_objects` | Core objects (object_code, object_name, object_type) |
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

### File Organization

- Core processing logic: `scripts/` directory
- Web application: `webapp/` directory
- SQL initialization: `mysql-local/bootstrap.sql`
- Configuration templates: `.env.example` files

### Error Handling

- Scripts should fail gracefully with informative error messages
- Database operations should use transactions where appropriate
- Long-running operations use `tqdm` for progress indication

### Naming Conventions

- Python files: `snake_case.py`
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Database tables: `snake_case` with `eav_` prefix for EAV tables

---

## API Endpoints

### Web Application Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main dashboard (v10.0) |
| `/health` | GET | Health check endpoint |
| `/extraction` | GET | Object extraction page |
| `/rag/query` | POST | RAG-based query endpoint |
| `/api/olm/*` | REST | Object Extraction API |

### Object Extraction API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/olm/extracted-objects` | GET | List extracted objects |
| `/api/olm/object-relations/<code>` | GET | Get object's three-tier relations |
| `/api/olm/relation-stats` | GET | Relation statistics |
| `/api/olm/run-extraction` | POST | Execute object extraction |
| `/api/olm/export-objects` | GET | Export objects to JSON |
| `/api/olm/objects` | POST | Create new object |
| `/api/olm/objects/<code>` | PUT | Update object |
| `/api/olm/objects/<code>` | DELETE | Delete object |

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
3. Test data import: `python scripts/eav_full.py --excel ./DATA/2.xlsx`
4. Test object extraction: `python scripts/object_extractor.py --no-db --output test.json`

---

## Git Workflow

### Branch Naming

- Feature branches: `feature/<description>`
- Bug fixes: `fix/<description>`
- Claude/AI branches: `claude/<description>-<session-id>`

### Commit Messages

- Use clear, descriptive messages
- Include context for changes
- Reference issue numbers when applicable

### Files to Never Commit

- `.env` files (use `.env.example` as template)
- `venv/` directories
- `__pycache__/` directories
- Large data files (`*.xlsx`, `*.csv` in `dataset/`)
- Model files (`models/`, `*.bin`, `*.safetensors`)
- Database data (`mysql-local/dbdata/`)

---

## Important Notes for AI Assistants

1. **Language**: The codebase primarily uses Chinese for:
   - User-facing strings and documentation
   - Data content and attribute names
   - Comments in some files

2. **Database Port**: Default is 3307 (not 3306) to avoid WSL2 conflicts

3. **Three-Tier Architecture**:
   - Concept Entity (概念实体) - Business scenario layer
   - Logical Entity (逻辑实体) - Interaction form layer
   - Physical Entity (物理实体) - Database layer

4. **Required Object**: "项目" (Project) must always be extracted per client requirement

5. **Embedding Model**: Uses `shibing624/text2vec-base-chinese` (768 dimensions)

6. **Object Types**:
   - `CORE`: Core objects (Project, Device, Asset)
   - `DERIVED`: Derived objects (Task, Cost)
   - `AUXILIARY`: Auxiliary objects (Document, Process)

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| MySQL connection refused | Check port 3307, verify MySQL is running |
| Import encoding errors | Ensure files are UTF-8 encoded |
| Web service won't start | Check if port 5000 is in use: `fuser 5000/tcp` |
| Empty extraction results | Verify DATA/2.xlsx exists with DA-01/02/03 sheets |
| Missing model files | Models download automatically on first run |

### Log Locations

- Web app logs: `webapp/*.log` or `/tmp/webapp.log`
- Docker logs: `docker compose logs -f`

---

*Last updated: 2026-02*
