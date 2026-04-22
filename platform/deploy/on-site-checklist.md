# 现场部署清单（研发环境 V 区）

> 甲方（葛总）答复：SDK/组件库/达梦驱动等不对外发放，到现场部署时下载。本清单记录现场要做的所有动作，避免一次走不完两次跑。

## 服务器规格（已确认）

| 项 | 值 |
|----|----|
| 环境 | 南网云 - 研发 - V 区 |
| 资源类型 | 虚拟机 |
| 应用系统 | 软件工厂基座 |
| 主机名 | 软件工厂服务器 |
| 体系架构 | X86 |
| 操作系统 | **CentOS (Mini)** — 最小化安装，很多依赖要自装 |
| CPU | 32 核 |
| 内存 | 64 GB |
| 数据盘 | 500 GB |
| IP | 1 个（单机单节点，不做高可用） |
| 使用期限 | 12 个月 |

资源冗余充足：22 域 Excel ~250MB、SBERT 模型 ~400MB、JDK/JRE ~200MB、达梦 ~2GB、Docker 镜像合计 ~3GB，500GB 足够。32C/64G 下同机可跑达梦 + 后端 + 前端 + 算法微服务四容器。

## 现场取（甲方环境才有的）

| # | 名称 | 来源 | 放置位置 | 作用 |
|---|------|------|----------|------|
| 1 | 达梦 DM8 JDBC 驱动 `DmJdbcDriver18-*.jar` | 南网运维 DBA | `platform/deploy/lib/` | Spring Boot 连达梦 |
| 2 | 达梦 DM8 客户端工具（disql / dmfldr） | 南网运维 DBA | 服务器本地 | 执行 `dm-schema/*.sql` |
| 3 | 南网数字平台前端组件库 SDK (NPM tarball 或私有仓地址) | 甲方/葛总 | `platform/frontend/src-sdk/` | 替换 ElementPlus |
| 4 | 南网统一认证 SDK（如 CAS/OAuth2 接入包） | 南网安全组 | `platform/backend/lib/` | 接入 SSO（如需） |
| 5 | 南网内部 LLM 网关地址 + 鉴权 Token | 甲方/葛总 | 环境变量 `LLM_BASE_URL`/`LLM_API_KEY` | 替换 DeepSeek 外网调用 |
| 6 | 南网内网 Maven 私服地址 | 南网运维 | `~/.m2/settings.xml` | 构建依赖下载 |
| 7 | 南网内网 npm 私服地址 | 南网运维 | `.npmrc` 的 registry | 前端依赖下载 |
| 8 | 南网内网 Docker Harbor 地址（如有） | 南网运维 | `/etc/docker/daemon.json` insecure-registries | 镜像拉取 |

## 现场带（提前准备好）

| # | 名称 | 备注 |
|---|------|------|
| 1 | 完整 platform/ 源码 | `git clone` 或打 tar 带上；DATA/ 22 域 Excel 也一起带 |
| 2 | `outputs/extraction_*.json` 抽取结果 | 本地跑好的备份，作为冷启动数据（方案 C） |
| 3 | OpenJDK 17 离线 tar.gz | CentOS Mini 默认无 JDK |
| 4 | Docker 24 / docker-compose v2 离线 rpm | CentOS Mini 无 Docker |
| 5 | Node.js 20 LTS 离线 tar.xz | 前端构建 |
| 6 | 本地已构建的 `twin-fusion-platform.jar` + `dist/` 前端产物 | 万一现场网络拉依赖失败可直接用成品 |
| 7 | SBERT 模型 `text2vec-base-chinese` 离线权重 | ~400MB，huggingface 下载并打包，算法服务用 |
| 8 | DeepSeek 离线调用方案 **或** 确认走南网内部 LLM 网关 | 若无网关则先禁用 LLM 命名，走 simple_extractor 关键字回退 |

## 现场 8 小时时间窗排序

按先后执行，每步设置时间上限，超时则降级（不要死磕）：

```
[30min] 0. 基线
   - 拿服务器 ssh 登录、确认 sudo / 非 root / 端口策略（80/8080/5236/9000）
   - ping 南网内部服务 (maven/npm/harbor/LLM 网关)

[60min] 1. 基础环境
   - 装 JDK 17：解压 tar.gz → /opt/jdk-17 + profile 加 JAVA_HOME
   - 装 Docker + docker-compose：yum install -y docker 或上传 rpm
   - 装 Node.js 20：仅在需要现场构建前端时

[45min] 2. 达梦数据库
   - DBA 协助建 schema TWIN_FUSION
   - 执行 dm-schema/01_ddl_tf_eav.sql + 02_ddl_tf_om.sql
   - 建应用账号 twin_app，授予 TWIN_FUSION schema 全部权限

[45min] 3. 后端构建部署
   - platform/deploy/lib/ 放 DmJdbcDriver18
   - mvn -DskipTests package
   - docker compose -f deploy/docker-compose.yml up -d backend
   - curl http://localhost:8080/api/v1/health → {"systemName":"..."} 通

[60min] 4. 前端构建部署
   - 若拿到南网组件库：pnpm i @南网/ui-sdk + 改 main.ts 替换 ElementPlus
     若没拿到：保留 ElementPlus 跑通再说
   - vite build
   - docker compose up -d frontend
   - 浏览器打开 :80 看首页健康卡

[60min] 5. 数据冷启动（方案 C）
   - scp outputs/extraction_*.json 到服务器
   - 配 backend 的 twinfusion.outputs-dir 指过去
   - 刷 /api/v1/stats/domains 看数据出来

[60min] 6. LLM 接入（可选）
   - 若拿到南网 LLM 网关：改 DEEPSEEK_API_BASE 指过去
   - 跑一次 object_extractor.py 试算一个域
   - 否则跳过，算法服务以后再补

[90min] 7. 联调 + 验收
   - 前端首页 → 业务域 → 点一个域 → 看对象列表 → 看三层关联
   - 演示 Palantir 风格图谱渲染
   - 请葛总现场确认功能对齐任务书
```

## 降级预案

| 现场情况 | 降级做法 |
|----------|----------|
| 达梦建库受阻 | 后端切 `profile=local`，临时用 MySQL 替代（需现场装 MySQL） |
| 内网 Maven 不通 | 把本地 `~/.m2/repository/` 打包带来，`mvn -o -DskipTests package` 离线构建 |
| 南网组件库未拿到 | 前端用 ElementPlus 先上，演示后再替换 |
| LLM 网关未开 | 算法只跑 SBERT 聚类 + `simple_extractor.py` 关键字命名，不调 LLM |
| 500GB 不够 | docker system prune，或离线构建完就删中间镜像 |

## 回去要补的文档

- [ ] 网关/私服实际地址（写入 [deploy/README.md](README.md) 的"南网内网环境"章节）
- [ ] 达梦实际版本（8.1 vs 8.4）及关键字冲突列表（影响 dm-schema/*.sql）
- [ ] 南网组件库命名规范 & demo 示例（改 [../frontend/src/](../frontend/src/) 以对齐）
- [ ] LLM 网关的 request/response 格式（是否 OpenAI 兼容）
