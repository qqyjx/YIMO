-- ============================================================================
-- YIMO 对象抽取与三层架构关联 - 数据库初始化脚本
-- Object Extraction & Three-Tier Architecture Association
-- ============================================================================
-- 以 root 身份在系统 MySQL 或用户态 mysqld 中执行本脚本以创建数据库与账号

-- 数据库
CREATE DATABASE IF NOT EXISTS `eav_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建应用用户（仅本地）
CREATE USER IF NOT EXISTS 'eav_user'@'localhost' IDENTIFIED BY 'eavpass123';
GRANT ALL PRIVILEGES ON `eav_db`.* TO 'eav_user'@'localhost';

-- 为 TCP 访问(127.0.0.1) 同步创建与授权（Navicat/脚本默认用 127.0.0.1 走 TCP）
CREATE USER IF NOT EXISTS 'eav_user'@'127.0.0.1' IDENTIFIED BY 'eavpass123';
GRANT ALL PRIVILEGES ON `eav_db`.* TO 'eav_user'@'127.0.0.1';
FLUSH PRIVILEGES;

USE `eav_db`;

-- ============================================================================
-- EAV 核心表 - 数据导入基础
-- ============================================================================

-- EAV数据集表
CREATE TABLE IF NOT EXISTS `eav_datasets` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(256) NOT NULL COMMENT '数据集名称',
    `source_file` VARCHAR(512) COMMENT '来源文件路径',
    `source_type` VARCHAR(64) DEFAULT 'excel' COMMENT '来源类型(excel/csv/api)',
    `description` TEXT COMMENT '数据集描述',
    `row_count` INT DEFAULT 0 COMMENT '数据行数',
    `imported_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- EAV实体表
CREATE TABLE IF NOT EXISTS `eav_entities` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `dataset_id` BIGINT NOT NULL COMMENT '所属数据集ID',
    `row_index` INT NOT NULL COMMENT '原始行号',
    `entity_label` VARCHAR(512) COMMENT '实体标签(可选)',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_dataset` (`dataset_id`),
    KEY `idx_row` (`row_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- EAV属性定义表
