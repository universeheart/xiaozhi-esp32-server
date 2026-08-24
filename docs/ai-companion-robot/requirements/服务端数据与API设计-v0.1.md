# 服务端数据与 API 设计

> 版本：v0.1（2026-08-22 补充已确认决策）  
> 基线：`xiaozhi-esp32-server` 本地 commit `b903a88c`。  
> 目标：在保留现有 `ai_device`、`ai_agent`、`ai_agent_chat_history`、`ai_agent_voice_print` 和 `sys_user` 的基础上，支持一期范围。

## 1. 现有模型评估

### 1.1 可保留

- `sys_user`：家属/普通登录用户及平台用户的身份基表。
- `ai_device`：物理机器人主表；保留 `mac_address`、`agent_id`、版本和最后连接时间。
- `ai_agent`：机器人智能体和模型选择；保留 ASR/VAD/LLM/TTS/Memory/Intent 配置。
- `ai_agent_chat_history`：现有对话文本主表。
- `ai_agent_chat_audio`：仅测试环境保存音频。
- `ai_agent_voice_print`：声纹注册资料起点。
- 现有 model/provider、纠错词、知识库和 OTA 表暂时保留。

### 1.2 必须修正的结构限制

1. `ai_device.user_id` 只能表达单用户，不能支持家属—设备多对多绑定。
2. `ai_agent.system_prompt` 是可覆盖文本，无法提供草稿、审批、灰度和回滚。
3. `ai_agent.summary_memory` 是单一字符串，不能做事实级来源、冲突、纠正和删除。
4. `ai_agent_chat_history` 缺少 turn、说话人、模型/Prompt 版本、Trace 和幂等 ID。
5. Android 与 ESP32 状态没有分离，无法识别“主机在线但传感器故障”。
6. 缺少提醒、主动对话策略、LINE 绑定、告警和管理审计实体。

### 1.3 编码前安全修正

- 当前 `/device/register` 使用 `Math.random()` 生成 6 位码；应改为密码学安全随机数、短 TTL、单次使用、尝试次数限制和按设备/IP 限流。
- 当前 `/agent/saveMemory/{macAddress}`、聊天总结和标题生成接口未见用户权限注解；不得以现状暴露到公网，应改为服务间鉴权或受保护内部 API。
- 当前普通用户接口可读取智能体聊天历史，而一期需求是只有平台管理员可查看；权限必须收紧。
- 音频播放临时 URL 需极短 TTL、单次使用并校验管理员权限；禁止仅凭可猜/泄露 URL 长期访问。
- 不在 URL 路径中使用 MAC 作为授权依据；MAC 不是 Secret。
- 家属身份支持邮箱一次性验证码和 LINE Login；一期不支持手机号或邮箱密码。邮箱验证码须短时有效、单次使用、限流并防账号枚举。LINE Login 身份与 Messaging API 的通知绑定应分表管理，不能假定两个 channel 下的 user ID 可直接互换。

## 2. 标识和通用字段

- 业务主键新增表统一使用 UUID/ULID 字符串；现有自增表不强制重建。
- API 对外使用 `deviceId`，MAC 仅作为硬件属性，不作为公共主键。
- 所有可变业务表包含 `created_at/created_by/updated_at/updated_by/version`。
- 乐观锁使用 `version`；删除优先软删除 `deleted_at`，隐私删除任务再物理清理。
- 时间存 UTC；提醒额外保存 IANA 时区，默认 `Asia/Tokyo`。
- JSON 字段只存扩展/快照，不用 JSON 替代需要索引、约束和关联的核心列。

## 3. 新增与变更表

### 3.1 设备与用户

#### `ai_device` 变更

新增：

| 字段 | 类型 | 说明 |
|---|---|---|
| `primary_profile_id` | varchar(36) nullable | 老人主资料 |
| `device_secret_version` | int | 凭据轮换版本 |
| `status` | varchar(20) | PROVISIONING/ACTIVE/SUSPENDED/DISABLED |
| `region` | varchar(10) | `JP` |
| `timezone` | varchar(50) | `Asia/Tokyo` |
| `config_version` | bigint | 最新配置版本 |

现有 `user_id` 在迁移期作为原始 owner 保留；新代码读取绑定表。完成数据迁移后再决定是否废弃。

#### `ai_device_user_binding`

| 字段 | 说明 |
|---|---|
| `id` | UUID |
| `device_id` / `user_id` | 设备与家属 |
| `role` | 一期固定 `ADMIN`，保留 VIEWER |
| `status` | PENDING/ACTIVE/REVOKED |
| `source` | APP/LINE/ADMIN/MIGRATION |
| `bound_at` / `revoked_at` | 生命周期 |

