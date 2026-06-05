-- 为 dxf_template 表添加处理状态字段
ALTER TABLE `dxf_template` 
ADD COLUMN `status` VARCHAR(32) NOT NULL DEFAULT 'ready' COMMENT '处理状态：processing=处理中，ready=就绪，failed=失败' AFTER `is_official`,
ADD COLUMN `params_count` INT DEFAULT 0 COMMENT '可编辑参数数量' AFTER `status`;