CREATE TABLE IF NOT EXISTS `eav_attributes` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `dataset_id` BIGINT NOT NULL COMMENT '所属数据集ID',
    `name` VARCHAR(256) NOT NULL COMMENT '属性名称',
    `data_type` VARCHAR(64) DEFAULT 'string' COMMENT '数据类型(string/number/datetime/bool)',
    `ord_index` INT NOT NULL DEFAULT 0 COMMENT '属性顺序',
    `is_nullable` TINYINT(1) DEFAULT 1 COMMENT '是否可空',
    `description` TEXT COMMENT '属性描述',
    UNIQUE KEY `uniq_ds_name` (`dataset_id`, `name`),
    KEY `idx_dataset` (`dataset_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- EAV值表
CREATE TABLE IF NOT EXISTS `eav_values` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `entity_id` BIGINT NOT NULL COMMENT '实体ID',
    `attribute_id` BIGINT NOT NULL COMMENT '属性ID',
    `value_text` TEXT COMMENT '文本值',
    `value_number` DECIMAL(20,6) COMMENT '数值',
    `value_datetime` DATETIME(6) COMMENT '日期时间值',
    `value_bool` TINYINT(1) COMMENT '布尔值',
    KEY `idx_entity` (`entity_id`),
    KEY `idx_attr` (`attribute_id`),
    FULLTEXT KEY `ft_value_text` (`value_text`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 语义相似度匹配相关表
-- ============================================================================

-- 语义规范值表（SBERT语义聚类后的规范值）
CREATE TABLE IF NOT EXISTS `eav_semantic_canon` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `canon_text` VARCHAR(512) NOT NULL COMMENT '规范化文本',
    `cluster_id` INT COMMENT '聚类ID',
    `member_count` INT DEFAULT 1 COMMENT '聚类成员数量',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_canon` (`canon_text`(255)),
    KEY `idx_cluster` (`cluster_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 语义映射表（原始值到规范值的映射）
CREATE TABLE IF NOT EXISTS `eav_semantic_mapping` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `original_text` VARCHAR(512) NOT NULL COMMENT '原始文本',
    `canon_id` BIGINT NOT NULL COMMENT '规范值ID',
    `similarity_score` DECIMAL(5,4) COMMENT '相似度分数',
    `match_method` VARCHAR(64) DEFAULT 'sbert' COMMENT '匹配方法',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_original` (`original_text`(255)),
    KEY `idx_canon` (`canon_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 语义指纹表 - 存储实体的语义向量
CREATE TABLE IF NOT EXISTS `semantic_fingerprints` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `entity_id` BIGINT NOT NULL UNIQUE COMMENT 'EAV实体ID',
    `fingerprint_version` VARCHAR(32) DEFAULT 'v1' COMMENT '指纹算法版本',
    `embedding_model` VARCHAR(128) COMMENT '使用的向量模型',
    `embedding_dim` INT COMMENT '向量维度',
    `embedding_blob` LONGBLOB COMMENT '向量二进制存储',
    `text_summary` TEXT COMMENT '实体文本摘要(用于生成向量)',
    `key_attributes` JSON COMMENT '关键属性摘要',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_version` (`fingerprint_version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 对象抽取与三层架构关联表
-- ============================================================================

-- 1. 抽取的对象表（高度抽象的核心对象）
CREATE TABLE IF NOT EXISTS `extracted_objects` (
    `object_id` INT AUTO_INCREMENT PRIMARY KEY,
    `object_code` VARCHAR(64) NOT NULL COMMENT '对象编码，如 OBJ_PROJECT, OBJ_DEVICE',
    `object_name` VARCHAR(256) NOT NULL COMMENT '对象名称，如 项目、设备',
    `object_name_en` VARCHAR(256) COMMENT '对象英文名称',
    `parent_object_id` INT DEFAULT NULL COMMENT '父对象ID，支持对象层次结构',
    `object_type` ENUM('CORE', 'DERIVED', 'AUXILIARY') DEFAULT 'CORE' COMMENT '对象类型：核心/派生/辅助',
    `data_domain` VARCHAR(128) DEFAULT 'default' COMMENT '数据域编码，如 shupeidian（输配电）, jicai（计划财务）',
    `description` TEXT COMMENT '对象描述',
    `extraction_source` VARCHAR(64) COMMENT '抽取来源：SEMANTIC_CLUSTER_LLM/SEMANTIC_CLUSTER_RULE/MANUAL',
    `extraction_confidence` DECIMAL(5,4) DEFAULT 0.0 COMMENT '抽取置信度 0-1',
    `llm_reasoning` TEXT COMMENT '大模型抽取时的推理过程',
    `is_verified` BOOLEAN DEFAULT FALSE COMMENT '是否经过人工验证',
    `verified_by` VARCHAR(128) COMMENT '验证人',
    `verified_at` TIMESTAMP NULL COMMENT '验证时间',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`parent_object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE SET NULL,
    UNIQUE KEY `uk_code_domain` (`object_code`, `data_domain`),
    INDEX `idx_object_name` (`object_name`),
    INDEX `idx_object_type` (`object_type`),
    INDEX `idx_data_domain` (`data_domain`),
    INDEX `idx_is_verified` (`is_verified`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='抽取的核心对象表';

-- 2. 对象同义词表（支持多种叫法）
CREATE TABLE IF NOT EXISTS `object_synonyms` (
    `synonym_id` INT AUTO_INCREMENT PRIMARY KEY,
    `object_id` INT NOT NULL,
    `synonym` VARCHAR(256) NOT NULL COMMENT '同义词/别名',
    `source` VARCHAR(64) COMMENT '来源：概念实体/逻辑实体/业务对象等',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE CASCADE,
    INDEX `idx_synonym` (`synonym`),
    INDEX `idx_object_id` (`object_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象同义词表';

-- 3. 对象属性定义表
CREATE TABLE IF NOT EXISTS `object_attribute_definitions` (
    `attr_def_id` INT AUTO_INCREMENT PRIMARY KEY,
    `object_id` INT NOT NULL,
    `attr_name` VARCHAR(256) NOT NULL COMMENT '属性名称',
    `attr_code` VARCHAR(128) COMMENT '属性编码',
    `attr_type` VARCHAR(64) COMMENT '属性类型：STRING/NUMBER/DATE/ENUM等',
    `is_required` BOOLEAN DEFAULT FALSE COMMENT '是否必填',
    `is_key_attribute` BOOLEAN DEFAULT FALSE COMMENT '是否关键属性',
    `description` TEXT COMMENT '属性描述',
    `extracted_from` VARCHAR(64) COMMENT '抽取来源层：CONCEPT/LOGICAL/PHYSICAL',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE CASCADE,
    INDEX `idx_object_attr` (`object_id`, `attr_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象属性定义表';

-- ============================================================================
-- 4. 对象与三层架构关联关系表（核心）
-- 表示对象与概念实体、逻辑实体、物理实体的关联关系
-- ============================================================================
CREATE TABLE IF NOT EXISTS `object_entity_relations` (
    `relation_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `object_id` INT NOT NULL COMMENT '对象ID',
    `entity_layer` ENUM('CONCEPT', 'LOGICAL', 'PHYSICAL') NOT NULL COMMENT '实体层级：概念/逻辑/物理',
    `entity_name` VARCHAR(512) NOT NULL COMMENT '实体名称',
    `entity_code` VARCHAR(256) COMMENT '实体编码',

    -- 关联强度和类型
    `relation_type` ENUM('DIRECT', 'INDIRECT', 'DERIVED', 'CLUSTER') DEFAULT 'CLUSTER' COMMENT '关联类型：直接/间接/派生/聚类',
    `relation_strength` DECIMAL(5,4) DEFAULT 0.0 COMMENT '关联强度 0-1',

    -- 关联来源
    `match_method` ENUM('EXACT', 'CONTAINS', 'SEMANTIC', 'LLM', 'SEMANTIC_CLUSTER') DEFAULT 'SEMANTIC_CLUSTER' COMMENT '匹配方法',
    `semantic_similarity` DECIMAL(5,4) COMMENT '语义相似度（SBERT计算）',

    -- 层级关联路径
    `via_concept_entity` VARCHAR(512) DEFAULT NULL COMMENT '间接关联时的中间概念实体名称（逻辑实体通过哪个概念实体关联）',

    -- 元数据（来自原始Excel）
    `data_domain` VARCHAR(128) COMMENT '数据域',
    `data_subdomain` VARCHAR(128) COMMENT '数据子域',
    `source_file` VARCHAR(256) COMMENT '来源文件',
    `source_sheet` VARCHAR(256) COMMENT '来源工作表',
    `source_row` INT COMMENT '来源行号',

    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE CASCADE,
    INDEX `idx_object_layer` (`object_id`, `entity_layer`),
    INDEX `idx_entity_name` (`entity_name`(255)),
    INDEX `idx_entity_layer` (`entity_layer`),
    INDEX `idx_relation_strength` (`relation_strength`),
    INDEX `idx_data_domain` (`data_domain`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象与三层架构实体关联关系表';

-- 5. 对象关联统计视图（全局）
CREATE OR REPLACE VIEW `v_object_relation_stats` AS
SELECT
    o.`object_id`,
    o.`object_code`,
    o.`object_name`,
    o.`object_type`,
    o.`data_domain`,
    COUNT(DISTINCT CASE WHEN r.`entity_layer` = 'CONCEPT' THEN r.`entity_name` END) AS `concept_entity_count`,
    COUNT(DISTINCT CASE WHEN r.`entity_layer` = 'LOGICAL' THEN r.`entity_name` END) AS `logical_entity_count`,
    COUNT(DISTINCT CASE WHEN r.`entity_layer` = 'PHYSICAL' THEN r.`entity_name` END) AS `physical_entity_count`,
    COUNT(DISTINCT r.`entity_name`) AS `total_entity_count`,
    AVG(r.`relation_strength`) AS `avg_relation_strength`,
    GROUP_CONCAT(DISTINCT r.`data_domain`) AS `related_domains`
FROM `extracted_objects` o
LEFT JOIN `object_entity_relations` r ON o.`object_id` = r.`object_id`
GROUP BY o.`object_id`, o.`object_code`, o.`object_name`, o.`object_type`, o.`data_domain`;

-- 5.1 按数据域统计视图
CREATE OR REPLACE VIEW `v_domain_stats` AS
SELECT
    COALESCE(o.`data_domain`, 'default') AS `data_domain`,
    COUNT(DISTINCT o.`object_id`) AS `object_count`,
    COUNT(DISTINCT r.`relation_id`) AS `relation_count`,
    COUNT(DISTINCT CASE WHEN r.`entity_layer` = 'CONCEPT' THEN r.`entity_name` END) AS `concept_entity_count`,
    COUNT(DISTINCT CASE WHEN r.`entity_layer` = 'LOGICAL' THEN r.`entity_name` END) AS `logical_entity_count`,
    COUNT(DISTINCT CASE WHEN r.`entity_layer` = 'PHYSICAL' THEN r.`entity_name` END) AS `physical_entity_count`,
    AVG(r.`relation_strength`) AS `avg_relation_strength`
FROM `extracted_objects` o
LEFT JOIN `object_entity_relations` r ON o.`object_id` = r.`object_id`
GROUP BY o.`data_domain`;

-- 5.2 对象与BA-04业务对象匹配映射表
CREATE TABLE IF NOT EXISTS `object_business_object_mapping` (
    `mapping_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `object_id` INT NOT NULL COMMENT '抽取对象ID',
    `object_code` VARCHAR(64) NOT NULL COMMENT '抽取对象编码',
    `business_object_name` VARCHAR(512) NOT NULL COMMENT 'BA-04业务对象名称',
    `match_method` VARCHAR(64) DEFAULT 'CLUSTER_ENTITY' COMMENT '匹配方法',
    `match_score` DECIMAL(5,4) DEFAULT 0 COMMENT '匹配分数',
    `data_domain` VARCHAR(128) COMMENT '数据域编码',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE CASCADE,
    INDEX `idx_object_id` (`object_id`),
    INDEX `idx_object_code` (`object_code`),
    INDEX `idx_biz_obj_name` (`business_object_name`(255)),
    INDEX `idx_data_domain` (`data_domain`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='抽取对象与BA-04业务对象匹配映射表';

-- 6. 对象抽取批次记录表
CREATE TABLE IF NOT EXISTS `object_extraction_batches` (
    `batch_id` INT AUTO_INCREMENT PRIMARY KEY,
    `batch_code` VARCHAR(64) NOT NULL UNIQUE COMMENT '批次编码',
    `data_domain` VARCHAR(128) NOT NULL DEFAULT 'default' COMMENT '数据域编码',
    `data_domain_name` VARCHAR(256) COMMENT '数据域名称',
    `extraction_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `source_files` JSON COMMENT '输入文件列表',
    `llm_model` VARCHAR(128) COMMENT '使用的大模型',
    `llm_prompt` TEXT COMMENT '使用的提示词',
    `total_objects_extracted` INT DEFAULT 0 COMMENT '抽取对象数量',
    `total_relations_created` INT DEFAULT 0 COMMENT '创建关联数量',
    `status` ENUM('RUNNING', 'COMPLETED', 'FAILED') DEFAULT 'RUNNING',
    `error_message` TEXT,
    `created_by` VARCHAR(128),
    INDEX `idx_batch_code` (`batch_code`),
    INDEX `idx_data_domain` (`data_domain`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象抽取批次记录表';

-- 7. 对象与批次关联表
CREATE TABLE IF NOT EXISTS `object_batch_mapping` (
    `mapping_id` INT AUTO_INCREMENT PRIMARY KEY,
    `object_id` INT NOT NULL,
    `batch_id` INT NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE CASCADE,
    FOREIGN KEY (`batch_id`) REFERENCES `object_extraction_batches`(`batch_id`) ON DELETE CASCADE,
    UNIQUE KEY `uk_object_batch` (`object_id`, `batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象与抽取批次关联表';

-- ============================================================================
-- 数据库升级脚本（支持现有数据库添加 data_domain 字段）
-- ============================================================================
-- 为 extracted_objects 表添加 data_domain 字段（如果不存在）
SET @col_exists = (SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_schema = 'eav_db'
                   AND table_name = 'extracted_objects'
                   AND column_name = 'data_domain');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE extracted_objects ADD COLUMN data_domain VARCHAR(128) DEFAULT ''default'' COMMENT ''数据域编码'' AFTER object_type, ADD INDEX idx_data_domain (data_domain)',
    'SELECT ''Column data_domain already exists''');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 为 object_extraction_batches 表添加 data_domain 字段（如果不存在）
SET @col_exists = (SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_schema = 'eav_db'
                   AND table_name = 'object_extraction_batches'
                   AND column_name = 'data_domain');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE object_extraction_batches ADD COLUMN data_domain VARCHAR(128) DEFAULT ''default'' COMMENT ''数据域编码'' AFTER batch_code, ADD COLUMN data_domain_name VARCHAR(256) COMMENT ''数据域名称'' AFTER data_domain, ADD INDEX idx_data_domain (data_domain)',
    'SELECT ''Column data_domain already exists in batches''');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 为 object_entity_relations 表添加 via_concept_entity 字段（如果不存在）
SET @col_exists = (SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_schema = 'eav_db'
                   AND table_name = 'object_entity_relations'
                   AND column_name = 'via_concept_entity');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE object_entity_relations ADD COLUMN via_concept_entity VARCHAR(512) DEFAULT NULL COMMENT ''间接关联时的中间概念实体名称'' AFTER semantic_similarity',
    'SELECT ''Column via_concept_entity already exists''');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================================
-- 初始化核心对象（预置常见对象，可由大模型扩展）
-- 注意：这些是默认域的对象，各域可以有自己的对象实例
-- ============================================================================
INSERT INTO `extracted_objects` (`object_code`, `object_name`, `object_name_en`, `object_type`, `data_domain`, `description`, `extraction_source`, `extraction_confidence`, `is_verified`) VALUES
('OBJ_PROJECT', '项目', 'Project', 'CORE', 'default', '电网建设项目，包括输变电工程项目、配网工程项目等', 'MANUAL', 1.0, TRUE),
('OBJ_DEVICE', '设备', 'Device', 'CORE', 'default', '电网设备，包括变压器、断路器、线路等各类电气设备', 'MANUAL', 1.0, TRUE),
('OBJ_ASSET', '资产', 'Asset', 'CORE', 'default', '固定资产，包括设备资产、房屋资产等', 'MANUAL', 1.0, TRUE),
('OBJ_CONTRACT', '合同', 'Contract', 'CORE', 'default', '各类业务合同，包括工程合同、采购合同等', 'MANUAL', 1.0, TRUE),
('OBJ_PERSONNEL', '人员', 'Personnel', 'CORE', 'default', '相关人员，包括项目人员、运维人员等', 'MANUAL', 1.0, TRUE),
('OBJ_ORGANIZATION', '组织', 'Organization', 'CORE', 'default', '组织机构，包括部门、单位、项目部等', 'MANUAL', 1.0, TRUE),
('OBJ_DOCUMENT', '文档', 'Document', 'AUXILIARY', 'default', '各类业务文档，包括设计文档、验收文档等', 'MANUAL', 1.0, TRUE),
('OBJ_PROCESS', '流程', 'Process', 'AUXILIARY', 'default', '业务流程，包括审批流程、验收流程等', 'MANUAL', 1.0, TRUE)
ON DUPLICATE KEY UPDATE `object_name` = VALUES(`object_name`);

-- ============================================================================
-- 对象生命周期历史表（全生命周期管理）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `object_lifecycle_history` (
    `history_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `object_id` INT NOT NULL COMMENT '对象ID',
    `lifecycle_stage` ENUM('Planning','Design','Construction','Operation','Finance') NOT NULL COMMENT '生命周期阶段',
    `stage_entered_at` DATETIME(6) COMMENT '进入该阶段时间',
    `stage_exited_at` DATETIME(6) COMMENT '离开该阶段时间',
    `attributes_snapshot` JSON COMMENT '该阶段的对象属性快照',
    `data_domain` VARCHAR(128) COMMENT '数据域',
    `source_system` VARCHAR(256) COMMENT '来源系统(SAP/ERP等)',
    `notes` TEXT COMMENT '备注',
    `created_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE CASCADE,
    KEY `idx_object_stage` (`object_id`, `lifecycle_stage`),
    KEY `idx_stage_time` (`lifecycle_stage`, `stage_entered_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象生命周期历史表';

-- ============================================================================
-- 穿透式溯源链路表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `traceability_chains` (
    `chain_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `chain_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '链路编码',
    `chain_name` VARCHAR(256) COMMENT '链路名称',
    `chain_type` ENUM('FINANCIAL','PROCUREMENT','CONSTRUCTION','CUSTOM') DEFAULT 'CUSTOM' COMMENT '链路类型',
    `data_domain` VARCHAR(128) COMMENT '数据域',
    `description` TEXT COMMENT '描述',
    `created_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='穿透式溯源链路表';

CREATE TABLE IF NOT EXISTS `traceability_chain_nodes` (
    `node_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `chain_id` BIGINT NOT NULL COMMENT '链路ID',
    `node_order` INT NOT NULL COMMENT '节点顺序',
    `object_id` INT COMMENT '关联对象ID',
    `entity_layer` ENUM('CONCEPT','LOGICAL','PHYSICAL') COMMENT '实体层级',
    `entity_name` VARCHAR(512) COMMENT '实体名称',
    `node_label` VARCHAR(256) COMMENT '节点显示名称',
    `node_type` ENUM('SOURCE','INTERMEDIATE','TARGET') DEFAULT 'INTERMEDIATE' COMMENT '节点类型',
    `source_file` VARCHAR(256) COMMENT '来源文件',
    `source_sheet` VARCHAR(256) COMMENT '来源工作表',
    `metadata` JSON COMMENT '扩展元数据',
    FOREIGN KEY (`chain_id`) REFERENCES `traceability_chains`(`chain_id`) ON DELETE CASCADE,
    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE SET NULL,
    KEY `idx_chain_order` (`chain_id`, `node_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='溯源链路节点表';

-- ============================================================================
-- 机理函数表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `mechanism_functions` (
    `func_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `func_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '函数编码',
    `func_name` VARCHAR(256) NOT NULL COMMENT '函数名称',
    `func_type` ENUM('FORMULA','RULE','THRESHOLD','VALIDATION') NOT NULL COMMENT '函数类型',
    `category` ENUM('FINANCIAL','PHYSICAL','BUSINESS','QUALITY') DEFAULT 'BUSINESS' COMMENT '函数类别',
    `expression` JSON NOT NULL COMMENT '函数表达式(JSON格式)',
    `description` TEXT COMMENT '描述',
    `source_object_code` VARCHAR(128) COMMENT '触发对象编码',
    `target_object_code` VARCHAR(128) COMMENT '作用对象编码',
    `severity` ENUM('INFO','WARNING','CRITICAL') DEFAULT 'WARNING' COMMENT '严重级别',
    `is_active` BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    `data_domain` VARCHAR(128) COMMENT '数据域',
    `created_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_source_obj` (`source_object_code`),
    KEY `idx_type_active` (`func_type`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='机理函数定义表';

-- ============================================================================
-- 预警记录表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `alert_records` (
    `alert_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `func_id` BIGINT NOT NULL COMMENT '触发的机理函数',
    `alert_level` ENUM('INFO','WARNING','CRITICAL') NOT NULL COMMENT '预警级别',
    `alert_title` VARCHAR(256) COMMENT '预警标题',
    `alert_detail` TEXT COMMENT '预警详情',
    `related_object_id` INT COMMENT '关联对象ID',
    `related_entity_name` VARCHAR(512) COMMENT '关联实体名称',
    `trigger_value` TEXT COMMENT '触发时的实际值',
    `threshold_value` TEXT COMMENT '阈值',
    `is_resolved` BOOLEAN DEFAULT FALSE COMMENT '是否已处理',
    `resolved_by` VARCHAR(128) COMMENT '处理人',
    `resolved_at` TIMESTAMP(6) NULL COMMENT '处理时间',
    `created_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (`func_id`) REFERENCES `mechanism_functions`(`func_id`) ON DELETE CASCADE,
    KEY `idx_level_resolved` (`alert_level`, `is_resolved`),
    KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='预警记录表';

-- ============================================================================
-- 预置机理函数（来自0.md中的业务规则示例）
-- ============================================================================
INSERT INTO `mechanism_functions` (`func_code`, `func_name`, `func_type`, `category`, `expression`, `description`, `source_object_code`, `severity`, `is_active`) VALUES
('MF_CONTRACT_AUDIT', '合同金额审计红线', 'THRESHOLD', 'FINANCIAL',
 '{"field": "合同金额", "operator": ">", "value": 3000000, "unit": "元", "action": "ALERT", "message": "合同金额超过300万审计红线，需走A级审批路径"}',
 '当合同金额超过300万元时触发审计预警，要求走A级审批路径', 'OBJ_CONTRACT', 'CRITICAL', TRUE),
('MF_POWER_FORMULA', '功率计算公式', 'FORMULA', 'PHYSICAL',
 '{"expression": "功率 = 电压 * 电流", "variables": ["电压", "电流"], "result": "功率", "unit": "W"}',
 '基础物理公式：功率 = 电压 × 电流', 'OBJ_DEVICE', 'INFO', TRUE),
('MF_APPROVAL_RULE', '付款审批路径规则', 'RULE', 'BUSINESS',
 '{"condition": "合同金额 > 3000000", "then": "审批路径 = A级审批", "else": "审批路径 = B级审批", "description": "根据合同金额决定审批路径"}',
 '根据合同金额自动判定审批路径', 'OBJ_CONTRACT', 'WARNING', TRUE)
ON DUPLICATE KEY UPDATE `func_name` = VALUES(`func_name`);

-- ============================================================================
-- 预置溯源链路（计划财务域穿透式结算溯源演示）
-- ============================================================================
INSERT INTO `traceability_chains` (`chain_code`, `chain_name`, `chain_type`, `data_domain`, `description`) VALUES
('CHAIN_SETTLE_TRACE', '数字化项目结算穿透溯源', 'FINANCIAL', 'jicai',
 '从财务结算出发，向上穿透至项目立项概算，横向穿透至采购合同合规性，向下穿透至资产台账，实现全链路业务溯源'),
('CHAIN_CONTRACT_AUDIT', '合同金额审计穿透链', 'FINANCIAL', 'jicai',
 '从合同金额出发，穿透至项目预算、资产入账、指标核算，验证合同执行的财务一致性'),
('CHAIN_ASSET_LIFECYCLE', '资产全生命周期溯源', 'PROCUREMENT', 'jicai',
 '从资产登记出发，溯源至采购合同、项目立项、票据凭证，覆盖资产从采购到入账的全过程')
ON DUPLICATE KEY UPDATE `chain_name` = VALUES(`chain_name`);

-- 链路1节点：数字化项目结算穿透溯源
-- 项目(立项) → 合同(签订) → 资产(入账) → 指标(核算) → 票据(结算)
INSERT INTO `traceability_chain_nodes` (`chain_id`, `node_order`, `object_id`, `entity_layer`, `entity_name`, `node_label`, `node_type`, `source_file`, `source_sheet`) VALUES
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_SETTLE_TRACE'), 0,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'CONCEPT', '项目', '项目立项/概算', 'SOURCE', 'DATA/jicai/1.xlsx', 'DA-01'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_SETTLE_TRACE'), 1,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_CONTRACT' LIMIT 1),
 'CONCEPT', '合同', '合同签订/合规审查', 'INTERMEDIATE', 'DATA/jicai/1.xlsx', 'DA-01'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_SETTLE_TRACE'), 2,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_ASSET' LIMIT 1),
 'LOGICAL', '资产', '资产入账/台账登记', 'INTERMEDIATE', 'DATA/jicai/1.xlsx', 'DA-02'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_SETTLE_TRACE'), 3,
 NULL, 'LOGICAL', '指标', '指标核算/费用归集', 'INTERMEDIATE', 'DATA/jicai/1.xlsx', 'DA-02'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_SETTLE_TRACE'), 4,
 NULL, 'PHYSICAL', '票据', '结算票据/凭证核销', 'TARGET', 'DATA/jicai/1.xlsx', 'DA-03');

-- 链路2节点：合同金额审计穿透链
INSERT INTO `traceability_chain_nodes` (`chain_id`, `node_order`, `object_id`, `entity_layer`, `entity_name`, `node_label`, `node_type`, `source_file`, `source_sheet`) VALUES
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_CONTRACT_AUDIT'), 0,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_CONTRACT' LIMIT 1),
 'CONCEPT', '合同', '合同金额/条款', 'SOURCE', 'DATA/jicai/1.xlsx', 'DA-01'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_CONTRACT_AUDIT'), 1,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'CONCEPT', '项目', '项目预算/概算对比', 'INTERMEDIATE', 'DATA/jicai/1.xlsx', 'DA-01'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_CONTRACT_AUDIT'), 2,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_ASSET' LIMIT 1),
 'LOGICAL', '资产', '资产入账金额', 'INTERMEDIATE', 'DATA/jicai/1.xlsx', 'DA-02'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_CONTRACT_AUDIT'), 3,
 NULL, 'PHYSICAL', '指标', '财务指标核算结果', 'TARGET', 'DATA/jicai/1.xlsx', 'DA-03');

-- 链路3节点：资产全生命周期溯源
INSERT INTO `traceability_chain_nodes` (`chain_id`, `node_order`, `object_id`, `entity_layer`, `entity_name`, `node_label`, `node_type`, `source_file`, `source_sheet`) VALUES
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_ASSET_LIFECYCLE'), 0,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_ASSET' LIMIT 1),
 'CONCEPT', '资产', '资产登记/分类', 'SOURCE', 'DATA/jicai/1.xlsx', 'DA-01'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_ASSET_LIFECYCLE'), 1,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_CONTRACT' LIMIT 1),
 'CONCEPT', '合同', '采购合同关联', 'INTERMEDIATE', 'DATA/jicai/1.xlsx', 'DA-01'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_ASSET_LIFECYCLE'), 2,
 (SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'LOGICAL', '项目', '项目立项来源', 'INTERMEDIATE', 'DATA/jicai/1.xlsx', 'DA-02'),
((SELECT chain_id FROM traceability_chains WHERE chain_code='CHAIN_ASSET_LIFECYCLE'), 3,
 NULL, 'LOGICAL', '票据', '票据凭证核对', 'TARGET', 'DATA/jicai/1.xlsx', 'DA-02');

-- ============================================================================
-- 治理看板视图（财务数据一致性分析）
-- ============================================================================

-- 对象治理完整性视图：检查每个对象的三层关联完整性和属性覆盖
CREATE OR REPLACE VIEW `v_governance_completeness` AS
SELECT
    o.object_id,
    o.object_code,
    o.object_name,
    o.object_type,
    o.data_domain,
    COALESCE(rs.concept_count, 0) AS concept_count,
    COALESCE(rs.logical_count, 0) AS logical_count,
    COALESCE(rs.physical_count, 0) AS physical_count,
    COALESCE(rs.total_relations, 0) AS total_relations,
    CASE
        WHEN COALESCE(rs.concept_count,0) > 0 AND COALESCE(rs.logical_count,0) > 0 AND COALESCE(rs.physical_count,0) > 0 THEN 'COMPLETE'
        WHEN COALESCE(rs.total_relations,0) = 0 THEN 'EMPTY'
        ELSE 'PARTIAL'
    END AS completeness_status,
    (SELECT COUNT(*) FROM object_attribute_definitions ad WHERE ad.object_id = o.object_id) AS attr_defined_count,
    (SELECT COUNT(*) FROM object_lifecycle_history lh WHERE lh.object_id = o.object_id) AS lifecycle_record_count,
    (SELECT COUNT(DISTINCT c.chain_id) FROM traceability_chain_nodes cn
     JOIN traceability_chains c ON c.chain_id = cn.chain_id
     WHERE cn.object_id = o.object_id) AS traceability_chain_count
FROM extracted_objects o
LEFT JOIN v_object_relation_stats rs ON rs.object_id = o.object_id;

-- 治理缺陷视图：识别关联缺失、弱关联、孤立对象
CREATE OR REPLACE VIEW `v_governance_defects` AS
SELECT
    o.object_code,
    o.object_name,
    o.data_domain,
    'MISSING_LAYER' AS defect_type,
    CASE
        WHEN NOT EXISTS (SELECT 1 FROM object_entity_relations r WHERE r.object_id = o.object_id AND r.entity_layer = 'CONCEPT') THEN '缺少概念层关联'
        WHEN NOT EXISTS (SELECT 1 FROM object_entity_relations r WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL') THEN '缺少逻辑层关联'
        WHEN NOT EXISTS (SELECT 1 FROM object_entity_relations r WHERE r.object_id = o.object_id AND r.entity_layer = 'PHYSICAL') THEN '缺少物理层关联'
    END AS defect_detail,
    'WARNING' AS severity
FROM extracted_objects o
WHERE NOT EXISTS (SELECT 1 FROM object_entity_relations r WHERE r.object_id = o.object_id AND r.entity_layer = 'CONCEPT')
   OR NOT EXISTS (SELECT 1 FROM object_entity_relations r WHERE r.object_id = o.object_id AND r.entity_layer = 'LOGICAL')
   OR NOT EXISTS (SELECT 1 FROM object_entity_relations r WHERE r.object_id = o.object_id AND r.entity_layer = 'PHYSICAL')
UNION ALL
SELECT
    o.object_code,
    o.object_name,
    r.data_domain,
    'WEAK_RELATION' AS defect_type,
    CONCAT('弱关联: ', r.entity_name, ' (强度=', ROUND(r.relation_strength, 2), ')') AS defect_detail,
    'INFO' AS severity
FROM object_entity_relations r
JOIN extracted_objects o ON o.object_id = r.object_id
WHERE r.relation_strength < 0.5
UNION ALL
SELECT
    o.object_code,
    o.object_name,
    o.data_domain,
    'NO_ATTRIBUTES' AS defect_type,
    '对象未定义任何属性' AS defect_detail,
    'INFO' AS severity
FROM extracted_objects o
WHERE NOT EXISTS (SELECT 1 FROM object_attribute_definitions ad WHERE ad.object_id = o.object_id);

-- ============================================================================
-- 对象去重决策记录表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `object_dedup_decisions` (
    `decision_id` INT AUTO_INCREMENT PRIMARY KEY,
    `source_object_code` VARCHAR(64) NOT NULL COMMENT '被合并/关联的源对象',
    `source_domain` VARCHAR(128) COMMENT '源对象数据域',
    `target_object_code` VARCHAR(64) NOT NULL COMMENT '目标对象',
    `target_domain` VARCHAR(128) COMMENT '目标对象数据域',
    `decision` ENUM('MERGED', 'LINKED', 'IGNORED') NOT NULL COMMENT '决策类型',
    `similarity_score` DECIMAL(5,4) COMMENT '相似度分数',
    `decided_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_dedup_source` (`source_object_code`, `source_domain`),
    INDEX `idx_dedup_target` (`target_object_code`, `target_domain`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对象去重决策记录';

-- ============================================================================
-- 预置生命周期演示数据（全部16个对象，覆盖5阶段）
-- ============================================================================

-- === 计划财务域 (jicai) ===

-- OBJ_COST 费用: Planning → Finance (费用对象主要涉及规划和财务两个阶段)
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_COST' LIMIT 1),
 'Planning', '2024-01-15 09:00:00', '2024-04-20 17:00:00',
 '{"预算类别": "运维费用", "年度预算额": "2800万元", "费用科目数": 45, "归口部门": "财务部", "审批状态": "编制中"}',
 'jicai', 'SAP-FI', '年度运维费用预算编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_COST' LIMIT 1),
 'Operation', '2024-04-20 17:00:00', '2024-12-31 23:59:59',
 '{"已执行预算": "1956万元", "预算执行率": "69.9%", "超支科目": 3, "节余科目": 12, "费用归集完整率": "94.2%"}',
 'jicai', 'SAP-FI', '费用执行与归集'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_COST' LIMIT 1),
 'Finance', '2025-01-05 09:00:00', NULL,
 '{"年度决算额": "2650万元", "预决算偏差率": "5.4%", "审计状态": "已审计", "结转金额": "150万元", "核销笔数": 1287}',
 'jicai', 'SAP-FI', '年度费用决算与审计');

-- OBJ_METRIC 指标: Planning → Operation → Finance
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_METRIC' LIMIT 1),
 'Planning', '2024-01-10 09:00:00', '2024-03-15 17:00:00',
 '{"指标体系版本": "v2024.1", "KPI数量": 28, "考核维度": 4, "目标制定部门": "运营管理部", "审批状态": "已批准"}',
 'jicai', 'KPI-System', '年度KPI指标体系设计'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_METRIC' LIMIT 1),
 'Operation', '2024-03-15 17:00:00', '2024-12-31 23:59:59',
 '{"达标指标数": 22, "预警指标数": 4, "未达标指标数": 2, "综合达标率": "78.6%", "数据采集频率": "月度"}',
 'jicai', 'KPI-System', '指标执行与监控'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_METRIC' LIMIT 1),
 'Finance', '2025-01-10 09:00:00', NULL,
 '{"年度综合评分": 82.5, "考核结果": "良好", "奖惩金额": "180万元", "整改要求数": 5, "指标调整建议": 3}',
 'jicai', 'KPI-System', '年度考核与评价');

-- OBJ_ASSET 资产: Planning → Construction → Operation → Finance (全4阶段)
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_ASSET' LIMIT 1),
 'Planning', '2023-11-01 09:00:00', '2024-02-28 17:00:00',
 '{"资产类别": "输变电设备", "计划采购数量": 156, "预算总额": "4500万元", "采购方式": "公开招标", "需求部门": "设备管理部"}',
 'jicai', 'SAP-AM', '资产采购计划编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_ASSET' LIMIT 1),
 'Construction', '2024-02-28 17:00:00', '2024-08-15 17:00:00',
 '{"已到货数量": 142, "验收合格数": 138, "不合格数": 4, "安装进度": "88.5%", "质量合格率": "97.2%"}',
 'jicai', 'SAP-AM', '资产到货验收与安装'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_ASSET' LIMIT 1),
 'Operation', '2024-08-15 17:00:00', '2025-03-01 17:00:00',
 '{"在运资产数": 138, "资产完好率": "99.1%", "累计折旧": "675万元", "维修次数": 12, "故障率": "0.7%"}',
 'jicai', 'SAP-AM', '资产投运与维护'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_ASSET' LIMIT 1),
 'Finance', '2025-03-01 17:00:00', NULL,
 '{"资产原值": "4280万元", "累计折旧": "856万元", "净值": "3424万元", "报废数量": 2, "资产卡片数": 138}',
 'jicai', 'SAP-AM', '资产台账与财务核算');

-- OBJ_PERSONNEL 人员: Planning → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PERSONNEL' LIMIT 1),
 'Planning', '2024-01-05 09:00:00', '2024-03-01 17:00:00',
 '{"编制人数": 320, "在岗人数": 305, "缺编岗位": 15, "招聘计划": 20, "培训预算": "85万元"}',
 'jicai', 'HR-System', '年度人员编制与招聘计划'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PERSONNEL' LIMIT 1),
 'Operation', '2024-03-01 17:00:00', NULL,
 '{"在岗人数": 318, "持证上岗率": "96.2%", "培训完成率": "88.7%", "人均工时": 1920, "安全考核通过率": "99.1%"}',
 'jicai', 'HR-System', '人员在岗管理与培训');

-- OBJ_VOUCHER 票据: Planning → Finance
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_VOUCHER' LIMIT 1),
 'Planning', '2024-01-15 09:00:00', '2024-03-01 17:00:00',
 '{"票据类型": "增值税专用发票", "管理制度版本": "v2024", "电子票据覆盖率": "75%", "合规审查规则数": 28}',
 'jicai', 'SAP-FI', '票据管理制度与规则配置'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_VOUCHER' LIMIT 1),
 'Operation', '2024-03-01 17:00:00', '2024-12-31 23:59:59',
 '{"本年收票数": 8560, "验真通过率": "99.7%", "退票数": 26, "电子票据比例": "82.3%", "平均报销周期": "4.2天"}',
 'jicai', 'SAP-FI', '票据日常收验与报销'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_VOUCHER' LIMIT 1),
 'Finance', '2025-01-05 09:00:00', NULL,
 '{"年度票据总额": "1.85亿元", "已核销金额": "1.82亿元", "待核销金额": "300万元", "归档完成率": "97.5%", "审计异常票据": 8}',
 'jicai', 'SAP-FI', '票据核销与归档审计');

-- === 输配电域 (shupeidian) ===

-- OBJ_PROJECT 项目: 全5阶段 (Planning→Design→Construction→Operation→Finance)
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'Planning', '2023-06-01 09:00:00', '2023-09-30 17:00:00',
 '{"项目名称": "220kV翠湖变电站扩建工程", "概算金额": "1.2亿元", "建设规模": "2×180MVA主变", "计划工期": "18个月", "审批状态": "已批复"}',
 'shupeidian', 'PMS', '项目可研与初设批复'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'Design', '2023-10-01 09:00:00', '2024-01-31 17:00:00',
 '{"设计单位": "南方电网设计院", "图纸数量": 342, "设计审查轮次": 3, "技术方案": "GIS方案", "设计变更": 5}',
 'shupeidian', 'PMS', '施工图设计与审查'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'Construction', '2024-02-01 09:00:00', '2024-11-30 17:00:00',
 '{"施工单位": "南方电网工程公司", "施工进度": "100%", "质量验收合格率": "98.5%", "安全事故": 0, "里程碑完成": "8/8"}',
 'shupeidian', 'PMS', '施工建设与验收'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'Operation', '2024-12-01 09:00:00', '2025-06-30 17:00:00',
 '{"投运日期": "2024-12-01", "运行状态": "正常", "负荷率": "65.3%", "巡检次数": 48, "缺陷数": 2}',
 'shupeidian', 'PMS', '项目投运与移交生产'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PROJECT' LIMIT 1),
 'Finance', '2025-06-30 17:00:00', NULL,
 '{"竣工决算额": "1.15亿元", "概决算偏差": "-4.2%", "资产转固金额": "1.12亿元", "质保期": "24个月", "尾款结算状态": "进行中"}',
 'shupeidian', 'SAP-FI', '竣工决算与资产转固');

