#!/usr/bin/env bash
# YIMO Web服务启动脚本
# 支持多种Python环境：venv, conda, 系统Python
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$ROOT_DIR")"
APP_PATH="$ROOT_DIR/app.py"
LOG_PATH="$ROOT_DIR/webapp.log"
PID_PATH="$ROOT_DIR/webapp.pid"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  YIMO Web 服务启动脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查app.py是否存在
if [[ ! -f "$APP_PATH" ]]; then
  echo -e "${RED}[start_web] app.py not found at $APP_PATH${NC}" >&2
  exit 1
fi

# 自动检测Python环境
detect_python() {
  # 1. 优先使用项目根目录的venv
  if [[ -f "$PROJECT_ROOT/venv/bin/python" ]]; then
    echo "$PROJECT_ROOT/venv/bin/python"
    return 0
  fi

  # 2. 检查当前目录的venv
  if [[ -f "$ROOT_DIR/venv/bin/python" ]]; then
    echo "$ROOT_DIR/venv/bin/python"
    return 0
  fi

  # 3. 检查是否在conda环境中
  if [[ -n "${CONDA_PREFIX:-}" ]] && command -v python &> /dev/null; then
    echo "python"
    return 0
  fi

  # 4. 使用系统python3
  if command -v python3 &> /dev/null; then
    echo "python3"
    return 0
  fi

  echo ""
  return 1
}

PYTHON_CMD=$(detect_python)
if [[ -z "$PYTHON_CMD" ]]; then
  echo -e "${RED}[start_web] 未找到Python环境，请先运行 deploy.sh 或激活conda环境${NC}" >&2
  exit 1
fi

echo -e "${YELLOW}[start_web] 使用Python: $PYTHON_CMD${NC}"

# 检查关键依赖
echo -e "${YELLOW}[start_web] 检查依赖...${NC}"
if ! $PYTHON_CMD -c "import flask" 2>/dev/null; then
  echo -e "${RED}[start_web] Flask未安装，请运行: pip install -r requirements.txt${NC}" >&2
  exit 1
fi

# 检查faiss（非必须，但RAG功能需要）
if ! $PYTHON_CMD -c "import faiss" 2>/dev/null; then
  echo -e "${YELLOW}[start_web] faiss未安装，尝试安装faiss-cpu...${NC}"
  if $PYTHON_CMD -m pip install -q faiss-cpu 2>/dev/null; then
    echo -e "${GREEN}[start_web] faiss-cpu安装成功${NC}"
  else
    echo -e "${YELLOW}[start_web] 警告: faiss安装失败，RAG功能将不可用${NC}"
  fi
fi

# 检查是否已有服务运行
if [[ -f "$PID_PATH" ]]; then
  old_pid=$(cat "$PID_PATH" 2>/dev/null || true)
  if [[ -n "$old_pid" ]] && ps -p "$old_pid" > /dev/null 2>&1; then
    echo -e "${GREEN}[start_web] 服务已在运行中 (PID $old_pid)${NC}"
    exit 0
  else
    echo -e "${YELLOW}[start_web] 清理过期PID文件${NC}"
    rm -f "$PID_PATH"
  fi
fi

# 准备日志文件
mkdir -p "$ROOT_DIR"
: > "$LOG_PATH"

# 设置环境变量
export NO_PROXY="127.0.0.1,localhost,::1"

# 启动服务
echo -e "${YELLOW}[start_web] 启动Flask应用...${NC}"
(
  cd "$ROOT_DIR"
  nohup $PYTHON_CMD "$APP_PATH" >> "$LOG_PATH" 2>&1 &
  echo $! > "$PID_PATH"
)

# 健康检查
if [[ -s "$PID_PATH" ]]; then
  new_pid=$(cat "$PID_PATH")
  echo -e "${GREEN}[start_web] 服务已启动 (PID $new_pid)${NC}"
  echo -e "${YELLOW}[start_web] 正在进行健康检查...${NC}"

  for i in {1..10}; do
    sleep 2
    if curl --noproxy '*' -sS -m 5 http://127.0.0.1:5000/health 2>/dev/null | grep -q "ok"; then
      echo -e "${GREEN}[start_web] ✓ 服务已就绪!${NC}"
      echo -e ""
      echo -e "  访问地址: ${YELLOW}http://localhost:5000${NC}"
      echo -e "  统一本体: ${YELLOW}http://localhost:5000/lifecycle${NC}"
      echo -e "  异常监控: ${YELLOW}http://localhost:5000/anomalies${NC}"
      echo -e "  查看日志: ${YELLOW}tail -f $LOG_PATH${NC}"
      exit 0
    fi
    echo -e "${YELLOW}[start_web] 等待服务启动... ($i/10)${NC}"
  done

  echo -e "${RED}[start_web] 健康检查超时，请查看日志: $LOG_PATH${NC}" >&2
  exit 1
else
  echo -e "${RED}[start_web] 启动失败${NC}" >&2
  exit 1
fi
