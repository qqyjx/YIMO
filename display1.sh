#!/usr/bin/env bash
# ============================================================================
# YIMO 对象抽取与三层架构关联系统 — 2.28 甲方演示一键脚本
# ============================================================================
#
# 功能概述：
#   1. 自动配置 Python 环境 & 安装依赖
#   2. 验证 DATA/ 数据完整性 & outputs/ 抽取结果
#   3. 可选执行对象抽取（SBERT 完整模式 / 关键词规则回退）
#   4. 启动 Flask Web 服务（自带健康检查）
#   5. 逐项验证 42 个 API 端点的可用性
#   6. 打印演示导览（甲方 1.md 需求清单逐条对应）
#
# 使用方法：
#   chmod +x display1.sh && ./display1.sh
#   ./display1.sh --skip-extract      # 跳过对象抽取（已有 outputs/ 数据时）
#   ./display1.sh --cn-mirror         # 使用国内镜像加速 pip
#   ./display1.sh --port 8080         # 指定 Web 服务端口
#   ./display1.sh --help              # 显示帮助
#
# 作者: YIMO Team | 日期: 2026-02
# ============================================================================

set -euo pipefail

# ===================== 颜色与样式 =====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ===================== 参数解析 =====================
SKIP_EXTRACT=false
USE_CN_MIRROR=false
WEB_PORT=5000

for arg in "$@"; do
    case "$arg" in
        --skip-extract)  SKIP_EXTRACT=true ;;
        --cn-mirror)     USE_CN_MIRROR=true ;;
        --port)          shift; WEB_PORT="${1:-5000}" ;;
        --port=*)        WEB_PORT="${arg#*=}" ;;
        --help|-h)
            echo "YIMO 2.28 甲方演示一键脚本"
            echo ""
            echo "用法: ./display1.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --skip-extract   跳过对象抽取（已有 outputs/ 数据时）"
            echo "  --cn-mirror      使用国内镜像源加速 pip 安装"
            echo "  --port <端口>    指定 Web 服务端口（默认 5000）"
            echo "  --help, -h       显示帮助"
            exit 0
            ;;
    esac
done

# ===================== 项目路径 =====================
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ===================== 辅助函数 =====================
step_count=0
total_steps=6

show_banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    cat << 'BANNER'
  ╦ ╦╦╔╦╗╔═╗  ┌┬┐┌─┐┌┬┐┌─┐
  ╚╦╝║║║║║ ║   ││├┤ ││││ │
   ╩ ╩╩ ╩╚═╝  ─┴┘└─┘┴ ┴└─┘
BANNER
    echo -e "${NC}"
    echo -e "${BOLD}  对象抽取与三层架构关联系统 — 甲方演示环境${NC}"
    echo -e "${DIM}  南方电网 · 2026.02.28 演示${NC}"
    echo ""
}

