# 支撑孪生体新范式多维数据融合分析框架原型系统 — 部署版

## 这是什么

**YIMO 仓库下有两份代码，职责分明：**

| 目录 | 用途 | 技术栈 | 目标环境 |
|------|------|--------|----------|
| [/webapp](../webapp/) | **本地演示版** — 过第三方测试、功能评审、甲方阶段性展示 | Python 3.10 + Flask + MySQL | WSL 本地 / 内部 Demo |
| [/platform](.) | **远程部署版** — 部署到南方电网服务器 | Java 17 + Spring Boot 3 + 达梦 DM8 + Vue 3 | 南网正式 / 测试环境 |

两份代码 **不共享运行态**，只共享 [DATA/](../DATA/)（22 业务域 BA/DA/AA Excel）与 [docs/requirement-1/](../docs/requirement-1/)（甲方需求）。前者演进快、优先验证算法与功能；后者严格对齐南网规范（[../docs/code/](../docs/code/)），准备合规落地。

---

## 规范对齐清单

本工程严格按以下规范编写（源自 [docs/code/开发规范.zip](../docs/code/开发规范.zip)）：

| 规范 | 摘要 | 本工程落地位置 |
|------|------|----------------|
| 南网数研院 JAVA 代码规范 | 类 UpperCamelCase、方法/变量 lowerCamelCase、常量全大写，Service 方法 `get/list/count/save/update/remove` 前缀，包名单数小写 | [backend/src/main/java/com/csg/twinfusion/](backend/src/main/java/com/csg/twinfusion/) |
| JAVA 安全编码规范 | 参数校验、SQL 注入防护、异常不泄露堆栈、日志脱敏 | `common/GlobalExceptionHandler`、`common/SqlInjectionInterceptor` |
| 达梦数据库设计开发规范 | 表名 `<业务简称>[_二级域]_<实体>` 大写下划线，必含 `CREATE_TIME`/`UPDATE_TIME`，每字段注释，无 `IS_` 前缀布尔 | [dm-schema/](dm-schema/) |
| 数字平台科技公司前端代码规范 | 组件化、TypeScript、命名与样式约束 | [frontend/](frontend/) |
| 网页端应用界面设计规范 | 五大价值观（安全/智能/连接/自然/轻量），一致性/对齐/反馈/易操作原则 | frontend UI 初版 Element Plus，**上线前替换为南网数字平台组件库** |

---

## 命名约定

- **业务域简称**：`TF`（TwinFusion — 孪生体融合框架）
- **二级域简称**：`EAV`（通用属性值）/ `OM`（对象管理 Object Management）/ `LC`（生命周期 LifeCycle）/ `TR`（溯源 Traceability）/ `MF`（机理函数 Mechanism Function）/ `AL`（预警 Alert）/ `GV`（治理 Governance）
- **表示例**：`TF_EAV_DATASET`、`TF_OM_EXTRACTED_OBJECT`、`TF_OM_ENTITY_RELATION`
- **Java 包**：`com.csg.twinfusion.{controller|service|mapper|entity|dto|config|common}`（csg = China Southern power Grid）

---

## 目录结构

```
platform/
├── backend/                    # Spring Boot 3 + MyBatis-Plus + DM8
│   ├── pom.xml
│   └── src/main/java/com/csg/twinfusion/
│       ├── TwinFusionApplication.java
│       ├── config/             # 数据源、跨域、拦截器、Swagger
│       ├── controller/         # REST 入口（对应 webapp/olm_api.py 的端点）
│       ├── service/            # 业务逻辑
│       ├── mapper/             # MyBatis mapper 接口
│       ├── entity/             # 数据库实体（与 DM 表 1:1）
│       ├── dto/                # 前后端交互 DTO
│       └── common/             # 异常、拦截器、工具、Result
├── dm-schema/                  # 达梦 DDL + 迁移脚本
│   ├── 01_ddl_tf_eav.sql       # EAV 核心 4 表
│   ├── 02_ddl_tf_om.sql        # 对象抽取 + 三层关联
│   ├── 03_ddl_tf_lc_tr_mf_al.sql  # 生命周期/溯源/机理函数/预警
│   ├── 04_ddl_tf_gv_views.sql  # 治理视图
│   └── 99_init_dict_data.sql   # 预置字典数据
├── frontend/                   # Vue 3 + Vite + TS
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/                # Axios 封装
│       ├── router/             # Vue Router
│       ├── layouts/            # 布局组件
│       ├── views/              # 页面（对齐 webapp/templates 功能）
│       └── components/         # 通用组件
├── deploy/                     # 部署脚本
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
└── docs/                       # 设计与部署文档
    ├── 部署说明.md
    ├── 数据字典.md
    └── API 设计.md
```

---

## 当前状态

- [x] 目录结构、POM、应用入口就绪（一次 mvn spring-boot:run 可启动 /health）
- [x] DM8 DDL 核心表（EAV + OM + 关联）
- [x] 前端 Vite + Vue 3 骨架 + /health 调用
- [ ] 接入 [webapp/scripts/object_extractor.py](../scripts/object_extractor.py) 抽取逻辑（建议做成 Python 旁挂微服务或用 DJL 重实现 SBERT 调用，**待与甲方确认南网内部是否部署 SBERT 模型**）
- [ ] 南网数字平台前端组件库（向甲方索要 NPM 地址/SDK）
- [ ] DeepSeek 内网可达性确认 → 若不可达需替换为南网内部 LLM 网关

---

## 本地跑起

```bash
# 后端
cd platform/backend
mvn spring-boot:run   # :8080
curl http://localhost:8080/api/v1/health

# 前端
cd platform/frontend
pnpm install
pnpm dev              # :5173

# 达梦本地（需预装 DM8；测试期可短暂用 MySQL 兼容模式）
cd platform/dm-schema
./init.sh             # 见脚本，或手动 disql 执行 01-99 ddl
```

---

## 与本地演示版（webapp/）的关系

- 两份代码独立演进，**互不调用**。
- 共享数据源：[DATA/](../DATA/) 22 业务域 Excel。
- 甲方功能评审以 webapp/ 为准（迭代快）；南网上线以 platform/ 为准（合规）。
- 功能对齐节奏：webapp/ 新功能稳定 2 周后才同步到 platform/。
