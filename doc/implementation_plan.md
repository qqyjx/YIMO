# 未完成需求实施计划

> 创建日期: 2026-02-19
> 基于需求审查结果 (CLAUDE.md Requirements Fulfillment Status)

---

## 总览

| 阶段 | 内容 | 依赖 | 预计复杂度 |
|------|------|------|-----------|
| Phase 1 | 数据库表结构扩展 | 无 | 中 |
| Phase 2 | 全生命周期管理完善 | Phase 1 | 中 |
| Phase 3 | 穿透式业务溯源完善 | Phase 1 | 中 |
| Phase 4 | 机理函数框架 | Phase 1 | 高 |
| Phase 5 | 穿透式预警与辅助决策 | Phase 4 | 中 |
| Phase 6 | 财务域落地场景 | Phase 2,3 + 甲方提供数据 | 高 |
| Phase 7 | 财务数据一致性治理看板 | Phase 6 | 中 |
| Phase 8 | 与企业数据中台对比 | 甲方提供中台接口规格 | 高 |
| Phase 9 | HTAP非结构化数据融合 | 甲方提供技术方案 | 极高 |

**说明**: Phase 1-5 可自主推进; Phase 6-9 依赖甲方输入，先搭框架。

---

## Phase 1: 数据库表结构扩展

### 目标
为后续功能创建必要的数据库表和索引。

### 实施内容

#### 1.1 对象生命周期历史表
```sql
CREATE TABLE object_lifecycle_history (
    history_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    object_id INT NOT NULL,
    lifecycle_stage ENUM('Planning','Design','Construction','Operation','Finance'),
    stage_entered_at DATETIME(6),
    stage_exited_at DATETIME(6),
    attributes_snapshot JSON COMMENT '该阶段的对象属性快照',
    data_domain VARCHAR(128),
    source_system VARCHAR(256) COMMENT '来源系统(SAP/ERP等)',
    notes TEXT,
    created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (object_id) REFERENCES extracted_objects(object_id),
    KEY idx_object_stage (object_id, lifecycle_stage),
    KEY idx_stage_time (lifecycle_stage, stage_entered_at)
);
```

#### 1.2 审计日志表
```sql
CREATE TABLE audit_logs (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL,
    record_id BIGINT NOT NULL,
    action ENUM('INSERT','UPDATE','DELETE') NOT NULL,
    old_values JSON,
    new_values JSON,
    change_reason VARCHAR(512),
    operated_by VARCHAR(128),
    operated_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_table_record (table_name, record_id),
    KEY idx_operated_at (operated_at)
);
```

#### 1.3 穿透链路表
```sql
CREATE TABLE traceability_chains (
    chain_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    chain_code VARCHAR(128) NOT NULL UNIQUE COMMENT '链路编码',
    chain_name VARCHAR(256) COMMENT '链路名称(如:项目结算溯源链)',
    chain_type ENUM('FINANCIAL','PROCUREMENT','CONSTRUCTION','CUSTOM'),
    data_domain VARCHAR(128),
    description TEXT,
    created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE traceability_chain_nodes (
    node_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    chain_id BIGINT NOT NULL,
    node_order INT NOT NULL COMMENT '节点在链路中的顺序',
    object_id INT COMMENT '关联的对象ID',
    entity_layer ENUM('CONCEPT','LOGICAL','PHYSICAL'),
    entity_name VARCHAR(512),
    node_label VARCHAR(256) COMMENT '节点显示名称',
    node_type ENUM('SOURCE','INTERMEDIATE','TARGET'),
    source_file VARCHAR(256),
    source_sheet VARCHAR(256),
    metadata JSON,
    FOREIGN KEY (chain_id) REFERENCES traceability_chains(chain_id) ON DELETE CASCADE,
    FOREIGN KEY (object_id) REFERENCES extracted_objects(object_id),
    KEY idx_chain_order (chain_id, node_order)
);
```

