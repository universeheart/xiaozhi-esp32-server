ALTER TABLE `ai_agent`
ADD COLUMN `additional_prompt` LONGTEXT NULL COMMENT '角色个性特色' AFTER `system_prompt`;

