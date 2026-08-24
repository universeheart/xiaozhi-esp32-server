# DOC-MOVE-01：协作文档迁入服务端仓

- 日期：2026-08-25
- 状态：DONE
- 目标：让服务端与 Android 协作者通过同一 Git 仓查看需求、计划、进度和验收摘要。

## 迁移

| 原目录 | 新目录 | 原文件数 |
|---|---|---:|
| 工作区 `需求设计` | `docs/ai-companion-robot/requirements` | 21 |
| 工作区 `开发记录` | `docs/ai-companion-robot/development` | 5 |
| 工作区 `测试证据` | `docs/ai-companion-robot/test-evidence` | 1 |

新增：协作入口 `README.md`、测试证据 `.gitignore` 和本任务记录。

## 提交边界

- Git 提交需求、ADR、开发记录、测试步骤和脱敏 Markdown 摘要。
- `test-evidence/.gitignore` 默认忽略所有原始产物，只放行目录、`.gitignore`、README 和 Markdown。
- APK、音频、截图、抓包、大型日志、数据库备份、Token、密码、数据库连接串和敏感对话不得提交。
- 服务端 `application-dev.yml` 继续作为单独本地修改，不属于本次文档迁移。

## 验证

1. 三个来源目录精确移动到服务端仓：PASS。
2. 迁移后 Markdown 相对链接检查，失效链接 0：PASS。
3. 旧绝对目录引用检查：PASS；只剩中文描述性用语，无旧路径。
4. `git diff --check`：PASS。
5. `test-evidence/sample/raw.log` 被忽略、Markdown README 被放行：PASS。
6. 文档目录可提交，服务端本地配置保持独立修改：PASS。

## 根路径说明

当前根目录包含中文。现有 Git、Python 和文档操作已验证可用；Android/Flutter、Gradle、NDK 或原生依赖若出现非 ASCII 路径问题，再整体迁移到 `D:\CodexWorking\ai-companion-robot`。在没有实证失败前不再次变更工作区，以免同时改变路径、权限和构建环境。

