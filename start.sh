#!/usr/bin/env bash
# ============================================================
# YIMO 一键启动脚本
# ============================================================
# 用法:
#   ./start.sh              # 启动 Web 服务
#   ./start.sh --stop       # 停止服务
#   ./start.sh --restart    # 重启服务
#   ./start.sh --status     # 查看服务状态
#   ./start.sh --port 8080  # 指定端口（默认 5000）
#   ./start.sh --extract    # 先运行对象抽取再启动
# ============================================================
set -euo pipefail

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
WEBAPP_DIR="$PROJECT_DIR/webapp"
PID_FILE="$WEBAPP_DIR/webapp.pid"
LOG_FILE="$WEBAPP_DIR/webapp.log"

# ===================== 参数解析 =====================
ACTION="start"
WEB_PORT=5000
DO_EXTRACT=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stop)      ACTION="stop";    shift ;;
        --restart)   ACTION="restart"; shift ;;
        --status)    ACTION="status";  shift ;;
        --extract)   DO_EXTRACT=true;  shift ;;
        --port)      shift; WEB_PORT="${1:-5000}"; shift ;;
        --port=*)    WEB_PORT="${1#*=}"; shift ;;
        -h|--help)
            echo "YIMO 启动脚本"
            echo ""
            echo "用法: ./start.sh [选项]"
            echo "  --stop        停止服务"
            echo "  --restart     重启服务"
            echo "  --status      查看服务状态"
            echo "  --port <N>    指定端口（默认 5000）"
            echo "  --extract     启动前运行对象抽取"
            echo "  -h, --help    帮助"
            exit 0
            ;;
        *) echo -e "${RED}未知参数: $1${NC}"; exit 1 ;;
    esac
done

# ===================== 辅助函数 =====================
get_pid() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null || true)
        if [[ -n "$pid" ]] && ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    return 1
}

detect_python() {
    if [[ -f "$PROJECT_DIR/venv/bin/python" ]]; then
        echo "$PROJECT_DIR/venv/bin/python"
    elif [[ -n "${CONDA_PREFIX:-}" ]] && command -v python &>/dev/null; then
        echo "python"
    elif command -v python3 &>/dev/null; then
        echo "python3"
    else
        echo ""
    fi
}

# ===================== stop =====================
do_stop() {
    local pid
    if pid=$(get_pid); then
        echo -e "${YELLOW}停止服务 (PID $pid)...${NC}"
        local pgid
        pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ') || pgid="$pid"
        kill -- -"$pgid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        for _ in {1..10}; do
            ps -p "$pid" > /dev/null 2>&1 || break
            sleep 0.5
        done
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        echo -e "${GREEN}✓ 服务已停止${NC}"
    else
        # 也清理可能残留的进程
        pkill -f "python.*app\.py" 2>/dev/null || true
        echo -e "${YELLOW}服务未在运行${NC}"
    fi
}

# ===================== status =====================
do_status() {
    local pid
    if pid=$(get_pid); then
        echo -e "${GREEN}✓ 服务运行中 (PID $pid, 端口 $WEB_PORT)${NC}"
        if curl --noproxy '*' -sS -m 3 "http://127.0.0.1:$WEB_PORT/health" 2>/dev/null | grep -q "ok"; then
            echo -e "${GREEN}✓ 健康检查通过${NC}"
        else
            echo -e "${YELLOW}! 健康检查失败${NC}"
        fi
    else
        echo -e "${YELLOW}服务未运行${NC}"
    fi
}

