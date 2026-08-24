# ENV-01：四仓开发基线与禁止覆盖清单

- 状态：DONE
- 执行日期：2026-08-22
- 需求/ADR：DEV-PROC-01、ADR-022
- 执行：Codex；待人工助手 A 确认 dirty 文件归属

## 范围

- 只读核对四个本地仓的 HEAD、remote、工作树文件名和许可证。
- 不读取或记录配置文件中的凭据值，不 fetch、不修改、不提交。

## 基线

| 仓库 | 本地路径 | HEAD | 许可证 | 工作树 |
|---|---|---|---|---|
| 服务端 | `D:\Projects\ProjectRobot\xiaozhi-esp32-server` | `b903a88cd500` | MIT | 2 个已修改文件 |
| ESP32 参考 | `D:\Projects\ProjectRobot\xiaozhi-esp32` | `1874c6206ceb` | MIT | clean |
| Python 测试端 | `D:\Projects\ProjectRobot\py-xiaozhi` | `45c8a0400df5` | MIT | clean |
| Android 主客户端 | `D:\Projects\ProjectRobot\xiaozhi-android-client` | `459d79de7d1b` | Apache-2.0 | 7 个已修改、2 个未跟踪路径 |

四仓 `origin` 均指向用户 fork `https://github.com/universeheart/...`；原始 upstream URL 以《开源项目复用分析-v0.1.md》为准。

## 禁止覆盖清单

以下内容一律按用户现有改动处理，在人工确认和建立开发副本前不覆盖、不清理：

- 服务端：`main/manager-api/src/main/resources/application-dev.yml`
- 服务端：`main/manager-web/package-lock.json`
- Android：`android/app/build.gradle.kts`
- Android：`android/build.gradle.kts`
- Android：`android/gradle.properties`
- Android：`android/gradle/wrapper/gradle-wrapper.properties`
- Android：`android/settings.gradle.kts`
- Android：`pubspec.lock`
- Android：`pubspec.yaml`
- Android：`.artifacts/`
- Android：`android/build/`

## 验证记录

| 类型 | 步骤 | 结果 |
|---|---|---|
| 自动/只读 | 对每个仓执行 `git rev-parse --short=12 HEAD` | PASS |
| 自动/只读 | 对每个仓执行 `git status --short` | PASS；上述 dirty 清单已记录 |
| 自动/只读 | 读取 LICENSE 前三行 | PASS；三项 MIT、一项 Apache-2.0 |
| 人工 | 确认 Android dirty 文件是已有可编译环境产生/所需改动，全部保留 | PASS（2026-08-22） |
| 人工 | 确认服务端两个 dirty 文件是本地运行配置，均需保留 | PASS（2026-08-22） |

## 结论和下一步

技术核对与人工确认均已完成。Android dirty 文件全部保留；服务端 `application-dev.yml` 与 `package-lock.json` 是本地运行配置，也全部保留。后续修改必须绕开这些用户改动，确需重叠时先展示差异。当前任务实际权限仍将 `D:\Projects\ProjectRobot` 标记为只读；重启 Codex 并重新进入任务后复核权限。
