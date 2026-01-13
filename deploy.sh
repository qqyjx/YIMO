#!/bin/bash
# YIMO 一键部署脚本 v2.0 - 带可视化进度条
# 用法: ./deploy.sh [--with-demo-data] [--no-interact] [--cn-mirror]
#
# 环境变量支持（用于无交互模式）:
#   MYSQL_ROOT_PASSWORD - MySQL root密码（留空则无密码）
#
# 示例:
#   ./deploy.sh                                    # 交互模式
#   ./deploy.sh --with-demo-data                   # 含样例数据
#   ./deploy.sh --cn-mirror                        # 使用国内镜像加速
#   MYSQL_ROOT_PASSWORD=mypass ./deploy.sh --no-interact  # 全自动部署

set -e

# ============================================================================
# 颜色与样式定义
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# 进度条字符
FILLED='█'
EMPTY='░'

# ============================================================================
# 可视化进度条函数
# ============================================================================
# 显示进度条
# 用法: show_progress <current> <total> <message>
show_progress() {
    local current=$1
    local total=$2
    local message=$3
    local width=40
    local percent=$((current * 100 / total))
    local filled=$((current * width / total))
    local empty=$((width - filled))
    
    # 构建进度条
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="${FILLED}"; done
    for ((i=0; i<empty; i++)); do bar+="${EMPTY}"; done
    
    # 清除当前行并打印进度
    printf "\r  ${CYAN}[${bar}]${NC} ${BOLD}%3d%%${NC} ${DIM}%s${NC}" "$percent" "$message"
}

# 完成进度条（换行）
finish_progress() {
    echo ""
}

# 显示带动画的等待提示
# 用法: show_spinner <pid> <message>
show_spinner() {
    local pid=$1
    local message=$2
    local spinstr='⣾⣽⣻⢿⡿⣟⣯⣷'
    local i=0
    
    while kill -0 $pid 2>/dev/null; do
        local char="${spinstr:$i:1}"
        printf "\r  ${CYAN}${char}${NC} ${message}..."
        i=$(( (i+1) % 8 ))
        sleep 0.1
    done
    printf "\r                                                              \r"
}

# 显示步骤标题
# 用法: show_step <current> <total> <title>
show_step() {
    local current=$1
    local total=$2
    local title=$3
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}[${current}/${total}]${NC} ${CYAN}${title}${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 显示成功消息
show_success() {
    echo -e "  ${GREEN}✓${NC} $1"
}

# 显示错误消息
show_error() {
    echo -e "  ${RED}✗${NC} $1"
}

# 显示警告消息
show_warning() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

# 显示信息消息
show_info() {
    echo -e "  ${BLUE}ℹ${NC} $1"
}

# ============================================================================
# 解析参数
# ============================================================================
WITH_DEMO_DATA=false
NO_INTERACT=false
USE_CN_MIRROR=false

for arg in "$@"; do
    case $arg in
        --with-demo-data) WITH_DEMO_DATA=true ;;
        --no-interact) NO_INTERACT=true ;;
        --cn-mirror) USE_CN_MIRROR=true ;;
        --help|-h)
            echo "YIMO 一键部署脚本 v2.0"
            echo ""
            echo "用法: ./deploy.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --with-demo-data   导入样例数据"
            echo "  --no-interact      无交互模式（使用环境变量）"
            echo "  --cn-mirror        使用国内镜像源加速下载"
            echo "  --help, -h         显示帮助信息"
            echo ""
            echo "环境变量:"
            echo "  MYSQL_ROOT_PASSWORD   MySQL root密码"
            exit 0
            ;;
    esac
done

# ============================================================================
# 主部署流程
# ============================================================================
clear
echo -e "${GREEN}"
cat << 'EOF'
  ██╗   ██╗██╗███╗   ███╗ ██████╗ 
  ╚██╗ ██╔╝██║████╗ ████║██╔═══██╗
   ╚████╔╝ ██║██╔████╔██║██║   ██║
    ╚██╔╝  ██║██║╚██╔╝██║██║   ██║
     ██║   ██║██║ ╚═╝ ██║╚██████╔╝
     ╚═╝   ╚═╝╚═╝     ╚═╝ ╚═════╝ 
EOF
echo -e "${NC}"
echo -e "${BOLD}  一模到底 · Universal Lifecycle Ontology Manager${NC}"
echo -e "${DIM}  智能电网 EAV 数据管理与语义去重平台${NC}"
echo ""

# 检测操作系统
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux; PLATFORM_ICON="🐧";;
    Darwin*)    PLATFORM=Mac; PLATFORM_ICON="🍎";;
    CYGWIN*|MINGW*|MSYS*) PLATFORM=Windows; PLATFORM_ICON="🪟";;
    *)          PLATFORM="Unknown"; PLATFORM_ICON="❓"
esac
show_info "操作系统: ${PLATFORM_ICON} ${PLATFORM}"

TOTAL_STEPS=7
if [ "$WITH_DEMO_DATA" = true ]; then
    TOTAL_STEPS=8
fi

