#!/usr/bin/env bash
# 对 DATA/ 下所有中文域子目录批量执行对象抽取
# 使用 LLM 命名（需 DEEPSEEK_API_KEY 环境变量）
# 产物：outputs/extraction_<域>.json，以及数据库写入

set -e
cd "$(dirname "$0")/.."

if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "警告：未检测到 DEEPSEEK_API_KEY，将使用规则命名（质量可能下降）"
    LLM_FLAG="--no-llm"
else
    echo "检测到 DEEPSEEK_API_KEY，启用 LLM 精细命名"
    LLM_FLAG="--use-llm"
fi

source venv/bin/activate 2>/dev/null || true

TOTAL=$(ls DATA/ | grep -v _archive | grep -v '\.zip$' | wc -l)
I=0
FAILED=()

mkdir -p outputs/multi_domain_logs

for d in DATA/*/; do
    domain=$(basename "$d")
    [ "$domain" = "_archive" ] && continue
    [[ "$domain" == *.zip ]] && continue
    # 必须有 2.xlsx (数据架构)
    if [ ! -f "$d/2.xlsx" ]; then
        echo "  [跳过] $domain  （缺少数据架构 2.xlsx）"
        continue
    fi

    I=$((I+1))
    OUTPUT="outputs/extraction_${domain}.json"
    LOG="outputs/multi_domain_logs/${domain}.log"
    echo ""
    echo "=== [$I/$TOTAL] 抽取域: $domain ==="

    python scripts/object_extractor.py \
        --data-dir "$d" \
        --data-domain "$domain" \
        --target-clusters 15 \
        $LLM_FLAG \
        --no-db \
        --output "$OUTPUT" 2>&1 | tee "$LOG" | tail -5

    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        FAILED+=("$domain")
        echo "  ❌ $domain 抽取失败，详见 $LOG"
    else
        echo "  ✅ $domain 抽取完成 → $OUTPUT"
    fi
done

echo ""
echo "=============================================="
echo "批量抽取完成"
echo "  成功: $((I - ${#FAILED[@]})) / $I"
if [ ${#FAILED[@]} -gt 0 ]; then
    echo "  失败域: ${FAILED[*]}"
fi
echo ""
echo "下一步：导入 DB"
echo "  python scripts/import_json_to_db.py --outputs-dir outputs --reset"
