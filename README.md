# YIMO - 对象抽取与三层架构关联系统

从数据架构文档中自动抽取"对象"（如项目、设备、资产），并建立与三层架构（概念实体、逻辑实体、物理实体）的关联关系。

## 快速开始

```bash
# 一键演示（推荐）
chmod +x demo.sh && ./demo.sh

# 访问 http://localhost:5000/extraction
```

## 核心概念

**三层架构**：

| 层级 | 说明 | 数据来源 |
|------|------|----------|
| 概念实体 | 业务场景层 | DA-01 概念实体清单 |
| 逻辑实体 | 交互表单层 | DA-02 逻辑实体清单 |
| 物理实体 | 数据库层 | DA-03 物理实体清单 |

**对象**：从三层架构实体中抽取的高度抽象概念（项目、设备、资产、合同等）

## 数据目录结构

```
DATA/
├── shupeidian/          # 输配电域
│   ├── 1.xlsx
│   ├── 2.xlsx
│   └── 3.xlsx
└── jicai/               # 集采域
    ├── 1.xlsx
    ├── 2.xlsx
    └── 3.xlsx
```

每个 Excel 文件需包含以下工作表：
- `DA-01 数据实体清单-概念实体清单`
- `DA-02 数据实体清单-逻辑实体清单`
- `DA-03数据实体清单-物理实体清单`

## 使用方法

### 一键演示（推荐）

```bash
./demo.sh
```

脚本会自动：
1. 检查并安装依赖
2. 抽取所有数据域的对象
3. 启动 Web 服务
4. 打印访问地址

### 启停服务

```bash
# 启动（推荐，自动检测环境、健康检查）
cd webapp && ./start_web.sh

# 停止
cd webapp && ./stop_web.sh
```

### 手动运行

```bash
# 1. 对象抽取（规则命名，输出到 JSON）
python3 scripts/object_extractor.py \
    --data-dir DATA/shupeidian \
    --data-domain shupeidian \
    --target-clusters 15 \
    --no-db \
    --output outputs/extraction_shupeidian.json

# 2. 对象抽取（LLM 命名，需配置 DEEPSEEK_API_KEY）
python3 scripts/object_extractor.py \
    --data-dir DATA/shupeidian \
    --data-domain shupeidian \
    --target-clusters 15 \
    --use-llm \
    --no-db \
    --output outputs/extraction_shupeidian.json

# 3. 启动 Web 服务
cd webapp && python3 app.py

# 4. 访问 http://localhost:5000/extraction
```

## 数据源机制

系统采用 **数据库优先 + JSON 回退** 的双数据源架构：

- **数据库可用时**：从 MySQL 实时查询对象和关联关系
- **数据库不可用时**：自动回退到 `outputs/extraction_<domain>.json` 文件
- 通过 `/api/olm/export-objects?domain=shupeidian` 可将数据库数据导出到 JSON，保持两者同步

## Web 界面操作

1. 打开 http://localhost:5000/extraction
2. 使用顶部下拉框选择数据域（输配电/集采），支持多域切换
3. 点击对象卡片，查看其关联的三层实体
4. 关联实体按强度排序，高强度用绿色标记

## 抽取算法

采用 **语义聚类 + LLM归纳命名** 的自下而上归纳方法：

```
实体名称收集 → SBERT向量化 → 层次聚类(15个) → LLM归纳命名 → 对象输出
```

- **SBERT模型**: `shibing624/text2vec-base-chinese`
- **聚类算法**: AgglomerativeClustering（余弦距离）
- **LLM命名**: Deepseek API（可选，需配置 API Key）
- **关联强度**: 样本实体 0.9，其他成员 0.7

## 数据库结构

### EAV 核心表

| 表名 | 说明 |
|------|------|
| `eav_datasets` | 数据集元信息 |
| `eav_entities` | 实体（每行数据） |
| `eav_attributes` | 属性定义 |
| `eav_values` | 值存储 |

### 语义相似度表

| 表名 | 说明 |
|------|------|
| `eav_semantic_canon` | 规范值（SBERT聚类后的代表文本） |
| `eav_semantic_mapping` | 原始值 → 规范值映射 |

### 对象抽取表

| 表名 | 说明 |
|------|------|
| `extracted_objects` | 抽取的核心对象 |
| `object_synonyms` | 对象同义词 |
| `object_entity_relations` | 对象与三层架构关联关系（核心） |
| `object_extraction_batches` | 抽取批次记录 |

## 项目结构

```
YIMO/
├── demo.sh                    # 一键演示脚本
├── scripts/
│   ├── object_extractor.py    # 语义聚类对象抽取（核心）
│   └── simple_extractor.py    # 简化版（无 SBERT）
├── webapp/
│   ├── app.py                 # Flask 应用
│   ├── olm_api.py             # 对象抽取 API
│   └── templates/
│       └── object_extraction.html
├── DATA/                      # 数据域目录
│   ├── shupeidian/            # 输配电
│   └── jicai/                 # 集采
└── outputs/                   # 抽取结果 JSON
```

## API 接口

| 接口 | 说明 |
|------|------|
| `GET /api/olm/extracted-objects?domain=` | 获取对象列表 |
| `GET /api/olm/object-relations/<code>?domain=` | 获取对象关联的三层实体 |
| `POST /api/olm/run-extraction` | 执行对象抽取 |

## 配置

### 环境变量

```bash
# 数据库配置（可选，无数据库时使用 JSON 文件）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_DB=eav_db
MYSQL_USER=eav_user
MYSQL_PASSWORD=eavpass123

# LLM 配置（用于对象命名）
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
```

### 对象抽取参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--target-clusters` | 15 | 目标聚类数量 |
| `--use-llm` | False | 使用 Deepseek LLM 归纳命名 |
| `--no-db` | False | 不写入数据库，输出到 JSON |
| `--output` | None | 输出 JSON 文件路径 |

## 依赖

- Python 3.10+
- pandas, flask, scikit-learn, numpy, openpyxl, tqdm, pymysql
- sentence-transformers（用于语义聚类）
- requests（用于 LLM API 调用）

## 停止服务

```bash
# 推荐方式
cd webapp && ./stop_web.sh

# 备用
pkill -f 'python3.*app.py'
```

## License

MIT