-- OBJ_DEVICE 设备: Planning → Design → Construction → Operation (4阶段，无Finance)
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DEVICE' LIMIT 1),
 'Planning', '2023-08-01 09:00:00', '2023-12-15 17:00:00',
 '{"设备类型": "180MVA主变压器", "技术参数": "220/110/10kV", "采购方式": "公开招标", "预算金额": "3200万元", "需求数量": 2}',
 'shupeidian', 'EAM', '设备选型与采购计划'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DEVICE' LIMIT 1),
 'Design', '2023-12-15 17:00:00', '2024-03-01 17:00:00',
 '{"制造厂家": "特变电工", "出厂编号": "TBE-2024-0156", "型式试验": "合格", "技术协议版本": "v3.2", "监造次数": 4}',
 'shupeidian', 'EAM', '设备制造与监造'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DEVICE' LIMIT 1),
 'Construction', '2024-03-01 17:00:00', '2024-10-15 17:00:00',
 '{"安装进度": "100%", "调试状态": "完成", "保护定值已整定": true, "一次设备耐压试验": "合格", "二次回路校验": "合格"}',
 'shupeidian', 'EAM', '设备安装调试与验收'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DEVICE' LIMIT 1),
 'Operation', '2024-10-15 17:00:00', NULL,
 '{"运行状态": "正常", "累计运行小时": 4380, "油色谱监测": "正常", "局放监测值": "< 5pC", "下次检修计划": "2026-04"}',
 'shupeidian', 'EAM', '设备投运与状态监测');

