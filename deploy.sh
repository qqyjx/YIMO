#!/bin/bash
# YIMO 一键部署脚本
# 用法: ./deploy.sh [--with-demo-data] [--no-interact]
#
# 环境变量支持（用于无交互模式）:
#   MYSQL_ROOT_PASSWORD - MySQL root密码（留空则无密码）
#
# 示例:
#   ./deploy.sh                                    # 交互模式
#   ./deploy.sh --with-demo-data                   # 含样例数据
#   MYSQL_ROOT_PASSWORD=mypass ./deploy.sh --no-interact  # 全自动部署

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 解析参数
WITH_DEMO_DATA=false
NO_INTERACT=false
for arg in "$@"; do
  case $arg in
    --with-demo-data) WITH_DEMO_DATA=true ;;
    --no-interact) NO_INTERACT=true ;;
  esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  YIMO 一模到底 - 一键部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 检测操作系统
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux;;
    Darwin*)    PLATFORM=Mac;;
    CYGWIN*|MINGW*|MSYS*) PLATFORM=Windows;;
    *)          PLATFORM="Unknown"
esac
echo -e "${YELLOW}检测到操作系统: ${PLATFORM}${NC}"

# 检查 Python
echo -e "\n${YELLOW}[1/7] 检查 Python 环境...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo -e "${GREEN}✓ Python ${PYTHON_VERSION} 已安装${NC}"
else
    echo -e "${RED}✗ 未找到 Python3，请先安装 Python 3.10+${NC}"
    exit 1
fi

# 检查 MySQL
echo -e "\n${YELLOW}[2/7] 检查 MySQL 服务...${NC}"
if command -v mysql &> /dev/null; then
    if mysqladmin ping -h 127.0.0.1 --silent 2>/dev/null; then
        echo -e "${GREEN}✓ MySQL 服务运行中${NC}"
    else
        echo -e "${RED}✗ MySQL 服务未运行，请先启动 MySQL${NC}"
        echo -e "${YELLOW}  Ubuntu/Debian: sudo systemctl start mysql${NC}"
        echo -e "${YELLOW}  CentOS/RHEL: sudo systemctl start mysqld${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ 未找到 MySQL，请先安装 MySQL 8.0+${NC}"
    exit 1
fi

# 创建虚拟环境
echo -e "\n${YELLOW}[3/7] 创建 Python 虚拟环境...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
else
    echo -e "${GREEN}✓ 虚拟环境已存在${NC}"
fi

# 激活虚拟环境并安装依赖
echo -e "\n${YELLOW}[4/7] 安装 Python 依赖...${NC}"
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# 配置数据库
echo -e "\n${YELLOW}[5/7] 配置数据库...${NC}"

# 获取MySQL root密码
if [ "$NO_INTERACT" = true ]; then
    # 无交互模式：使用环境变量
    MYSQL_ROOT_PASS="${MYSQL_ROOT_PASSWORD:-}"
    echo -e "${YELLOW}无交互模式：使用环境变量 MYSQL_ROOT_PASSWORD${NC}"
else
    # 交互模式：提示输入
    read -sp "请输入 MySQL root 密码 (直接回车跳过如果无密码): " MYSQL_ROOT_PASS
    echo ""
fi

MYSQL_CMD="mysql -u root -h 127.0.0.1"
if [ -n "$MYSQL_ROOT_PASS" ]; then
    MYSQL_CMD="mysql -u root -p${MYSQL_ROOT_PASS} -h 127.0.0.1"
fi

# 创建数据库和用户
$MYSQL_CMD -e "
  CREATE DATABASE IF NOT EXISTS eav_db CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'eav_user'@'localhost' IDENTIFIED BY 'eavpass123';
  CREATE USER IF NOT EXISTS 'eav_user'@'127.0.0.1' IDENTIFIED BY 'eavpass123';
  GRANT ALL ON eav_db.* TO 'eav_user'@'localhost';
  GRANT ALL ON eav_db.* TO 'eav_user'@'127.0.0.1';
  FLUSH PRIVILEGES;
" 2>/dev/null && echo -e "${GREEN}✓ 数据库用户已配置${NC}" || {
    echo -e "${RED}✗ 数据库配置失败，请检查 MySQL root 密码${NC}"
    exit 1
}

# 初始化数据库表
$MYSQL_CMD eav_db < mysql-local/bootstrap.sql 2>/dev/null && echo -e "${GREEN}✓ 数据库表已初始化${NC}"

# 创建配置文件
echo -e "\n${YELLOW}[6/7] 创建配置文件...${NC}"
if [ ! -f "webapp/.env" ]; then
    cat > webapp/.env << 'EOF'
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DB=eav_db
MYSQL_USER=eav_user
MYSQL_PASSWORD=eavpass123
TABLE_PREFIX=eav
EMBED_MODEL=shibing624/text2vec-base-chinese
MODEL_CACHE=./models
DEEPSEEK_API_KEY=your_api_key_here
RAG_TOP_K=5
EOF
    echo -e "${GREEN}✓ 配置文件已创建${NC}"
else
    echo -e "${GREEN}✓ 配置文件已存在${NC}"
fi

# 导入样例数据（可选）
if [ "$WITH_DEMO_DATA" = true ]; then
    echo -e "\n${YELLOW}[6.5/7] 导入样例数据...${NC}"
    python scripts/import_all.py --stage Planning --dir DATA/lifecycle_demo/planning/ 2>/dev/null || true
    python scripts/import_all.py --stage Design --dir DATA/lifecycle_demo/design/ 2>/dev/null || true
    python scripts/import_all.py --stage Construction --dir DATA/lifecycle_demo/construction/ 2>/dev/null || true
    python scripts/import_all.py --stage Operation --dir DATA/lifecycle_demo/operation/ 2>/dev/null || true
    python scripts/import_all.py --stage Finance --dir DATA/lifecycle_demo/finance/ 2>/dev/null || true
    echo -e "${GREEN}✓ 样例数据已导入${NC}"
fi

# 启动服务
echo -e "\n${YELLOW}[7/7] 启动 Web 服务...${NC}"
cd webapp
nohup python app.py > /tmp/yimo_webapp.log 2>&1 &
sleep 3

if curl -s http://localhost:5000/health | grep -q "ok"; then
    echo -e "${GREEN}✓ Web 服务已启动${NC}"
else
    echo -e "${RED}✗ 服务启动失败，请检查日志: /tmp/yimo_webapp.log${NC}"
    exit 1
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e ""
echo -e "  访问地址: ${YELLOW}http://localhost:5000${NC}"
echo -e "  健康检查: ${YELLOW}http://localhost:5000/health${NC}"
echo -e "  统一本体: ${YELLOW}http://localhost:5000/lifecycle${NC}"
echo -e "  异常监控: ${YELLOW}http://localhost:5000/anomalies${NC}"
echo -e ""
echo -e "  停止服务: ${YELLOW}fuser -k 5000/tcp${NC}"
echo -e "  查看日志: ${YELLOW}tail -f /tmp/yimo_webapp.log${NC}"
echo -e ""
