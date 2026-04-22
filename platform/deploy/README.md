# 部署说明

## 目标环境（已确认）

甲方分配：**南网云 - 研发 - V 区** 虚拟机，规格：

| CPU | 内存 | 数据盘 | OS | IP | 使用期限 |
|-----|------|--------|----|----|----------|
| 32 核 | 64 GB | 500 GB | CentOS (Mini) | 1 个 | 12 个月 |

**注意**：CentOS Mini 是最小化安装，**默认无 JDK、无 Docker、无 Node**，部署时需一并带离线安装包 —— 清单见 [on-site-checklist.md](on-site-checklist.md)。

甲方（葛总）明确：**南网数字平台前端组件库 / 达梦驱动 / LLM 网关配置 等不外发，到现场取**。

## 南网正式环境

1. 将 platform/ 目录上传至堡垒机 / 运维机。
2. 配置达梦连接环境变量（需向运维申请）：
   ```bash
   export DM_HOST=10.x.x.x
   export DM_PORT=5236
   export DM_SCHEMA=TWIN_FUSION
   export DM_USER=twin_app
   export DM_PASSWORD=<secret>
   ```
3. 运维 DBA 执行 [../dm-schema/](../dm-schema/) 下所有 DDL（执行顺序 01→02→03→04→99）。
4. 将达梦官方 JDBC 驱动 `DmJdbcDriver18-*.jar` 放到 `deploy/lib/`（此目录不入 git）。
5. 启动：
   ```bash
   cd platform/deploy
   docker compose up -d --build
   ```
6. 健康检查：
   ```bash
   curl http://<服务器IP>:8080/api/v1/health
   curl http://<服务器IP>/
   ```

## 本地冒烟（WSL / Mac / 本地 Linux）

本地默认用 MySQL 兼容栈跑通链路（`PROFILE=local`），**不连达梦**：

```bash
# 确保 ../../mysql-local 下的 MySQL 已启动 (见 /home/qq/YIMO/start.sh)
cd platform/backend
mvn spring-boot:run

# 另起终端
cd platform/frontend
npm install
npm run dev
# 浏览器访问 http://localhost:5173/
```

## 离线安装包清单（后续交付需要补齐）

- Java 17 OpenJDK tar.gz（若目标机无互联网）
- 达梦 DM8 客户端 + JDBC Driver（由南网提供）
- Node.js 20 LTS + 离线 npm 缓存（`.npm` 目录打包）
- Docker / docker-compose 离线包（若目标机不允许 docker hub 拉取，需镜像同步到南网内网 Harbor）
- Nginx 静态资源压缩脚本
- 南网数字平台前端组件库 SDK（待索取）

## 限制与 TODO

- [ ] 对接南网统一认证（Oauth2 / CAS），替换当前无鉴权状态
- [ ] DeepSeek 内网替代方案（若外网不可达）
- [ ] SBERT 嵌入服务：两种方案
  1. 把 webapp 中的 Python 抽取算法打成独立容器，后端通过 HTTP 调
  2. 用 DJL + OnnxRuntime 在 JVM 内直接跑，转换模型为 ONNX
- [ ] 日志采集接入南网 ELK
- [ ] 监控指标接入南网监控
