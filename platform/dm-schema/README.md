# 达梦 DM8 建表脚本

## 执行顺序

```
01_ddl_tf_eav.sql          -- EAV 核心 4 表
02_ddl_tf_om.sql           -- 对象抽取 + 三层关联
03_ddl_tf_lc_tr_mf_al.sql  -- 生命周期/溯源/机理函数/预警 (待补)
04_ddl_tf_gv_views.sql     -- 治理视图 (待补)
99_init_dict_data.sql      -- 字典预置数据 (待补)
```

## 执行方式

### 南网正式环境 (达梦 DM8)

```bash
# 假定 SYSDBA 已登陆, 库名 TWIN_FUSION
disql SYSDBA/SYSDBA@10.x.x.x:5236 <<EOF
CREATE SCHEMA TWIN_FUSION;
SET SCHEMA TWIN_FUSION;
START ./01_ddl_tf_eav.sql
START ./02_ddl_tf_om.sql
EOF
```

### 本地开发 (MySQL 兼容模式临时替代)

后端 `application-local.yml` 已配置走 MySQL 127.0.0.1:3307。DDL 语法在 MySQL 下大多不兼容（`IDENTITY(1,1)`、`COMMENT ON` 子句），需要另一份 MySQL 版 DDL；当前复用 [../../mysql-local/bootstrap.sql](../../mysql-local/bootstrap.sql)，待交付前由运维 DBA 确认达梦版本可正常执行。

## 命名规范速查 (达梦开发规范)

| 对象 | 规则 | 示例 |
|------|------|------|
| 表名 | `<业务简称>[_二级域]_<实体名>` 大写 | `TF_OM_EXTRACTED_OBJECT` |
| 字段 | 大写 + 下划线, 命名见义 | `OBJECT_CODE`, `ENTITY_LAYER` |
| 主键 | 代理键 `ID`, IDENTITY 自增 | — |
| 公共字段 | `CREATE_TIME`, `UPDATE_TIME` 必填 | — |
| 布尔字段 | 无 `IS_` 前缀, 用 CHAR(1) CHECK IN ('0','1') | `VALUE_BOOL` |
| 外键 | `FK_<表缩写>_<引用对象>` | `FK_TF_EAV_VALUE_ENTITY` |
| 索引 | `IDX_<表>_<字段>` | `IDX_TF_OM_OBJECT_DOMAIN` |
| 注释 | COMMENT ON TABLE/COLUMN, 逐字段必写 | — |

## 已完成

- [x] 01 EAV 4 表 (DATASET / ENTITY / ATTRIBUTE / VALUE)
- [x] 02 OM 2 表 (EXTRACTED_OBJECT / ENTITY_RELATION)
- [x] 03 LC + TR + MF + AL 4 模块共 5 表 (LC_OBJECT_HISTORY / TR_CHAIN / TR_CHAIN_NODE / MF_FUNCTION / AL_ALERT_RECORD)
- [x] 04 GV 治理 2 视图 (V_TF_GV_COMPLETENESS / V_TF_GV_DEFECTS)
- [x] 99 预置 4 机理函数 + 3 溯源链路 (MERGE INTO 幂等)

## 待办

- [ ] 99_init_dict_data.sql 中链路节点的 INSERT 翻译 (依赖 OBJECT_ID 子查询, 需 DBA 协助)
- [ ] 次要表: object_synonyms / object_attribute_definitions / object_business_object_mapping / object_extraction_batches / object_batch_mapping / object_dedup_decisions / formula_chains / field_lineage 等
  (这些当前 webapp 用得少, 可分阶段补)
- [ ] 正式交付前由南网 DBA 审核达梦 8.1 上的关键字冲突（参见《达梦数据库设计开发规范》附录 9）
- [ ] 索引调优: 上线后根据热点查询补复合索引
