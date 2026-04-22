# API 对齐计划：webapp → platform

把 [webapp/olm_api.py](../../webapp/olm_api.py) 的 60+ 端点按优先级分 4 批迁到 Java 后端。迁移原则：

1. **去 `/olm/` 前缀**：`/api/olm/xxx` → `/api/v1/xxx`，版本号替换业务前缀，便于后续版本演进
2. **Service 层命名对齐南网 JAVA 规范**：`get/list/count/save/update/remove` 前缀
3. **数据源渐进**：先读 `outputs/extraction_*.json`（与 webapp 同源），DM 表建好后切库
4. **响应体**：统一 `Result<T>` 结构（code/message/data），不再沿用 webapp 的裸字段

## 端点映射全表

### Phase 1 — 浏览与可视化（**7 个，必做**）

| webapp 端点 | platform 端点 | 方法 | Controller | Service 方法 |
|-------------|---------------|------|------------|--------------|
| `/api/olm/extracted-objects` | `/api/v1/objects` | GET | `ObjectController` | `objectService.listObjects(domain)` |
| `/api/olm/object-relations/<code>` | `/api/v1/objects/{code}/relations` | GET | `ObjectController` | `objectService.getRelations(code, domain)` |
| `/api/olm/stats` | `/api/v1/stats` | GET | `StatsController` | `statsService.getOverall()` |
| `/api/olm/domain-stats` | `/api/v1/stats/domains` | GET | `StatsController` | `statsService.listDomainStats()` |
| `/api/olm/summary` | `/api/v1/summary` | GET | `DashboardController` | `dashboardService.getSummary(domain)` |
| `/api/olm/graph-data-three-tier` | `/api/v1/graph/three-tier` | GET | `GraphController` | `graphService.getThreeTierGraph(params)` |
| `/api/olm/sankey-data` | `/api/v1/graph/sankey` | GET | `GraphController` | `graphService.getSankeyData(domain)` |

### Phase 2 — 管理操作（**8 个**）

| webapp | platform | 方法 |
|--------|----------|------|
| `/api/olm/objects` | `/api/v1/objects` | POST |
| `/api/olm/objects/<code>` | `/api/v1/objects/{code}` | PUT/DELETE |
| `/api/olm/merge-objects` | `/api/v1/objects/merge` | POST |
| `/api/olm/bulk-merge-small` | `/api/v1/objects/bulk-merge-small` | POST |
| `/api/olm/granularity-report` | `/api/v1/objects/granularity` | GET |
| `/api/olm/small-objects` | `/api/v1/objects/small` | GET |
| `/api/olm/cross-domain-duplicates` | `/api/v1/objects/cross-domain-duplicates` | GET |
| `/api/olm/run-extraction` | `/api/v1/extraction/run` | POST |

### Phase 3 — 生命周期 / 溯源（**8 个**）

| webapp | platform |
|--------|----------|
| `/api/olm/object-lifecycle/<code>` | `/api/v1/lifecycle/{code}` (GET/POST) |
| `/api/olm/lifecycle-stats` | `/api/v1/lifecycle/stats` |
| `/api/olm/lifecycle-analytics` | `/api/v1/lifecycle/analytics` |
| `/api/olm/lifecycle-report/<code>` | `/api/v1/lifecycle/{code}/report` |
| `/api/olm/traceability-chains` | `/api/v1/trace/chains` (GET/POST) |
| `/api/olm/traceability-chain/<id>` | `/api/v1/trace/chains/{id}` |
| `/api/olm/trace-object/<code>` | `/api/v1/trace/by-object/{code}` |

### Phase 4 — 机理函数 / 预警 / 治理（**14 个**）

| webapp | platform |
|--------|----------|
| `/api/olm/mechanism-functions` | `/api/v1/mechanism/functions` (CRUD) |
| `/api/olm/mechanism-functions/evaluate` | `/api/v1/mechanism/functions/evaluate` |
| `/api/olm/mechanism-functions/presets` | `/api/v1/mechanism/functions/presets` |
| `/api/olm/alerts` | `/api/v1/alerts` (GET) |
| `/api/olm/alerts/<id>/resolve` | `/api/v1/alerts/{id}/resolve` |
| `/api/olm/alerts/summary` | `/api/v1/alerts/summary` |
| `/api/olm/alerts/run-check` | `/api/v1/alerts/run-check` |
| `/api/olm/governance/metrics` | `/api/v1/governance/metrics` |
| `/api/olm/governance/completeness` | `/api/v1/governance/completeness` |
| `/api/olm/governance/defects` | `/api/v1/governance/defects` |
| `/api/olm/governance/domain-comparison` | `/api/v1/governance/domain-comparison` |
| `/api/olm/relation-rules` | `/api/v1/relations/rules` (CRUD) |
| `/api/olm/relation-rules/evaluate` | `/api/v1/relations/rules/evaluate` |
| `/api/olm/relation-rules/graph` | `/api/v1/relations/rules/graph` |

## 不迁移（仅 webapp 保留）

- `/deepseek/chat` — DeepSeek 代理，南网内网大概率不能直连，platform 改走内部 LLM 网关
- `/rag/query` — FAISS 向量检索，并入算法服务（见 [algorithm-integration.md](algorithm-integration.md)）
- `/api/domains` — 已在 platform 实现（`DomainController`）

## 数据源策略

| 阶段 | 数据源 |
|------|--------|
| Phase 1 接入 | JSON 文件（`outputs/extraction_<domain>.json`，与 webapp 共享） |
| Phase 2-4 接入 | DM 数据库（执行 `dm-schema/` DDL 后切换） |
| 算法重新抽取 | 调用 Python 算法服务（见 algorithm-integration.md） |

## 估时

- Phase 1：1-2 工作日（7 端点 + 4 Service + 4 DTO）
- Phase 2-4：2-3 工作日
- DM 迁库：1 工作日（待 DDL 03/04/99 补齐）

合计 1 周左右可对齐 37 个核心端点。