-- OBJ_CONTRACT 合同: Planning → Operation → Finance
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_CONTRACT' LIMIT 1),
 'Planning', '2023-07-15 09:00:00', '2023-11-30 17:00:00',
 '{"合同类型": "工程施工合同", "标段数": 3, "招标方式": "公开招标", "预算控制价": "8500万元", "评审状态": "已评审"}',
 'shupeidian', 'SAP-MM', '合同招标与签订'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_CONTRACT' LIMIT 1),
 'Operation', '2023-11-30 17:00:00', '2025-03-15 17:00:00',
 '{"合同金额": "7860万元", "已付金额": "6288万元", "付款比例": "80%", "变更金额": "+320万元", "索赔事项": 0}',
 'shupeidian', 'SAP-MM', '合同执行与付款'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_CONTRACT' LIMIT 1),
 'Finance', '2025-03-15 17:00:00', NULL,
 '{"结算金额": "8180万元", "结算偏差": "-3.8%", "质保金": "409万元", "发票到齐率": "98.5%", "审计状态": "待审计"}',
 'shupeidian', 'SAP-FI', '合同结算与审计');

-- OBJ_TASK 任务: Planning → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TASK' LIMIT 1),
 'Planning', '2024-01-08 09:00:00', '2024-02-01 17:00:00',
 '{"任务类型": "年度检修计划", "计划任务数": 560, "涉及设备数": 1230, "人力需求": "4500人·天", "预算额": "1800万元"}',
 'shupeidian', 'PMS', '年度检修任务编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TASK' LIMIT 1),
 'Operation', '2024-02-01 17:00:00', NULL,
 '{"已完成任务": 485, "完成率": "86.6%", "超期任务": 12, "平均工期偏差": "+1.3天", "安全事故": 0}',
 'shupeidian', 'PMS', '任务执行与监控');

