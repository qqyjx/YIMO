-- 将 raw_text 正规化为 canonical_text 的示例视图
-- 假设 EAV 前缀为 `eav`，如不同请替换

CREATE OR REPLACE VIEW v_eav_attr_normalized AS
SELECT
    e.id              AS entity_id,
    e.dataset_id      AS dataset_id,
    a.id              AS attribute_id,
    a.name            AS attribute_name,
    v.raw_text        AS raw_text,
    COALESCE(c.canonical_text, v.raw_text) AS normalized_text
FROM eav_values v
JOIN eav_entities e   ON e.id = v.entity_id
JOIN eav_attributes a ON a.id = v.attribute_id
LEFT JOIN eav_semantic_mapping m
    ON m.dataset_id = e.dataset_id
      AND m.attribute_id = v.attribute_id
      AND m.from_text COLLATE utf8mb4_unicode_ci = v.raw_text COLLATE utf8mb4_unicode_ci
LEFT JOIN eav_semantic_canon c
       ON c.id = m.canonical_id;
