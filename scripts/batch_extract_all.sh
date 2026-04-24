#!/usr/bin/env bash
# 批量对 DATA/ 下全部域跑 object_extractor.
# 每域独立 python 子进程, 规则命名 (--no-llm), 纯 JSON 输出 (--no-db).
#
# 用法:
#   bash scripts/batch_extract_all.sh             # 跑全部 22 域
#   bash scripts/batch_extract_all.sh 产业金融     # 只跑一个域 (debug)

set -u
cd "$(dirname "$0")/.."

PY=venv/bin/python
EXTRACTOR=scripts/object_extractor.py
OUTDIR=outputs
LOGFILE=/tmp/yimo_batch_extract.log
SUMMARY=/tmp/yimo_batch_summary.txt

: > "$LOGFILE"
: > "$SUMMARY"
echo "batch extract started at $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOGFILE"

# 抽要跑的域列表
if [ $# -ge 1 ]; then
    domains=("$@")
else
    domains=()
    for d in DATA/*/; do
        name=$(basename "$d")
        [ "$name" = "_archive" ] && continue
        [[ "$name" =~ ^_ ]] && continue
        domains+=("$name")
    done
fi

total=${#domains[@]}
idx=0
ok=0
fail=0
t_start=$(date +%s)

for domain in "${domains[@]}"; do
    idx=$((idx+1))
    out="$OUTDIR/extraction_${domain}.json"
    ts=$(date '+%H:%M:%S')
    echo "[$ts $idx/$total] → $domain" | tee -a "$LOGFILE"

    t0=$(date +%s)
    if timeout 600 "$PY" "$EXTRACTOR" \
        --data-dir DATA --data-domain "$domain" \
        --no-llm --no-db \
        -o "$out" >> "$LOGFILE" 2>&1; then
        t_cost=$(( $(date +%s) - t0 ))
        # 解析对象数 / 关联数
        stat=$(python3 -c "
import json
try:
    d = json.load(open('$out'))
    objs = len(d.get('objects', []))
    rels = len(d.get('relations', []))
    print(f'{objs} 对象 / {rels} 关联')
except Exception as e:
    print(f'parse-err: {e}')
" 2>&1)
        printf "  ✓ [%d/%d] %s (%ds, %s)\n" "$idx" "$total" "$domain" "$t_cost" "$stat" | tee -a "$SUMMARY"
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
    echo "logs: $LOGFILE"
    echo "outputs: $(ls $OUTDIR/extraction_*.json 2>/dev/null | wc -l) 个 JSON"
} | tee -a "$SUMMARY"
echo "finished at $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOGFILE"
