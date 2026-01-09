-- ============================================================================
-- YIMO 一模到底本体管理器 - 数据库初始化脚本
-- Universal Lifecycle Ontology Manager (ULOM) Bootstrap SQL
-- ============================================================================
-- 以 root 身份在系统 MySQL 或用户态 mysqld 中执行本脚本以创建数据库与账号

-- 数据库
CREATE DATABASE IF NOT EXISTS `eav_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建应用用户（仅本地）
CREATE USER IF NOT EXISTS 'eav_user'@'localhost' IDENTIFIED BY 'eav_pass_123!';
GRANT ALL PRIVILEGES ON `eav_db`.* TO 'eav_user'@'localhost';

-- 为 TCP 访问(127.0.0.1) 同步创建与授权（Navicat/脚本默认用 127.0.0.1 走 TCP）
CREATE USER IF NOT EXISTS 'eav_user'@'127.0.0.1' IDENTIFIED BY 'eav_pass_123!';
GRANT ALL PRIVILEGES ON `eav_db`.* TO 'eav_user'@'127.0.0.1';
FLUSH PRIVILEGES;

USE `eav_db`;

-- ============================================================================
-- 生命周期阶段定义
-- "一模到底"核心理念：资产从规划到运维全生命周期统一管理
-- ============================================================================

-- 生命周期阶段枚举表（便于扩展）
CREATE TABLE IF NOT EXISTS `lifecycle_stages` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(50) NOT NULL UNIQUE COMMENT '阶段代码',
    `name_cn` VARCHAR(100) NOT NULL COMMENT '中文名称',
    `name_en` VARCHAR(100) NOT NULL COMMENT '英文名称',
    `ord_index` INT NOT NULL DEFAULT 0 COMMENT '阶段顺序(用于时序校验)',
    `description` TEXT COMMENT '阶段描述',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 初始化五大生命周期阶段
INSERT IGNORE INTO `lifecycle_stages` (`code`, `name_cn`, `name_en`, `ord_index`, `description`) VALUES
    ('Planning', '规划', 'Planning', 1, '资产规划阶段：需求分析、可研、立项'),
    ('Design', '设计', 'Design', 2, '设计阶段：初设、施工图、BOM清单'),
    ('Construction', '建设', 'Construction', 3, '建设阶段：采购、施工、验收'),
    ('Operation', '运维', 'Operation', 4, '运维阶段：巡检、检修、状态监测'),
    ('Finance', '财务', 'Finance', 5, '财务阶段：资产入账、折旧、处置');

-- ============================================================================
-- 全局资产索引表 - "白圆"(White Circle) 实现
-- 这是"一模到底"的核心：每个物理资产只有一个全局唯一标识
-- ============================================================================

CREATE TABLE IF NOT EXISTS `global_asset_index` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `global_uid` VARCHAR(64) NOT NULL UNIQUE COMMENT '全局唯一资产标识(UUID或业务编码)',
    `asset_name` VARCHAR(512) COMMENT '资产名称(融合后的规范名)',
    `asset_type` VARCHAR(256) COMMENT '资产类型',
    `asset_class` VARCHAR(128) COMMENT '资产大类(如:变压器/线路/开关)',
    `trust_score` DECIMAL(5,4) DEFAULT 1.0000 COMMENT '数据可信度(0-1)',
    `fusion_status` ENUM('pending', 'partial', 'complete', 'conflict') DEFAULT 'pending' COMMENT '融合状态',
    `golden_attributes` JSON COMMENT '黄金记录:融合后的权威属性集',
    `source_count` INT DEFAULT 0 COMMENT '关联的源数据数量',
    `first_seen_stage` VARCHAR(50) COMMENT '首次出现的生命周期阶段',
    `latest_stage` VARCHAR(50) COMMENT '最新的生命周期阶段',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_asset_type` (`asset_type`),
    KEY `idx_asset_class` (`asset_class`),
    KEY `idx_fusion_status` (`fusion_status`),
    KEY `idx_trust_score` (`trust_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 实体-全局资产映射表
-- 将不同阶段、不同来源的 eav_entities 映射到同一个 global_uid
-- ============================================================================

CREATE TABLE IF NOT EXISTS `entity_global_mapping` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `entity_id` BIGINT NOT NULL COMMENT '关联的EAV实体ID',
    `global_uid` VARCHAR(64) NOT NULL COMMENT '全局资产UID',
    `lifecycle_stage` VARCHAR(50) NOT NULL COMMENT '该实体所属生命周期阶段',
    `confidence` DECIMAL(5,4) DEFAULT 1.0000 COMMENT '映射置信度(0-1)',
    `mapping_method` ENUM('manual', 'rule', 'llm', 'semantic') DEFAULT 'manual' COMMENT '映射方法',
    `mapping_reason` TEXT COMMENT '映射原因/证据',
    `is_primary` TINYINT(1) DEFAULT 0 COMMENT '是否为该阶段的主记录',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `created_by` VARCHAR(128) COMMENT '创建者(用户或agent)',
    UNIQUE KEY `uniq_entity_stage` (`entity_id`, `lifecycle_stage`),
    KEY `idx_global_uid` (`global_uid`),
    KEY `idx_stage` (`lifecycle_stage`),
    KEY `idx_confidence` (`confidence`),
    CONSTRAINT `fk_mapping_global` FOREIGN KEY (`global_uid`) 
        REFERENCES `global_asset_index` (`global_uid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 数据异常/告警表 - AIOps一致性监控
-- ============================================================================

CREATE TABLE IF NOT EXISTS `data_anomalies` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `global_uid` VARCHAR(64) COMMENT '关联的全局资产UID',
    `anomaly_type` ENUM(
        'temporal_violation',   -- 时序违规(如运维早于建设)
        'value_drift',          -- 值漂移(同属性不同阶段值不一致)
        'missing_stage',        -- 缺失阶段
        'duplicate_conflict',   -- 重复冲突
        'schema_mismatch',      -- 模式不匹配
        'orphan_entity'         -- 孤立实体(无法关联到全局资产)
    ) NOT NULL COMMENT '异常类型',
    `severity` ENUM('info', 'warning', 'error', 'critical') DEFAULT 'warning' COMMENT '严重程度',
    `attribute_name` VARCHAR(256) COMMENT '涉及的属性名',
    `expected_value` TEXT COMMENT '期望值',
    `actual_value` TEXT COMMENT '实际值',
    `source_entities` JSON COMMENT '涉及的源实体ID列表',
    `description` TEXT NOT NULL COMMENT '异常描述',
    `suggestion` TEXT COMMENT '修复建议',
    `status` ENUM('open', 'acknowledged', 'resolved', 'ignored') DEFAULT 'open' COMMENT '处理状态',
    `resolved_at` DATETIME(6) COMMENT '解决时间',
    `resolved_by` VARCHAR(128) COMMENT '解决者',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_global_uid` (`global_uid`),
    KEY `idx_anomaly_type` (`anomaly_type`),
    KEY `idx_severity` (`severity`),
    KEY `idx_status` (`status`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 本体融合日志表 - 记录LLM/规则引擎的融合决策
-- ============================================================================

CREATE TABLE IF NOT EXISTS `fusion_logs` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `global_uid` VARCHAR(64) COMMENT '目标全局资产UID',
    `source_entity_id` BIGINT COMMENT '源实体ID',
    `target_entity_id` BIGINT COMMENT '目标实体ID(如果是合并)',
    `action` ENUM('create', 'merge', 'split', 'update', 'reject') NOT NULL COMMENT '融合动作',
    `agent_type` ENUM('rule', 'llm', 'semantic', 'human') NOT NULL COMMENT '执行代理类型',
    `prompt_used` TEXT COMMENT 'LLM使用的Prompt',
    `response_raw` TEXT COMMENT 'LLM原始响应',
    `confidence` DECIMAL(5,4) COMMENT '置信度',
    `reasoning` TEXT COMMENT '推理过程/依据',
    `execution_time_ms` INT COMMENT '执行耗时(毫秒)',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_global_uid` (`global_uid`),
    KEY `idx_action` (`action`),
    KEY `idx_agent_type` (`agent_type`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 语义指纹表 - 存储实体的语义向量
-- ============================================================================

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
-- 完成提示
-- ============================================================================
SELECT '✅ YIMO 一模到底本体管理器 Schema 初始化完成!' AS message;