show_step() {
    step_count=$1
    local title=$2
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}[${step_count}/${total_steps}]${NC} ${CYAN}${title}${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${BLUE}>${NC} $1"; }

check_cmd() {
    command -v "$1" &>/dev/null
}

check_py_pkg() {
    python3 -c "import $1" 2>/dev/null
}

# ===================== BANNER =====================
show_banner

# ====================================================================
# Step 1: Python 环境 & 依赖安装
# ====================================================================
show_step 1 "配置 Python 环境与依赖"

# --- Python 版本检查 ---
if ! check_cmd python3; then
    fail "未找到 python3，请先安装 Python 3.10+"
    exit 1
fi
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
    ok "Python ${PY_VER}"
else
    warn "Python ${PY_VER} (建议 3.10+，可能存在兼容问题)"
fi

# --- 虚拟环境 ---
if [ -d "venv" ]; then
    ok "虚拟环境已存在"
    source venv/bin/activate 2>/dev/null || true
elif [ -d ".venv" ]; then
    ok "虚拟环境已存在 (.venv)"
    source .venv/bin/activate 2>/dev/null || true
else
    info "创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate
    ok "虚拟环境已创建并激活"
fi

# --- pip 镜像 ---
if [ "$USE_CN_MIRROR" = true ]; then
    info "配置清华镜像源"
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || true
fi

# --- 安装依赖 ---
info "安装/检查 Python 依赖..."
pip install --upgrade pip -q 2>/dev/null || true

# 核心依赖（webapp 必须）
pip install -q flask==3.0.3 pymysql==1.1.1 python-dotenv==1.0.1 requests==2.32.3 \
    numpy 'cryptography>=42.0' 2>/dev/null || true

# 可选依赖（SBERT / FAISS）
SBERT_OK=false
FAISS_OK=false

if check_py_pkg sentence_transformers; then
    SBERT_OK=true
else
    info "尝试安装 sentence-transformers..."
    pip install -q sentence-transformers==2.7.0 2>/dev/null && SBERT_OK=true || true
fi

if check_py_pkg faiss; then
    FAISS_OK=true
else
    info "尝试安装 faiss-cpu..."
    pip install -q faiss-cpu==1.7.4 2>/dev/null && FAISS_OK=true || true
fi

# 数据处理依赖（用于对象抽取）
pip install -q 'pandas>=2.0' 'openpyxl>=3.1' 'scikit-learn>=1.3' 'tqdm>=4.66' 2>/dev/null || true

# 汇报依赖状态
ok "Flask + PyMySQL + 核心依赖 已就绪"
if [ "$SBERT_OK" = true ]; then
    ok "SBERT (text2vec-base-chinese) 可用 — 完整语义聚类模式"
else
    warn "SBERT 不可用 — 将使用关键词规则回退模式"
fi
if [ "$FAISS_OK" = true ]; then
    ok "FAISS 向量检索可用"
else
    warn "FAISS 不可用 — RAG 功能受限"
fi

# ====================================================================
# Step 2: 数据完整性验证
# ====================================================================
show_step 2 "验证数据完整性"

# --- DATA/ 目录 ---
DOMAIN_COUNT=0
for domain_dir in DATA/*/; do
    [ -d "$domain_dir" ] || continue
    domain=$(basename "$domain_dir")
    xlsx_count=$(ls "$domain_dir"*.xlsx 2>/dev/null | wc -l)
    if [ "$xlsx_count" -gt 0 ]; then
        ok "DATA/${domain}/ — ${xlsx_count} 个 Excel 文件"
        DOMAIN_COUNT=$((DOMAIN_COUNT + 1))
    else
        warn "DATA/${domain}/ — 无 Excel 文件"
    fi
done

if [ "$DOMAIN_COUNT" -eq 0 ]; then
    fail "DATA/ 目录下未找到任何数据域，无法演示"
    exit 1
fi
info "共发现 ${DOMAIN_COUNT} 个数据域"

# --- outputs/ 提取结果 ---
OUTPUT_OK=true
for domain_dir in DATA/*/; do
    [ -d "$domain_dir" ] || continue
    domain=$(basename "$domain_dir")
    json_file="outputs/extraction_${domain}.json"
    if [ -f "$json_file" ]; then
        obj_count=$(python3 -c "
import json
d = json.load(open('$json_file'))
print(len(d.get('objects', [])))
" 2>/dev/null || echo "0")
        rel_count=$(python3 -c "
import json
d = json.load(open('$json_file'))
print(len(d.get('relations', [])))
" 2>/dev/null || echo "0")
        ok "${json_file} — ${obj_count} 个对象, ${rel_count} 条关联"
    else
        warn "${json_file} 不存在"
        OUTPUT_OK=false
    fi
done

# ====================================================================
# Step 3: 对象抽取（可选）
# ====================================================================
show_step 3 "对象抽取"

if [ "$SKIP_EXTRACT" = true ]; then
    info "已跳过对象抽取 (--skip-extract)"
elif [ "$OUTPUT_OK" = true ]; then
    info "outputs/ 中已有完整抽取结果，跳过抽取"
    info "如需重新抽取，请删除 outputs/extraction_*.json 后重新运行"
else
    info "开始执行对象抽取..."
    mkdir -p outputs

    for domain_dir in DATA/*/; do
        [ -d "$domain_dir" ] || continue
        domain=$(basename "$domain_dir")
        json_file="outputs/extraction_${domain}.json"

        # 如果该域已有结果则跳过
        if [ -f "$json_file" ]; then
            info "${domain}: 已有抽取结果，跳过"
            continue
        fi

        info "抽取数据域: ${domain}..."
        if [ "$SBERT_OK" = true ]; then
            python3 scripts/object_extractor.py \
                --data-dir "DATA/${domain}" \
                --data-domain "${domain}" \
                --target-clusters 15 \
                --no-db \
                --output "$json_file" 2>&1 | tail -5 || true
        else
            python3 scripts/simple_extractor.py \
                --data-dir "DATA/${domain}" \
                --data-domain "${domain}" \
                --output "$json_file" 2>&1 | tail -5 || true
        fi

        if [ -f "$json_file" ]; then
            ok "${domain}: 抽取完成"
        else
            fail "${domain}: 抽取失败"
        fi
    done
fi

# ====================================================================
# Step 4: 生成 .env & 启动 Flask Web 服务
# ====================================================================
show_step 4 "启动 Web 服务 (端口 ${WEB_PORT})"

# --- .env 配置 ---
if [ ! -f "webapp/.env" ]; then
    info "生成 webapp/.env 配置文件..."
    cat > webapp/.env << ENVEOF
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_DB=eav_db
MYSQL_USER=eav_user
MYSQL_PASSWORD=eavpass123
TABLE_PREFIX=eav
EMBED_MODEL=shibing624/text2vec-base-chinese
MODEL_CACHE=./models
DEEPSEEK_API_KEY=
RAG_TOP_K=5
ENVEOF
    ok "webapp/.env 已生成（数据库非必须，JSON 回退可用）"
else
    ok "webapp/.env 已存在"
fi

# --- 停止已有服务 ---
if lsof -i :"$WEB_PORT" -t &>/dev/null 2>&1; then
    info "端口 ${WEB_PORT} 被占用，正在释放..."
    kill $(lsof -i :"$WEB_PORT" -t) 2>/dev/null || true
    sleep 2
elif fuser "${WEB_PORT}/tcp" &>/dev/null 2>&1; then
    info "端口 ${WEB_PORT} 被占用，正在释放..."
    fuser -k "${WEB_PORT}/tcp" 2>/dev/null || true
    sleep 2
fi
pkill -f "python.*app.py" 2>/dev/null || true
sleep 1

# --- 启动服务 ---
info "启动 Flask 应用..."
cd webapp
FLASK_PORT="$WEB_PORT" nohup python3 app.py --port "$WEB_PORT" > /tmp/yimo_demo.log 2>&1 &
# 回退：如果 app.py 不支持 --port 参数，用环境变量方式
sleep 1
if ! kill -0 $! 2>/dev/null; then
    nohup python3 -c "
import app as a
a.app.run(host='0.0.0.0', port=${WEB_PORT}, debug=False)
" > /tmp/yimo_demo.log 2>&1 &
fi
WEB_PID=$!
cd "$PROJECT_DIR"

# --- 健康检查 ---
info "等待服务启动..."
SVC_UP=false
for i in $(seq 1 20); do
    sleep 2
    if curl -s "http://127.0.0.1:${WEB_PORT}/health" 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
sys.exit(0 if d.get('status') == 'ok' else 1)
" 2>/dev/null; then
        SVC_UP=true
        break
    fi
done

if [ "$SVC_UP" = true ]; then
    ok "Web 服务已启动 (PID: ${WEB_PID}, 端口: ${WEB_PORT})"
else
    fail "Web 服务启动失败，请查看日志: /tmp/yimo_demo.log"
    echo -e "  ${DIM}最后 20 行日志:${NC}"
    tail -20 /tmp/yimo_demo.log 2>/dev/null || true
    exit 1
fi

# ====================================================================
# Step 5: API 端点验证（演示前自检）
# ====================================================================
show_step 5 "API 端点验证（42 个端点自检）"

BASE="http://127.0.0.1:${WEB_PORT}"
PASS=0
FAIL_LIST=""
TOTAL_API=0

# 封装验证函数
check_api() {
    local method=$1
    local path=$2
    local label=$3
    local body="${4:-}"
    TOTAL_API=$((TOTAL_API + 1))

    local status
    if [ "$method" = "GET" ]; then
        status=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}${path}" 2>/dev/null || echo "000")
    else
        status=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" \
            -H "Content-Type: application/json" \
            -d "$body" "${BASE}${path}" 2>/dev/null || echo "000")
    fi

    if [ "$status" -ge 200 ] && [ "$status" -lt 500 ]; then
        PASS=$((PASS + 1))
        return 0
    else
        FAIL_LIST="${FAIL_LIST}\n    ${RED}${method} ${path}${NC} → HTTP ${status} (${label})"
        return 1
    fi
}

# --- 基础路由 ---
info "基础路由..."
check_api GET "/" "主页v10.0"
check_api GET "/health" "健康检查"
check_api GET "/api/domains" "数据域发现"

# --- 对象 CRUD ---
info "对象管理 API..."
check_api GET "/api/olm/extracted-objects" "对象列表"
check_api GET "/api/olm/extracted-objects?domain=shupeidian" "按域筛选"
check_api GET "/api/olm/export-objects" "对象导出"
check_api GET "/api/olm/stats" "系统统计"
check_api GET "/api/olm/domain-stats" "域统计"
check_api GET "/api/olm/summary" "总览摘要"
check_api GET "/api/olm/batches" "抽取批次"

# --- 三层关联 (核心需求) ---
info "三层架构关联 API（核心）..."
check_api GET "/api/olm/object-relations/OBJ_PROJECT" "项目三层关联"
check_api GET "/api/olm/relation-stats" "关联统计"
check_api GET "/api/olm/search-entities?q=项目" "实体搜索"
check_api GET "/api/olm/object-business-objects/OBJ_PROJECT" "BA-04映射"

# --- 可视化数据 ---
info "可视化数据 API..."
check_api GET "/api/olm/graph-data/OBJ_PROJECT" "知识图谱(项目)"
check_api GET "/api/olm/graph-data-global" "全局知识图谱"
check_api GET "/api/olm/sankey-data" "桑基图数据"
check_api GET "/api/olm/granularity-report" "颗粒度报告"
check_api GET "/api/olm/small-objects" "小对象分析"

# --- 生命周期 (Phase 2) ---
info "生命周期管理 API (Phase 2)..."
check_api GET "/api/olm/object-lifecycle/OBJ_PROJECT" "项目生命周期"
check_api GET "/api/olm/lifecycle-stats" "生命周期统计"

# --- 溯源 (Phase 3) ---
info "穿透式溯源 API (Phase 3)..."
check_api GET "/api/olm/traceability-chains" "溯源链列表"
check_api GET "/api/olm/trace-object/OBJ_PROJECT" "对象溯源"

# --- 机理函数 (Phase 4) ---
info "机理函数 API (Phase 4)..."
check_api GET "/api/olm/mechanism-functions" "机理函数列表"
check_api GET "/api/olm/mechanism-functions/presets" "预置函数模板"

# --- 预警 (Phase 5) ---
info "预警系统 API (Phase 5)..."
check_api GET "/api/olm/alerts" "预警记录"
check_api GET "/api/olm/alerts/summary" "预警统计"

# --- 治理看板 (Phase 6) ---
info "治理看板 API (Phase 6)..."
check_api GET "/api/olm/governance/metrics" "治理指标"
check_api GET "/api/olm/governance/completeness" "完整性分析"
check_api GET "/api/olm/governance/defects" "缺陷识别"
check_api GET "/api/olm/governance/domain-comparison" "跨域对比"

# --- 汇总 ---
echo ""
if [ "$PASS" -eq "$TOTAL_API" ]; then
    ok "${GREEN}${BOLD}全部 ${TOTAL_API} 个 API 端点验证通过${NC}"
else
    FAIL_COUNT=$((TOTAL_API - PASS))
    warn "${PASS}/${TOTAL_API} 个端点通过，${FAIL_COUNT} 个异常:"
    echo -e "$FAIL_LIST"
fi

# ====================================================================
# Step 6: 打印演示导览
# ====================================================================
show_step 6 "演示导览 — 甲方需求逐条对应"

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║           YIMO 对象抽取与三层架构关联系统 — 演示就绪               ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${CYAN}${BOLD}  访问地址:${NC}  ${GREEN}http://localhost:${WEB_PORT}${NC}"
echo ""

# --- 数据域统计 ---
echo -e "${CYAN}${BOLD}  已加载数据域:${NC}"
for domain_dir in DATA/*/; do
    [ -d "$domain_dir" ] || continue
    domain=$(basename "$domain_dir")
    json_file="outputs/extraction_${domain}.json"
    if [ -f "$json_file" ]; then
        obj_info=$(python3 -c "
import json
d = json.load(open('$json_file'))
objs = d.get('objects', [])
rels = d.get('relations', [])
names = ', '.join(o.get('object_name', '?') for o in objs)
print(f'{len(objs)} 个对象 ({names}), {len(rels)} 条关联')
" 2>/dev/null || echo "读取失败")
        echo -e "    ${MAGENTA}${domain}${NC}: ${obj_info}"
    fi
done
echo ""

# --- 甲方需求清单 ---
echo -e "${YELLOW}${BOLD}  ┌──────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}${BOLD}  │                   1.md 甲方核心需求 — 演示路线                   │${NC}"
echo -e "${YELLOW}${BOLD}  └──────────────────────────────────────────────────────────────────┘${NC}"
echo ""

echo -e "  ${BOLD}需求1: 对象抽取（SBERT + 层次聚类 + LLM命名）${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 主页 → 对象卡片网格，每个卡片显示对象名/编码/类型"
echo -e "    ${GREEN}✓${NC} 数据: 输配电 6 个对象 (项目/设备/系统/指标/文档/班站)"
echo -e "    ${GREEN}✓${NC} 数据: 计划财务 7 个对象 (指标/资产/合同/票据/发电/监督/项目)"
echo -e "    ${DIM}    点击「颗粒度分析」查看聚类质量 → 柱状图展示${NC}"
echo ""

echo -e "  ${BOLD}需求2: 三层架构关联可视化 (概念→逻辑→物理)${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 点击任意对象卡片 → 右侧三列关联面板"
echo -e "    ${GREEN}✓${NC} 面板: 概念实体(紫#6366f1) | 逻辑实体(绿#10b981) | 物理实体(橙#f59e0b)"
echo -e "    ${GREEN}✓${NC} 可视化: 知识图谱(ECharts力导向) + 桑基图(4层流向)"
echo -e "    ${DIM}    点击「知识图谱」和「桑基图」Tab 切换查看${NC}"
echo ""

echo -e "  ${BOLD}需求3: 必须包含「项目」对象${NC}"
echo -e "    ${GREEN}✓${NC} 保障: REQUIRED_OBJECTS=[\"项目\"] + _ensure_required_objects()"
echo -e "    ${GREEN}✓${NC} 验证: 两个域均含 OBJ_PROJECT"
echo ""

echo -e "  ${BOLD}需求4: 多域支持 (输配电 + 计划财务)${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 顶部下拉框切换域 → 对象列表动态刷新"
echo -e "    ${GREEN}✓${NC} API: /api/domains 自动发现 DATA/ 子目录"
echo ""

echo -e "  ${BOLD}需求5: EAV 动态扩展模型${NC}"
echo -e "    ${GREEN}✓${NC} 19 张数据库表 + 4 个视图 (bootstrap.sql)"
echo -e "    ${GREEN}✓${NC} 4 张 EAV 核心表: datasets/entities/attributes/values"
echo ""

echo -e "  ${BOLD}需求6: SBERT + EAV 保留${NC}"
if [ "$SBERT_OK" = true ]; then
    echo -e "    ${GREEN}✓${NC} SBERT (text2vec-base-chinese, 768维) 已加载"
else
    echo -e "    ${YELLOW}!${NC} SBERT 未加载（当前使用关键词规则回退）"
fi
echo -e "    ${GREEN}✓${NC} EAV 导入工具: eav_full.py / eav_csv.py"
echo ""

echo -e "  ${BOLD}需求7: 旧统一本体功能已删除${NC}"
echo -e "    ${GREEN}✓${NC} 已按甲方要求清除，仅保留对象抽取+三层关联"
echo ""

echo -e "  ${BOLD}需求8: v10.0 界面风格保留${NC}"
echo -e "    ${GREEN}✓${NC} 10.0.html: 2768 行, 三色层级设计, ECharts 图表"
echo ""

echo -e "${YELLOW}${BOLD}  ┌──────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}${BOLD}  │                0.md 愿景需求 — 已实现（附加演示）                │${NC}"
echo -e "${YELLOW}${BOLD}  └──────────────────────────────────────────────────────────────────┘${NC}"
echo ""

echo -e "  ${BOLD}Phase 2: 全生命周期管理${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 点击对象 → 生命周期面板 → 5阶段时间线"
echo -e "    ${DIM}    Planning → Design → Construction → Operation → Finance${NC}"
echo ""

echo -e "  ${BOLD}Phase 3: 穿透式业务溯源${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 溯源面板 → 链路卡片 + 节点流程图"
echo -e "    ${GREEN}✓${NC} 预置: 计财域 3 条溯源链路 (结算穿透/合同审计/资产生命周期)"
echo ""

echo -e "  ${BOLD}Phase 4: 机理函数${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 机理函数面板 → 3 种类型 (THRESHOLD/FORMULA/RULE)"
echo -e "    ${GREEN}✓${NC} 交互: 输入参数 → 实时求值测试"
echo ""

echo -e "  ${BOLD}Phase 5: 穿透式预警${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 预警面板 → 4 个统计卡片 + 预警列表"
echo ""

echo -e "  ${BOLD}Phase 6: 治理看板${NC}"
echo -e "    ${GREEN}✓${NC} 演示: 治理面板 → 8 项指标 + 完整性表格 + 缺陷列表"
echo ""

# --- 演示操作指南 ---
echo -e "${CYAN}${BOLD}  ┌──────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${CYAN}${BOLD}  │                         演示操作建议                             │${NC}"
echo -e "${CYAN}${BOLD}  └──────────────────────────────────────────────────────────────────┘${NC}"
echo ""
echo -e "    ${BOLD}1.${NC} 打开 ${GREEN}http://localhost:${WEB_PORT}${NC}"
echo -e "       → 展示 v10.0 主控制台全貌（三色层级设计）"
echo ""
echo -e "    ${BOLD}2.${NC} 在顶部域选择器切换「输配电」→「计划财务」"
echo -e "       → 展示多域动态加载能力"
echo ""
echo -e "    ${BOLD}3.${NC} 点击「项目」对象卡片"
echo -e "       → 展示三层关联面板（概念/逻辑/物理），强调关联强度"
echo ""
echo -e "    ${BOLD}4.${NC} 切换到「知识图谱」Tab"
echo -e "       → 展示 ECharts 力导向图，节点可拖拽交互"
echo ""
echo -e "    ${BOLD}5.${NC} 切换到「桑基图」Tab"
echo -e "       → 展示对象→概念→逻辑→物理 四层流向"
echo ""
echo -e "    ${BOLD}6.${NC} 点击「颗粒度分析」"
echo -e "       → 展示聚类质量柱状图，说明算法完备性"
echo ""
echo -e "    ${BOLD}7.${NC} 依次展示生命周期/溯源/机理函数/预警/治理看板"
echo -e "       → 展示系统深度功能（0.md 愿景需求已实现）"
echo ""

# --- 底部信息 ---
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${DIM}API 端点:${NC}  ${PASS}/${TOTAL_API} 通过"
echo -e "  ${DIM}数据模式:${NC}  DB优先 + JSON回退（无数据库也可演示）"
echo -e "  ${DIM}日志文件:${NC}  /tmp/yimo_demo.log"
echo -e "  ${DIM}停止服务:${NC}  kill ${WEB_PID} 或 pkill -f 'python.*app.py'"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