-- OBJ_AUDIT 监督: Planning → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_AUDIT' LIMIT 1),
 'Planning', '2024-01-10 09:00:00', '2024-02-28 17:00:00',
 '{"监督类型": "工程质量监督", "年度计划检查数": 120, "监督重点领域": "安全/质量/进度/投资", "监督人员": 15}',
 'shupeidian', 'QMS', '年度监督计划制定'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_AUDIT' LIMIT 1),
 'Operation', '2024-02-28 17:00:00', NULL,
 '{"已检查次数": 98, "发现问题数": 156, "已整改数": 142, "整改完成率": "91.0%", "重大问题": 3}',
 'shupeidian', 'QMS', '监督执行与问题跟踪');

-- OBJ_SYSTEM 系统: Design → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_SYSTEM' LIMIT 1),
 'Design', '2023-09-01 09:00:00', '2024-01-15 17:00:00',
 '{"系统名称": "配网自动化系统", "覆盖范围": "10kV配网", "接入终端数": 5600, "通信方式": "4G/光纤", "设计容量": "10000终端"}',
 'shupeidian', 'IT-System', '系统方案设计与评审'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_SYSTEM' LIMIT 1),
 'Construction', '2024-01-15 17:00:00', '2024-06-30 17:00:00',
 '{"部署进度": "100%", "接入终端": 5200, "联调测试通过率": "97.8%", "安全等保等级": "三级", "数据迁移完成率": "100%"}',
 'shupeidian', 'IT-System', '系统建设与联调'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_SYSTEM' LIMIT 1),
 'Operation', '2024-06-30 17:00:00', NULL,
 '{"系统可用率": "99.95%", "日均处理事件": 12500, "在线终端率": "98.2%", "月度故障次数": 2, "用户满意度": 4.3}',
 'shupeidian', 'IT-System', '系统运行维护');

