# ENV-02：可写开发仓与提交方式

- 状态：DONE
- 执行日期：2026-08-22
- 前置：ENV-01
- 执行：用户提供工作副本，Codex 校验

## 决策

- 四个完整仓库统一位于 `D:\CodexWorking\AI陪伴机器人\Projects`。
- 服务端和 Android 为实际开发仓；ESP32 与 Python 仓主要用于协议/行为参考和测试。
- Codex 在这些工作副本中修改与测试，用户自行审查并手动 commit。
- `D:\Projects\ProjectRobot` 下原仓保持不动，不作为后续代码修改目标。

## 写权限验证

在 `Projects` 根创建 `.codex-write-probe` 后成功删除，证明当前任务具有写权限；探针不位于任何 Git 仓内且未残留。

## 新工作副本基线

| 仓库 | HEAD | origin | dirty 保护项 |
|---|---|---|---|
| `xiaozhi-esp32-server` | `b903a88cd500` | `universeheart/xiaozhi-esp32-server` | `application-dev.yml`、`manager-web/package-lock.json` |
| `xiaozhi-esp32` | `1874c6206ceb` | `universeheart/xiaozhi-esp32` | 无 |
| `py-xiaozhi` | `841c5f1688c2` | `universeheart/py-xiaozhi` | 无 |
| `xiaozhi-android-client` | `459d79de7d1b` | `universeheart/xiaozhi-android-client` | 7 个 tracked 构建配置；`.artifacts/`、`android/build/` 未跟踪 |

`py-xiaozhi` 新副本 HEAD 与旧路径 `45c8a0400df5` 不同。新副本 Git 元数据完整且工作树 clean；从本任务起以用户提供的新副本 `841c5f1688c2` 为准，不执行回退。

## 验收

1. 四仓均存在 `.git`，可读取 HEAD、origin 和 status：PASS。
2. 服务端/Android dirty 项与人工确认的保护范围一致：PASS。
3. 工作区写入/删除探针：PASS。
4. 原路径未修改：PASS。

结论：后续可以在新工作副本开始构建、测试和代码修改。

