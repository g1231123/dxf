-- 为已存在的 dxf_template 表添加 is_official 字段
-- 执行时间：2026-05-27

ALTER TABLE `dxf_template` 
ADD COLUMN `is_official` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否官方模板：0=用户上传，1=官方上传' AFTER `extent_max_y`,
ADD INDEX `idx_is_official` (`is_official`);
