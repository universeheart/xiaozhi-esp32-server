# UPD-01：服务端更新与长期记忆基线评估

- 日期：2026-08-24
- 状态：DONE（构建验证转 BLD-S-01）
- 仓库：`Projects/xiaozhi-esp32-server`
- 旧基线：`b903a88cd500`
- 新 HEAD：`fa8fd06ce80b`
- 分支：`main`，与 `origin/main` 一致

## 更新范围

旧基线之后新增 4 个 commit：

- `5cc9bcc7`：SuperBrain memory module
- `c791c7c7`：Python 依赖版本调整
- `b2d74845`：记忆提示词优化
- `fa8fd06c`：记忆实现和用户结构化数据存储/更新

合计 27 个文件，约新增 1514 行、删除 52 行。主要增加：

- `superbrain_native` Memory Provider；
- 本地 profile、semantic、procedural、episodic、working memory 文件；
- `memory_profile` 数据表和 manager-api upsert；
- 记忆专用 LLM 配置与管理后台选择；
- 会话过程中的记忆查询和异步保存；
- Gemini Provider 调整。

## 配置冲突处理结果

`main/manager-api/src/main/resources/application-dev.yml` 最初为 Git `UU`，但复核证明：

- 当前文件无冲突标记；
- 当前、ours、theirs 三个版本均有 50 个 YAML 键路径；
- 当前文件未缺少 ours/theirs 的任何键，新版没有新增键需要补入；
- 仓库无 merge/rebase/cherry-pick 进行中，HEAD 与 `origin/main` 一致；属于更新后恢复本地配置留下的孤立 unmerged index。

已执行“标记 resolved 后立即取消暂存”，文件内容 blob 前后相同。最终状态：普通未暂存 `M application-dev.yml`，unmerged 0，staged 0。数据库密码仍只在本地工作文件中，不因本次处理进入暂存区。

## 可复用结论

- Provider 扩展方式符合现有服务框架，可保留。
- 文件写入采用临时文件 + `os.replace`，单文件更新具备原子性。
- `threading.Lock` 串行同设备保存，可降低旧快照覆盖新快照风险。
- manager-api 入口使用现有 `server` 过滤器，不是匿名公网接口。
- 模型输出要求 JSON，结构化字段可作为后续标准模型的迁移输入。

## 与产品目标的差距

1. `memory_profile` 以 `mac_address` 唯一，只能表达一设备一画像，不支持一个主用户下多个声纹子用户。
2. MAC 被同时当用户身份和数据归属键；后续应迁移到 `device_id + person_profile_id`，MAC 只做硬件属性。
3. 本地 `.superbrain_mem` 与数据库 `profile_md` 形成双事实源，尚无明确主从、版本和冲突恢复规则。
4. 画像是覆盖式快照，缺少来源消息、置信度、有效期、替代关系、纠正/删除和审计。
5. `profile_md` 包含完整长期画像，缺少字段级敏感分类和最小化存储。
6. 未找到 SuperBrain/Memory 专项自动测试；迁移、并发、模型异常和重复保存没有回归证据。
7. 记忆查询仍可能调用同步 LLM，需要测量是否阻塞主对话事件循环和首包延迟。
8. 新增 migration 使用固定历史时间 ID，需在空库和已运行库验证 Liquibase 执行顺序及重复部署行为。

## 建议执行顺序

1. ~~`UPD-01A`：检查并处理 `application-dev.yml` 冲突，不输出 Secret。~~ DONE
2. ~~`UPD-01B`：确认工作树只剩用户明确保留的本地配置。~~ DONE
3. `BLD-S-01`：构建 Python 服务、manager-api、manager-web，记录依赖与命令。
4. `MEM-BASE-01`：增加离线单元/契约测试，覆盖用户目录隔离、JSON 解析、重复快照、原子更新、LLM 异常和 API payload。
5. `MEM-DB-01`：空库/升级库迁移演练，检查 `memory_profile` upsert 和回滚/补偿。
6. `MEM-ARCH-01`：设计兼容层，把现有 MAC 画像映射到 `person_profile`/`ai_memory_item`；一期先复用，不立即重写 Provider。
7. 完成上述工作后，再进入 `SEC-01` 全仓安全整改和 Android/对话链路开发。

## 当前结论

冲突收口已完成，新代码可以作为“长期记忆原型候选基线”。下一步由用户执行全模块构建/启动并反馈，随后 Codex分析结果并进入记忆专项测试。暂不删除或重写现有 SuperBrain 实现。

