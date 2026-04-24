#!/usr/bin/env bash
# 只跑 2.xlsx <= 4MB 的小中域, 避免大域拖慢总体.
# 大域 (人力资源 8M / 市场营销 9M / 计划财务 10M / 战略规划 10M /
#       供应链 12M / 输配电 13M / 数字化 5.5M / 安全监管 7M) 跳过,
# 演示时走 JSON fallback, 不影响看数据.

set -u
cd "$(dirname "$0")/.."

PY=venv/bin/python
SCRIPT=scripts/eav_full.py
LOG=/tmp/yimo_eav_small_batch.log
SUMMARY=/tmp/yimo_eav_small_summary.txt
MAX_SIZE=$((2 * 1024 * 1024))     # 2 MB (3MB+ 的 eav_full.py 会挂)

DB_ARGS="--host 127.0.0.1 --port 3307 --user eav_user --password eavpass123 --db eav_db"

: > "$LOG"
: > "$SUMMARY"
echo "EAV small-domain batch started at $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"

# 查 DB 里已入 EAV 的域 (用于跳过已完成项, 避免重跑)
existing=$(mysql -h 127.0.0.1 -P 3307 -ueav_user -peavpass123 -N -e \
    "SELECT DISTINCT data_domain FROM eav_db.eav_datasets WHERE data_domain NOT IN ('jicai','shupeidian','default')" \
    2>/dev/null | tr '\n' ' ')
echo "已入 EAV 的域: $existing" | tee -a "$SUMMARY"

domains=()
skipped_big=()
skipped_done=()
for d in DATA/*/; do
    name=$(basename "$d")
    [ "$name" = "_archive" ] && continue
    [[ "$name" =~ ^_ ]] && continue
    xlsx="$d/2.xlsx"
    [ -f "$xlsx" ] || continue
    if [[ " $existing " == *" $name "* ]]; then
        skipped_done+=("$name")
        continue
    fi
    size=$(stat -c "%s" "$xlsx")
    if [ "$size" -gt "$MAX_SIZE" ]; then
        skipped_big+=("$name ($(printf "%.1f" $(echo "$size/1048576" | bc -l))M)")
    else
        domains+=("$name")
    fi
done

{
    echo "共发现 $((${#domains[@]} + ${#skipped_big[@]})) 域, 跑 ${#domains[@]} 个小中域"
    echo "跳过 ${#skipped_big[@]} 个大域: ${skipped_big[*]}"
} | tee -a "$SUMMARY"

total=${#domains[@]}
idx=0
ok=0
fail=0
t_start=$(date +%s)

for domain in "${domains[@]}"; do
    idx=$((idx+1))
    xlsx="DATA/$domain/2.xlsx"
    ts=$(date '+%H:%M:%S')
    echo "[$ts $idx/$total] EAV ← $domain" | tee -a "$LOG"

    t0=$(date +%s)
    if timeout --kill-after=15 180 "$PY" "$SCRIPT" \
        --excel "$xlsx" $DB_ARGS \
        --dataset-name "${domain}_DA" \
        --data-domain "$domain" \
        >> "$LOG" 2>&1; then
        t_cost=$(( $(date +%s) - t0 ))
        printf "  ✓ [%d/%d] %s (%ds)\n" "$idx" "$total" "$domain" "$t_cost" | tee -a "$SUMMARY"
        ok=$((ok+1))
    else
        rc=$?
        t_cost=$(( $(date +%s) - t0 ))
        printf "  ✗ [%d/%d] %s FAILED rc=%d after %ds\n" "$idx" "$total" "$domain" "$rc" "$t_cost" | tee -a "$SUMMARY"
        fail=$((fail+1))
    fi
done

t_total=$(( $(date +%s) - t_start ))
{
    echo "---"
    echo "done: ok=$ok fail=$fail total=$total skipped_big=${#skipped_big[@]} time=${t_total}s"
} | tee -a "$SUMMARY"
echo "finished at $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
