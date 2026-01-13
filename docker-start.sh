#!/bin/bash
# YIMO Docker 一键启动脚本
# 无需预装 MySQL，只需要 Docker

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  YIMO 一模到底 - Docker 一键启动${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查 Docker
echo -e "\n${YELLOW}[1/4] 检查 Docker 环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}未找到 Docker，请先安装 Docker${NC}"
    echo -e "${YELLOW}安装指南: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}Docker 服务未运行，请启动 Docker${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker 已就绪${NC}"

# 检查 Docker Compose
echo -e "\n${YELLOW}[2/4] 检查 Docker Compose...${NC}"
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo -e "${RED}未找到 Docker Compose${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose 已就绪${NC}"

# 可选：设置 Deepseek API Key
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo -e "\n${YELLOW}[提示] 未设置 DEEPSEEK_API_KEY 环境变量${NC}"
    echo -e "${YELLOW}       RAG/LLM 功能将不可用，其他功能正常${NC}"
    echo -e "${YELLOW}       设置方法: export DEEPSEEK_API_KEY=your_key${NC}"
fi

# 启动服务
echo -e "\n${YELLOW}[3/4] 启动 Docker 容器...${NC}"
$COMPOSE_CMD up -d --build

# 等待服务就绪
echo -e "\n${YELLOW}[4/4] 等待服务启动...${NC}"
echo -e "${YELLOW}      首次启动需下载模型，可能需要几分钟...${NC}"

for i in {1..30}; do
    if curl -s http://localhost:5000/health 2>/dev/null | grep -q "ok"; then
        echo -e "\n${GREEN}========================================${NC}"
        echo -e "${GREEN}  启动成功！${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo -e ""
        echo -e "  主页:       ${YELLOW}http://localhost:5000${NC}"
        echo -e "  统一本体:   ${YELLOW}http://localhost:5000/lifecycle${NC}"
        echo -e "  异常监控:   ${YELLOW}http://localhost:5000/anomalies${NC}"
        echo -e "  健康检查:   ${YELLOW}http://localhost:5000/health${NC}"
        echo -e ""
        echo -e "  查看日志:   ${YELLOW}docker compose logs -f${NC}"
        echo -e "  停止服务:   ${YELLOW}docker compose down${NC}"
        echo -e "  清理数据:   ${YELLOW}docker compose down -v${NC}"
        echo -e ""
        exit 0
    fi
    echo -e "${YELLOW}  等待中... ($i/30)${NC}"
    sleep 5
done

echo -e "${RED}服务启动超时，请检查日志:${NC}"
echo -e "${YELLOW}docker compose logs${NC}"
exit 1
