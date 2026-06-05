-- 创建可编辑参数表
CREATE TABLE IF NOT EXISTS `dxf_editable_params` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '参数ID',
    `template_id` VARCHAR(64) NOT NULL COMMENT '模板ID',
    `entity_handle` VARCHAR(32) NOT NULL COMMENT '实体句柄',
    `entity_type` VARCHAR(32) NOT NULL COMMENT '实体类型（LINE/CIRCLE/TEXT等）',
    `layer` VARCHAR(255) DEFAULT NULL COMMENT '所属图层',
    `param_name` VARCHAR(64) NOT NULL COMMENT '参数名（start/end/radius/text等）',
    `param_value` TEXT NOT NULL COMMENT '当前值（JSON格式）',
    `param_type` VARCHAR(32) NOT NULL COMMENT '参数类型（point/number/string等）',
    `constraints` TEXT DEFAULT NULL COMMENT '约束条件（JSON格式：min/max/options等）',
    `description` VARCHAR(255) DEFAULT NULL COMMENT '参数说明',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX `idx_template_id` (`template_id`),
    INDEX `idx_handle` (`entity_handle`),
    INDEX `idx_layer` (`layer`),
    INDEX `idx_type` (`entity_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DXF模板可编辑参数表';
