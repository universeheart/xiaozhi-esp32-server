-- 新增 SuperBrain 原生记忆模型供应器
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_Memory_superbrain';
DELETE FROM `ai_model_config` WHERE `id` = 'Memory_superbrain';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES (
  'SYSTEM_Memory_superbrain',
  'Memory',
  'superbrain_native',
  'SuperBrain',
  '[{"key":"llm","label":"LLM模型","type":"string"}]',
  6,
  1,
  NOW(),
  1,
  NOW()
);

-- 新增 SuperBrain 记忆模型配置
INSERT INTO `ai_model_config` VALUES (
  'Memory_superbrain',
  'Memory',
  'superbrain_native',
  'SuperBrain',
  0,
  1,
  '{"type": "superbrain_native", "llm": ""}',
  NULL,
  'SuperBrain 原生记忆，默认使用当前选中的主LLM，也可以配置记忆总结专用LLM',
  6,
  NULL,
  NULL,
  NULL,
  NULL
);

UPDATE `ai_model_config` SET
`remark` = 'SuperBrain 原生记忆说明：
1. 使用当前选中的默认大模型进行记忆总结。
2. 也可以在 llm 字段中指定独立的 LLM 模型作为记忆总结模型。
3. 本地配置模式下会保存到 data/.superbrain_memory.yaml。
4. 接入 manager-api 时沿用现有聊天总结保存流程。',
`doc_link` = NULL
WHERE `id` = 'Memory_superbrain';
