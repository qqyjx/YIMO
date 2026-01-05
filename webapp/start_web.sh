#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$ROOT_DIR/app.py"
LOG_PATH="$ROOT_DIR/webapp.log"
PID_PATH="$ROOT_DIR/webapp.pid"
CONDA_BIN="/home/xdx/miniconda3/bin/conda"
ENV_PREFIX="/data1/xyf/smartgrid/grideav"
PY_CMD=("$CONDA_BIN" run -p "$ENV_PREFIX" python "$APP_PATH")

if [[ ! -x "$CONDA_BIN" ]]; then
  echo "[start_web] conda binary not found at $CONDA_BIN" >&2
  exit 1
fi

if [[ ! -f "$APP_PATH" ]]; then
  echo "[start_web] app.py not found at $APP_PATH" >&2
  exit 1
fi

echo "[start_web] Using env prefix: $ENV_PREFIX"

echo "[start_web] Checking faiss installation in env..."
if ! "$CONDA_BIN" run -p "$ENV_PREFIX" python -c "import faiss" >/dev/null 2>&1; then
  echo "[start_web] faiss not found, installing faiss-cpu via pip..."
  if ! "$CONDA_BIN" run -p "$ENV_PREFIX" python -m pip install -q faiss-cpu; then
    echo "[start_web] WARNING: failed to install faiss-cpu; RAG may be disabled." >&2
  else
    echo "[start_web] faiss-cpu installed successfully."
  fi
else
  echo "[start_web] faiss already available."
fi

if [[ -f "$PID_PATH" ]]; then
  old_pid=$(cat "$PID_PATH" || true)
  if [[ -n "$old_pid" ]] && ps -p "$old_pid" > /dev/null 2>&1; then
    echo "[start_web] Web app already running (PID $old_pid)."
    exit 0
  else
    echo "[start_web] Removing stale PID file."
    rm -f "$PID_PATH"
  fi
fi

mkdir -p "$ROOT_DIR"
: > "$LOG_PATH"

export NO_PROXY="127.0.0.1,localhost,::1"

(
  cd "$ROOT_DIR"
  echo "[start_web] Launching Flask app via $CONDA_BIN (env prefix: $ENV_PREFIX)" >> "$LOG_PATH"
  nohup "${PY_CMD[@]}" >> "$LOG_PATH" 2>&1 &
  echo $! > "$PID_PATH"
)

if [[ -s "$PID_PATH" ]]; then
  new_pid=$(cat "$PID_PATH")
  echo "[start_web] Started web app (PID $new_pid). Logs: $LOG_PATH"
  # simple health probe with retries
  echo "[start_web] Probing /health ..."
  for i in {1..10}; do
    sleep 2
    if curl --noproxy '*' -sS -m 5 http://127.0.0.1:5000/health >> "$LOG_PATH" 2>&1; then
      echo "[start_web] Health check OK" >> "$LOG_PATH"
      echo "[start_web] Service is ready!"
      exit 0
    fi
    echo "[start_web] Waiting for service to start... ($i/10)"
  done
  echo "[start_web] Health check FAILED after retries" >> "$LOG_PATH"
  echo "[start_web] WARNING: Service might be slow to start or failed. Check $LOG_PATH"
else
  echo "[start_web] Failed to capture PID." >&2
  exit 1
fi
