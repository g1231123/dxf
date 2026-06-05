-- ============================================
-- DXF 模板服务完整数据库迁移脚本
-- 执行顺序：从上到下依次执行
-- ============================================

-- 1. 创建 dxf_template 表（如果不存在）
CREATE TABLE IF NOT EXISTS `dxf_template` (
    `id` VARCHAR(64) NOT NULL COMMENT '模板ID (UUID)',
    `name` VARCHAR(255) NOT NULL COMMENT '模板名称',
    `original_filename` VARCHAR(255) NOT NULL COMMENT '原始文件名',
    `file_url` VARCHAR(512) NOT NULL COMMENT '原始文件的 MinIO URL',
    `template_url` VARCHAR(512) NOT NULL COMMENT '模板 JSON 的 MinIO URL',
    `dxf_version` VARCHAR(32) DEFAULT NULL COMMENT 'DXF 版本',
    `layer_count` INT DEFAULT 0 COMMENT '图层数量',
    `block_count` INT DEFAULT 0 COMMENT '块数量',
    `entity_count` INT DEFAULT 0 COMMENT '实体数量',
    `extent_min_x` DOUBLE DEFAULT NULL COMMENT '范围最小X',
    `extent_min_y` DOUBLE DEFAULT NULL COMMENT '范围最小Y',
    `extent_max_x` DOUBLE DEFAULT NULL COMMENT '范围最大X',
    `extent_max_y` DOUBLE DEFAULT NULL COMMENT '范围最大Y',
    `is_official` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否官方模板：0=用户，1=官方',
    `status` VARCHAR(32) NOT NULL DEFAULT 'ready' COMMENT '处理状态：processing=处理中，ready=就绪，failed=失败',
    `params_count` INT DEFAULT 0 COMMENT '可编辑参数数量',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_name` (`name`),
    INDEX `idx_original_filename` (`original_filename`),
    INDEX `idx_is_official` (`is_official`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DXF模板表';


-- 2. 如果表已存在，添加缺失的字段
-- 添加 is_official 字段（如果不存在）
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'dxf_template' 
    AND COLUMN_NAME = 'is_official'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `dxf_template` ADD COLUMN `is_official` TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''是否官方模板：0=用户，1=官方'' AFTER `extent_max_y`, ADD INDEX `idx_is_official` (`is_official`)',
    'SELECT ''Column is_official already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- 添加 status 字段（如果不存在）
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'dxf_template' 
    AND COLUMN_NAME = 'status'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `dxf_template` ADD COLUMN `status` VARCHAR(32) NOT NULL DEFAULT ''ready'' COMMENT ''处理状态：processing=处理中，ready=就绪，failed=失败'' AFTER `is_official`, ADD INDEX `idx_status` (`status`)',
    'SELECT ''Column status already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- 添加 params_count 字段（如果不存在）
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'dxf_template' 
    AND COLUMN_NAME = 'params_count'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `dxf_template` ADD COLUMN `params_count` INT DEFAULT 0 COMMENT ''可编辑参数数量'' AFTER `status`',
    'SELECT ''Column params_count already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- 3. 创建可编辑参数表
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
    INDEX `idx_type` (`entity_type`),
    FOREIGN KEY (`template_id`) REFERENCES `dxf_template`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DXF模板可编辑参数表';


-- 4. 验证表结构
SELECT 
    'dxf_template' AS table_name,
    COUNT(*) AS column_count
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = DATABASE() 
AND TABLE_NAME = 'dxf_template'

UNION ALL

SELECT 
    'dxf_editable_params' AS table_name,
    COUNT(*) AS column_count
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = DATABASE() 
AND TABLE_NAME = 'dxf_editable_params';


-- 5. 显示表结构
SHOW CREATE TABLE `dxf_template`;
SHOW CREATE TABLE `dxf_editable_params`;


-- ============================================
-- 迁移完成
-- ============================================
