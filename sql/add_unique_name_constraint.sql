-- 为 dxf_template 表的 name 字段添加唯一约束
-- 确保模板名称不重复

-- 先删除原有的普通索引
ALTER TABLE `dxf_template` DROP INDEX IF EXISTS `idx_name`;

-- 添加唯一索引
ALTER TABLE `dxf_template` ADD UNIQUE INDEX `uk_name` (`name`);
