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
- [x] **API 对齐 Phase 1（7 端点）** — 见 [docs/api-alignment.md](docs/api-alignment.md)
  - `/api/v1/health` · `/api/v1/domains` · `/api/v1/objects` · `/api/v1/objects/{code}/relations` · `/api/v1/stats` · `/api/v1/stats/domains` · `/api/v1/summary`
  - 数据源: 复用 webapp 侧 `outputs/extraction_*.json`（迁库前的临时方案）
- [x] **算法接入设计** — 见 [docs/algorithm-integration.md](docs/algorithm-integration.md)
  - Phase 1 走 **方案 C**（复用 webapp 产物 JSON），Phase 2 切 **方案 A**（Python 微服务）
- [ ] Phase 2 API（CRUD / 合并 / 抽取触发）— 8 端点
- [ ] Phase 3 API（生命周期 / 溯源）— 8 端点
- [ ] Phase 4 API（机理函数 / 预警 / 治理）— 14 端点
- [ ] 算法微服务容器（algo:9000）— 包 object_extractor.py 成 FastAPI
- [ ] 南网数字平台前端组件库（向甲方索要 NPM 地址/SDK）
- [ ] DeepSeek 内网可达性确认 → 若不可达替换为南网内部 LLM 网关

---

## 本地跑起 (实测通过)

### 前置依赖

```bash
# 1) JDK 17 (用户态, 无需 sudo)
mkdir -p ~/.local && cd ~/.local
curl -L -o jdk17.tar.gz \
  "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.10%2B7/OpenJDK17U-jdk_x64_linux_hotspot_17.0.10_7.tar.gz"
mkdir -p jvm && tar -xzf jdk17.tar.gz -C jvm/ --strip-components=1

# 2) Maven 3.9
curl -L -o maven.tar.gz \
  "https://archive.apache.org/dist/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz"
mkdir -p maven && tar -xzf maven.tar.gz -C maven/ --strip-components=1

# 3) 加 PATH
cat >> ~/.bashrc <<'EOF'
export JAVA_HOME=$HOME/.local/jvm
export PATH=$JAVA_HOME/bin:$HOME/.local/maven/bin:$PATH
EOF
source ~/.bashrc

# 4) Maven 走代理 + 阿里源 (国内必配)
cat > ~/.m2/settings.xml <<'EOF'
<settings>
  <proxies>
    <proxy>
      <id>local-mihomo</id><active>true</active><protocol>https</protocol>
      <host>127.0.0.1</host><port>7890</port>
      <nonProxyHosts>localhost|127.0.0.1</nonProxyHosts>
    </proxy>
  </proxies>
  <mirrors>
    <mirror>
      <id>aliyun</id><mirrorOf>central</mirrorOf>
      <url>https://maven.aliyun.com/repository/public</url>
    </mirror>
  </mirrors>
</settings>
EOF
```

### 后端 Spring Boot

```bash
cd platform/backend
mvn package -DskipTests          # 第一次 ~3 分钟下依赖

# 启动 (用绝对路径指向 DATA/outputs, 避免相对路径解析错误)
java -jar target/twin-fusion-platform.jar \
  --spring.profiles.active=local \
  --algo.base-url=http://localhost:9000 \
  --twinfusion.data-dir=$HOME/YIMO/DATA \
  --twinfusion.outputs-dir=$HOME/YIMO/outputs

curl http://localhost:8080/api/v1/health    # → systemName + UP
curl http://localhost:8080/api/v1/summary   # → 22 域 / 135 对象 / 125094 关联
# Knife4j 文档: http://localhost:8080/doc.html
```

### 前端 Vue 3 + Vite

```bash
cd platform/frontend
npm config set registry https://registry.npmmirror.com
npm install                       # ~30 秒
npm run dev -- --host 0.0.0.0     # :5173

# 浏览器打开 http://localhost:5173/
# Vite 自动代理 /api/* → :8080 Spring Boot
```

### 达梦本地 (可选)

```bash
cd platform/dm-schema
# 需预装 DM8 客户端; 测试期 backend 已走 MySQL profile=local 兜底
disql USER/PWD@127.0.0.1:5236 < 01_ddl_tf_eav.sql
disql USER/PWD@127.0.0.1:5236 < 02_ddl_tf_om.sql
# ... 03/04/99 同上
```

---

## 与本地演示版（webapp/）的关系

- 两份代码独立演进，**互不调用**。
- 共享数据源：[DATA/](../DATA/) 22 业务域 Excel。
- 甲方功能评审以 webapp/ 为准（迭代快）；南网上线以 platform/ 为准（合规）。
- 功能对齐节奏：webapp/ 新功能稳定 2 周后才同步到 platform/。
