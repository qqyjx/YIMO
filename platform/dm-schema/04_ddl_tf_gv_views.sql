-- ============================================================================
-- 04 - GV (Governance) 治理视图
-- ============================================================================
-- 给 governance dashboard 提供即时聚合, 替代每次扫表.
-- 达梦 8.x 视图语法兼容 ANSI SQL, 与 MySQL 等价.
-- ============================================================================

-- 三层完整性 (每对象一行, 标识哪些层有/缺)
CREATE OR REPLACE VIEW "V_TF_GV_COMPLETENESS" AS
SELECT
    o."ID"            AS "OBJECT_ID",
    o."OBJECT_CODE"   AS "OBJECT_CODE",
    o."OBJECT_NAME"   AS "OBJECT_NAME",
    o."DATA_DOMAIN"   AS "DATA_DOMAIN",
    SUM(CASE WHEN r."ENTITY_LAYER" = 'CONCEPT'  THEN 1 ELSE 0 END) AS "CONCEPT_COUNT",
    SUM(CASE WHEN r."ENTITY_LAYER" = 'LOGICAL'  THEN 1 ELSE 0 END) AS "LOGICAL_COUNT",
    SUM(CASE WHEN r."ENTITY_LAYER" = 'PHYSICAL' THEN 1 ELSE 0 END) AS "PHYSICAL_COUNT",
    CASE
        WHEN SUM(CASE WHEN r."ENTITY_LAYER" = 'CONCEPT'  THEN 1 ELSE 0 END) > 0
         AND SUM(CASE WHEN r."ENTITY_LAYER" = 'LOGICAL'  THEN 1 ELSE 0 END) > 0
         AND SUM(CASE WHEN r."ENTITY_LAYER" = 'PHYSICAL' THEN 1 ELSE 0 END) > 0
        THEN 'COMPLETE' ELSE 'INCOMPLETE'
    END AS "COMPLETENESS_STATUS",
    AVG(r."RELATION_STRENGTH") AS "AVG_RELATION_STRENGTH"
FROM "TF_OM_EXTRACTED_OBJECT" o
LEFT JOIN "TF_OM_ENTITY_RELATION" r ON r."OBJECT_ID" = o."ID"
GROUP BY o."ID", o."OBJECT_CODE", o."OBJECT_NAME", o."DATA_DOMAIN";

COMMENT ON TABLE "V_TF_GV_COMPLETENESS" IS '治理视图: 每对象三层完整性 + 平均关联强度';


-- 缺陷识别 (筛出 "缺层" / "弱关联" / "无样例" 的对象)
CREATE OR REPLACE VIEW "V_TF_GV_DEFECTS" AS
SELECT
    o."ID"            AS "OBJECT_ID",
    o."OBJECT_CODE"   AS "OBJECT_CODE",
    o."OBJECT_NAME"   AS "OBJECT_NAME",
    o."DATA_DOMAIN"   AS "DATA_DOMAIN",
    CASE
        WHEN NOT EXISTS (
            SELECT 1 FROM "TF_OM_ENTITY_RELATION" r
            WHERE r."OBJECT_ID" = o."ID" AND r."ENTITY_LAYER" = 'CONCEPT'
        ) THEN 'MISSING_CONCEPT'
        WHEN NOT EXISTS (
            SELECT 1 FROM "TF_OM_ENTITY_RELATION" r
            WHERE r."OBJECT_ID" = o."ID" AND r."ENTITY_LAYER" = 'LOGICAL'
        ) THEN 'MISSING_LOGICAL'
        WHEN NOT EXISTS (
            SELECT 1 FROM "TF_OM_ENTITY_RELATION" r
            WHERE r."OBJECT_ID" = o."ID" AND r."ENTITY_LAYER" = 'PHYSICAL'
        ) THEN 'MISSING_PHYSICAL'
        WHEN (
            SELECT AVG(r2."RELATION_STRENGTH")
            FROM "TF_OM_ENTITY_RELATION" r2
            WHERE r2."OBJECT_ID" = o."ID"
        ) < 0.6 THEN 'WEAK_RELATION'
        ELSE 'OK'
    END AS "DEFECT_TYPE",
    o."CLUSTER_SIZE",
    (SELECT COUNT(*) FROM "TF_OM_ENTITY_RELATION" r WHERE r."OBJECT_ID" = o."ID") AS "RELATION_COUNT"
FROM "TF_OM_EXTRACTED_OBJECT" o;

COMMENT ON TABLE "V_TF_GV_DEFECTS" IS '治理视图: 对象缺陷识别 (缺层/弱关联/数据稀疏)';
