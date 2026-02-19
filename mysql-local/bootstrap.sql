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
-- 完成提示
-- ============================================================================
SELECT '✅ YIMO 对象抽取与三层架构关联 Schema 初始化完成（含生命周期、溯源链路、机理函数、预警表）!' AS message;