约束：唯一 `(device_id,user_id)`；至少保留一个 ACTIVE 管理员，除非执行恢复出厂。

#### `ai_person_profile`

表达实际对话人，不等同登录账号：

| 字段 | 说明 |
|---|---|
| `id` / `device_id` / `agent_id` | 关联 |
| `profile_type` | PRIMARY/SUB |
| `display_name` | 称呼 |
| `language` / `dialect` | zh-CN、东北方言等 |
| `voiceprint_id` | 可空，关联现有声纹 |
| `status` | ACTIVE/ARCHIVED |

唯一约束：每设备最多一个 ACTIVE PRIMARY。

### 3.2 设备状态和配置

#### `ai_device_component_state`

一设备多组件当前态：

| 字段 | 说明 |
|---|---|
| `device_id` + `component` | 唯一；ANDROID/ESP32/RADAR/AUDIO/MOTION |
| `online` / `health` | ONLINE/OFFLINE，OK/DEGRADED/FAULT |
| `version` | App/固件/协议版本 |
| `last_seen_at` | 最后心跳 |
| `state_json` | 电量、网络、温度、错误位等快照 |

当前态存 MySQL，短期高频心跳先写 Redis 并按状态变化/固定周期落库。

#### `ai_device_config`

| 字段 | 说明 |
|---|---|
| `device_id` / `config_key` | 唯一配置键 |
| `desired_value_json` | 云端期望值 |
| `reported_value_json` | Android 实际值 |
| `source_type/source_id` | ELDER_VOICE/FAMILY_APP/LINE/ADMIN/DEFAULT |
| `version` | 单调递增 |
| `applied_at/error_code` | 应用结果 |

配置优先级：平台安全上下限不可覆盖；其它同一配置键采用“最后一次已授权显式修改生效”。老人语音、家属 App 和 LINE 均可后续覆盖，但必须记录来源。客户端 PATCH 必须携带 `If-Match/version` 防止无提示覆盖。

授权规则：语音可改低风险偏好；账号、设备所有权、安全联系人、恢复出厂、长期数据导出/删除等敏感操作必须使用家属 App/后台强认证和二次确认。声纹只提供个性化上下文，不作为敏感操作的单一认证因子。

#### `ai_device_event`

保存低频重要事件，不保存全部 DOA 高频流：`event_id` 唯一、设备、组件、事件类型、严重度、发生/接收时间、负载和处理状态。DOA 只采样指标，告警必须持久化。

### 3.3 人设和 Prompt

#### `ai_persona_profile`

| 字段 | 说明 |
|---|---|
| `device_id` / `person_profile_id` | 作用范围 |
| `dialect_level` / `humor_level` | 0–100 |
| `novel_vocabulary_level` / `initiative_level` | 0–100 |
| `response_length` / `empathy_level` | 0–100 |
| `effective_config_json` | 最终离散规则快照 |

#### `ai_prompt_release`

| 字段 | 说明 |
|---|---|
| `id` / `name` / `semantic_version` | 版本身份 |
| `template_text` / `variables_schema_json` | 模板与变量约束 |
| `status` | DRAFT/TESTING/PUBLISHED/RETIRED |
| `checksum` | 防止内容漂移 |
| `published_at/published_by` | 发布审计 |
| `parent_release_id` | 来源版本 |

#### `ai_prompt_assignment`

作用目标 `GLOBAL/DEVICE_GROUP/DEVICE`、目标 ID、release ID、生效时间和灰度百分比。优先级 `DEVICE > DEVICE_GROUP > GLOBAL`。

### 3.4 对话和音频

#### `ai_agent_chat_history` 变更

新增：

| 字段 | 说明 |
|---|---|
| `message_id` | UUID 唯一，报告重试幂等 |
| `turn_id` | 同一用户问答轮次 |
| `device_id` | 不再只靠 MAC |
| `person_profile_id` | 实际/推断说话人，可空 |
| `trace_id` | 可观测链路 |
| `prompt_release_id` | 实际 Prompt |
| `model_snapshot_json` | ASR/LLM/TTS 名称、版本、地区 |
| `asr_confidence` | 用户消息可用 |
| `emotion_json` / `safety_labels_json` | 派生结果 |
| `source` | VOICE/TEXT/PROACTIVE/REMINDER |

索引：`(device_id,created_at)`、`(session_id,created_at)`、`turn_id`、`person_profile_id`；内容列不得建立普通全文日志副本。

#### `ai_agent_chat_audio` 变更

增加 `environment`、`capture_reason`、`expires_at`、`delete_status`。生产环境应用层强制拒绝写入；测试音频清理采用任务状态而不是直接在请求线程删除大对象。