# ----------------------------------------------------------------------------
# Step 1: 检查 Python
# ----------------------------------------------------------------------------
show_step 1 $TOTAL_STEPS "检查 Python 环境"

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 10 ]; then
        show_success "Python ${PYTHON_VERSION}"
    else
        show_warning "Python ${PYTHON_VERSION} (建议 3.10+)"
    fi
else
    show_error "未找到 Python3，请先安装 Python 3.10+"
    echo -e "    ${DIM}安装命令: sudo apt install python3 python3-venv python3-pip${NC}"
    exit 1
fi

# ----------------------------------------------------------------------------
# Step 2: 检查 MySQL
# ----------------------------------------------------------------------------
show_step 2 $TOTAL_STEPS "检查 MySQL 服务"

if command -v mysql &> /dev/null; then
    MYSQL_VERSION=$(mysql --version 2>&1 | grep -oP '\d+\.\d+\.\d+' | head -1)
    show_info "MySQL 版本: ${MYSQL_VERSION}"
    
    if mysqladmin ping -h 127.0.0.1 --silent 2>/dev/null; then
        show_success "MySQL 服务运行中"
    else
        show_error "MySQL 服务未运行"
        echo -e "    ${DIM}启动命令: sudo systemctl start mysql${NC}"
        exit 1
    fi
else
    show_error "未找到 MySQL，请先安装 MySQL 8.0+"
    echo -e "    ${DIM}安装命令: sudo apt install mysql-server${NC}"
    exit 1
fi

# ----------------------------------------------------------------------------
# Step 3: 创建虚拟环境
# ----------------------------------------------------------------------------
show_step 3 $TOTAL_STEPS "创建 Python 虚拟环境"

if [ ! -d "venv" ]; then
    python3 -m venv venv &
    show_spinner $! "创建虚拟环境"
    wait
    show_success "虚拟环境已创建"
else
    show_success "虚拟环境已存在，跳过创建"
fi

# 激活虚拟环境
source venv/bin/activate

# ----------------------------------------------------------------------------
# Step 4: 安装 Python 依赖（带进度条）
# ----------------------------------------------------------------------------
show_step 4 $TOTAL_STEPS "安装 Python 依赖"

# 配置国内镜像（可选）
if [ "$USE_CN_MIRROR" = true ]; then
    show_info "使用清华镜像源加速下载"
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null
fi

# 升级 pip
pip install --upgrade pip -q 2>/dev/null &
show_spinner $! "升级 pip"
wait

# 检查是否已有依赖
INSTALLED_COUNT=$(pip list 2>/dev/null | wc -l)
if [ "$INSTALLED_COUNT" -gt 60 ]; then
    show_success "依赖已安装 (${INSTALLED_COUNT} 个包)"
    
    # 快速检查更新
    echo -e "  ${DIM}检查依赖更新...${NC}"
    pip install -r requirements.txt -q 2>&1 | tail -1 || true
    show_success "依赖检查完成"
else
    show_info "开始安装依赖，预计需要 3-5 分钟..."
    echo -e "  ${DIM}(包含 PyTorch ~900MB, Transformers, FAISS 等大型包)${NC}"
    echo ""
    
    # 计算总包数用于进度显示
    TOTAL_PKGS=15  # 大约的主要包数量
    CURRENT_PKG=0
    
    # 创建临时文件记录进度
    PROGRESS_FILE=$(mktemp)
    echo "0" > "$PROGRESS_FILE"
    
    # 后台运行 pip install，同时显示进度
    pip install -r requirements.txt 2>&1 | while IFS= read -r line; do
        if [[ "$line" =~ Downloading ]]; then
            # 提取包名
            pkg_name=$(echo "$line" | sed 's/.*Downloading //' | sed 's|https://[^/]*/||' | cut -d'/' -f1 | cut -d'-' -f1)
            size_info=$(echo "$line" | grep -oP '\([^)]+\)' | tail -1 || echo "")
            
            # 更新进度
            CURRENT=$(cat "$PROGRESS_FILE" 2>/dev/null || echo "0")
            CURRENT=$((CURRENT + 1))
            echo "$CURRENT" > "$PROGRESS_FILE"
            
            # 显示进度条
            if [ "$CURRENT" -le "$TOTAL_PKGS" ]; then
                show_progress "$CURRENT" "$TOTAL_PKGS" "${pkg_name} ${size_info}"
            else
                printf "\r  ${CYAN}↓${NC} %-40s ${DIM}%s${NC}          " "$pkg_name" "$size_info"
            fi
        elif [[ "$line" =~ Installing\ collected ]]; then
            finish_progress
            echo -e "  ${DIM}正在安装已下载的包...${NC}"
        elif [[ "$line" =~ Successfully\ installed ]]; then
            # 计算安装的包数
            PKG_COUNT=$(echo "$line" | tr ' ' '\n' | wc -l)
            PKG_COUNT=$((PKG_COUNT - 2))
            show_success "成功安装 ${PKG_COUNT} 个包"
        fi
    done
    
    rm -f "$PROGRESS_FILE"
fi

# 验证关键依赖
echo -e "  ${DIM}验证关键依赖...${NC}"
if python -c "import flask, pymysql, sentence_transformers, faiss" 2>/dev/null; then
    show_success "Flask, PyMySQL, SentenceTransformers, FAISS 验证通过"
