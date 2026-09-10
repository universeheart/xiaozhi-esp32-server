ALTER TABLE `ai_agent`
ADD COLUMN `additional_prompt` LONGTEXT NULL COMMENT '角色附加提示词' AFTER `system_prompt`;
