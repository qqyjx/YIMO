#!/usr/bin/env bash
# 用 eav_fast_import.py 跑 DB 里还没入的大域.
# 办公/企业架构/党建/系统运行/数字化/安全监管/市场营销/人力资源/战略规划/计划财务/供应链/输配电

set -u
cd "$(dirname "$0")/.."

PY=venv/bin/python
SCRIPT=scripts/eav_fast_import.py
LOG=/tmp/yimo_eav_fast.log
SUMMARY=/tmp/yimo_eav_fast_summary.txt

: > "$LOG"
: > "$SUMMARY"
echo "EAV fast batch started at $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"

# DB 里已入 (非 legacy) 的域 - 跳过
existing=$(mysql -h 127.0.0.1 -P 3307 -ueav_user -peavpass123 -N -e \
    "SELECT DISTINCT data_domain FROM eav_db.eav_datasets WHERE data_domain NOT IN ('jicai','shupeidian','default')" \
    2>/dev/null | tr '\n' ' ')
echo "已入 EAV: $existing" | tee -a "$SUMMARY"

domains=()
for d in DATA/*/; do
    name=$(basename "$d")
    [[ "$name" =~ ^_ ]] && continue
    [ -f "$d/2.xlsx" ] || continue
    if [[ " $existing " == *" $name "* ]]; then continue; fi
    domains+=("$name")
done

total=${#domains[@]}
echo "待跑: $total 域 — ${domains[*]}" | tee -a "$SUMMARY"

idx=0; ok=0; fail=0
t_start=$(date +%s)

for domain in "${domains[@]}"; do
    idx=$((idx+1))
    xlsx="DATA/$domain/2.xlsx"
    ts=$(date '+%H:%M:%S')
    echo "[$ts $idx/$total] FAST ← $domain" | tee -a "$LOG"

    t0=$(date +%s)
    if timeout --kill-after=15 600 "$PY" "$SCRIPT" \
        --excel "$xlsx" \
        --data-domain "$domain" \
        --dataset-name "${domain}_DA" \
        >> "$LOG" 2>&1; then
        t_cost=$(( $(date +%s) - t0 ))
        # 从 log 最后 10 行抓 entities 数
        ent=$(tail -10 "$LOG" | grep -oP 'entities=\K[0-9,]+' | tail -1 || echo "?")
        printf "  ✓ [%d/%d] %s (%ds, %s ents)\n" "$idx" "$total" "$domain" "$t_cost" "$ent" | tee -a "$SUMMARY"
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
    echo "done: ok=$ok fail=$fail total=$total time=${t_total}s"
} | tee -a "$SUMMARY"
