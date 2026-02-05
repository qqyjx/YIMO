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

### 手动运行

```bash
# 1. 对象抽取（输出到 JSON）
python3 scripts/object_extractor.py \
    --data-dir DATA/shupeidian \
    --data-domain shupeidian \
    --target-clusters 15 \
    --no-db \
    --output outputs/extraction_shupeidian.json

# 2. 启动 Web 服务
cd webapp && python3 app.py

# 3. 访问 http://localhost:5000/extraction
```

## Web 界面操作

1. 打开 http://localhost:5000/extraction
2. 使用顶部下拉框选择数据域（输配电/集采）
3. 点击对象卡片，查看其关联的三层实体
4. 关联实体按强度排序，高强度用绿色标记

## 抽取算法

采用 **语义聚类 + 规则命名** 的自下而上归纳方法：

```
实体名称收集 → SBERT向量化 → 层次聚类(15个) → 规则/LLM命名 → 对象输出
```

- **SBERT模型**: `shibing624/text2vec-base-chinese`
- **聚类算法**: AgglomerativeClustering（余弦距离）
- **关联强度**: 样本实体 0.9，其他成员 0.7

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

## 依赖

- Python 3.10+
- pandas, flask, scikit-learn, numpy, openpyxl, tqdm
- sentence-transformers（可选，用于语义聚类）

## 停止服务

```bash
pkill -f 'python3.*app.py'
```

## License

MIT
