# YIMO EAV 工作总结

> 南方电网智能数据管理项目 - EAV 模块技术文档

## 1. 项目背景

YIMO 是面向南方电网的智能数据管理平台，采用 EAV (Entity-Attribute-Value) 数据模型来处理电网设备的异构、稀疏数据。本文档总结了 EAV 模块的已完成工作和技术实现。

---

## 2. 已完成的 EAV 工作

### 2.1 核心功能模块

| 模块 | 状态 | 描述 |
|------|------|------|
| EAV 数据导入 | ✅ 完成 | Excel/CSV 多表单导入，自动类型推断 |
| EAV 数据库模型 | ✅ 完成 | 4 张核心表 + 2 张语义辅助表 |
| 语义去重引擎 | ✅ 完成 | SBERT 句向量 + 余弦相似度聚类 |
| 全局去重 | ✅ 完成 | 跨数据集同名属性合并处理 |
| Web 可视化 | ✅ 完成 | Flask + RAG 检索 + LLM 集成 |
| 自动化脚本 | ✅ 完成 | 批量处理、监控、报告生成 |

### 2.2 技术实现亮点

1. **灵活的 EAV 模型**：适应电网设备参数多样化、属性不固定的特点
2. **多 GPU 加速**：已验证 4×RTX 4090 D 并行编码
3. **中文语义理解**：使用 `text2vec-base-chinese` 专用中文模型
4. **透明规范化**：通过 SQL 视图实现数据自动规范化

---

## 3. EAV 数据库架构

### 3.1 核心表结构

```
┌─────────────────┐     ┌─────────────────┐
│  eav_datasets   │────<│  eav_entities   │
│ (数据集元信息)  │     │ (实体/每行数据) │
└─────────────────┘     └────────┬────────┘
                                 │
┌─────────────────┐     ┌────────┴────────┐
│ eav_attributes  │────<│   eav_values    │
│  (属性定义)     │     │  (值存储)       │
└─────────────────┘     └─────────────────┘
```

### 3.2 语义辅助表

```
┌─────────────────────┐     ┌─────────────────────┐
│ eav_semantic_canon  │────<│ eav_semantic_mapping│
│ (规范值/簇代表)     │     │ (原文→规范值映射)  │
└─────────────────────┘     └─────────────────────┘
```

### 3.3 表字段详情

#### eav_datasets（数据集表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| name | VARCHAR | 数据集名称 |
| source_file | VARCHAR | 源文件路径 |
| imported_at | DATETIME | 导入时间 |

#### eav_entities（实体表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| dataset_id | INT | 所属数据集 |
| external_id | VARCHAR | 外部 ID |
| row_number | INT | 原始行号 |
| row_hash | VARCHAR | 行数据哈希 |

#### eav_attributes（属性表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| dataset_id | INT | 所属数据集 |
| name | VARCHAR | 属性名（标准化） |
| display_name | VARCHAR | 显示名 |
| data_type | ENUM | text/number/datetime/bool |
| ord_index | INT | 列顺序 |

#### eav_values（值表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| entity_id | INT | 所属实体 |
| attribute_id | INT | 所属属性 |
| value_text | TEXT | 文本值 |
| value_number | DECIMAL | 数值 |
| value_datetime | DATETIME | 日期时间值 |
| value_bool | TINYINT | 布尔值 |
| raw_text | TEXT | 原始文本（保留） |

---

## 4. 语义去重技术方案

### 4.1 处理流程

```
原始数据 → EAV 导入 → 属性值提取 → SBERT 编码 → 相似度计算 → 聚类 → 规范值生成
```

### 4.2 算法参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 相似度阈值 | 0.86 | 余弦相似度，越高越严格 |
| 批处理大小 | 512 | GPU 编码批大小 |
| 最大候选数 | 5000 | 每属性最大文本数 |

### 4.3 去重模式

1. **单数据集模式**：独立处理每个数据集的属性值
2. **全局模式**：跨数据集合并同名属性，统一聚类

---

## 5. 代码文件清单

### 5.1 核心脚本

| 文件 | 行数 | 功能 |
|------|------|------|
| `scripts/eav_full.py` | ~600 | Excel 多表单导入 |
| `scripts/eav_csv.py` | ~400 | CSV 导入 |
| `scripts/eav_semantic_dedupe.py` | ~800 | 语义去重主逻辑 |
| `scripts/auto_finalize_global.py` | ~150 | 自动监控收尾 |
| `scripts/check_db_semantic.py` | ~80 | 数据库健康检查 |

### 5.2 Web 应用

| 文件 | 功能 |
|------|------|
| `webapp/app.py` | Flask 主应用 + RAG 接口 |
| `webapp/templates/*.html` | 前端页面模板 |
| `webapp/start_web.sh` | 启动脚本 |

### 5.3 配置与工具

| 文件 | 功能 |
|------|------|
| `scripts/run_dedupe_full.sh` | 完整去重运行脚本 |
| `scripts/create_normalized_view.sql` | 规范化视图 SQL |
| `mysql-local/init_local_mysql.sh` | 本地 MySQL 初始化 |

---

## 6. 运行成果

### 6.1 数据统计（示例）

```
已处理数据集：3
总实体数：~50,000
总属性数：~200
去重映射记录：22,273
规范值簇数：12,582
频次覆盖：555,300
```

### 6.2 输出目录结构

```
outputs/semantic_dedupe_gpu_full/
├── single/                  # 单数据集去重结果
│   ├── dataset_1/
│   ├── dataset_2/
│   └── summary/
└── global/                  # 全局去重结果
    ├── dataset_1_global/
    ├── dataset_2_global/
    └── summary/
        ├── FINALIZED_OK     # 完成标记
        └── db_check.txt     # 检查报告
```

---

## 7. 技术栈总结

### 7.1 后端

- **语言**：Python 3.10+
- **数据库**：MySQL 8.0 (InnoDB, UTF8MB4)
- **Web 框架**：Flask 3.0
- **向量模型**：Sentence-Transformers (SBERT)
- **向量检索**：FAISS

### 7.2 核心依赖

```
pandas >= 2.0          # 数据处理
openpyxl >= 3.1        # Excel 读写
pymysql >= 1.1         # MySQL 驱动
sentence-transformers  # 文本向量化
scikit-learn           # 聚类算法
torch                  # 深度学习框架
faiss-cpu/gpu          # 向量索引
flask >= 3.0           # Web 框架
```

---

## 8. 下一步工作建议

### 8.1 功能增强

- [ ] 增量导入支持（检测已存在数据，只导入新增）
- [ ] 更多数据源支持（JSON、API 接口）
- [ ] 属性自动分类与标签

### 8.2 性能优化

- [ ] 大规模数据分片处理
- [ ] 索引优化与查询缓存
- [ ] 异步任务队列（Celery）

### 8.3 安全加固

- [ ] Web API 认证（JWT/OAuth2）
- [ ] 数据库连接加密
- [ ] 操作审计日志

### 8.4 部署运维

- [ ] Docker 容器化部署
- [ ] Kubernetes 编排支持
- [ ] 监控告警集成

---

## 9. 参考资料

- [SBERT 官方文档](https://www.sbert.net/)
- [text2vec-base-chinese 模型](https://huggingface.co/shibing624/text2vec-base-chinese)
- [FAISS 向量检索库](https://github.com/facebookresearch/faiss)
- [EAV 数据模型介绍](https://en.wikipedia.org/wiki/Entity%E2%80%93attribute%E2%80%93value_model)

---

## 10. 联系方式

如有问题或建议，请联系项目团队。

---

*文档版本：v1.0*
*更新日期：2025-01*
