-- DXF 模板表
-- 数据库: draw_design

CREATE TABLE IF NOT EXISTS `dxf_template` (
    `id` VARCHAR(64) NOT NULL COMMENT '模板ID (UUID)',
    `name` VARCHAR(255) NOT NULL COMMENT '模板名称（用户自定义或默认文件名）',
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
    `is_official` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否官方模板：0=用户上传，1=官方上传',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_name` (`name`),
    INDEX `idx_original_filename` (`original_filename`),
    INDEX `idx_is_official` (`is_official`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DXF 模板表';
