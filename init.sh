#!/usr/bin/env bash
# init.sh — YIMO 代码项目环境初始化
# 每次 agent session 开始时运行，只读不写
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "=== Code Project Init: $(basename "$PROJECT_DIR") ==="
echo "Timestamp: $(date -Iseconds)"
echo ""

# --- 1. 运行时检查 ---
echo "[1/6] Checking runtime environment..."
TOOLS_OK=true
for tool in python3 pip3; do
    if command -v "$tool" &>/dev/null; then
        echo "  ✓ $tool: $(command -v "$tool") ($(python3 --version 2>&1))"
    else
        echo "  ✗ $tool: NOT FOUND"
        TOOLS_OK=false
    fi
done
# MySQL 检查
if command -v mysql &>/dev/null; then
    echo "  ✓ mysql: $(command -v mysql)"
else
    echo "  ⚠ mysql: NOT FOUND (MySQL client not installed)"
fi
echo ""

# --- 2. 项目结构 ---
echo "[2/6] Checking project structure..."
REQUIRED=("CLAUDE.md" "requirements.txt")
OPTIONAL=("task.json" "claude-progress.txt")

for f in "${REQUIRED[@]}"; do
    if [ -f "$f" ]; then
        echo "  ✓ $f"
    else
        echo "  ✗ $f MISSING (required)"
    fi
done
for f in "${OPTIONAL[@]}"; do
    if [ -f "$f" ]; then
        echo "  ✓ $f"
    else
        echo "  - $f (not yet created)"
    fi
done

# 核心目录
for d in scripts webapp mysql-local DATA; do
    if [ -d "$d" ]; then
        FILE_COUNT=$(find "$d" -type f 2>/dev/null | wc -l)
        echo "  ✓ $d/ ($FILE_COUNT files)"
    else
        echo "  - $d/ not found"
    fi
done
echo ""

# --- 3. 健康检查 ---
echo "[3/6] Health check..."
# Python 语法检查
PY_FILES=$(find scripts/ webapp/ -name "*.py" 2>/dev/null | wc -l)
echo "  Python files: $PY_FILES"
SYNTAX_ERRORS=0
while IFS= read -r f; do
    if ! python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
        echo "  ✗ Syntax error: $f"
        SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
    fi
done < <(find scripts/ webapp/ -name "*.py" 2>/dev/null)
if [ "$SYNTAX_ERRORS" -eq 0 ]; then
    echo "  ✓ No Python syntax errors"
fi

# MySQL 连通性（如果可用）
if command -v mysql &>/dev/null; then
    if mysql -u root -P 3307 -e "SELECT 1" &>/dev/null 2>&1; then
        echo "  ✓ MySQL connection OK (port 3307)"
    else
        echo "  ⚠ MySQL not accessible on port 3307"
    fi
fi
echo ""

# --- 4. Git 状态 ---
echo "[4/6] Git status..."
if git rev-parse --git-dir &>/dev/null 2>&1; then
    BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
    DIRTY=$(git status --porcelain 2>/dev/null | wc -l)
    LAST_COMMIT=$(git log -1 --oneline 2>/dev/null || echo "no commits")
    echo "  Branch: $BRANCH"
    echo "  Uncommitted changes: $DIRTY files"
    echo "  Last commit: $LAST_COMMIT"
else
    echo "  Not a git repository"
fi
echo ""

# --- 5. TODO 扫描 ---
echo "[5/6] Scanning for TODOs..."
TODO_COUNT=$(grep -rc "TODO\|FIXME\|HACK\|XXX" scripts/ webapp/ --include="*.py" 2>/dev/null | awk -F: '{sum += $2} END {print sum+0}')
echo "  TODOs/FIXMEs: $TODO_COUNT"
if [ "$TODO_COUNT" -gt 0 ]; then
    grep -rn "TODO\|FIXME\|HACK\|XXX" scripts/ webapp/ --include="*.py" 2>/dev/null | head -10
fi
echo ""

# --- 6. 数据状态 ---
echo "[6/6] Data status..."
if [ -d DATA ]; then
    DATA_FILES=$(find DATA/ -type f 2>/dev/null | wc -l)
    echo "  DATA/ files: $DATA_FILES"
    for f in DATA/1.xlsx DATA/2.xlsx DATA/3.xlsx; do
        if [ -f "$f" ]; then
            echo "  ✓ $f"
        else
            echo "  - $f not found"
        fi
    done
fi
echo ""

# --- 汇总 ---
echo "=== Init Complete ==="
echo "Ready for agent session. (YIMO - Object Extraction System)"
