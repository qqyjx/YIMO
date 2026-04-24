#!/usr/bin/env bash
# 批量把 DATA/<22 中文域>/2.xlsx (数据架构 DA 表) 导入 EAV 库.
#
# 为什么只跑 2.xlsx: DA 表含三层实体清单 (DA-01/02/03), 是对象抽取的原始输入,
# 也是 EAV 展示的核心 payload. 业务架构 (1.xlsx) 和应用架构 (3.xlsx) 可后续补.
#
# 单域独立子进程, 串行跑; 预计 15-30 分钟完成 22 域.

set -u
cd "$(dirname "$0")/.."

PY=venv/bin/python
SCRIPT=scripts/eav_full.py
LOG=/tmp/yimo_eav_batch.log
SUMMARY=/tmp/yimo_eav_summary.txt

DB_ARGS="--host 127.0.0.1 --port 3307 --user eav_user --password eavpass123 --db eav_db"

: > "$LOG"
: > "$SUMMARY"
echo "EAV batch import started at $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"

domains=()
for d in DATA/*/; do
    name=$(basename "$d")
    [ "$name" = "_archive" ] && continue
    [[ "$name" =~ ^_ ]] && continue
    domains+=("$name")
done

total=${#domains[@]}
idx=0
ok=0
fail=0
t_start=$(date +%s)

for domain in "${domains[@]}"; do
    idx=$((idx+1))
    xlsx="DATA/$domain/2.xlsx"
    if [ ! -f "$xlsx" ]; then
        echo "  [SKIP] $domain: 2.xlsx 不存在" | tee -a "$SUMMARY"
        continue
    fi
    ts=$(date '+%H:%M:%S')
    echo "[$ts $idx/$total] EAV ← $domain (2.xlsx)" | tee -a "$LOG"

    t0=$(date +%s)
    if timeout 900 "$PY" "$SCRIPT" \
        --excel "$xlsx" $DB_ARGS \
        --dataset-name "${domain}_DA" \
        --data-domain "$domain" \
        >> "$LOG" 2>&1; then
        t_cost=$(( $(date +%s) - t0 ))
        printf "  ✓ [%d/%d] %s (%ds)\n" "$idx" "$total" "$domain" "$t_cost" | tee -a "$SUMMARY"
        ok=$((ok+1))
    else
        rc=$?
        printf "  ✗ [%d/%d] %s FAILED rc=%d\n" "$idx" "$total" "$domain" "$rc" | tee -a "$SUMMARY"
        fail=$((fail+1))
    fi
done

t_total=$(( $(date +%s) - t_start ))
{
    echo "---"
    echo "done: ok=$ok fail=$fail total=$total time=${t_total}s"
    echo "logs: $LOG"
} | tee -a "$SUMMARY"
echo "finished at $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
