# MEM-BASE-01：SuperBrain 离线回归测试基线

- 日期：2026-08-25
- 状态：DONE
- 服务端基线：`fa8fd06ce80b` + 当前未提交测试
- 测试环境：Windows，Python 3.14.7
- 生产推荐版本：Python 3.10；后续 CI/服务环境需再跑同一命令

## 实现

新增标准库 `unittest` 测试：

- `main/xiaozhi-server/tests/test_superbrain_native.py`
- `main/xiaozhi-server/tests/test_manage_api_client_memory.py`

测试通过桩替换日志、LLM 和 manager-api 边界，不连接网络、数据库或真实模型，不读取真实记忆目录。

## 覆盖

1. 普通、Markdown fenced 和嵌入文本中的画像 JSON 提取。
2. working memory 字段规范化和未知字段丢弃。
3. 不同设备的用户目录隔离及根目录边界。
4. 文本/JSON 临时文件 + replace 原子写入，无 `.tmp` 残留。
5. 画像更新保留旧字段、更新新字段并固定当前设备身份。
6. 同一轮对话的 working/episodic 快照幂等。
7. 同一对话重复保存只调用一次 LLM 和一次画像 upsert。
8. LLM 异常不向上抛出，并保留原始对话快照。
9. Python 画像 snake_case 到 Java DTO camelCase 的完整 payload 契约。
10. manager-api client 未初始化时 upsert 安全 no-op。

## 命令和结果

```powershell
cd main/xiaozhi-server
python -m unittest discover -s tests -p 'test_*.py' -v
```

最终结果：`Ran 10 tests in 0.829s`，`OK`。

第一次加入 API 契约测试时，Codex 系统 Python 未安装生产依赖 `httpx`。测试改为仅在缺少 `httpx` 时注入最小类型桩；生产代码不变。在完整服务端环境中会使用真实 `httpx` 模块。

## 未覆盖与下一步

- MySQL/Liquibase 空库、升级库和重复启动迁移：转 `MEM-DB-01`。
- 真 LLM 输出质量、网络重试与 manager-api 真连接：后续集成测试。
- 多进程、崩溃恢复和大规模画像性能：试产加固阶段。
- Python 3.10 回归：服务端实际环境/CI 执行。

测试产生的 `__pycache__` 已删除，可重新生成，不需要恢复。

