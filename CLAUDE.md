# CLAUDE.md - AI Assistant Guide for YIMO

> This document provides context and guidelines for AI assistants working on the YIMO codebase.

## Project Overview

**YIMO** (Your Intelligent Master Ontology) is a Universal Lifecycle Ontology Manager for smart grid asset data management. The core concept is "一模到底" (Unified Ontology) - using a single unified ontology model to track assets throughout their entire lifecycle from planning to operations.

### Problem Solved

Smart grid assets often have different identities across systems:
- Feasibility Study: "1#主变" (Main Transformer 1)
- Design: "主变一" (Main Transformer One)
- Construction: "主变压器1" (Main Power Transformer 1)
- SCADA: "TRF001"
- Finance: "资产-变1" (Asset-Transformer 1)

YIMO assigns a global unique identifier (e.g., `GA-2024-TRF-001`) and tracks it through the entire lifecycle.

### Core Components

1. **EAV Data Model** - Entity-Attribute-Value storage for heterogeneous equipment data
2. **Semantic Deduplication** - SBERT-based Chinese text clustering
3. **Lifecycle Fusion Agent** - LLM-driven entity matching across lifecycle stages
4. **AIOps Consistency Monitor** - Real-time data quality monitoring
5. **Web Visualization** - Flask app with RAG queries and Deepseek LLM integration

---

## Codebase Structure

```
YIMO/
├── scripts/                    # Core Python processing modules
│   ├── eav_full.py            # Excel → EAV import (multi-sheet)
│   ├── eav_csv.py             # CSV → EAV import
│   ├── eav_semantic_dedupe.py # SBERT semantic deduplication
│   ├── import_all.py          # Batch import with lifecycle staging
│   ├── agent_lifecycle_fusion.py    # LLM entity fusion
│   ├── aiops_consistency_monitor.py # Data quality monitoring
│   ├── object_lifecycle_manager.py  # Three-tier ontology management
│   ├── mechanism_function_engine.py # Business rules engine
│   ├── penetration_query_engine.py  # Cross-layer query engine
│   ├── auto_finalize_global.py      # Auto finalization & reporting
│   └── check_db_semantic.py         # Database health checks
│
├── webapp/                     # Flask web application
│   ├── app.py                 # Main Flask app + RAG interface
│   ├── olm_api.py             # REST API Blueprint for OLM
│   ├── requirements.txt       # Python web dependencies
│   ├── .env.example           # Configuration template
│   ├── start_web.sh           # Service start script
│   ├── stop_web.sh            # Service stop script
│   ├── components/            # TypeScript/React frontend components
│   │   ├── ChatModule.tsx
│   │   ├── VisionModule.tsx
│   │   └── WriterModule.tsx
│   └── templates/             # Jinja2 HTML templates
│       ├── 10.0.html          # Main dashboard (v10.0)
│       ├── lifecycle_manager.html
│       ├── object_lifecycle_manager.html
│       ├── anomalies.html
│       └── finance_supervision.html
│
├── mysql-local/               # MySQL configuration
│   ├── bootstrap.sql          # Database initialization
│   ├── my.cnf                 # MySQL config
│   └── init_local_mysql.sh    # Local MySQL setup
│
├── DATA/                      # Sample data directory
│   ├── 1.xlsx, 2.xlsx, 3.xlsx # Original datasets
│   └── lifecycle_demo/        # Lifecycle demo data
│
├── doc/                       # Documentation
├── figures/                   # Architecture diagrams (Mermaid)
├── outputs/                   # Execution results
├── bat/                       # Windows batch scripts
│
├── docker-compose.yml         # Docker orchestration
├── Dockerfile                 # Multi-stage container build
├── deploy.sh                  # Interactive deployment script
├── docker-start.sh            # Docker quick-start
└── requirements.txt           # Root Python dependencies
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.10+, Flask 3.0 |
| **Database** | MySQL 8.0 (InnoDB, UTF8MB4) |
| **ML/AI** | SBERT (text2vec-base-chinese), FAISS |
| **LLM** | Deepseek API integration |
| **Frontend** | HTML5/Jinja2, TypeScript/React components |
| **DevOps** | Docker, Docker Compose, Bash |

### Key Dependencies

```
flask>=3.0.3               # Web framework
pymysql>=1.1.1             # MySQL driver
sentence-transformers>=2.7 # SBERT embeddings
faiss-cpu>=1.7.4           # Vector search
pandas>=2.0                # Data processing
openpyxl>=3.1              # Excel I/O
python-dotenv>=1.0.1       # Environment config
requests>=2.32.3           # HTTP client
SQLAlchemy>=2.0.32         # ORM
```

---

## Development Workflows

### Environment Setup

```bash
# Option 1: Docker (recommended)
./docker-start.sh

# Option 2: Local development
./deploy.sh                    # Interactive setup
./deploy.sh --with-demo-data   # With sample data
./deploy.sh --cn-mirror        # Use China pip mirror
```

### Running the Web Application

```bash
# Start service
cd webapp && ./start_web.sh

# Manual start with venv
source venv/bin/activate
cd webapp && python app.py

# Background mode
nohup python app.py > /tmp/webapp.log 2>&1 &

# Stop service
./stop_web.sh
# or
fuser -k 5000/tcp

# Verify health
curl http://localhost:5000/health
```

### Data Import Pipeline

```bash
# Stage 1: Import Excel with lifecycle stage
python scripts/eav_full.py --excel ./DATA/planning/equipment.xlsx --stage Planning

# Stage 2: Import CSV
python scripts/eav_csv.py --csv ./data.csv --db eav_db

