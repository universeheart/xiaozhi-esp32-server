# SEC-01：默认凭据、敏感日志与权限风险收口

> 日期：2026-08-27
> 状态：DONE（开发阶段风险接受）
> 代码基线：服务端 `72592ff10734`、Android `459d79de7d1b`，均叠加已确认保留的本地修改

## 1. 扫描边界

- 对四个仓库的 Git 跟踪文本文件进行只读扫描；排除构建缓存、依赖目录和二进制文件。
- 检查私钥头、JWT、常见云厂商/API Token 格式、Secret/密码赋值、Android 权限、导出组件、release signing 和敏感日志。
- `main/manager-api/src/main/resources/application-dev.yml` 只作为受保护的本地配置登记，不读取、不输出、不修改其中的值，也不得纳入提交。
- 扫描记录只保存文件、键路径、风险类别和行号，不保存凭据内容。

## 2. 已完成整改

### 服务端

- `main/xiaozhi-server/config.yaml` 中仓库共用的天气服务 Key 已替换为明确占位符。
- 该旧 Key 已存在于 Git 历史提交 `8a066163fe5b`；从当前版本移除不能使旧值失效，必须由人工在供应商控制台撤销或轮换。
- `main/manager-api/src/main/resources/application.yml` 中 Knife4j 基础认证的弱默认密码已移除，改为环境变量 `KNIFE4J_BASIC_PASSWORD`；基础认证默认仍为关闭。

### Android

- 未配置 Token 时不再注入 `test-token` 或任何默认 Authorization 凭据。
- 删除 Token、Bearer 头、认证消息、设备 ID、文本请求正文和收到消息正文的明文日志。
- 配置列表只显示“已配置/未配置”，不再显示 Token/API Key 本文或前缀；Token 编辑框使用隐藏输入。
- 新增 3 项回归测试，覆盖无 Token、有 Token和启用但空 Token 三种认证行为。

## 3. 验证证据

- 高置信 Secret 格式扫描：未发现私钥头、JWT、OpenAI/GitHub/AWS 形式的真实凭据。
- Android 定向测试：`flutter test test/xiaozhi_websocket_manager_test.dart`，3 项全部通过。
- 敏感日志/默认 Token 复扫：代码中不再存在 `test-token`、Token/Bearer 明文日志或认证消息正文日志。
- `flutter analyze` 可完成，但仓库现有基线仍报告 467 项 warning/info；本次改动未引入编译错误，静态分析债务不在本任务批量清理。
- 两仓 `git diff --check`：除已有 Markdown 行尾空格约定提示外，无新增补丁格式错误。

## 4. 未关闭风险

1. Android 的 Xiaozhi、Dify 和 MiniMax 凭据仍随配置 JSON 保存在普通 `SharedPreferences`。迁移到 Android Keystore 支持的安全存储需要兼容旧配置迁移和回滚，建议拆为 `SEC-A-02`。
2. Android release 构建仍使用 debug signing，只允许开发测试；正式发布签名与密钥托管进入试产加固任务。
3. Android 当前请求的存储、录音和蓝牙权限范围需要结合目标 Android 14 设备功能逐项缩减；`MANAGE_EXTERNAL_STORAGE` 请求路径需在真机任务中移除或给出产品级必要性证明。
4. 部分 Provider 会记录错误响应正文，可能包含第三方返回的敏感业务数据；应在统一日志组件任务中改为状态码、trace ID 和脱敏摘要。

## 5. 开发阶段风险接受

- 2026-08-28 用户确认：天气服务账号为开发期公共共享账号，当前继续使用；本地开发数据库密码允许保存在本地配置文件。
- 上述决定仅适用于开发环境，不表示生产安全验收通过。进入共享测试、公开演示或试产部署前，必须重新启用天气 Key 和数据库凭据轮换要求。
- 受保护的 `application-dev.yml` 继续保留在本机，不输出其中的值，也不纳入本任务提交。
- `SEC-01` 以“代码侧默认 Token/敏感日志已收口，开发凭据风险已知并接受”关闭。
