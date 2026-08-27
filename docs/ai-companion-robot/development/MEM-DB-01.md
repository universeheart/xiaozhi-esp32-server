# MEM-DB-01：长期记忆数据库迁移演练

> 日期：2026-08-27  
> 服务端基线：`fa8fd06ce80b`  
> 结论：PASS

## 1. 目标与隔离措施

验证 Liquibase `202608221930` 对长期记忆表的迁移行为：

1. 完整空库首次部署；
2. 同一数据库重复启动；
3. 带旧 `member_profile` 数据的升级部署；
4. 表结构、唯一索引和画像字段回填。

测试使用带 `ai-companion-test=MEM-DB-01` 标签的临时 MySQL 8.4 容器、随机宿主端口和纯虚拟画像。未挂载宿主目录，未连接 `application-dev.yml` 中的开发数据库。验证结束后，临时 Java 进程和容器均已删除。

## 2. 环境

- Docker Desktop 4.87.0
- Docker Engine 29.7.2
- MySQL 8.4
- Microsoft OpenJDK 21.0.12
- Maven 3.9.12
- 构建：`mvn -DskipTests package`
- 启动：使用命令行参数覆盖随机服务端口与临时数据源；凭据不记录

补充发现：系统默认命令行 Java 25 会导致当前 Lombok 注解处理失败；切换到项目配置的 Java 21 后构建成功。Java 21 是当前可复现构建约束。

## 3. 验证结果

| 场景 | 关键断言 | 结果 |
|---|---|---|
| 空库首次部署 | 应用完整启动；Liquibase 共记录 100 个 changeSet | PASS |
| 长期记忆迁移 | `202608221930` 恰好 1 条；`memory_profile` 存在 | PASS |
| 重复启动 | 第二次应用完整启动；changeSet 总数仍为 100，目标 changeSet 仍为 1 | PASS |
| 升级前状态 | 目标 changeSet=0、新表=0、旧画像样本=1 | PASS |
| 升级迁移 | 应用完整启动；目标 changeSet=1、新表=1 | PASS |
| 数据回填 | 旧画像 11 个业务字段逐字段一致；目标 MAC 仅 1 行 | PASS |
| 唯一约束 | `uk_memory_profile_mac_address` 存在且为唯一索引 | PASS |
| 环境清理 | 临时 manager-api 进程和 MySQL 容器已删除 | PASS |

虚拟画像标识：`AA:BB:CC:DD:EE:01` / `test-member-01`，不包含真实用户信息。

## 4. 结论与限制

`202608221930.sql` 可在 MySQL 8.4 上完成空库创建、旧表回填和 Liquibase 幂等启动，当前无需修改迁移 SQL。

本次仅验证迁移正确性，不代表现有长期记忆模型已满足多人声纹、字段级敏感度、画像纠错/删除、审计和单一事实源等产品要求；这些仍按后续设计任务处理。

另发现启动日志固定打印 `http://localhost:8002/xiaozhi/doc.html`，即使实际使用随机端口也不会变化。该问题不影响迁移结果，后续可作为日志可观测性小项修复。

## 5. 下一步

`MEM-DB-01` 关闭。G0 下一主任务为 `BLD-A-01`：固化 Android/Flutter/JDK/SDK 构建基线，再进入 Android 音频链路测试。
