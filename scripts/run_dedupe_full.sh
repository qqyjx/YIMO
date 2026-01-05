#!/usr/bin/env bash
set -euo pipefail

# Robust launcher: kills stale conda-run wrappers, uses absolute Python interp,
# ensures logs are written, and (optionally) cleans outputs before run.

PY="/home/xdx/miniconda3/envs/grideav/bin/python"
ROOT="/data1/xyf/smartgrid/outputs/semantic_dedupe_gpu_full"
MODEL="/data1/xyf/models/shibing624--text2vec-base-chinese"
MCACHE="/data1/xyf/models"

SLOG="$ROOT/single/run_single_latest.log"; SPID="$ROOT/single/run_single_latest.pid"
GLOG="$ROOT/global/run_global_latest.log"; GPID="$ROOT/global/run_global_latest.pid"

mkdir -p "$ROOT/single" "$ROOT/global" "$ROOT/single/summary" "$ROOT/global/summary"

kill_if_wrapper() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid; pid=$(cat "$pid_file" || true)
    if [[ -n "${pid}" ]] && ps -p "$pid" -o cmd= 1>/dev/null 2>&1; then
      local cmd; cmd=$(ps -p "$pid" -o cmd=)
      # If it's a conda wrapper or not our script, kill it to avoid log swallowing
      if echo "$cmd" | grep -q 'conda run'; then
        kill "$pid" 2>/dev/null || true
      fi
    fi
  fi
}

echo "[STEP] Stop stale wrappers (if any)"
kill_if_wrapper "$SPID"
kill_if_wrapper "$GPID"

if [[ "${CLEAN_OUTPUTS:-0}" == "1" ]]; then
  echo "[STEP] Clean previous outputs under $ROOT (CLEAN_OUTPUTS=1)"
  rm -rf "$ROOT/single" "$ROOT/global"
  mkdir -p "$ROOT/single" "$ROOT/global" "$ROOT/single/summary" "$ROOT/global/summary"
fi

echo "[STEP] Launch SINGLE mode (dataset-ids=1,2,3) with multi-GPU"
: > "$SLOG"
nohup "$PY" /data1/xyf/smartgrid/scripts/eav_semantic_dedupe.py \
  --dataset-ids 1,2,3 \
  --model "$MODEL" \
  --model-cache "$MCACHE" \
  --device cuda \
  --multi-gpu -1 \
  --batch-size 512 \
  --threshold 0.86 \
  --max-values 200000 \
  --offline \
  --out-dir "$ROOT/single" \
  > "$SLOG" 2>&1 & echo $! > "$SPID"

sleep 1
echo "[INFO] SINGLE started. PID=$(cat "$SPID" 2>/dev/null || echo NA). Log=$SLOG"

echo "[STEP] Launch GLOBAL mode (dataset-ids=1,2,3) with multi-GPU"
: > "$GLOG"
nohup "$PY" /data1/xyf/smartgrid/scripts/eav_semantic_dedupe.py \
  --dataset-ids 1,2,3 --global-dedupe \
  --model "$MODEL" \
  --model-cache "$MCACHE" \
  --device cuda \
  --multi-gpu -1 \
  --batch-size 512 \
  --threshold 0.86 \
  --max-values 200000 \
  --offline \
  --out-dir "$ROOT/global" \
  > "$GLOG" 2>&1 & echo $! > "$GPID"

sleep 1
echo "[INFO] GLOBAL started. PID=$(cat "$GPID" 2>/dev/null || echo NA). Log=$GLOG"

# Optional: start auto finalizers
if [[ "${AUTO_FINALIZE:-1}" == "1" ]]; then
  echo "[STEP] Start auto finalizers"
  nohup "$PY" /data1/xyf/smartgrid/scripts/auto_finalize_global.py \
    --out-dir "$ROOT/global" --dataset-ids 1,2,3 --interval 120 \
    > "$ROOT/global/summary/auto_finalize.log" 2>&1 & echo $! > "$ROOT/global/summary/auto_finalize.pid"

  nohup bash -lc 'PID=$(cat '"$SPID"' 2>/dev/null || echo); \
    if [ -n "$PID" ]; then while kill -0 $PID 2>/dev/null; do sleep 120; done; fi; \
    '"$PY"' /data1/xyf/smartgrid/scripts/summarize_dedupe_outputs.py --root '"$ROOT"'/single --out '"$ROOT"'/single/summary; \
    '"$PY"' /data1/xyf/smartgrid/scripts/generate_tech_report.py --root '"$ROOT"'/single --title "EAV 语义去重运行报告（单集）" --notes "自动收尾"; \
    date +"[FINALIZED_SINGLE] %F %T" > '"$ROOT"'/single/summary/FINALIZED_OK' \
    > "$ROOT/single/summary/auto_finalize_single.log" 2>&1 & echo $! > "$ROOT/single/summary/auto_finalize_single.pid"
fi

echo "[NEXT] Tail logs (optional):"
echo "  tail -f $SLOG"
echo "  tail -f $GLOG"