#### 1.4 机理函数表
```sql
CREATE TABLE mechanism_functions (
    func_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    func_code VARCHAR(128) NOT NULL UNIQUE,
    func_name VARCHAR(256) NOT NULL COMMENT '函数名称(如:合同金额审计红线)',
    func_type ENUM('FORMULA','RULE','THRESHOLD','VALIDATION') NOT NULL,
    category ENUM('FINANCIAL','PHYSICAL','BUSINESS','QUALITY') DEFAULT 'BUSINESS',
    expression TEXT NOT NULL COMMENT '函数表达式(JSON格式)',
    description TEXT,
    source_object_code VARCHAR(128) COMMENT '触发对象',
    target_object_code VARCHAR(128) COMMENT '作用对象',
    severity ENUM('INFO','WARNING','CRITICAL') DEFAULT 'WARNING',
    is_active BOOLEAN DEFAULT TRUE,
    data_domain VARCHAR(128),
    created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY idx_source_obj (source_object_code),
    KEY idx_type_active (func_type, is_active)
);
```

#### 1.5 预警记录表
```sql
CREATE TABLE alert_records (
    alert_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    func_id BIGINT NOT NULL COMMENT '触发的机理函数',
    alert_level ENUM('INFO','WARNING','CRITICAL') NOT NULL,
    alert_title VARCHAR(256),
    alert_detail TEXT,
    related_object_id INT,
    related_entity_name VARCHAR(512),
    trigger_value TEXT COMMENT '触发时的实际值',
    threshold_value TEXT COMMENT '阈值',
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_by VARCHAR(128),
    resolved_at TIMESTAMP(6),
    created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (func_id) REFERENCES mechanism_functions(func_id),
    KEY idx_level_resolved (alert_level, is_resolved),
    KEY idx_created (created_at)
);
```

### 修改文件
- `mysql-local/bootstrap.sql` — 追加新表定义（使用已有的条件ALTER模式确保幂等）

---

## Phase 2: 全生命周期管理完善

### 目标
补全对象属性的时态历史追踪，实现对象在不同生命周期阶段的属性变化可视化。

### 实施内容

#### 2.1 后端 API (olm_api.py 新增端点)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/olm/object-lifecycle/<code>` | GET | 查询对象的生命周期历史 |
| `/api/olm/object-lifecycle/<code>` | POST | 新增生命周期阶段记录 |
| `/api/olm/lifecycle-stats` | GET | 各阶段对象分布统计 |

#### 2.2 前端 (10.0.html 新增面板)

- **侧边栏新增**: "生命周期" 导航项
- **生命周期时间线面板**:
  - 水平时间线: Planning → Design → Construction → Operation → Finance
  - 每个阶段节点可展开查看属性快照
  - 高亮当前阶段
  - 使用 ECharts timeline 组件或自定义 CSS timeline

### 修改文件
- `webapp/olm_api.py` — 新增3个端点
- `webapp/templates/10.0.html` — 新增生命周期面板
- `mysql-local/bootstrap.sql` — Phase 1 已创建表

---

## Phase 3: 穿透式业务溯源完善

### 目标
建立从财务结算到底层业务数据的完整溯源链路，支持可视化追踪。

### 实施内容

#### 3.1 后端 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/olm/traceability-chains` | GET | 列出所有溯源链路 |
| `/api/olm/traceability-chains` | POST | 创建溯源链路 |
| `/api/olm/traceability-chain/<chain_id>` | GET | 查询链路详情(含全部节点) |
| `/api/olm/trace-object/<code>` | GET | 从对象出发追溯所有关联链路 |

#### 3.2 自动链路生成
在 `object_extractor.py` 中新增链路推断逻辑：
- 基于 `object_entity_relations` 中的 `via_concept_entity` 字段
- 自动推断: 对象A(概念层) → 对象B(逻辑层) → 对象C(物理层) 的穿透路径
- 输出预置链路模板（如"项目结算溯源链"）

#### 3.3 前端

- **侧边栏新增**: "溯源链路" 导航项
- **溯源可视化面板**:
  - 链路列表（卡片式）
  - 选中链路后展示节点流程图（ECharts graph 或自定义流程图）
  - 节点可点击查看关联实体详情
  - 层级颜色编码与现有三色方案一致