# Batch import by stage
python scripts/import_all.py --stage planning --dir ./DATA/planning/
python scripts/import_all.py --stage design --dir ./DATA/design/
python scripts/import_all.py --stage construction --dir ./DATA/construction/
python scripts/import_all.py --stage operation --dir ./DATA/operation/
python scripts/import_all.py --stage finance --dir ./DATA/finance/
```

### Semantic Deduplication

```bash
# Single dataset mode
python scripts/eav_semantic_dedupe.py --dataset-id 1 \
  --threshold 0.86 --batch-size 512 --multi-gpu -1

# Global mode (cross-dataset)
python scripts/eav_semantic_dedupe.py --dataset-ids 1,2,3 --global-dedupe
```

### Lifecycle Fusion

```bash
# Build unified ontology
python scripts/agent_lifecycle_fusion.py --batch-size 100 --mode full

# Monitor data consistency
python scripts/aiops_consistency_monitor.py --check-all

# Generate reports
python scripts/auto_finalize_global.py
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

### Lifecycle Tables

| Table | Purpose |
|-------|---------|
| `lifecycle_stages` | Five standard stages (Planning/Design/Construction/Operation/Finance) |
| `global_asset_index` | Unified ontology (global_uid, trust_score, golden_attributes) |
| `entity_global_mapping` | Entity to global asset mappings with confidence |
| `fusion_logs` | LLM fusion decision audit trail |
| `data_anomalies` | Quality alerts and monitoring |

### Anomaly Types Monitored

- `temporal_violation` - Lifecycle order violations
- `value_drift` - Unexpected value changes across stages
- `missing_stage` - Gaps in lifecycle continuity
- `duplicate_conflict` - Multiple candidates for same asset
- `schema_mismatch` - Type inconsistencies
- `orphan_entity` - Unlinked entities

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
| `/` | GET | Main dashboard (add `?v=10.0` for v10) |
| `/health` | GET | Health check endpoint |
| `/lifecycle` | GET | Unified ontology visualization |
| `/anomalies` | GET | Anomaly monitoring dashboard |
| `/rag/query` | POST | RAG-based query endpoint |
| `/api/olm/*` | REST | Object Lifecycle Manager API |

### OLM API Blueprint

- `GET /api/olm/assets` - List global assets
- `GET /api/olm/assets/<uid>` - Get asset details
- `POST /api/olm/assets` - Create new asset
- `PUT /api/olm/assets/<uid>` - Update asset
- `GET /api/olm/mappings` - Entity-global mappings
- `GET /api/olm/anomalies` - Data anomalies

---

## Testing & Verification

### Health Checks

```bash
# Service health
curl http://localhost:5000/health

# Database validation
python scripts/check_db_semantic.py
```

### Demo Data

```bash
# Generate lifecycle demo data
cd DATA/lifecycle_demo && python generate_demo_data.py

# Deploy with demo data
./deploy.sh --with-demo-data
```

### Common Verification Steps

1. Check web service: `curl http://localhost:5000/health`
2. Verify database connection: `python scripts/check_db_semantic.py`
3. Test data import: `python scripts/eav_full.py --excel ./DATA/1.xlsx`
4. Verify fusion: Check `/lifecycle` page for unified assets

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

## Common Tasks

### Adding a New Data Source

1. Place data files in appropriate `DATA/<stage>/` directory
2. Run import: `python scripts/import_all.py --stage <stage> --dir <path>`
3. Run fusion: `python scripts/agent_lifecycle_fusion.py`
4. Verify in web UI at `/lifecycle`

### Modifying Database Schema

1. Update `mysql-local/bootstrap.sql`
2. Apply changes: `mysql -u eav_user -p eav_db < mysql-local/bootstrap.sql`
3. Update relevant Python models/queries

### Adding New Web Pages

1. Create template in `webapp/templates/`
2. Add route in `webapp/app.py`
3. Update navigation links in main template

### Debugging Data Quality Issues

1. Check anomalies: `python scripts/aiops_consistency_monitor.py --check-all`
2. View dashboard: `http://localhost:5000/anomalies`
3. Review fusion logs in `fusion_logs` table

---

## Important Notes for AI Assistants

1. **Language**: The codebase primarily uses Chinese for:
   - User-facing strings and documentation
   - Data content and attribute names
   - Comments in some files

2. **Database Port**: Default is 3307 (not 3306) to avoid WSL2 conflicts

3. **Lifecycle Stages**: Always use the five standard stages:
   - Planning (规划)
   - Design (设计)
   - Construction (建设)
   - Operation (运维)
   - Finance (财务)

4. **Global UID Format**: `GA-YYYY-<TYPE>-NNN` (e.g., `GA-2024-TRF-001`)

5. **Trust Score**: Range 0-1, DECIMAL(5,4), reflects data completeness/consistency

6. **Embedding Model**: Uses `shibing624/text2vec-base-chinese` (768 dimensions)

7. **Multi-GPU Support**: Use `--multi-gpu -1` to utilize all available GPUs

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| MySQL connection refused | Check port 3307, verify MySQL is running |
| Import encoding errors | Ensure files are UTF-8 encoded |
| Web service won't start | Check if port 5000 is in use: `fuser 5000/tcp` |
| Empty lifecycle visualization | Run `agent_lifecycle_fusion.py` first |
| Missing model files | Models download automatically on first run |

### Log Locations

- Web app logs: `webapp/*.log` or `/tmp/webapp.log`
- Deduplication outputs: `outputs/semantic_dedupe_gpu_full/`
- Docker logs: `docker compose logs -f`

---

*Last updated: 2026-02*
