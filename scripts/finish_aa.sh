#!/usr/bin/env bash
# Finish the remaining AA (slot 3) files that were OOM-interrupted.
# Drives the loop from bash so the parent shell uses almost no RAM;
# each xlsx is processed in an isolated python subprocess.
set -u

ROOT=/home/qq/YIMO
ZIP="$ROOT/DATA/_archive/网公司应用架构-蓝图-导入日志20250520(1).zip"
WORKER="$ROOT/scripts/_ingest_one.py"
BACKUP="$ROOT/DATA/_archive/backup_$(date +%Y%m%d)"
SRC_STAGE=/tmp/yimo_aa_stage
mkdir -p "$BACKUP" "$SRC_STAGE"

# Fresh extract of the AA zip
rm -rf "$SRC_STAGE"/* 2>/dev/null
unzip -o -d "$SRC_STAGE" "$ZIP" > /dev/null 2>&1

# domain keywords in priority order (same as Python script)
declare -a KEYS=(
  "纪检监察:纪检监察" "国际业务:国际业务" "产业金融:产业金融" "供应链:供应链"
  "安全监管:安全监管" "审计:审计" "法规:法规" "党建:党建" "办公:办公"
  "巡视:巡视" "工会:工会" "系统运行:系统运行" "人力资源:人力资源"
  "计划与财务:计划财务" "计财:计划财务" "企业架构:企业架构" "科技创新:科技创新"
  "政策研究:政策研究" "输配电:输配电" "战略规划:战略规划" "新兴业务:新兴业务"
  "市场营销:市场营销" "数字化:数字化"
)

identify_domain() {
  local name="$1"
  for kv in "${KEYS[@]}"; do
    local kw="${kv%%:*}" dom="${kv##*:}"
    case "$name" in
      *"$kw"*) echo "$dom"; return 0 ;;
    esac
  done
  return 1
}

# Process only domains that are still stale (04-16 or older on 3.xlsx).
# These are the AA files not yet refreshed from the new zip.
STALE=("人力资源" "企业架构" "党建" "办公" "安全监管" "审计" "战略规划"
       "政策研究" "法规" "科技创新" "纪检监察" "计划财务")

is_stale() {
  local d="$1"
  for s in "${STALE[@]}"; do
    [ "$s" = "$d" ] && return 0
  done
  return 1
}

processed=0
skipped=0
for f in "$SRC_STAGE"/*.xlsx; do
  base=$(basename "$f")
  domain=$(identify_domain "$base") || { echo "  [SKIP unmatched] $base"; continue; }
  if ! is_stale "$domain"; then
    skipped=$((skipped+1))
    continue
  fi
  dest_dir="$ROOT/DATA/$domain"
  mkdir -p "$dest_dir" "$BACKUP/$domain"
  # back up old slot 3
  [ -f "$dest_dir/3.xlsx" ] && cp -p "$dest_dir/3.xlsx" "$BACKUP/$domain/3.xlsx"
  cp -p "$f" "$dest_dir/3.xlsx"
  # drop verification col in an isolated python process
  out=$(python3 "$WORKER" "$dest_dir/3.xlsx" 2>&1)
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "  [$domain] ERR rc=$rc $out"
  else
    removed=$(echo "$out" | sed -n 's/^removed=\(.*\)/\1/p')
    tag="no 校验 col"
    [ "$removed" != "0" ] && tag="dropped $removed"
    echo "  [$domain] slot 3: $tag"
  fi
  processed=$((processed+1))
done
echo
echo "finished: processed=$processed skipped_already_done=$skipped"