### 修改文件
- `webapp/olm_api.py` — 新增4个端点
- `webapp/templates/10.0.html` — 新增溯源面板
- `scripts/object_extractor.py` — 新增链路推断函数

---

## Phase 4: 机理函数框架

### 目标
实现业务规则和物理公式的定义、存储和执行框架。

### 实施内容

#### 4.1 函数表达式格式设计

```json
{
  "type": "THRESHOLD",
  "field": "合同金额",
  "operator": ">",
  "value": 3000000,
  "unit": "元",
  "action": "ALERT",
  "message": "合同金额超过300万审计红线"
}
```

```json
{
  "type": "FORMULA",
  "expression": "功率 = 电压 * 电流",
  "variables": ["电压", "电流"],
  "result": "功率",
  "unit": "W"
}
```

```json
{
  "type": "RULE",
  "condition": "合同金额 > 3000000",
  "then": "审批路径 = 'A级审批'",
  "else": "审批路径 = 'B级审批'"
}
```

#### 4.2 后端 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/olm/mechanism-functions` | GET | 列出所有机理函数 |
| `/api/olm/mechanism-functions` | POST | 创建机理函数 |
| `/api/olm/mechanism-functions/<func_id>` | PUT | 更新机理函数 |
| `/api/olm/mechanism-functions/<func_id>` | DELETE | 删除机理函数 |
| `/api/olm/mechanism-functions/evaluate` | POST | 执行函数评估(给定输入值) |
| `/api/olm/mechanism-functions/presets` | GET | 获取预置函数模板 |

#### 4.3 预置机理函数

根据 0.md 中的例子，预置以下函数：
1. **合同金额审计红线**: 合同金额 > 300万 → 触发审计预警
2. **功率公式**: 功率 = 电压 × 电流
3. **付款路径规则**: 根据金额走不同审批路径

#### 4.4 前端

- **侧边栏新增**: "机理函数" 导航项
- **函数管理面板**:
  - 函数列表（表格式，含类型/状态/严重级别筛选）
  - 新建/编辑函数表单（JSON表达式编辑器）
  - 函数测试面板（输入参数 → 查看结果）
  - 对象间函数关系图（ECharts graph: 对象A --函数--> 对象B）

### 修改文件
- `webapp/olm_api.py` — 新增6个端点
- `webapp/templates/10.0.html` — 新增机理函数面板
- `mysql-local/bootstrap.sql` — Phase 1 已创建表

---

## Phase 5: 穿透式预警与辅助决策

### 目标
基于机理函数自动触发风险预警，提供决策辅助看板。

### 实施内容

#### 5.1 后端 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/olm/alerts` | GET | 查询预警记录(支持级别/状态筛选) |
| `/api/olm/alerts/<alert_id>/resolve` | POST | 标记预警已处理 |
| `/api/olm/alerts/summary` | GET | 预警统计概览 |
| `/api/olm/alerts/run-check` | POST | 手动触发全量规则检查 |

#### 5.2 规则检查引擎
在 `scripts/` 新增 `rule_engine.py`:
- 遍历所有 `is_active=True` 的机理函数
- 对每个函数，从 EAV 数据中提取相关属性值
- 评估表达式，生成预警记录
- 支持手动触发和定时触发

#### 5.3 前端

- **总览面板扩展**: 新增预警统计卡片（待处理预警数、本周新增、严重级别分布）
- **侧边栏新增**: "风险预警" 导航项
- **预警看板面板**:
  - 预警列表（按严重级别排序，未处理在前）
  - 预警详情弹窗（触发函数、实际值、阈值、关联对象）
  - 标记已处理按钮
  - 预警趋势图（ECharts line chart: 按日/周统计）

### 修改文件
- `webapp/olm_api.py` — 新增4个端点
- `webapp/templates/10.0.html` — 扩展总览 + 新增预警面板
- `scripts/rule_engine.py` — 新建规则引擎

---