-- OBJ_STANDARD 标准: Planning → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_STANDARD' LIMIT 1),
 'Planning', '2024-01-05 09:00:00', '2024-04-30 17:00:00',
 '{"标准体系": "输配电技术标准", "现行标准数": 186, "待修订数": 23, "新编计划": 8, "主管部门": "技术标准处"}',
 'shupeidian', 'STD-System', '标准体系年度修订计划'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_STANDARD' LIMIT 1),
 'Operation', '2024-04-30 17:00:00', NULL,
 '{"已修订标准": 18, "新发布标准": 5, "培训覆盖人数": 2800, "标准执行符合率": "95.3%", "不符合项": 12}',
 'shupeidian', 'STD-System', '标准执行与符合性检查');

-- OBJ_DOCUMENT 文档: Design → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DOCUMENT' LIMIT 1),
 'Design', '2023-10-01 09:00:00', '2024-03-31 17:00:00',
 '{"文档类型": "工程设计文档", "文档总数": 1280, "版本管理": "SVN", "审批流程": "三级审批", "密级分类": "内部"}',
 'shupeidian', 'DMS', '设计文档编制与审批'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DOCUMENT' LIMIT 1),
 'Operation', '2024-03-31 17:00:00', NULL,
 '{"归档文档数": 1156, "归档完成率": "90.3%", "在线查阅次数": 4500, "借阅申请": 89, "过期文档": 34}',
 'shupeidian', 'DMS', '文档归档与日常管理');

-- OBJ_PLAN 计划: Planning → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PLAN' LIMIT 1),
 'Planning', '2023-10-15 09:00:00', '2024-01-31 17:00:00',
 '{"计划类型": "电网发展五年规划", "规划期": "2024-2028", "投资总额": "85亿元", "新建变电站": 12, "新建线路": "580公里"}',
 'shupeidian', 'PMS', '电网发展规划编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PLAN' LIMIT 1),
 'Operation', '2024-01-31 17:00:00', NULL,
 '{"本年完成投资": "16.8亿元", "投资完成率": "19.8%", "开工项目": 35, "竣工项目": 18, "里程碑完成率": "92%"}',
 'shupeidian', 'PMS', '规划执行跟踪');

-- OBJ_TEAM 班站: Planning → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TEAM' LIMIT 1),
 'Planning', '2024-01-02 09:00:00', '2024-02-15 17:00:00',
 '{"班站类型": "配电运维班", "编制人数": 12, "管辖设备数": 860, "管辖线路": "45条10kV线路", "责任区域": "城区东片"}',
 'shupeidian', 'HR-System', '班站年度工作计划'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TEAM' LIMIT 1),
 'Operation', '2024-02-15 17:00:00', NULL,
 '{"在岗人数": 11, "月均巡检次数": 240, "故障抢修响应时间": "25分钟", "安全天数": 456, "技能竞赛获奖": 2}',
 'shupeidian', 'HR-System', '班站日常运维管理');

-- OBJ_移交信 移交管理: Construction → Operation
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_移交信' LIMIT 1),
 'Construction', '2024-08-01 09:00:00', '2024-11-30 17:00:00',
 '{"移交类型": "工程竣工移交", "移交设备数": 86, "资料清单项": 42, "验收签章": "已完成", "遗留问题": 3}',
 'shupeidian', 'PMS', '工程竣工移交准备'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_移交信' LIMIT 1),
 'Operation', '2024-11-30 17:00:00', NULL,
 '{"已移交设备": 86, "运维接管确认": "已确认", "遗留问题处理": "2/3已解决", "质保跟踪状态": "进行中", "运行月报": "正常"}',
 'shupeidian', 'PMS', '移交后运维接管');

