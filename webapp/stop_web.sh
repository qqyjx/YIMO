#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_PATH="$ROOT_DIR/webapp.pid"

if [[ ! -f "$PID_PATH" ]]; then
  echo "[stop_web] PID file not found ($PID_PATH). Is the app running?"
  exit 0
fi

pid=$(cat "$PID_PATH" || true)
if [[ -z "$pid" ]]; then
  echo "[stop_web] PID file empty; removing."
  rm -f "$PID_PATH"
  exit 0
fi

if ! ps -p "$pid" > /dev/null 2>&1; then
  echo "[stop_web] Process $pid not running; removing stale PID file."
  rm -f "$PID_PATH"
  exit 0
fi

pgid=$(ps -o pgid= -p "$pid" | tr -d ' ')
if [[ -z "$pgid" ]]; then
  echo "[stop_web] Unable to determine process group for PID $pid; using direct kill." >&2
  pgid="$pid"
fi

echo "[stop_web] Sending SIGTERM to process group $pgid"
kill -- -"$pgid" 2>/dev/null || true

for _ in {1..20}; do
  if ps -p "$pid" > /dev/null 2>&1; then
    sleep 0.5
  else
    break
  fi
done

if ps -p "$pid" > /dev/null 2>&1; then
  echo "[stop_web] Process still running; sending SIGKILL to group $pgid."
  kill -9 -"$pgid" 2>/dev/null || true
fi

rm -f "$PID_PATH"
echo "[stop_web] Web app stopped."