### 3.5 记忆和声纹

#### `ai_memory_item`

| 字段 | 说明 |
|---|---|
| `id` / `device_id` / `person_profile_id` | 归属 |
| `memory_type` | PROFILE/RELATION/PREFERENCE/EVENT/HABIT/STORY |
| `subject/predicate/object_text` | 结构化事实 |
| `normalized_json` | 日期、地点等结构化值 |
| `confidence/importance` | 0–1 |
| `source_message_id` | 证据轮次 |
| `valid_from/valid_to` | 时间范围 |
| `status` | ACTIVE/SUPERSEDED/DELETED |
| `last_accessed_at` | 检索/遗忘策略 |

`ai_agent.summary_memory` 暂时保留为兼容缓存，由结构化记忆生成，不作为唯一事实源。

声纹表新增 `person_profile_id`、`provider`、`provider_version`、`enrollment_status`、`quality_score`；声纹向量/音频应与普通聊天音频分开权限和保留规则。

### 3.6 提醒和主动对话

#### `ai_reminder`

`device_id`、标题、规则类型、`scheduled_at_utc`、时区、RRULE、启用、来源、下次触发、最后触发和版本。触发记录单独进入 `ai_reminder_execution`，唯一 `(reminder_id,scheduled_for)` 防重复。

#### `ai_proactive_policy`

设备级免打扰、夜间时段、空闲阈值、每日上限、最小间隔、需在场标记和启用状态。

### 3.7 LINE 和告警

#### `ai_line_binding`

`user_id`、LINE user ID（应用层加密/脱敏展示）、状态、link nonce、关注/阻止状态、绑定/解除时间。Channel access token 不存本表，进入 Secret 管理。

#### `ai_alert`

`id`、唯一 `event_id`、设备、类型、严重度、状态、发生/接收/确认/解决时间、证据 JSON、确认人和解决备注。

#### `ai_alert_delivery`

每个告警×接收人一条：渠道、目标绑定、状态、尝试次数、`retry_key`、平台 message ID、最后错误和发送/送达时间。

### 3.8 审计

`ai_audit_log`：actor type/id、action、resource type/id、before/after 的脱敏差异、来源 IP/客户端、trace ID、时间和结果。禁止记录密码、Token、完整音频或无必要的完整对话正文。

### 3.9 日本公共与本地生活信息

- `ai_information_source`：来源登记、权威等级、准入状态、许可/署名、覆盖、配置版本和 Secret 引用。
- `ai_information_item`：统一事实、来源事件 ID、地理范围、有效期、发布时间、获取时间、哈希、更正/取消关系。
- `ai_information_fetch_run`：采集结果、延迟、解析版本、计数和脱敏错误。
- `ai_information_subscription`：设备、类别、位置/阈值、时间、频率和启用状态。
- `ai_information_delivery`：候选、触发原因、播报/跳过结果和幂等键。

字段、索引、来源准入和缓存规则见《日本公共与本地生活信息服务详细设计-v0.1.md》。事实不得与方言/幽默等表达偏好混存。

## 4. REST API 分组

新接口统一 `/api/v1`；现有接口在兼容期保留，内部逐步迁移。

### 4.1 设备身份与机器人端

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/device-activations` | 设备凭据换一次性绑定码 |
| POST | `/api/v1/device-sessions` | 设备凭据换短期 Token |
| POST | `/api/v1/devices/{id}/components/{component}/heartbeat` | Android/ESP32 心跳 |
| POST | `/api/v1/devices/{id}/events:batch` | 重要事件批量上报 |
| GET | `/api/v1/devices/{id}/config?afterVersion=n` | 增量拉配置 |
| POST | `/api/v1/devices/{id}/config-reports` | 报告配置执行结果 |

设备接口使用设备 Token，不能使用家属用户 Token。

### 4.2 家属绑定与设置

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/device-bindings` | 一次性码绑定 |
| GET | `/api/v1/devices` | 当前家属设备列表 |
| GET | `/api/v1/devices/{id}` | 状态与能力 |
| DELETE | `/api/v1/devices/{id}/bindings/{bindingId}` | 解绑 |
| GET/PATCH | `/api/v1/devices/{id}/settings` | 音量、亮度、免打扰等 |
| GET/PATCH | `/api/v1/devices/{id}/persona` | 人设维度 |
| CRUD | `/api/v1/devices/{id}/reminders` | 提醒 |
| GET/PATCH | `/api/v1/devices/{id}/proactive-policy` | 主动对话策略 |

一期家属接口不提供对话历史和原始音频。

### 4.3 管理端

