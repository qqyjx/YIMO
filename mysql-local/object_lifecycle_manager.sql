-- ============================================================================
-- YIMO 对象生命周期管理器 - Object Lifecycle Manager (OLM)
-- 底层对象管理器数据库扩展
-- ============================================================================
-- 功能：构建"底层对象管理器"，实现全生命周期的统一对象管理和穿透式监管
-- ============================================================================

USE `eav_db`;

-- ============================================================================
-- 第一部分：三层本体模型 (Three-Layer Ontology Model)
-- 底层：物理实体（客观实体）
-- 中层：逻辑实体（交互表单）
-- 上层：概念实体（业务场景）
-- ============================================================================

-- 概念实体表（业务场景层 - Concept Layer）
CREATE TABLE IF NOT EXISTS `ontology_concept_entities` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `entity_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '概念实体编号',
    `entity_name` VARCHAR(512) NOT NULL COMMENT '概念实体名称',
    `data_domain` VARCHAR(256) COMMENT '数据域',
    `data_subdomain` VARCHAR(256) COMMENT '数据子域',
    `business_object_code` VARCHAR(128) COMMENT '关联业务对象编号',
    `business_object_name` VARCHAR(512) COMMENT '关联业务对象名称',
    `is_core` TINYINT(1) DEFAULT 0 COMMENT '是否核心概念实体',
    `data_classification` VARCHAR(128) COMMENT '数据分类(主数据/事务数据等)',
    `usage_scope` VARCHAR(256) COMMENT '使用范围',
    `data_owner` VARCHAR(256) COMMENT '数据Owner',
    `description` TEXT COMMENT '实体描述',
    `source_file` VARCHAR(512) COMMENT '来源文件',
    `source_sheet` VARCHAR(256) COMMENT '来源工作表',
    `source_row` INT COMMENT '来源行号',
    `embedding_vector` LONGBLOB COMMENT 'SBERT语义向量',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_data_domain` (`data_domain`),
    KEY `idx_business_object` (`business_object_code`),
    KEY `idx_is_core` (`is_core`),
    FULLTEXT KEY `ft_entity_name` (`entity_name`, `description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 逻辑实体表（交互表单层 - Logical Layer）
CREATE TABLE IF NOT EXISTS `ontology_logical_entities` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `entity_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '逻辑实体编码',
    `entity_name` VARCHAR(512) NOT NULL COMMENT '逻辑实体名称',
    `concept_entity_code` VARCHAR(128) COMMENT '关联概念实体编号',
    `data_domain` VARCHAR(256) COMMENT '数据域',
    `data_item` VARCHAR(256) COMMENT '数据项',
    `business_object_code` VARCHAR(128) COMMENT '业务对象编号',
    `business_object_name` VARCHAR(512) COMMENT '业务对象名称',
    `description` TEXT COMMENT '实体描述',
    `source_file` VARCHAR(512) COMMENT '来源文件',
    `source_sheet` VARCHAR(256) COMMENT '来源工作表',
    `source_row` INT COMMENT '来源行号',
    `embedding_vector` LONGBLOB COMMENT 'SBERT语义向量',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_concept_entity` (`concept_entity_code`),
    KEY `idx_data_domain` (`data_domain`),
    KEY `idx_business_object` (`business_object_code`),
    FULLTEXT KEY `ft_entity_name` (`entity_name`, `description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 逻辑实体属性表（表单字段定义）
CREATE TABLE IF NOT EXISTS `ontology_logical_attributes` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `logical_entity_code` VARCHAR(128) NOT NULL COMMENT '所属逻辑实体编码',
    `attribute_name` VARCHAR(256) NOT NULL COMMENT '属性名',
    `attribute_code` VARCHAR(256) COMMENT '属性代码',
    `attribute_comment` TEXT COMMENT '注释',
    `data_type` VARCHAR(128) COMMENT '数据类型',
    `is_primary_key` TINYINT(1) DEFAULT 0 COMMENT '是否业务主键',
    `is_foreign_key` TINYINT(1) DEFAULT 0 COMMENT '是否外键',
    `is_not_null` TINYINT(1) DEFAULT 0 COMMENT '是否非空',
    `default_value` VARCHAR(512) COMMENT '默认值',
    `data_security_class` VARCHAR(128) COMMENT '数据安全分类',
    `data_security_level` VARCHAR(64) COMMENT '数据安全等级',
    `build_status` VARCHAR(64) COMMENT '建设状态',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_logical_entity` (`logical_entity_code`),
    KEY `idx_attribute_name` (`attribute_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 物理实体表（客观实体层 - Physical Layer）
CREATE TABLE IF NOT EXISTS `ontology_physical_entities` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `entity_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '物理实体编码',
    `entity_name` VARCHAR(512) NOT NULL COMMENT '物理实体名称',
    `logical_entity_code` VARCHAR(128) COMMENT '关联逻辑实体编码',
    `data_domain` VARCHAR(256) COMMENT '数据域',
    `table_schema` VARCHAR(256) COMMENT '所属数据库Schema',
    `table_name` VARCHAR(256) COMMENT '物理表名',
    `description` TEXT COMMENT '实体描述',
    `source_file` VARCHAR(512) COMMENT '来源文件',
    `source_sheet` VARCHAR(256) COMMENT '来源工作表',
    `source_row` INT COMMENT '来源行号',
    `embedding_vector` LONGBLOB COMMENT 'SBERT语义向量',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_logical_entity` (`logical_entity_code`),
    KEY `idx_data_domain` (`data_domain`),
    KEY `idx_table_name` (`table_name`(191)),
    FULLTEXT KEY `ft_entity_name` (`entity_name`, `description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 物理实体字段表（库表字段定义）
CREATE TABLE IF NOT EXISTS `ontology_physical_fields` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `physical_entity_code` VARCHAR(128) NOT NULL COMMENT '所属物理实体编码',
    `field_name` VARCHAR(256) NOT NULL COMMENT '字段名称',
    `field_code` VARCHAR(256) COMMENT '字段代码',
    `field_comment` TEXT COMMENT '注释',
    `data_type` VARCHAR(128) COMMENT '数据类型',
    `is_primary_key` TINYINT(1) DEFAULT 0 COMMENT '是否业务主键',
    `is_foreign_key` TINYINT(1) DEFAULT 0 COMMENT '是否外键',
    `is_not_null` TINYINT(1) DEFAULT 0 COMMENT '是否非空',
    `default_value` VARCHAR(512) COMMENT '默认值',
    `logical_attribute_id` BIGINT COMMENT '关联逻辑属性ID',
    `build_status` VARCHAR(64) COMMENT '建设状态',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_physical_entity` (`physical_entity_code`),
    KEY `idx_field_name` (`field_name`(191)),
    KEY `idx_logical_attribute` (`logical_attribute_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 三层实体关联表（层间穿透关系）
CREATE TABLE IF NOT EXISTS `ontology_layer_relations` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `source_layer` ENUM('concept', 'logical', 'physical') NOT NULL COMMENT '源层级',
    `source_entity_code` VARCHAR(128) NOT NULL COMMENT '源实体编码',
    `target_layer` ENUM('concept', 'logical', 'physical') NOT NULL COMMENT '目标层级',
    `target_entity_code` VARCHAR(128) NOT NULL COMMENT '目标实体编码',
    `relation_type` ENUM('derive', 'implement', 'compose', 'reference', 'associate') DEFAULT 'derive' COMMENT '关系类型',
    `relation_strength` DECIMAL(5,4) DEFAULT 1.0000 COMMENT '关联强度(0-1)',
    `mapping_method` ENUM('manual', 'rule', 'semantic', 'llm') DEFAULT 'manual' COMMENT '映射方法',
    `description` TEXT COMMENT '关系描述',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uniq_relation` (`source_layer`, `source_entity_code`, `target_layer`, `target_entity_code`),
    KEY `idx_source` (`source_layer`, `source_entity_code`),
    KEY `idx_target` (`target_layer`, `target_entity_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 第二部分：业务对象管理 (Business Object Management)
-- 从三层实体中抽取的核心业务对象（如项目、设备、合同等）
-- ============================================================================

-- 业务对象定义表
CREATE TABLE IF NOT EXISTS `business_objects` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `object_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '业务对象编号',
    `object_name` VARCHAR(512) NOT NULL COMMENT '业务对象名称',
    `object_type` ENUM('project', 'asset', 'contract', 'invoice', 'material', 'personnel', 'organization', 'document', 'process', 'other') DEFAULT 'other' COMMENT '对象类型',
    `object_category` VARCHAR(256) COMMENT '对象大类',
    `parent_object_code` VARCHAR(128) COMMENT '父对象编号(支持层级结构)',
    `description` TEXT COMMENT '对象描述',
    `data_items` JSON COMMENT '数据项列表',
    `business_constraints` JSON COMMENT '业务约束条件',
    `is_core_object` TINYINT(1) DEFAULT 0 COMMENT '是否核心对象',
    `source_process` VARCHAR(512) COMMENT '来源业务流程',
    `source_step` VARCHAR(512) COMMENT '来源业务步骤',
    `related_concept_entities` JSON COMMENT '关联概念实体列表',
    `related_logical_entities` JSON COMMENT '关联逻辑实体列表',
    `related_physical_entities` JSON COMMENT '关联物理实体列表',
    `embedding_vector` LONGBLOB COMMENT 'SBERT语义向量',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_object_type` (`object_type`),
    KEY `idx_object_category` (`object_category`(191)),
    KEY `idx_parent_object` (`parent_object_code`),
    KEY `idx_is_core` (`is_core_object`),
    FULLTEXT KEY `ft_object_name` (`object_name`, `description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 对象实例表（具体的业务对象实例）
CREATE TABLE IF NOT EXISTS `object_instances` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `instance_uid` VARCHAR(64) NOT NULL UNIQUE COMMENT '实例唯一标识',
    `object_code` VARCHAR(128) NOT NULL COMMENT '业务对象编号',
    `instance_name` VARCHAR(512) COMMENT '实例名称',
    `current_stage` VARCHAR(50) COMMENT '当前生命周期阶段',
    `status` ENUM('draft', 'active', 'suspended', 'completed', 'archived') DEFAULT 'draft' COMMENT '实例状态',
    `golden_attributes` JSON COMMENT '黄金属性集（融合后的权威属性）',
    `trust_score` DECIMAL(5,4) DEFAULT 1.0000 COMMENT '数据可信度(0-1)',
    `global_asset_uid` VARCHAR(64) COMMENT '关联全局资产UID(如有)',
    `source_entity_id` BIGINT COMMENT '关联EAV实体ID',
    `external_ids` JSON COMMENT '外部系统ID映射(如ERP编号、财务编号等)',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_object_code` (`object_code`),
    KEY `idx_current_stage` (`current_stage`),
    KEY `idx_status` (`status`),
    KEY `idx_global_asset` (`global_asset_uid`),
    KEY `idx_source_entity` (`source_entity_id`),
    CONSTRAINT `fk_instance_object` FOREIGN KEY (`object_code`)
        REFERENCES `business_objects` (`object_code`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 对象时态属性表（时态建模 - Temporal Modeling）
CREATE TABLE IF NOT EXISTS `object_temporal_attributes` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `instance_uid` VARCHAR(64) NOT NULL COMMENT '对象实例UID',
    `lifecycle_stage` VARCHAR(50) NOT NULL COMMENT '生命周期阶段',
    `attribute_name` VARCHAR(256) NOT NULL COMMENT '属性名称',
    `attribute_value` TEXT COMMENT '属性值',
    `attribute_type` VARCHAR(64) COMMENT '属性类型(text/number/datetime/bool/json)',
    `value_number` DECIMAL(20,6) COMMENT '数值型属性值(便于计算)',
    `value_datetime` DATETIME(6) COMMENT '日期型属性值',
    `value_json` JSON COMMENT 'JSON型属性值',
    `effective_from` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '生效开始时间',
    `effective_to` DATETIME(6) COMMENT '生效结束时间(NULL表示当前有效)',
    `source_type` ENUM('form', 'system', 'manual', 'calculated', 'inferred') DEFAULT 'form' COMMENT '数据来源类型',
    `source_reference` VARCHAR(512) COMMENT '数据来源引用(表单ID、系统名等)',
    `confidence` DECIMAL(5,4) DEFAULT 1.0000 COMMENT '属性值置信度',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_instance_stage` (`instance_uid`, `lifecycle_stage`),
    KEY `idx_attribute_name` (`attribute_name`(191)),
    KEY `idx_effective_time` (`effective_from`, `effective_to`),
    KEY `idx_source_type` (`source_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 对象关联关系表（对象间的业务关联）
CREATE TABLE IF NOT EXISTS `object_relations` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `source_instance_uid` VARCHAR(64) NOT NULL COMMENT '源对象实例UID',
    `target_instance_uid` VARCHAR(64) NOT NULL COMMENT '目标对象实例UID',
    `relation_type` ENUM('parent_child', 'compose', 'reference', 'derive', 'depend', 'associate', 'conflict') DEFAULT 'associate' COMMENT '关系类型',
    `relation_name` VARCHAR(256) COMMENT '关系名称(如"所属项目"、"采购合同"等)',
    `relation_attributes` JSON COMMENT '关系附加属性',
    `strength` DECIMAL(5,4) DEFAULT 1.0000 COMMENT '关联强度',
    `effective_from` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '关系生效时间',
    `effective_to` DATETIME(6) COMMENT '关系失效时间',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_source_instance` (`source_instance_uid`),
    KEY `idx_target_instance` (`target_instance_uid`),
    KEY `idx_relation_type` (`relation_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 第三部分：机理函数系统 (Mechanism Function System)
-- 业务规则、物理公式、校验规则等
-- ============================================================================

-- 机理函数定义表
CREATE TABLE IF NOT EXISTS `mechanism_functions` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `function_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '函数编号',
    `function_name` VARCHAR(512) NOT NULL COMMENT '函数名称',
    `function_type` ENUM('physical', 'business', 'validation', 'calculation', 'transformation', 'routing') DEFAULT 'business' COMMENT '函数类型',
    `category` VARCHAR(256) COMMENT '函数分类',
    `description` TEXT COMMENT '函数描述',
    `formula_expression` TEXT COMMENT '公式表达式(数学公式或规则表达式)',
    `formula_latex` TEXT COMMENT 'LaTeX格式公式(用于显示)',
    `input_parameters` JSON COMMENT '输入参数定义[{name, type, unit, description}]',
    `output_parameters` JSON COMMENT '输出参数定义[{name, type, unit, description}]',
    `python_code` TEXT COMMENT 'Python实现代码',
    `javascript_code` TEXT COMMENT 'JavaScript实现代码(前端校验)',
    `sql_expression` TEXT COMMENT 'SQL表达式(数据库层计算)',
    `applicable_objects` JSON COMMENT '适用的业务对象类型列表',
    `applicable_stages` JSON COMMENT '适用的生命周期阶段列表',
    `preconditions` JSON COMMENT '前置条件',
    `postconditions` JSON COMMENT '后置条件',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `version` VARCHAR(32) DEFAULT '1.0' COMMENT '版本号',
    `source_reference` TEXT COMMENT '来源参考(规范文件、标准等)',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_function_type` (`function_type`),
    KEY `idx_category` (`category`(191)),
    KEY `idx_is_active` (`is_active`),
    FULLTEXT KEY `ft_function_name` (`function_name`, `description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 业务规则表（从企业架构导入的规则）
CREATE TABLE IF NOT EXISTS `business_rules` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `rule_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '规则编号',
    `rule_name` VARCHAR(512) NOT NULL COMMENT '规则名称',
    `rule_type` ENUM('definition', 'judgment', 'calculation', 'inference', 'constraint', 'authorization', 'routing') DEFAULT 'judgment' COMMENT '规则分类',
    `rule_description` TEXT COMMENT '规则描述',
    `rule_details` JSON COMMENT '规则细则列表',
    `rule_elements` JSON COMMENT '规则要素[{name, logic, value, unit}]',
    `element_logic` ENUM('and', 'or', 'xor', 'not', 'custom') DEFAULT 'and' COMMENT '要素间逻辑关系',
    `result_value` TEXT COMMENT '判定结果值',
    `is_digitized` TINYINT(1) DEFAULT 0 COMMENT '是否已数字化实现',
    `mechanism_function_id` BIGINT COMMENT '关联机理函数ID(如已实现)',
    `supported_processes` JSON COMMENT '支撑的业务流程列表',
    `supported_steps` JSON COMMENT '支撑的业务步骤列表',
    `severity` ENUM('info', 'warning', 'error', 'critical') DEFAULT 'warning' COMMENT '违规严重程度',
    `source_file` VARCHAR(512) COMMENT '来源文件',
    `source_sheet` VARCHAR(256) COMMENT '来源工作表',
    `source_row` INT COMMENT '来源行号',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_rule_type` (`rule_type`),
    KEY `idx_is_digitized` (`is_digitized`),
    KEY `idx_severity` (`severity`),
    KEY `idx_is_active` (`is_active`),
    KEY `idx_mechanism_function` (`mechanism_function_id`),
    FULLTEXT KEY `ft_rule_name` (`rule_name`, `rule_description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 规则执行日志表（规则触发和执行记录）
CREATE TABLE IF NOT EXISTS `rule_executions` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `execution_uid` VARCHAR(64) NOT NULL UNIQUE COMMENT '执行唯一标识',
    `rule_code` VARCHAR(128) NOT NULL COMMENT '规则编号',
    `trigger_type` ENUM('auto', 'manual', 'scheduled', 'event') DEFAULT 'auto' COMMENT '触发方式',
    `trigger_event` VARCHAR(256) COMMENT '触发事件',
    `target_instance_uid` VARCHAR(64) COMMENT '目标对象实例UID',
    `input_data` JSON COMMENT '输入数据',
    `output_data` JSON COMMENT '输出数据',
    `result_status` ENUM('pass', 'fail', 'warning', 'error', 'skip') DEFAULT 'pass' COMMENT '执行结果',
    `result_message` TEXT COMMENT '结果消息',
    `execution_time_ms` INT COMMENT '执行耗时(毫秒)',
    `executed_by` VARCHAR(128) COMMENT '执行者(用户/系统)',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_rule_code` (`rule_code`),
    KEY `idx_target_instance` (`target_instance_uid`),
    KEY `idx_result_status` (`result_status`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 第四部分：穿透式查询系统 (Penetration Query System)
-- 实现从业务场景追溯到底层数据的全链路追溯
-- ============================================================================

-- 穿透路径定义表
CREATE TABLE IF NOT EXISTS `penetration_paths` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `path_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '路径编号',
    `path_name` VARCHAR(512) NOT NULL COMMENT '路径名称',
    `path_type` ENUM('vertical', 'horizontal', 'diagonal') DEFAULT 'vertical' COMMENT '穿透类型(垂直/水平/斜向)',
    `description` TEXT COMMENT '路径描述',
    `start_point` JSON COMMENT '起点定义{layer, entity_type, conditions}',
    `end_point` JSON COMMENT '终点定义{layer, entity_type, conditions}',
    `path_steps` JSON COMMENT '路径步骤列表[{step_order, from_layer, to_layer, relation_type, join_condition}]',
    `applicable_scenarios` JSON COMMENT '适用场景列表',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_path_type` (`path_type`),
    KEY `idx_is_active` (`is_active`),
    FULLTEXT KEY `ft_path_name` (`path_name`, `description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 穿透查询日志表
CREATE TABLE IF NOT EXISTS `penetration_queries` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `query_uid` VARCHAR(64) NOT NULL UNIQUE COMMENT '查询唯一标识',
    `query_type` ENUM('trace_up', 'trace_down', 'trace_horizontal', 'full_chain') DEFAULT 'full_chain' COMMENT '查询类型',
    `start_layer` ENUM('concept', 'logical', 'physical', 'object') COMMENT '起始层级',
    `start_entity_id` VARCHAR(128) COMMENT '起始实体ID',
    `end_layer` ENUM('concept', 'logical', 'physical', 'object') COMMENT '终止层级',
    `query_path_code` VARCHAR(128) COMMENT '使用的穿透路径编号',
    `query_conditions` JSON COMMENT '查询条件',
    `result_count` INT DEFAULT 0 COMMENT '结果数量',
    `result_summary` JSON COMMENT '结果摘要',
    `result_detail` LONGTEXT COMMENT '详细结果(大文本存储)',
    `execution_time_ms` INT COMMENT '执行耗时(毫秒)',
    `queried_by` VARCHAR(128) COMMENT '查询用户',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_query_type` (`query_type`),
    KEY `idx_start_layer` (`start_layer`),
    KEY `idx_query_path` (`query_path_code`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 第五部分：财务域监管应用 (Finance Domain Supervision)
-- 典型落地场景：基于财务域的穿透式监管
-- ============================================================================

-- 财务对象类型表（财务域特有的对象类型）
CREATE TABLE IF NOT EXISTS `finance_object_types` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `type_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '类型编号',
    `type_name` VARCHAR(256) NOT NULL COMMENT '类型名称',
    `parent_type_code` VARCHAR(128) COMMENT '父类型编号',
    `category` ENUM('asset', 'liability', 'equity', 'income', 'expense', 'project', 'budget', 'settlement', 'invoice', 'contract') COMMENT '财务大类',
    `standard_attributes` JSON COMMENT '标准属性定义',
    `validation_rules` JSON COMMENT '校验规则列表',
    `description` TEXT COMMENT '类型描述',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_category` (`category`),
    KEY `idx_parent_type` (`parent_type_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 财务结算追溯表（财务结算与业务数据的关联）
CREATE TABLE IF NOT EXISTS `finance_settlement_traces` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `settlement_uid` VARCHAR(64) NOT NULL COMMENT '结算单据UID',
    `settlement_type` VARCHAR(128) COMMENT '结算类型',
    `settlement_amount` DECIMAL(20,2) COMMENT '结算金额',
    `settlement_date` DATE COMMENT '结算日期',
    `project_instance_uid` VARCHAR(64) COMMENT '关联项目实例UID',
    `contract_instance_uid` VARCHAR(64) COMMENT '关联合同实例UID',
    `asset_instance_uid` VARCHAR(64) COMMENT '关联资产实例UID',
    `feasibility_reference` VARCHAR(512) COMMENT '可研概算引用',
    `procurement_reference` VARCHAR(512) COMMENT '采购合同引用',
    `construction_reference` VARCHAR(512) COMMENT '施工记录引用',
    `trace_chain` JSON COMMENT '完整追溯链路',
    `validation_status` ENUM('pending', 'validated', 'warning', 'error') DEFAULT 'pending' COMMENT '勾稽校验状态',
    `validation_details` JSON COMMENT '校验详情',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_settlement_type` (`settlement_type`),
    KEY `idx_project_instance` (`project_instance_uid`),
    KEY `idx_contract_instance` (`contract_instance_uid`),
    KEY `idx_validation_status` (`validation_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 财务审计红线表（预警规则）
CREATE TABLE IF NOT EXISTS `finance_audit_redlines` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `redline_code` VARCHAR(128) NOT NULL UNIQUE COMMENT '红线编号',
    `redline_name` VARCHAR(512) NOT NULL COMMENT '红线名称',
    `redline_type` ENUM('amount', 'ratio', 'count', 'time', 'process', 'approval') DEFAULT 'amount' COMMENT '红线类型',
    `threshold_value` DECIMAL(20,6) COMMENT '阈值',
    `threshold_unit` VARCHAR(64) COMMENT '阈值单位',
    `comparison_operator` ENUM('gt', 'gte', 'lt', 'lte', 'eq', 'neq', 'between', 'in') DEFAULT 'gt' COMMENT '比较运算符',
    `threshold_range` JSON COMMENT '阈值范围(用于between/in)',
    `applicable_objects` JSON COMMENT '适用对象类型',
    `trigger_action` JSON COMMENT '触发动作{action_type, action_params}',
    `severity` ENUM('info', 'warning', 'error', 'critical') DEFAULT 'warning' COMMENT '严重程度',
    `description` TEXT COMMENT '规则描述',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_redline_type` (`redline_type`),
    KEY `idx_severity` (`severity`),
    KEY `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 财务预警记录表
CREATE TABLE IF NOT EXISTS `finance_alerts` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `alert_uid` VARCHAR(64) NOT NULL UNIQUE COMMENT '预警唯一标识',
    `redline_code` VARCHAR(128) COMMENT '触发的红线编号',
    `rule_code` VARCHAR(128) COMMENT '触发的规则编号',
    `alert_type` ENUM('redline', 'rule', 'anomaly', 'consistency') DEFAULT 'rule' COMMENT '预警类型',
    `severity` ENUM('info', 'warning', 'error', 'critical') DEFAULT 'warning' COMMENT '严重程度',
    `target_instance_uid` VARCHAR(64) COMMENT '涉及对象实例UID',
    `alert_title` VARCHAR(512) NOT NULL COMMENT '预警标题',
    `alert_message` TEXT COMMENT '预警详情',
    `current_value` TEXT COMMENT '当前值',
    `expected_value` TEXT COMMENT '期望值/阈值',
    `trace_info` JSON COMMENT '追溯信息',
    `status` ENUM('open', 'acknowledged', 'investigating', 'resolved', 'ignored') DEFAULT 'open' COMMENT '处理状态',
    `handled_by` VARCHAR(128) COMMENT '处理人',
    `handled_at` DATETIME(6) COMMENT '处理时间',
    `resolution_notes` TEXT COMMENT '处理备注',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_redline_code` (`redline_code`),
    KEY `idx_rule_code` (`rule_code`),
    KEY `idx_alert_type` (`alert_type`),
    KEY `idx_severity` (`severity`),
    KEY `idx_status` (`status`),
    KEY `idx_target_instance` (`target_instance_uid`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 初始化财务域示例数据
-- ============================================================================

-- 插入常用财务审计红线
INSERT IGNORE INTO `finance_audit_redlines`
    (`redline_code`, `redline_name`, `redline_type`, `threshold_value`, `threshold_unit`, `comparison_operator`, `applicable_objects`, `trigger_action`, `severity`, `description`)
VALUES
    ('FR001', '合同金额超300万审计红线', 'amount', 3000000.00, 'CNY', 'gt',
     '["contract"]',
     '{"action_type": "require_approval", "action_params": {"approval_level": "director", "notify_audit": true}}',
     'warning', '合同金额超过300万元需要总监审批并通知审计部门'),
    ('FR002', '单笔付款超100万审批红线', 'amount', 1000000.00, 'CNY', 'gt',
     '["payment", "settlement"]',
     '{"action_type": "require_approval", "action_params": {"approval_level": "cfo"}}',
     'warning', '单笔付款金额超过100万元需要CFO审批'),
    ('FR003', '项目超预算10%预警', 'ratio', 0.10, 'ratio', 'gt',
     '["project"]',
     '{"action_type": "alert", "action_params": {"notify_roles": ["project_manager", "finance_manager"]}}',
     'warning', '项目实际支出超过预算10%时触发预警'),
    ('FR004', '结算周期超90天预警', 'time', 90, 'days', 'gt',
     '["settlement"]',
     '{"action_type": "alert", "action_params": {"notify_roles": ["finance_manager"]}}',
     'warning', '结算周期超过90天需要关注');

-- 插入常用财务对象类型
INSERT IGNORE INTO `finance_object_types`
    (`type_code`, `type_name`, `category`, `standard_attributes`, `description`)
VALUES
    ('FIN_PROJECT', '数字化项目', 'project',
     '[{"name": "项目编号", "type": "string", "required": true}, {"name": "项目名称", "type": "string", "required": true}, {"name": "项目预算", "type": "number", "unit": "CNY"}, {"name": "立项日期", "type": "date"}, {"name": "预计完成日期", "type": "date"}]',
     '数字化建设项目'),
    ('FIN_CONTRACT', '采购合同', 'contract',
     '[{"name": "合同编号", "type": "string", "required": true}, {"name": "合同名称", "type": "string", "required": true}, {"name": "合同金额", "type": "number", "unit": "CNY"}, {"name": "签订日期", "type": "date"}, {"name": "供应商", "type": "string"}]',
     '采购合同'),
    ('FIN_SETTLEMENT', '结算单据', 'settlement',
     '[{"name": "结算编号", "type": "string", "required": true}, {"name": "结算金额", "type": "number", "unit": "CNY"}, {"name": "结算日期", "type": "date"}, {"name": "关联合同", "type": "reference"}, {"name": "关联项目", "type": "reference"}]',
     '财务结算单据'),
    ('FIN_ASSET', '固定资产', 'asset',
     '[{"name": "资产编号", "type": "string", "required": true}, {"name": "资产名称", "type": "string", "required": true}, {"name": "资产原值", "type": "number", "unit": "CNY"}, {"name": "入账日期", "type": "date"}, {"name": "使用部门", "type": "string"}]',
     '固定资产');

-- ============================================================================
-- 完成提示
-- ============================================================================
SELECT '对象生命周期管理器 (OLM) Schema 初始化完成!' AS message;
SELECT CONCAT('创建表数量: ', COUNT(*)) AS table_count FROM information_schema.tables
WHERE table_schema = 'eav_db' AND table_name LIKE 'ontology_%'
   OR table_name LIKE 'business_%'
   OR table_name LIKE 'object_%'
   OR table_name LIKE 'mechanism_%'
   OR table_name LIKE 'penetration_%'
   OR table_name LIKE 'finance_%'
   OR table_name LIKE 'rule_%';
