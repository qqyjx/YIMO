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

## 待办

- [ ] 03 生命周期 / 溯源 / 机理函数 / 预警四模块（对应 MySQL bootstrap 第 359-531 行）
- [ ] 04 治理视图（V_GOVERNANCE_COMPLETENESS / V_GOVERNANCE_DEFECTS）
- [ ] 99 预置字典（业务域 / 预置对象 / 示例溯源链路）
- [ ] 正式交付前由南网 DBA 审核达梦 8.1 上的关键字冲突（参见《达梦数据库设计开发规范》附录 9）
