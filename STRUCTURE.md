# YIMO 仓库结构 — 演示版 / 合规版双轨

> 一图看懂：本仓库同时维护两套实现，**互不替代**，对应甲方明确的"本地演示 vs 远程部署 分开写"分工。
>
> 系统正式名（任务书）：**支撑孪生体新范式多维数据融合分析框架原型系统**

## 双版本对照速查

|       | 演示版（过第三方测试） | 合规版（南网正式部署） |
|-------|--------------------|---------------------|
| **目录** | [`webapp/`](webapp/) | [`platform/`](platform/) |
| **后端** | Python 3.10 + Flask 3.0 | Java 17 + Spring Boot 3.2 + MyBatis-Plus |
| **数据库** | MySQL 8 @ 3307 | 达梦 DM8（本地用 MySQL profile=local 兜底） |
| **前端** | Jinja2 HTML + ECharts (`templates/10.0.html` 5050 行) | Vue 3 + Vite + ElementPlus（南网组件库 SDK 拿到后替换） |
| **入口端口** | `:5000` | 后端 `:8080`，前端 `:5173` |
| **算法** | `scripts/object_extractor.py` 直接 import | `platform/algo/` FastAPI 容器（HTTP 调） |
| **目标场景** | 甲方功能评审、第三方软件测评 | 南网研发 V 区 / 正式环境合规上线 |
| **更新节奏** | 快迭代（每周可改） | 严控变更（按规范走、要 review） |
| **代码状态** | 22 域 EAV 入库 + 跨域分析 + 数据血缘 + 低代码 CRUD 全功能 | Phase 1+2 API 实现，Vue 3 骨架，DM DDL 5 表 2 视图 |

## 如何启动

### 演示版（最常用）

```bash
cd /home/qq/YIMO
bash start.sh                      # 自动起 MySQL + Flask
# 浏览器: http://localhost:5000/    （默认 v10.0 模板）
#         http://localhost:5000/?v=ontology  （新版 Palantir 风格预览）
```

### 合规版（验证用，不常起）

```bash
# 后端
cd /home/qq/YIMO/platform/backend
mvn package -DskipTests
java -jar target/twin-fusion-platform.jar \
  --spring.profiles.active=local \
  --twinfusion.data-dir=$HOME/YIMO/DATA \
  --twinfusion.outputs-dir=$HOME/YIMO/outputs

# 前端
cd /home/qq/YIMO/platform/frontend
npm install
npm run dev -- --host 0.0.0.0
# 浏览器: http://localhost:5173/    Vite 自动代理 /api → :8080
# 文档:   http://localhost:8080/doc.html  Knife4j Swagger
```

详见 [platform/README.md](platform/README.md) 完整指引（含 JDK17 离线安装、Maven 代理配置）。

## 共享资源（**两版本都读**）

| 目录 | 内容 | 谁在用 |
|------|------|------|
| [`DATA/`](DATA/) | 22 业务域 BA/DA/AA 三份 Excel | 演示版 + 合规版 |
| [`outputs/`](outputs/) | 抽取结果 JSON（22 域 + 跨域融合） | 演示版 + 合规版 |
| [`docs/`](docs/) | 甲方需求 + 演示材料 + 开发规范 zip | 双方 |
| [`mysql-local/`](mysql-local/) | MySQL 启动配置 + bootstrap.sql | 演示版主用，合规版本地冒烟兜底 |

## 顶层目录速览

```
YIMO/
├── README.md               项目总入口（功能介绍）
├── STRUCTURE.md            ← 本文档（双版本结构指南）
├── CLAUDE.md               AI 助手项目指南
│
├── webapp/                 ★ 演示版 (Flask, :5000)
│   ├── app.py              Flask 主入口
│   ├── olm_api.py          REST API 60+ 端点
│   ├── templates/          Jinja2 模板
│   │   ├── 10.0.html       v10.0 主仪表盘 (默认, 5050 行)
│   │   └── ontology.html   Palantir 风格预览版
│   └── .env                DeepSeek API Key (gitignored)
│
├── platform/               ★ 合规版 (南网部署目标)
│   ├── README.md           平台部署完整指引
│   ├── backend/            Spring Boot 3.2 + Maven (:8080)
│   ├── frontend/           Vue 3 + Vite (:5173)
│   ├── algo/               FastAPI 算法微服务 (:9000)
│   ├── dm-schema/          达梦 DM8 DDL (01-99 共 5 表 2 视图 + seed)
│   ├── deploy/             Dockerfile + docker-compose + 离线打包脚本
│   └── docs/               API 对齐表 / 算法接入设计
│
├── DATA/                   ☆ 共享: 22 业务域原始 Excel
├── outputs/                ☆ 共享: 抽取结果 JSON
├── scripts/                ☆ 共享: 22 个数据处理脚本
│   ├── object_extractor.py     SBERT + 聚类 + LLM 命名 (核心算法)
│   ├── eav_fast_import.py      30× 加速版 EAV 导入
│   ├── batch_extract_all.sh    批量抽取 22 域
│   ├── cross_domain_merge.py   跨域字面+语义对齐
│   ├── sample_join_extract.py  代表向量联合聚类
│   └── ...
│
├── docs/                   ☆ 共享: 文档
│   ├── 需求/               甲方原始需求 (xuqiu.md / xuqiu1.md + 截图)
│   ├── 演示材料/           本地演示 brief + 速查卡
│   ├── code/               南网开发规范 zip
│   ├── EAV-import-optimization.md  EAV 加速设计
│   └── product/            Palantir 调研 + 产品设计
│
├── mysql-local/            ☆ 演示版数据库
│   ├── bootstrap.sql       MySQL DDL (598 行, 演示版用)
│   └── my.cnf              MySQL 配置 (port 3307)
│
├── tests/                  演示版单元测试 (146 个 pytest)
├── start.sh                演示版一键启动脚本
└── venv/                   演示版 Python 虚拟环境 (gitignored)
```

## 双版本演进规则

1. **甲方功能反馈先落 webapp**（迭代快），稳定 1-2 周后同步到 platform
2. **南网规范变化先落 platform**（合规优先），不回灌 webapp
3. **DATA / outputs / docs 是单一真相源**，两版本都读，禁止各自 fork
4. **绝不在 webapp/ 里写 platform 类的合规改动**（如 Java 命名、达梦语法）
5. **绝不在 platform/ 里写 webapp 类的快迭代功能**（先定型再迁过来）

## 演示场景下的端口分工

| 场景 | 打开 | 数据来源 |
|------|------|---------|
| 甲方领导看演示 | :5000 (默认 v10.0) | webapp + MySQL |
| 给南网架构师看合规版 | :5173 (Vue 3) | platform/frontend → :8080 → JSON |
| API 文档展示 | :8080/doc.html | Knife4j Swagger |
| 数据库直查 | :3307 mysql | 23 个 data_domain 138 万 entities |

## 当前未实现（待甲方/南网确认）

详见 [docs/演示材料/本地演示brief.md](docs/演示材料/本地演示brief.md) 清单：

- HTAP 非结构化数据接入（视频/图像，需甲方提供数据源规格）
- 与企业数据中台对比（中台数据格式未定义）
- 南网数字平台前端组件库 SDK 替换 ElementPlus（葛总确认现场取）
- 达梦驱动 + 内部 LLM 网关（同上，现场取）

---

*最后更新: 2026-04-25 · platform 后端 + 前端实测跑通日*