- `/api/v1/admin/devices`：设备、组件状态、故障和配置。
- `/api/v1/admin/conversations`：长期文本查询，强制管理员权限和审计。
- `/api/v1/admin/test-audio`：测试音频查询/批量清理。
- `/api/v1/admin/prompt-releases`：草稿、测试、发布、灰度、回滚。
- `/api/v1/admin/model-routes`：供应商、地区、超时和启停。
- `/api/v1/admin/alerts`：告警状态和投递记录。
- `/api/v1/admin/audit-logs`：只读审计。

### 4.4 LINE

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/line/link-tokens` | 已登录家属生成一次性关联码 |
| POST | `/api/v1/line/webhook` | LINE webhook；验签、幂等、快速返回 |
| DELETE | `/api/v1/line/binding` | 解除当前账号关联 |
| POST | `/api/v1/devices/{id}/alerts:test` | 家属 App 发测试通知 |

### 4.5 公共与本地生活信息

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/information/query` | 即时查询，返回结构化事实包和引用 |
| POST | `/api/v1/information/evaluate` | 客户端按订阅/事件请求主动候选 |
| CRUD | `/api/v1/devices/{id}/information-subscriptions` | 订阅、频率和内容类别 |
| POST | `/api/v1/admin/information-sources/{id}:test` | 运行来源样例/连通性测试 |
| POST | `/api/v1/admin/information-sources/{id}:enable` | 经准入后启用来源 |
| GET | `/api/v1/admin/information-health` | 时效、错误率、配额和 schema 健康 |

## 5. 内部服务事件

初期不引入 Kafka；使用数据库 outbox + 后台 worker，避免两人团队增加运维复杂度。

`ai_outbox_event` 字段：事件 ID、aggregate type/id、event type、payload、created、available、processed、attempts、last error。事务内写业务表和 outbox；worker 处理 LINE、记忆抽取、会话总结和主动对话。

关键事件：

- `ConversationTurnCompleted`
- `MemoryCandidateCreated/MemoryChanged`
- `DeviceComponentOffline`
- `SensorAlertOpened`
- `ReminderDue`
- `PromptReleasePublished`
- `DeviceConfigChanged`

## 6. 幂等、并发和错误

- Android/ESP32 事件使用客户端生成 `eventId`，服务端唯一约束去重。
- 对话报告使用 `messageId`；相同 ID 重试返回原结果。
- LINE push 使用 alert delivery 的 retry key。
- 提醒执行使用唯一 `(reminder_id,scheduled_for)`。
- PATCH 设置必须携带版本；冲突返回 `409 CONFIG_VERSION_CONFLICT` 并带最新值。
- 通用错误结构：`code/message/retryable/traceId/details`；用户提示与内部异常分离。

## 7. 数据生命周期

| 数据 | 一期策略 |
|---|---|
| 对话文本 | 长期保存；管理员查看；保留期数值待后续政策确认 |
| 生产原始音频 | 不保存 |
| 测试原始音频 | 配置保存，管理员手动/批量清理，必须标环境 |
| 高频 DOA | 不逐条长期保存，只保留聚合指标/故障样本 |
| 心跳 | Redis 当前态；MySQL 只存状态变化和采样历史 |
| 记忆 | 长期保存，可纠正、替代和删除，保留来源 |
| 审计 | 建议至少 1 年，最终由政策确认 |

## 8. 数据库迁移顺序

沿用现有 `resources/db/changelog` 方式，禁止修改已执行迁移：

1. 新增绑定、人物资料、组件状态、配置、事件和审计表。
2. 给聊天历史和声纹表增加 nullable 字段及索引。
3. 从 `ai_device.user_id` 回填 `ai_device_user_binding`。
4. 新代码双读校验后切换绑定表为主。
5. 新增 Prompt、提醒、记忆、LINE、告警和 outbox 表。
6. 新增信息来源、标准事实、采集运行、订阅和投递表；先接固定样例，再启用真实来源。
7. 稳定后再清理已废弃字段，且不在一期中强制物理删除 `ai_device.user_id`。

每个 migration 需要前向脚本、数据校验查询和回滚/补偿说明；生产迁移前在备份副本演练。

## 9. 开发前需冻结的接口决策

1. `sys_user` 是否同时承载家属和平台管理员，还是增加独立身份类型/角色关联。
2. 邮件发送供应商、发件域名和验证码有效时间；认证方式已确定为邮箱一次性验证码 + LINE Login，一期不支持手机号或邮箱密码。
3. 对话文本“长期”的具体期限和删除流程。
4. 低风险语音设置的具体白名单和确认话术；敏感操作已确定禁止纯语音执行。
5. LINE 设置采用自然语言解析还是固定命令/按钮；一期建议固定命令和 postback。
