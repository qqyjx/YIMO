-- ============================================================================
-- 99 - 字典与预置数据 (机理函数 + 溯源链路 + 必备对象 "项目")
-- ============================================================================
-- 与 mysql-local/bootstrap.sql 中的 INSERT 等价, 但用达梦 MERGE INTO 实现幂等.
-- 上线前由 DBA 校验 LIMIT 1 子查询的目标对象在 TF_OM_EXTRACTED_OBJECT 已存在.
-- ============================================================================

-- ----------------- 预置 4 条机理函数 -----------------
MERGE INTO "TF_MF_FUNCTION" t USING (
    SELECT 'MF_CONTRACT_AUDIT' AS FUNC_CODE FROM DUAL UNION ALL
    SELECT 'MF_POWER_FORMULA'                FROM DUAL UNION ALL
    SELECT 'MF_APPROVAL_RULE'                FROM DUAL UNION ALL
    SELECT 'MF_PROJECT_AMOUNT'               FROM DUAL
) s ON (t."FUNC_CODE" = s.FUNC_CODE)
WHEN NOT MATCHED THEN INSERT ("FUNC_CODE","FUNC_NAME","FUNC_TYPE","CATEGORY","EXPRESSION","DESCRIPTION","SOURCE_OBJECT_CODE","SEVERITY","IS_ACTIVE")
    VALUES (s.FUNC_CODE, '占位 (待 99 后续 INSERT 替换)', 'RULE', 'BUSINESS', '{}', '', NULL, 'INFO', '1');

-- 真实数据 (覆盖式)
UPDATE "TF_MF_FUNCTION" SET
    "FUNC_NAME"     = '合同金额审计红线',
    "FUNC_TYPE"     = 'THRESHOLD',
    "CATEGORY"      = 'FINANCIAL',
    "EXPRESSION"    = '{"field":"合同金额","operator":">","value":3000000,"unit":"元","action":"ALERT","message":"合同金额超过300万审计红线，需走A级审批"}',
    "DESCRIPTION"   = '当合同金额超过300万元时触发审计预警，要求走A级审批路径',
    "SOURCE_OBJECT_CODE" = 'OBJ_CONTRACT',
    "SEVERITY"      = 'CRITICAL',
    "IS_ACTIVE"     = '1'
WHERE "FUNC_CODE" = 'MF_CONTRACT_AUDIT';

UPDATE "TF_MF_FUNCTION" SET
    "FUNC_NAME"     = '功率计算公式',
    "FUNC_TYPE"     = 'FORMULA',
    "CATEGORY"      = 'PHYSICAL',
    "EXPRESSION"    = '{"expression":"功率 = 电压 * 电流","variables":["电压","电流"],"result":"功率","unit":"W"}',
    "DESCRIPTION"   = '基础物理公式：功率 = 电压 × 电流',
    "SOURCE_OBJECT_CODE" = 'OBJ_DEVICE',
    "SEVERITY"      = 'INFO',
    "IS_ACTIVE"     = '1'
WHERE "FUNC_CODE" = 'MF_POWER_FORMULA';

UPDATE "TF_MF_FUNCTION" SET
    "FUNC_NAME"     = '付款审批路径规则',
    "FUNC_TYPE"     = 'RULE',
    "CATEGORY"      = 'BUSINESS',
    "EXPRESSION"    = '{"condition":"合同金额 > 3000000","then":"审批路径 = A级审批","else":"审批路径 = B级审批"}',
    "DESCRIPTION"   = '根据合同金额自动判定审批路径',
    "SOURCE_OBJECT_CODE" = 'OBJ_CONTRACT',
    "SEVERITY"      = 'WARNING',
    "IS_ACTIVE"     = '1'
WHERE "FUNC_CODE" = 'MF_APPROVAL_RULE';

UPDATE "TF_MF_FUNCTION" SET
    "FUNC_NAME"     = '项目总金额计算',
    "FUNC_TYPE"     = 'FORMULA',
    "CATEGORY"      = 'FINANCIAL',
    "EXPRESSION"    = '{"unit":"元","result":"项目总金额","variables":["立项金额","合同金额","变更金额"],"expression":"项目总金额 = 立项金额 + 合同金额 + 变更金额"}',
    "DESCRIPTION"   = '项目全周期金额由立项预算 + 合同采购 + 变更追加 三部分相加',
    "SOURCE_OBJECT_CODE" = 'OBJ_PROJECT',
    "DATA_DOMAIN"   = '计划财务',
    "SEVERITY"      = 'INFO',
    "IS_ACTIVE"     = '1'
WHERE "FUNC_CODE" = 'MF_PROJECT_AMOUNT';


-- ----------------- 预置 3 条溯源链路 (计财演示) -----------------
MERGE INTO "TF_TR_CHAIN" t USING (
    SELECT 'CHAIN_SETTLE_TRACE'   AS CHAIN_CODE FROM DUAL UNION ALL
    SELECT 'CHAIN_CONTRACT_AUDIT'                FROM DUAL UNION ALL
    SELECT 'CHAIN_ASSET_LIFECYCLE'               FROM DUAL
) s ON (t."CHAIN_CODE" = s.CHAIN_CODE)
WHEN NOT MATCHED THEN INSERT ("CHAIN_CODE","CHAIN_NAME","CHAIN_TYPE","DATA_DOMAIN","DESCRIPTION")
    VALUES (s.CHAIN_CODE, '占位', 'CUSTOM', NULL, '');

UPDATE "TF_TR_CHAIN" SET
    "CHAIN_NAME"   = '数字化项目结算穿透溯源',
    "CHAIN_TYPE"   = 'FINANCIAL',
    "DATA_DOMAIN"  = '计划财务',
    "DESCRIPTION"  = '从财务结算出发, 向上穿透至项目立项概算, 横向穿透至采购合同合规性, 向下穿透至资产台账'
WHERE "CHAIN_CODE" = 'CHAIN_SETTLE_TRACE';

UPDATE "TF_TR_CHAIN" SET
    "CHAIN_NAME"   = '合同金额审计穿透链',
    "CHAIN_TYPE"   = 'FINANCIAL',
    "DATA_DOMAIN"  = '计划财务',
    "DESCRIPTION"  = '从合同金额出发, 穿透至项目预算/资产入账/指标核算, 验证财务一致性'
WHERE "CHAIN_CODE" = 'CHAIN_CONTRACT_AUDIT';

UPDATE "TF_TR_CHAIN" SET
    "CHAIN_NAME"   = '资产全生命周期溯源',
    "CHAIN_TYPE"   = 'PROCUREMENT',
    "DATA_DOMAIN"  = '计划财务',
    "DESCRIPTION"  = '从资产登记出发, 溯源至采购合同/项目立项/票据凭证, 覆盖采购到入账全过程'
WHERE "CHAIN_CODE" = 'CHAIN_ASSET_LIFECYCLE';

-- 链路节点请按 mysql-local/bootstrap.sql 第 484-530 行 INSERT 翻译,
-- 涉及 (SELECT id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1) 在
-- DM 中需替换为 (SELECT MIN("ID") FROM "TF_OM_EXTRACTED_OBJECT" WHERE "OBJECT_CODE"='OBJ_PROJECT'),
-- 上线前由 DBA 配合产品同学逐条核对.
