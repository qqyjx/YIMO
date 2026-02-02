-- ============================================================
-- 对象抽取与三层架构关联关系表
-- 用于存储从DATA表单中抽取的"对象"及其与三层架构的关联
-- ============================================================

-- 1. 抽取的对象表（高度抽象的核心对象）
CREATE TABLE IF NOT EXISTS extracted_objects (
    object_id INT AUTO_INCREMENT PRIMARY KEY,
    object_code VARCHAR(64) NOT NULL UNIQUE COMMENT '对象编码，如 OBJ_PROJECT, OBJ_DEVICE',
    object_name VARCHAR(256) NOT NULL COMMENT '对象名称，如 项目、设备',
    object_name_en VARCHAR(256) COMMENT '对象英文名称',
    parent_object_id INT DEFAULT NULL COMMENT '父对象ID，支持对象层次结构',
    object_type ENUM('CORE', 'DERIVED', 'AUXILIARY') DEFAULT 'CORE' COMMENT '对象类型：核心/派生/辅助',
    description TEXT COMMENT '对象描述',
    extraction_source VARCHAR(64) COMMENT '抽取来源：LLM/RULE/MANUAL',
    extraction_confidence DECIMAL(5,4) DEFAULT 0.0 COMMENT '抽取置信度 0-1',
    llm_reasoning TEXT COMMENT '大模型抽取时的推理过程',
    is_verified BOOLEAN DEFAULT FALSE COMMENT '是否经过人工验证',
    verified_by VARCHAR(128) COMMENT '验证人',
    verified_at TIMESTAMP NULL COMMENT '验证时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_object_id) REFERENCES extracted_objects(object_id) ON DELETE SET NULL,
    INDEX idx_object_name (object_name),
    INDEX idx_object_type (object_type),
    INDEX idx_is_verified (is_verified)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='抽取的核心对象表';

-- 2. 对象同义词表（支持多种叫法）
CREATE TABLE IF NOT EXISTS object_synonyms (
    synonym_id INT AUTO_INCREMENT PRIMARY KEY,
    object_id INT NOT NULL,
    synonym VARCHAR(256) NOT NULL COMMENT '同义词/别名',
    source VARCHAR(64) COMMENT '来源：概念实体/逻辑实体/业务对象等',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (object_id) REFERENCES extracted_objects(object_id) ON DELETE CASCADE,
    INDEX idx_synonym (synonym),
    INDEX idx_object_id (object_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象同义词表';

-- 3. 对象属性定义表
CREATE TABLE IF NOT EXISTS object_attribute_definitions (
    attr_def_id INT AUTO_INCREMENT PRIMARY KEY,
    object_id INT NOT NULL,
    attr_name VARCHAR(256) NOT NULL COMMENT '属性名称',
    attr_code VARCHAR(128) COMMENT '属性编码',
    attr_type VARCHAR(64) COMMENT '属性类型：STRING/NUMBER/DATE/ENUM等',
    is_required BOOLEAN DEFAULT FALSE COMMENT '是否必填',
    is_key_attribute BOOLEAN DEFAULT FALSE COMMENT '是否关键属性',
    description TEXT COMMENT '属性描述',
    extracted_from VARCHAR(64) COMMENT '抽取来源层：CONCEPT/LOGICAL/PHYSICAL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (object_id) REFERENCES extracted_objects(object_id) ON DELETE CASCADE,
    INDEX idx_object_attr (object_id, attr_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象属性定义表';

-- ============================================================
-- 4. 对象与三层架构关联关系表（核心）
-- ============================================================
CREATE TABLE IF NOT EXISTS object_entity_relations (
    relation_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    object_id INT NOT NULL COMMENT '对象ID',
    entity_layer ENUM('CONCEPT', 'LOGICAL', 'PHYSICAL') NOT NULL COMMENT '实体层级',
    entity_name VARCHAR(512) NOT NULL COMMENT '实体名称',
    entity_code VARCHAR(256) COMMENT '实体编码',

    -- 关联强度和类型
    relation_type ENUM('DIRECT', 'INDIRECT', 'DERIVED', 'CLUSTER') DEFAULT 'DIRECT' COMMENT '关联类型：直接/间接/派生/聚类',
    relation_strength DECIMAL(5,4) DEFAULT 0.0 COMMENT '关联强度 0-1',

    -- 关联来源
    match_method ENUM('EXACT', 'CONTAINS', 'SEMANTIC', 'LLM', 'SEMANTIC_CLUSTER') DEFAULT 'EXACT' COMMENT '匹配方法：精确/包含/语义/LLM/语义聚类',
    semantic_similarity DECIMAL(5,4) COMMENT '语义相似度（SBERT计算）',

    -- 元数据（来自原始Excel）
    data_domain VARCHAR(128) COMMENT '数据域',
    data_subdomain VARCHAR(128) COMMENT '数据子域',
    source_file VARCHAR(256) COMMENT '来源文件',
    source_sheet VARCHAR(256) COMMENT '来源工作表',
    source_row INT COMMENT '来源行号',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (object_id) REFERENCES extracted_objects(object_id) ON DELETE CASCADE,
    INDEX idx_object_layer (object_id, entity_layer),
    INDEX idx_entity_name (entity_name(255)),
    INDEX idx_entity_layer (entity_layer),
    INDEX idx_relation_strength (relation_strength),
    INDEX idx_data_domain (data_domain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象与三层架构实体关联关系表';

-- 5. 对象关联统计视图
CREATE OR REPLACE VIEW v_object_relation_stats AS
SELECT
    o.object_id,
    o.object_code,
    o.object_name,
    o.object_type,
    COUNT(DISTINCT CASE WHEN r.entity_layer = 'CONCEPT' THEN r.entity_name END) AS concept_entity_count,
    COUNT(DISTINCT CASE WHEN r.entity_layer = 'LOGICAL' THEN r.entity_name END) AS logical_entity_count,
    COUNT(DISTINCT CASE WHEN r.entity_layer = 'PHYSICAL' THEN r.entity_name END) AS physical_entity_count,
    COUNT(DISTINCT r.entity_name) AS total_entity_count,
    AVG(r.relation_strength) AS avg_relation_strength,
    GROUP_CONCAT(DISTINCT r.data_domain) AS related_domains
FROM extracted_objects o
LEFT JOIN object_entity_relations r ON o.object_id = r.object_id
GROUP BY o.object_id, o.object_code, o.object_name, o.object_type;

-- 6. 对象抽取批次记录表
CREATE TABLE IF NOT EXISTS object_extraction_batches (
    batch_id INT AUTO_INCREMENT PRIMARY KEY,
    batch_code VARCHAR(64) NOT NULL UNIQUE COMMENT '批次编码',
    extraction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_files JSON COMMENT '输入文件列表',
    llm_model VARCHAR(128) COMMENT '使用的大模型',
    llm_prompt TEXT COMMENT '使用的提示词',
    total_objects_extracted INT DEFAULT 0 COMMENT '抽取对象数量',
    total_relations_created INT DEFAULT 0 COMMENT '创建关联数量',
    status ENUM('RUNNING', 'COMPLETED', 'FAILED') DEFAULT 'RUNNING',
    error_message TEXT,
    created_by VARCHAR(128),
    INDEX idx_batch_code (batch_code),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象抽取批次记录表';

-- 7. 对象与批次关联表
CREATE TABLE IF NOT EXISTS object_batch_mapping (
    mapping_id INT AUTO_INCREMENT PRIMARY KEY,
    object_id INT NOT NULL,
    batch_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (object_id) REFERENCES extracted_objects(object_id) ON DELETE CASCADE,
    FOREIGN KEY (batch_id) REFERENCES object_extraction_batches(batch_id) ON DELETE CASCADE,
    UNIQUE KEY uk_object_batch (object_id, batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象与抽取批次关联表';

-- ============================================================
-- 初始化核心对象（预置常见对象，可由大模型扩展）
-- ============================================================
INSERT INTO extracted_objects (object_code, object_name, object_name_en, object_type, description, extraction_source, extraction_confidence, is_verified) VALUES
('OBJ_PROJECT', '项目', 'Project', 'CORE', '电网建设项目，包括输变电工程项目、配网工程项目等', 'MANUAL', 1.0, TRUE),
('OBJ_DEVICE', '设备', 'Device', 'CORE', '电网设备，包括变压器、断路器、线路等各类电气设备', 'MANUAL', 1.0, TRUE),
('OBJ_ASSET', '资产', 'Asset', 'CORE', '固定资产，包括设备资产、房屋资产等', 'MANUAL', 1.0, TRUE),
('OBJ_CONTRACT', '合同', 'Contract', 'CORE', '各类业务合同，包括工程合同、采购合同等', 'MANUAL', 1.0, TRUE),
('OBJ_PERSONNEL', '人员', 'Personnel', 'CORE', '相关人员，包括项目人员、运维人员等', 'MANUAL', 1.0, TRUE),
('OBJ_ORGANIZATION', '组织', 'Organization', 'CORE', '组织机构，包括部门、单位、项目部等', 'MANUAL', 1.0, TRUE),
('OBJ_DOCUMENT', '文档', 'Document', 'AUXILIARY', '各类业务文档，包括设计文档、验收文档等', 'MANUAL', 1.0, TRUE),
('OBJ_PROCESS', '流程', 'Process', 'AUXILIARY', '业务流程，包括审批流程、验收流程等', 'MANUAL', 1.0, TRUE)
ON DUPLICATE KEY UPDATE object_name = VALUES(object_name);
