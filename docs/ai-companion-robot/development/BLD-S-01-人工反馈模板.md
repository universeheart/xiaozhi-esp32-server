# BLD-S-01：服务端构建与运行反馈模板

> 不需要整理成长报告，按实际执行填写即可。日志中如含密码、Token、数据库连接串，请先脱敏。

## 环境

- Windows 版本：
- Java / Maven 版本：
- Node / npm 版本：
- Python / pip 版本：
- MySQL / Redis 版本及运行方式：本机 / Docker / 远程

## 构建

| 模块 | 执行目录 | 命令 | 结果 | 首个错误/警告摘要 |
|---|---|---|---|---|
| `xiaozhi-server` |  |  | PASS/FAIL |  |
| `manager-api` |  |  | PASS/FAIL |  |
| `manager-web` |  |  | PASS/FAIL |  |
| `manager-mobile`（若本轮执行） |  |  | PASS/FAIL |  |

## 运行

| 模块 | 启动命令/方式 | 是否启动 | 验证动作 | 结果 |
|---|---|---|---|---|
| MySQL/Redis |  |  | 连接/健康检查 |  |
| `manager-api` |  |  | 启动完成、Liquibase、健康/API |  |
| `manager-web` |  |  | 登录页/后台页面 |  |
| `xiaozhi-server` |  |  | WebSocket 监听/设备连接 |  |

## 长期记忆专项观察

- Liquibase 四个新 changeSet 是否执行成功：
- `memory_profile` 是否创建/升级成功：
- 后台能否选择 SuperBrain 与记忆 LLM：
- 完成一轮对话后是否产生记忆文件/数据库画像：
- 第二轮对话是否能读取上一轮记忆：
- 错误日志摘要：

## 反馈附件

- 可直接粘贴首个完整异常堆栈。
- 如果日志很长，提供文件路径；不要复制 Secret。
- 说明是否为了运行临时修改了任何 tracked 文件。