-- ============================================================================
-- 对象间关系规则表（Phase 3: 对象对上挂载物理公式/业务规则/阈值约束）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `object_relation_rules` (
    `rule_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `rule_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '规则编码',
    `rule_name` VARCHAR(256) NOT NULL COMMENT '规则名称',

    -- 关系双端
    `source_object_code` VARCHAR(128) NOT NULL COMMENT '源对象编码',
    `target_object_code` VARCHAR(128) NOT NULL COMMENT '目标对象编码',
    `relation_type` ENUM('DRIVES','CONSTRAINS','COMPUTES','TRIGGERS','DERIVES')
        NOT NULL COMMENT '关系类型: 驱动/约束/计算/触发/派生',

    -- 规则定义
    `rule_category` ENUM('PHYSICAL_FORMULA','BUSINESS_RULE','THRESHOLD','VALIDATION','DERIVED_CALC')
        NOT NULL COMMENT '规则类别',
    `expression` JSON NOT NULL COMMENT '规则表达式(JSON格式)',
    `description` TEXT COMMENT '规则描述',

    -- 方向与强度
    `direction` ENUM('UNIDIRECTIONAL','BIDIRECTIONAL') DEFAULT 'UNIDIRECTIONAL' COMMENT '方向',
    `priority` INT DEFAULT 0 COMMENT '优先级(同对象对多规则时)',

    -- 生命周期关联
    `applicable_stages` JSON DEFAULT NULL COMMENT '适用的生命周期阶段列表',

    -- 元数据
    `severity` ENUM('INFO','WARNING','CRITICAL') DEFAULT 'INFO' COMMENT '严重级别',
    `is_active` BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    `data_domain` VARCHAR(128) COMMENT '数据域',
    `created_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    INDEX `idx_rr_source` (`source_object_code`),
    INDEX `idx_rr_target` (`target_object_code`),
    INDEX `idx_rr_pair` (`source_object_code`, `target_object_code`),
    INDEX `idx_rr_category` (`rule_category`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象间关系规则表 — 在对象对上挂载物理公式、业务规则、阈值约束';

-- ============================================================================
-- 预置关系规则（8条演示数据）
-- ============================================================================
INSERT INTO `object_relation_rules` (`rule_code`, `rule_name`, `source_object_code`, `target_object_code`, `relation_type`, `rule_category`, `expression`, `description`, `applicable_stages`, `severity`, `data_domain`) VALUES

-- 1. 物理公式：设备 → 资产（功率影响资产估值）
('RR_POWER_ASSET', '设备功率影响资产估值', 'OBJ_DEVICE', 'OBJ_ASSET',
 'COMPUTES', 'PHYSICAL_FORMULA',
 '{"formula": "P = U × I", "variables": {"U": "额定电压(V)", "I": "额定电流(A)"}, "result": "P(额定功率W)", "downstream_effect": "功率等级决定资产折旧类别"}',
 '根据设备额定电压和电流计算功率，功率等级影响资产分类和折旧策略',
 '["Operation", "Finance"]', 'INFO', 'shupeidian'),

-- 2. 业务规则：合同 → 项目（合同金额决定审批路径）
('RR_CONTRACT_PROJECT', '合同金额决定项目审批级别', 'OBJ_CONTRACT', 'OBJ_PROJECT',
 'CONSTRAINS', 'BUSINESS_RULE',
 '{"condition": "合同金额 > 3000000", "then": "项目审批路径 = A级审批", "else": "项目审批路径 = B级审批", "unit": "元"}',
 '合同金额超过300万元时项目需走A级审批路径，否则走B级',
 '["Planning", "Design"]', 'WARNING', 'jicai'),

-- 3. 阈值约束：费用 → 预算（费用超预算触发预警）
('RR_COST_BUDGET', '费用超预算预警', 'OBJ_COST', 'OBJ_BUDGET',
 'TRIGGERS', 'THRESHOLD',
 '{"field": "累计费用", "operator": ">", "reference_field": "预算额度", "tolerance": 0.1, "message": "费用已超预算{percent}%，需启动预算追加流程"}',
 '当累计费用超过预算额度10%时触发预警',
 '["Construction", "Operation", "Finance"]', 'CRITICAL', 'jicai'),

-- 4. 派生计算：项目 → 指标（项目完工率）
('RR_PROJECT_KPI', '项目完工率派生', 'OBJ_PROJECT', 'OBJ_KPI',
 'DERIVES', 'DERIVED_CALC',
 '{"formula": "完工率 = 已完成里程碑 / 总里程碑 × 100", "variables": {"已完成里程碑": "INTEGER", "总里程碑": "INTEGER"}, "result": "完工率(%)", "threshold_warning": 50, "threshold_ok": 80}',
 '根据里程碑完成数计算项目完工率，低于50%预警',
 '["Construction", "Operation"]', 'INFO', 'jicai'),

-- 5. 驱动关系：工单 → 设备（工单触发设备状态变更）
('RR_WORKORDER_DEVICE', '工单驱动设备状态', 'OBJ_WORKORDER', 'OBJ_DEVICE',
 'DRIVES', 'BUSINESS_RULE',
 '{"trigger": "工单状态 = 已完成", "action": "设备状态 = 已检修", "side_effect": "更新设备.最近检修日期 = 工单.完成日期"}',
 '工单完成后自动更新关联设备的检修状态和日期',
 '["Operation"]', 'INFO', 'shupeidian'),

-- 6. 物理约束：设备 → 设备（变压器负载约束，自环）
('RR_TRANSFORMER_LOAD', '变压器负载约束', 'OBJ_DEVICE', 'OBJ_DEVICE',
 'CONSTRAINS', 'PHYSICAL_FORMULA',
 '{"formula": "负载率 = 实际负荷 / 额定容量 × 100", "variables": {"实际负荷": "额定负荷(kVA)", "额定容量": "额定容量(kVA)"}, "constraint": "负载率 <= 80", "unit": "%", "message": "变压器负载率{value}%超过安全阈值80%"}',
 '监控变压器负载率，超过80%触发安全预警',
 '["Operation"]', 'CRITICAL', 'shupeidian'),

-- 7. 物理公式：资产 → 费用（折旧计算）
('RR_ASSET_DEPRECIATION', '资产折旧费用计算', 'OBJ_ASSET', 'OBJ_COST',
 'COMPUTES', 'PHYSICAL_FORMULA',
 '{"formula": "年折旧额 = (原值 - 残值) / 折旧年限", "variables": {"原值": "DECIMAL(元)", "残值": "DECIMAL(元)", "折旧年限": "INTEGER(年)"}, "result": "年折旧额(元)", "method": "直线法"}',
 '按直线法计算资产年度折旧额，结果计入费用',
 '["Operation", "Finance"]', 'INFO', 'jicai'),

-- 8. 物理公式：设备 → 线路（线损计算）
('RR_LINE_LOSS', '线路损耗计算', 'OBJ_DEVICE', 'OBJ_LINE',
 'COMPUTES', 'PHYSICAL_FORMULA',
 '{"formula": "ΔP = I² × R × L", "variables": {"I": "电流(A)", "R": "电阻率(Ω/km)", "L": "线路长度(km)"}, "result": "线损功率(W)", "industry_standard": "GB/T 12325"}',
 '根据电流、电阻率和线路长度计算线路损耗功率',
 '["Operation"]', 'WARNING', 'shupeidian')

ON DUPLICATE KEY UPDATE `rule_name` = VALUES(`rule_name`);

-- ============================================================================
-- 对象名称历史表（Phase 1: 重命名审计追踪）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `object_name_history` (
    `history_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `object_id` INT NOT NULL,
    `old_name` VARCHAR(256) NOT NULL COMMENT '原名称',
    `new_name` VARCHAR(256) NOT NULL COMMENT '新名称',
    `rename_source` ENUM('MANUAL','LLM','MERGE') NOT NULL DEFAULT 'MANUAL' COMMENT '重命名来源',
    `rename_reason` TEXT COMMENT '重命名原因',
    `renamed_by` VARCHAR(128) DEFAULT 'system' COMMENT '操作人',
    `created_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (`object_id`) REFERENCES `extracted_objects`(`object_id`) ON DELETE CASCADE,
    KEY `idx_onh_object_time` (`object_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='对象名称变更历史（审计追踪）';

-- ============================================================================
-- 生命周期阶段模板表（Phase 2: 阶段属性模板 + 验证规则）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `lifecycle_stage_templates` (
    `template_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `object_type` ENUM('CORE','DERIVED','AUXILIARY') NOT NULL COMMENT '适用的对象类型',
    `lifecycle_stage` ENUM('Planning','Design','Construction','Operation','Finance') NOT NULL COMMENT '生命周期阶段',
    `required_attributes` JSON NOT NULL COMMENT '必填属性列表',
    `optional_attributes` JSON COMMENT '可选属性列表',
    `validation_rules` JSON COMMENT '验证规则 {attr: {type, min, max, pattern}}',
    `trigger_functions` JSON COMMENT '进入该阶段时自动触发的机理函数编码列表',
    `description` TEXT COMMENT '阶段描述',
    UNIQUE KEY `uk_lst_type_stage` (`object_type`, `lifecycle_stage`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='生命周期阶段模板 — 定义每阶段必填/可选属性和验证规则';

-- 预置 CORE 类型 5 阶段模板
INSERT INTO `lifecycle_stage_templates` (`object_type`, `lifecycle_stage`, `required_attributes`, `optional_attributes`, `validation_rules`, `trigger_functions`, `description`) VALUES
('CORE', 'Planning',
 '["项目名称", "立项日期", "预算金额", "负责人"]',
 '["可行性报告", "审批状态", "优先级"]',
 '{"预算金额": {"type": "number", "min": 0}, "立项日期": {"type": "date"}}',
 NULL,
 '规划阶段：确定项目范围、预算和时间节点'),
('CORE', 'Design',
 '["设计方案", "技术规格", "审批状态"]',
 '["设计单位", "设计周期", "变更记录"]',
 '{"审批状态": {"type": "enum", "values": ["待审批", "已审批", "驳回"]}}',
 NULL,
 '设计阶段：完成技术方案设计和审批'),
('CORE', 'Construction',
 '["施工单位", "开工日期", "计划完工日期", "施工进度"]',
 '["质检记录", "安全检查", "变更单", "验收标准"]',
 '{"施工进度": {"type": "number", "min": 0, "max": 100}, "开工日期": {"type": "date"}}',
 '["MF_COST_MONITOR"]',
 '建设阶段：施工执行和过程管理'),
('CORE', 'Operation',
 '["运行状态", "投运日期", "运维负责人"]',
 '["巡检周期", "缺陷记录", "负荷数据", "检修计划"]',
 '{"运行状态": {"type": "enum", "values": ["正常运行", "带病运行", "停运检修", "退役"]}}',
 '["MF_LOAD_MONITOR"]',
 '运行阶段：投运后的运维管理'),
('CORE', 'Finance',
 '["资产原值", "累计折旧", "净值", "折旧方式"]',
 '["残值率", "折旧年限", "资产分类", "报废审批"]',
 '{"资产原值": {"type": "number", "min": 0}, "累计折旧": {"type": "number", "min": 0}}',
 '["MF_DEPRECIATION"]',
 '财务阶段：资产价值管理和折旧计算')
ON DUPLICATE KEY UPDATE `required_attributes` = VALUES(`required_attributes`);

-- ============================================================================
-- 补充生命周期演示数据（Phase 2: 扩充到 50+ 条）
-- ============================================================================

-- 费用对象生命周期
INSERT INTO `object_lifecycle_history` (`object_id`, `lifecycle_stage`, `stage_entered_at`, `stage_exited_at`, `attributes_snapshot`, `data_domain`, `source_system`, `notes`) VALUES
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_COST' LIMIT 1),
 'Planning', '2024-01-10', '2024-02-15',
 '{"预算编制": "已完成", "费用科目": "基建投资", "年度预算": 5000000}',
 'jicai', 'ERP', '年度预算编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_COST' LIMIT 1),
 'Construction', '2024-02-15', '2024-08-20',
 '{"累计支出": 3200000, "预算执行率": "64%", "费用类别": "材料费+人工费"}',
 'jicai', 'ERP', '建设期费用归集'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_COST' LIMIT 1),
 'Finance', '2024-08-20', NULL,
 '{"决算金额": 4800000, "审计状态": "已审计", "结余": 200000}',
 'jicai', 'ERP', '竣工决算'),

-- 指标对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_METRIC' LIMIT 1),
 'Planning', '2024-01-05', '2024-03-01',
 '{"指标体系": "已建立", "KPI数量": 15, "目标值设定": "已完成"}',
 'jicai', 'BI', '年度指标体系建立'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_METRIC' LIMIT 1),
 'Operation', '2024-03-01', NULL,
 '{"达标率": "87%", "预警指标": 3, "超标指标": 1, "监控频率": "月度"}',
 'jicai', 'BI', '指标监控运行中'),

-- 工单对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TASK' LIMIT 1),
 'Planning', '2024-03-01', '2024-03-15',
 '{"工单类型": "计划检修", "优先级": "高", "计划工期": 14}',
 'shupeidian', 'PMS', '检修计划编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TASK' LIMIT 1),
 'Construction', '2024-03-15', '2024-03-28',
 '{"施工班组": "检修一班", "进度": 100, "安全等级": "一级"}',
 'shupeidian', 'PMS', '检修执行'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TASK' LIMIT 1),
 'Operation', '2024-03-28', NULL,
 '{"验收状态": "已验收", "质量评分": 95, "遗留缺陷": 0}',
 'shupeidian', 'PMS', '工单已完成验收'),

-- 人员对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PERSONNEL' LIMIT 1),
 'Planning', '2023-01-01', '2023-06-30',
 '{"岗位规划": "已完成", "编制数": 120, "招聘计划": 15}',
 'jicai', 'HR', '年度人员规划'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PERSONNEL' LIMIT 1),
 'Operation', '2023-07-01', NULL,
 '{"在岗人数": 118, "培训完成率": "92%", "持证上岗率": "100%", "流动率": "3.5%"}',
 'jicai', 'HR', '人员日常管理'),

-- 票据对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_VOUCHER' LIMIT 1),
 'Planning', '2024-01-01', '2024-01-15',
 '{"票据类型": "增值税发票", "年度预估量": 5000}',
 'jicai', 'ERP', '票据管理规划'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_VOUCHER' LIMIT 1),
 'Operation', '2024-01-15', NULL,
 '{"已处理票据": 3200, "待处理": 150, "异常票据": 12, "合规率": "99.6%"}',
 'jicai', 'ERP', '票据流转中'),

-- 审计对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_AUDIT' LIMIT 1),
 'Planning', '2024-02-01', '2024-03-01',
 '{"审计计划": "年度内审", "审计范围": "全域", "重点领域": "合同管理、费用支出"}',
 'jicai', 'OA', '审计计划编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_AUDIT' LIMIT 1),
 'Construction', '2024-03-01', '2024-05-15',
 '{"已审项目": 8, "问题发现": 23, "整改完成": 18, "审计进度": "80%"}',
 'jicai', 'OA', '审计执行中'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_AUDIT' LIMIT 1),
 'Finance', '2024-05-15', NULL,
 '{"审计报告": "已出具", "整改率": "95.6%", "跟踪问题": 2}',
 'jicai', 'OA', '审计结论与跟踪'),

-- 标准对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_STANDARD' LIMIT 1),
 'Planning', '2023-06-01', '2023-09-01',
 '{"标准制定": "进行中", "参考标准": "GB/T 38329", "适用范围": "输配电数据标准"}',
 'shupeidian', 'OA', '标准制定'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_STANDARD' LIMIT 1),
 'Operation', '2023-09-01', NULL,
 '{"标准状态": "已发布", "版本号": "v2.1", "覆盖域": "输配电+计财", "执行率": "88%"}',
 'shupeidian', 'OA', '标准执行与监督'),

-- 文档对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DOCUMENT' LIMIT 1),
 'Design', '2024-01-15', '2024-02-28',
 '{"文档类型": "技术方案", "审批流程": "三级审批", "版本管理": "SVN"}',
 'shupeidian', 'OA', '技术文档编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_DOCUMENT' LIMIT 1),
 'Operation', '2024-02-28', NULL,
 '{"归档状态": "已归档", "文档数": 342, "待更新": 15, "过期文档": 8}',
 'shupeidian', 'OA', '文档归档管理'),

-- 规划对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PLAN' LIMIT 1),
 'Planning', '2023-10-01', '2024-01-01',
 '{"规划周期": "2024-2026", "投资总额": 25000000, "项目数": 12}',
 'jicai', 'ERP', '三年滚动规划编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PLAN' LIMIT 1),
 'Design', '2024-01-01', '2024-03-15',
 '{"方案评审": "已通过", "优化轮次": 3, "预算调整": "-5%"}',
 'jicai', 'ERP', '规划方案设计与评审'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_PLAN' LIMIT 1),
 'Operation', '2024-03-15', NULL,
 '{"执行进度": "42%", "已启动项目": 5, "延期项目": 1, "预算执行率": "38%"}',
 'jicai', 'ERP', '规划执行与跟踪'),

-- 团队对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TEAM' LIMIT 1),
 'Planning', '2023-12-01', '2024-01-15',
 '{"组织架构": "已调整", "新增岗位": 3, "团队规模": 25}',
 'shupeidian', 'HR', '年度组织调整'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_TEAM' LIMIT 1),
 'Operation', '2024-01-15', NULL,
 '{"在编人数": 24, "绩效达标率": "91%", "培训时数": 480, "项目参与数": 8}',
 'shupeidian', 'HR', '团队运营管理'),

-- 系统对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_SYSTEM' LIMIT 1),
 'Design', '2023-08-01', '2023-11-01',
 '{"系统类型": "PMS配电管理", "架构设计": "微服务", "技术选型": "Java+Vue"}',
 'shupeidian', 'IT', '系统架构设计'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_SYSTEM' LIMIT 1),
 'Construction', '2023-11-01', '2024-03-01',
 '{"开发进度": 100, "模块数": 12, "测试用例": 856, "缺陷修复率": "98%"}',
 'shupeidian', 'IT', '系统开发建设'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_SYSTEM' LIMIT 1),
 'Operation', '2024-03-01', NULL,
 '{"运行状态": "正常", "在线用户": 85, "日均事务": 12000, "可用率": "99.9%"}',
 'shupeidian', 'IT', '系统运维'),

-- 移交管理对象生命周期
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_移交信' LIMIT 1),
 'Planning', '2024-06-01', '2024-07-15',
 '{"移交类型": "竣工移交", "移交清单": "编制中", "接收单位": "运维部"}',
 'shupeidian', 'PMS', '移交计划编制'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_移交信' LIMIT 1),
 'Construction', '2024-07-15', '2024-08-30',
 '{"已移交设备": 45, "待移交": 12, "资料完整度": "92%", "遗留问题": 3}',
 'shupeidian', 'PMS', '移交执行'),
((SELECT object_id FROM extracted_objects WHERE object_code='OBJ_移交信' LIMIT 1),
 'Operation', '2024-08-30', NULL,
 '{"移交完成率": "100%", "遗留问题处理": "3/3已解决", "运维接管": "已确认"}',
 'shupeidian', 'PMS', '移交完成确认');

-- ============================================================================
-- 公式链表（Phase 3: 对象间级联计算 A→公式→B→公式→C）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `formula_chains` (
    `chain_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `chain_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '链编码',
    `chain_name` VARCHAR(256) NOT NULL COMMENT '链名称',
    `description` TEXT COMMENT '链描述',
    `is_active` BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    `data_domain` VARCHAR(128) COMMENT '数据域',
    `created_at` TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='公式链 — 定义对象间级联计算路径';

CREATE TABLE IF NOT EXISTS `formula_chain_steps` (
    `step_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `chain_id` BIGINT NOT NULL,
    `step_order` INT NOT NULL COMMENT '步骤顺序(1开始)',
    `rule_id` BIGINT NOT NULL COMMENT 'FK → object_relation_rules.rule_id',
    `input_mapping` JSON COMMENT '上一步输出到本步输入的映射',
    FOREIGN KEY (`chain_id`) REFERENCES `formula_chains`(`chain_id`) ON DELETE CASCADE,
    FOREIGN KEY (`rule_id`) REFERENCES `object_relation_rules`(`rule_id`) ON DELETE CASCADE,
    KEY `idx_fcs_chain_order` (`chain_id`, `step_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='公式链步骤 — 每步引用一条关系规则';

-- 预置公式链：设备(P=UI) → 资产(折旧) → 费用
INSERT INTO `formula_chains` (`chain_code`, `chain_name`, `description`, `data_domain`) VALUES
('FC_DEVICE_ASSET_COST', '设备→资产→费用 级联计算',
 '从设备功率计算出发，经资产折旧公式，最终影响费用归集。\n步骤: 1)P=U×I计算设备功率 2)年折旧额=(原值-残值)/年限 3)折旧费用纳入资产全生命周期成本',
 'cross_domain');

INSERT INTO `formula_chain_steps` (`chain_id`, `step_order`, `rule_id`, `input_mapping`) VALUES
((SELECT chain_id FROM formula_chains WHERE chain_code='FC_DEVICE_ASSET_COST' LIMIT 1),
 1,
 (SELECT rule_id FROM object_relation_rules WHERE rule_code='RR_POWER_ASSET' LIMIT 1),
 '{"description": "输入设备额定电压和电流，计算功率"}'),
((SELECT chain_id FROM formula_chains WHERE chain_code='FC_DEVICE_ASSET_COST' LIMIT 1),
 2,
 (SELECT rule_id FROM object_relation_rules WHERE rule_code='RR_ASSET_DEPRECIATION' LIMIT 1),
 '{"description": "基于功率等级确定资产分类，计算年折旧额", "P_to_category": "P>100kW→一类资产, P>10kW→二类, 其他→三类"}'),
((SELECT chain_id FROM formula_chains WHERE chain_code='FC_DEVICE_ASSET_COST' LIMIT 1),
 3,
 (SELECT rule_id FROM object_relation_rules WHERE rule_code='RR_COST_BUDGET' LIMIT 1),
 '{"description": "折旧费用纳入预算，检查是否超预算触发预警"}');

-- 预置公式链2：合同→项目→指标
INSERT INTO `formula_chains` (`chain_code`, `chain_name`, `description`, `data_domain`) VALUES
('FC_CONTRACT_PROJECT_KPI', '合同→项目→指标 业务链路',
 '合同金额决定项目审批级别，项目里程碑驱动完工率指标计算',
 'jicai');

INSERT INTO `formula_chain_steps` (`chain_id`, `step_order`, `rule_id`, `input_mapping`) VALUES
((SELECT chain_id FROM formula_chains WHERE chain_code='FC_CONTRACT_PROJECT_KPI' LIMIT 1),
 1,
 (SELECT rule_id FROM object_relation_rules WHERE rule_code='RR_CONTRACT_PROJECT' LIMIT 1),
 '{"description": "合同金额决定项目审批路径"}'),
((SELECT chain_id FROM formula_chains WHERE chain_code='FC_CONTRACT_PROJECT_KPI' LIMIT 1),
 2,
 (SELECT rule_id FROM object_relation_rules WHERE rule_code='RR_PROJECT_KPI' LIMIT 1),
 '{"description": "项目里程碑完成数计算完工率"}');

-- ============================================================================
-- ALTER: 机理函数关联关系规则
-- ============================================================================
ALTER TABLE `mechanism_functions`
    ADD COLUMN IF NOT EXISTS `linked_rule_id` BIGINT DEFAULT NULL COMMENT 'FK → object_relation_rules.rule_id',
    ADD KEY `idx_mf_linked_rule` (`linked_rule_id`);

-- ============================================================================
-- 完成提示
-- ============================================================================
SELECT '✅ YIMO Schema 初始化完成（含全部6阶段: 生命周期模板+名称历史+公式链+关系规则关联）!' AS message;