## Phase 6: 财务域落地场景 (依赖甲方提供数据)

### 前置条件
- [ ] 甲方提供财务域 DA-01/DA-02/DA-03 Excel 数据
- [ ] 确认财务域目录名（建议 `DATA/caiwu/`）

### 实施内容

#### 6.1 数据导入
- 在 `DATA/caiwu/` 放入财务域 Excel 文件
- 运行现有抽取流程: `python scripts/object_extractor.py --data-dir DATA`
- 生成 `outputs/extraction_caiwu.json`

#### 6.2 财务场景演示链路
构建"数字化项目结算"溯源链路：
```
财务结算单据 → 项目立项审批 → 采购合同 → 物资入库 → 现场施工记录
```

#### 6.3 前端
- 域选择器自动识别新域（已有能力）
- 财务场景专用溯源链路演示

### 修改文件
- `DATA/caiwu/` — 新增数据目录
- 可能需要更新 `DOMAIN_CONFIG`（如果财务域 sheet 格式特殊）

---

## Phase 7: 财务数据一致性治理看板 (依赖 Phase 6)

### 前置条件
- [ ] Phase 6 完成（财务域数据可用）
- [ ] 甲方确认比对规则和阈值

### 实施内容

#### 7.1 后端 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/olm/governance/consistency-check` | POST | 执行一致性比对 |
| `/api/olm/governance/report` | GET | 获取治理报告 |
| `/api/olm/governance/issues` | GET | 获取发现的问题列表 |

#### 7.2 比对逻辑
- 对比财务系统字段与 EA 标准逻辑实体
- 自动识别: 属性缺漏、定义冲突、重复项
- 基于机理函数（Phase 4）提供治理建议

#### 7.3 前端
- **侧边栏新增**: "数据治理" 导航项
- 一致性评分仪表盘
- 问题清单（可筛选/排序）
- 治理建议面板

---

## Phase 8: 与企业数据中台对比 (依赖甲方输入)

### 前置条件
- [ ] 甲方提供中台数据格式规格
- [ ] 甲方提供对比规则定义
- [ ] 确认中台 API 或数据导出方式

### 实施内容
- 中台数据导入适配器
- 对象名称/属性语义匹配（复用 SBERT）
- 差异报告生成
- 前端对比视图

---

## Phase 9: HTAP非结构化数据融合 (依赖甲方输入)

### 前置条件
- [ ] 甲方确认非结构化数据类型（照片/视频/文档）
- [ ] 甲方确认数据存储方案
- [ ] 甲方确认 HTAP 技术选型

### 实施内容
- 非结构化数据存储方案设计
- 多模态数据关联模型
- 混合查询接口

---

## 实施优先级建议

```
Phase 1 (数据库) ──┬── Phase 2 (生命周期) ──── Phase 6 (财务域) ── Phase 7 (治理看板)
                   ├── Phase 3 (溯源链路) ──┘
                   └── Phase 4 (机理函数) ──── Phase 5 (预警)

Phase 8 (中台对比) ← 等甲方输入
Phase 9 (HTAP)    ← 等甲方输入
```

**建议执行顺序**: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6(等数据) → Phase 7

---

## 工作量估算

| 阶段 | 新增/修改文件数 | 新增代码量(估) | 备注 |
|------|---------------|--------------|------|
| Phase 1 | 1 | ~120行SQL | bootstrap.sql追加 |
| Phase 2 | 2 | ~250行 | API ~150行 + 前端 ~100行 |
| Phase 3 | 3 | ~400行 | API ~200行 + 前端 ~100行 + 链路推断 ~100行 |
| Phase 4 | 2 | ~500行 | API ~300行 + 前端 ~200行 |
| Phase 5 | 3 | ~450行 | API ~150行 + 规则引擎 ~200行 + 前端 ~100行 |
| Phase 6 | 1-2 | ~50行 | 主要是数据导入配置 |
| Phase 7 | 2 | ~350行 | API ~200行 + 前端 ~150行 |
| **合计(可自主推进)** | | **~2070行** | Phase 1-5 |
