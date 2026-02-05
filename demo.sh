#!/bin/bash
# ============================================================
# YIMO 对象抽取与三层架构关联 - 一键演示脚本
# ============================================================
# 功能：
#   1. 检查并安装 Python 依赖
#   2. 从 DATA/ 目录抽取所有数据域的对象
#   3. 启动 Web 服务
#   4. 打印访问地址
#
# 使用方法：
#   chmod +x demo.sh && ./demo.sh
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}"
echo "============================================================"
echo "  YIMO 对象抽取与三层架构关联系统 - 演示"
echo "============================================================"
echo -e "${NC}"

# ============================================================
# 1. 检查 Python 依赖
# ============================================================
echo -e "${YELLOW}[1/4] 检查 Python 依赖...${NC}"

check_package() {
    python3 -c "import $1" 2>/dev/null && return 0 || return 1
}

MISSING_PACKAGES=""

for pkg in pandas flask sklearn numpy openpyxl tqdm; do
    if ! check_package "$pkg"; then
        MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
    fi
done

if [ -n "$MISSING_PACKAGES" ]; then
    echo -e "${YELLOW}  安装缺失的包:$MISSING_PACKAGES${NC}"
    pip install $MISSING_PACKAGES -q
fi

# 检查 sentence-transformers（可选，用于语义聚类）
if check_package "sentence_transformers"; then
    echo -e "${GREEN}  ✓ 完整模式：SBERT 可用，使用语义聚类${NC}"
    USE_SBERT=true
else
    echo -e "${YELLOW}  △ 简化模式：SBERT 不可用，使用关键词规则${NC}"
    USE_SBERT=false
fi

echo ""

# ============================================================
# 2. 对象抽取
# ============================================================
echo -e "${YELLOW}[2/4] 执行对象抽取...${NC}"

mkdir -p outputs

# 获取所有数据域
DOMAINS=$(ls -d DATA/*/ 2>/dev/null | xargs -n1 basename || echo "")

if [ -z "$DOMAINS" ]; then
    echo -e "${RED}  错误：DATA/ 目录下没有数据域文件夹${NC}"
    exit 1
fi

for domain in $DOMAINS; do
    echo -e "${BLUE}  → 抽取数据域: $domain${NC}"

    if [ "$USE_SBERT" = true ]; then
        # 使用完整的语义聚类
        python3 scripts/object_extractor.py \
            --data-dir "DATA/$domain" \
            --data-domain "$domain" \
            --target-clusters 15 \
            --no-db \
            --output "outputs/extraction_${domain}.json" \
            2>&1 | grep -E "^\[INFO\]|核心对象|关联关系" || true
    else
        # 使用简化版关键词规则
        python3 scripts/simple_extractor.py \
            --data-dir "DATA/$domain" \
            --data-domain "$domain" \
            --output "outputs/extraction_${domain}.json" \
            2>&1 | grep -E "^\[INFO\]|对象数|关联" || true
    fi

    echo ""
done

echo -e "${GREEN}  ✓ 对象抽取完成${NC}"
echo ""

# ============================================================
# 3. 停止已有服务
# ============================================================
echo -e "${YELLOW}[3/4] 准备启动 Web 服务...${NC}"

# 停止已有的 Flask 进程
pkill -f "python3.*app.py" 2>/dev/null || true
sleep 1

# ============================================================
# 4. 启动 Web 服务
# ============================================================
echo -e "${YELLOW}[4/4] 启动 Web 服务...${NC}"

cd webapp
nohup python3 app.py > /tmp/yimo_webapp.log 2>&1 &
WEB_PID=$!

# 等待服务启动
sleep 3

# 检查服务是否启动成功
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Web 服务启动成功 (PID: $WEB_PID)${NC}"
else
    echo -e "${RED}  × Web 服务启动失败，查看日志: /tmp/yimo_webapp.log${NC}"
    exit 1
fi

cd "$PROJECT_DIR"

# ============================================================
# 打印结果
# ============================================================
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  演示环境已就绪！${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "  ${BLUE}访问地址：${NC}"
echo -e "    主页:         http://localhost:5000/"
echo -e "    对象管理:     ${GREEN}http://localhost:5000/extraction${NC}"
echo ""
echo -e "  ${BLUE}已抽取的数据域：${NC}"
for domain in $DOMAINS; do
    obj_count=$(python3 -c "import json; d=json.load(open('outputs/extraction_${domain}.json')); print(len(d.get('objects',[])))" 2>/dev/null || echo "?")
    rel_count=$(python3 -c "import json; d=json.load(open('outputs/extraction_${domain}.json')); print(len(d.get('relations',[])))" 2>/dev/null || echo "?")
    echo -e "    - $domain: ${obj_count} 个对象, ${rel_count} 条关联"
done
echo ""
echo -e "  ${BLUE}使用说明：${NC}"
echo -e "    1. 打开浏览器访问 ${GREEN}http://localhost:5000/extraction${NC}"
echo -e "    2. 点击任意对象卡片，查看其关联的三层实体"
echo -e "    3. 使用顶部下拉框切换数据域"
echo ""
echo -e "  ${BLUE}停止服务：${NC}"
echo -e "    pkill -f 'python3.*app.py'"
echo ""
echo -e "${GREEN}============================================================${NC}"