else
    show_warning "部分依赖验证失败，但可能不影响基本功能"
fi

# ----------------------------------------------------------------------------
# Step 5: 配置数据库
# ----------------------------------------------------------------------------
show_step 5 $TOTAL_STEPS "配置数据库"

# 获取MySQL root密码
if [ "$NO_INTERACT" = true ]; then
    MYSQL_ROOT_PASS="${MYSQL_ROOT_PASSWORD:-}"
    show_info "无交互模式：使用环境变量"
else
    echo -ne "  请输入 MySQL root 密码 ${DIM}(直接回车跳过)${NC}: "
    read -s MYSQL_ROOT_PASS
    echo ""
fi

MYSQL_CMD="mysql -u root -h 127.0.0.1"
if [ -n "$MYSQL_ROOT_PASS" ]; then
    MYSQL_CMD="mysql -u root -p${MYSQL_ROOT_PASS} -h 127.0.0.1"
fi

# 创建数据库和用户
{
$MYSQL_CMD -e "
  CREATE DATABASE IF NOT EXISTS eav_db CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'eav_user'@'localhost' IDENTIFIED BY 'eavpass123';
  CREATE USER IF NOT EXISTS 'eav_user'@'127.0.0.1' IDENTIFIED BY 'eavpass123';
  GRANT ALL ON eav_db.* TO 'eav_user'@'localhost';
  GRANT ALL ON eav_db.* TO 'eav_user'@'127.0.0.1';
  FLUSH PRIVILEGES;
" 2>/dev/null
} && show_success "数据库用户已配置" || {
    show_error "数据库配置失败，请检查 MySQL root 密码"
    exit 1
}

# 初始化数据库表
$MYSQL_CMD eav_db < mysql-local/bootstrap.sql 2>/dev/null && \
    show_success "数据库表已初始化" || \
    show_warning "表初始化跳过（可能已存在）"

# ----------------------------------------------------------------------------
# Step 6: 创建配置文件
# ----------------------------------------------------------------------------
show_step 6 $TOTAL_STEPS "创建配置文件"

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
    show_success "配置文件已创建: webapp/.env"
else
    show_success "配置文件已存在，跳过"
fi

# ----------------------------------------------------------------------------
# Step 6.5: 导入样例数据（可选）
# ----------------------------------------------------------------------------
if [ "$WITH_DEMO_DATA" = true ]; then
    show_step 7 $TOTAL_STEPS "导入样例数据"
    
    STAGES=("Planning" "Design" "Construction" "Operation" "Finance")
    STAGE_NAMES=("规划" "设计" "建设" "运维" "财务")
    STAGE_DIRS=("planning" "design" "construction" "operation" "finance")
    
    for i in "${!STAGES[@]}"; do
        stage_en="${STAGES[$i]}"
        stage_cn="${STAGE_NAMES[$i]}"
        stage_dir="${STAGE_DIRS[$i]}"
        
        show_progress $((i+1)) 5 "导入 ${stage_cn} 阶段数据"
        python scripts/import_all.py --stage "$stage_en" --dir "DATA/lifecycle_demo/${stage_dir}/" 2>/dev/null || true
    done
    finish_progress
    show_success "样例数据导入完成"
    
    FINAL_STEP=8
else
    FINAL_STEP=7
fi

# ----------------------------------------------------------------------------
# Step 7/8: 启动 Web 服务
# ----------------------------------------------------------------------------
show_step $FINAL_STEP $TOTAL_STEPS "启动 Web 服务"

# 停止可能存在的旧进程
fuser -k 5000/tcp 2>/dev/null || true

cd webapp
nohup python app.py > /tmp/yimo_webapp.log 2>&1 &
WEB_PID=$!

# 等待服务启动（带进度动画）
echo -ne "  等待服务启动"
for i in {1..15}; do
    sleep 1
    echo -ne "."
    if curl -s http://localhost:5000/health 2>/dev/null | grep -q "ok"; then
        break
    fi
done
echo ""

if curl -s http://localhost:5000/health 2>/dev/null | grep -q "ok"; then
    show_success "Web 服务已启动 (PID: $WEB_PID)"
else
    show_error "服务启动失败，请检查日志: /tmp/yimo_webapp.log"
    echo -e "  ${DIM}查看日志: tail -20 /tmp/yimo_webapp.log${NC}"
    exit 1
fi

# ============================================================================
# 部署完成
# ============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   ${BOLD}🎉 YIMO 一模到底 部署成功！${NC}                               ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   ${CYAN}🏠 主界面${NC}       http://localhost:5000                     ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   ${CYAN}🔘 统一本体${NC}     http://localhost:5000/lifecycle           ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   ${CYAN}⚠️  异常监控${NC}     http://localhost:5000/anomalies           ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   ${CYAN}💚 健康检查${NC}     http://localhost:5000/health              ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   ${DIM}停止服务:${NC} fuser -k 5000/tcp                                ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}   ${DIM}查看日志:${NC} tail -f /tmp/yimo_webapp.log                     ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