# ===================== start =====================
do_start() {
    # 检查是否已运行
    local pid
    if pid=$(get_pid); then
        echo -e "${GREEN}服务已在运行 (PID $pid)${NC}"
        echo -e "  访问: ${CYAN}http://localhost:$WEB_PORT${NC}"
        return 0
    fi

    echo -e "${BOLD}YIMO 对象抽取与三层架构关联系统${NC}"
    echo ""

    # 检测 Python
    local py
    py=$(detect_python)
    if [[ -z "$py" ]]; then
        echo -e "${RED}✗ 未找到 Python 环境${NC}"
        echo "  请先创建 venv: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Python: $py ($($py --version 2>&1))"

    # 检查 Flask
    if ! $py -c "import flask" 2>/dev/null; then
        echo -e "${RED}✗ Flask 未安装，请运行: $py -m pip install -r webapp/requirements.txt${NC}"
        exit 1
    fi

    # 可选：对象抽取
    if [[ "$DO_EXTRACT" == true ]]; then
        echo -e "${YELLOW}运行对象抽取...${NC}"
        mkdir -p outputs
        for domain_dir in DATA/*/; do
            local domain
            domain=$(basename "$domain_dir")
            echo -e "  抽取: $domain"
            if $py -c "import sentence_transformers" 2>/dev/null; then
                $py scripts/object_extractor.py \
                    --data-dir "DATA/$domain" \
                    --data-domain "$domain" \
                    --target-clusters 15 \
                    --no-db \
                    --output "outputs/extraction_${domain}.json" 2>&1 | tail -3
            else
                $py scripts/simple_extractor.py \
                    --data-dir "DATA/$domain" \
                    --data-domain "$domain" \
                    --output "outputs/extraction_${domain}.json" 2>&1 | tail -3
            fi
        done
        echo -e "${GREEN}✓ 抽取完成${NC}"
    fi

    # 检查 outputs
    local json_count
    json_count=$(find outputs -name "extraction_*.json" 2>/dev/null | wc -l)
    if [[ "$json_count" -eq 0 ]]; then
        echo -e "${YELLOW}! outputs/ 下无抽取数据，首次使用请加 --extract 参数${NC}"
    else
        echo -e "${GREEN}✓${NC} 已有 $json_count 个数据域抽取结果"
    fi

    # 启动 Flask
    echo -e "${YELLOW}启动 Web 服务 (端口 $WEB_PORT)...${NC}"
    export FLASK_PORT="$WEB_PORT"
    export NO_PROXY="127.0.0.1,localhost,::1"
    mkdir -p "$WEBAPP_DIR"
    : > "$LOG_FILE"

    (
        cd "$WEBAPP_DIR"
        nohup $py app.py >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
    )

    # 健康检查
    local new_pid
    new_pid=$(cat "$PID_FILE" 2>/dev/null || true)
    echo -e "  PID: $new_pid"

    local ok=false
    for i in {1..15}; do
        if curl --noproxy '*' -sS -m 3 "http://127.0.0.1:$WEB_PORT/health" 2>/dev/null | grep -q "ok"; then
            ok=true
            break
        fi
        sleep 1
        echo -ne "\r  等待启动... ${i}s"
    done
    echo ""

    if [[ "$ok" == true ]]; then
        echo ""
        echo -e "${GREEN}════════════════════════════════════════${NC}"
        echo -e "${GREEN}  ✓ YIMO 服务已就绪${NC}"
        echo -e "${GREEN}════════════════════════════════════════${NC}"
        echo ""
        echo -e "  主页:       ${CYAN}http://localhost:$WEB_PORT/${NC}"
        echo -e "  对象管理:   ${CYAN}http://localhost:$WEB_PORT/extraction${NC}"
        echo -e "  健康检查:   ${CYAN}http://localhost:$WEB_PORT/health${NC}"
        echo ""
        echo -e "  日志: tail -f $LOG_FILE"
        echo -e "  停止: ./start.sh --stop"
        echo ""
    else
        echo -e "${RED}✗ 启动超时，查看日志:${NC}"
        tail -20 "$LOG_FILE"
        exit 1
    fi
}

# ===================== 主逻辑 =====================
case "$ACTION" in
    start)   do_start   ;;
    stop)    do_stop    ;;
    restart) do_stop; sleep 1; do_start ;;
    status)  do_status  ;;
esac
