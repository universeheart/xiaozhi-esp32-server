-- 将 SuperBrain 的 llm 字段渲染为大语言模型下拉选择
UPDATE `ai_model_provider`
SET `fields` = '[{"key":"llm","label":"LLM模型","type":"llm"}]'
WHERE `id` = 'SYSTEM_Memory_superbrain';
