#!/usr/bin/env bash
# 离线部署包构建脚本.
# 把 backend/frontend/algo/mysql 4 个镜像 + 必要源码打成单 tar.gz, 现场 docker load 即可启动.
#
# 用法:
#   bash platform/deploy/build-offline-bundle.sh                # 构 + 导, 输出 dist/
#   BUNDLE_VERSION=0.1.0 bash platform/deploy/build-offline-bundle.sh

set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT=$(pwd)
BUNDLE_VERSION="${BUNDLE_VERSION:-0.1.0}"
BUILD_DATE=$(date +%Y%m%d-%H%M)
DIST="$ROOT/dist"
mkdir -p "$DIST"

BUNDLE_NAME="twin-fusion-bundle-${BUNDLE_VERSION}-${BUILD_DATE}"
WORK="$DIST/$BUNDLE_NAME"
mkdir -p "$WORK"

echo "==> 1. 拉/构镜像"
# 数据库 (达梦在南网现场用; 这里离线包带 MySQL 8 作为 profile=local 兜底)
docker pull mysql:8.0 || echo "  mysql:8.0 已存在"
# 后端
docker compose -f platform/deploy/docker-compose.yml build backend
# 前端
docker compose -f platform/deploy/docker-compose.yml build frontend
# 算法 (耗时最长, 镜像内置 SBERT 模型 ~400MB)
docker compose -f platform/deploy/docker-compose.yml build algo

echo "==> 2. 导出镜像 tar"
docker save \
    mysql:8.0 \
    eclipse-temurin:17-jre-jammy \
    nginx:1.27-alpine \
    twin-fusion-platform:latest \
    twin-fusion-frontend:latest \
    twin-fusion-algo:latest \
    -o "$WORK/images.tar"
echo "  images.tar size: $(du -sh $WORK/images.tar | cut -f1)"

echo "==> 3. 复制源码 / 配置 / 数据"
# 部署相关
cp -r platform/deploy "$WORK/deploy"
# DM schema 用于 DBA 现场建库
cp -r platform/dm-schema "$WORK/dm-schema"
# Java backend 源码 (现场可能要 mvn rebuild)
cp -r platform/backend "$WORK/backend"
cp -r platform/frontend "$WORK/frontend"
cp -r platform/algo "$WORK/algo"
# Python 算法源码 (algo container 通过 volume 挂载)
cp -r scripts "$WORK/scripts"
# 文档 + 现场清单
mkdir -p "$WORK/docs"
cp -r platform/docs "$WORK/docs/platform"
cp -r docs/演示材料 "$WORK/docs/演示材料" 2>/dev/null || true
# 数据 (DATA 比较大, 单独打可选包)
cp -r outputs "$WORK/outputs"

echo "==> 4. 写 README + 环境变量模板"
cat > "$WORK/README.md" <<EOF
# 支撑孪生体新范式多维数据融合分析框架原型系统 - 离线部署包

版本: $BUNDLE_VERSION  构建时间: $BUILD_DATE

## 目标环境
南网云研发 V 区, CentOS Mini 32C/64G/500G + Docker (需预装).

## 现场启动 (5 步)

\`\`\`bash
# 1. 解压
tar xzf $BUNDLE_NAME.tar.gz
cd $BUNDLE_NAME

# 2. 加载所有镜像
docker load -i images.tar

# 3. 配置环境变量 (达梦/LLM 网关地址)
cp deploy/.env.example deploy/.env
vim deploy/.env

# 4. (可选) DBA 执行达梦 DDL
disql SYSDBA/<密码>@<DM_HOST>:5236 <<SQL
CREATE SCHEMA TWIN_FUSION;
SET SCHEMA TWIN_FUSION;
START dm-schema/01_ddl_tf_eav.sql
START dm-schema/02_ddl_tf_om.sql
START dm-schema/03_ddl_tf_lc_tr_mf_al.sql
START dm-schema/04_ddl_tf_gv_views.sql
START dm-schema/99_init_dict_data.sql
SQL

# 5. 启动栈
cd deploy
docker compose up -d
docker compose ps      # 4 个容器全 healthy
curl http://localhost:8080/api/v1/health
\`\`\`

## 大小

- images.tar: 约 3-4 GB
- 整包: 约 5-6 GB (含 outputs JSON)
- DATA/ Excel 数据另发: 约 380 MB (本包**不含** DATA, 现场需另外 scp)

## 与 DATA 数据合并

\`\`\`bash
# 现场把 DATA/ 也 scp 过来
scp -r DATA/ user@server:/path/to/$BUNDLE_NAME/
\`\`\`

DATA 通过 volume 挂载到 algo 容器, 不重新打镜像.

## 回滚

\`\`\`bash
docker compose down
docker tag twin-fusion-platform:0.0.9 twin-fusion-platform:latest   # 标到旧版
docker compose up -d
\`\`\`

旧版本镜像建议保留 3 个版本.
EOF

cat > "$WORK/deploy/.env.example" <<EOF
# 达梦 (南网现场必填)
DM_HOST=10.x.x.x
DM_PORT=5236
DM_SCHEMA=TWIN_FUSION
DM_USER=twin_app
DM_PASSWORD=__请从运维取__

# LLM (南网内部网关, 不可达时算法服务降级关键词命名)
DEEPSEEK_API_BASE=https://内网网关/v1
DEEPSEEK_API_KEY=__请从运维取__
DEEPSEEK_MODEL=deepseek-v4-pro

# 算法服务 base URL (Java backend 用)
ALGO_BASE_URL=http://algo:9000

# Profile (生产强制 prod)
PROFILE=prod
TZ=Asia/Shanghai
EOF

echo "==> 5. 打包 tar.gz"
cd "$DIST"
tar czf "$BUNDLE_NAME.tar.gz" "$BUNDLE_NAME/"
SIZE=$(du -sh "$BUNDLE_NAME.tar.gz" | cut -f1)
echo
echo "✓ DONE: $DIST/$BUNDLE_NAME.tar.gz ($SIZE)"
echo
echo "现场只需:"
echo "  scp $DIST/$BUNDLE_NAME.tar.gz user@server:~/"
echo "  ssh user@server"
echo "  tar xzf $BUNDLE_NAME.tar.gz && cd $BUNDLE_NAME"
echo "  docker load -i images.tar"
echo "  cd deploy && docker compose up -d"
