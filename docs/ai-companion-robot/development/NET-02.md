# NET-02：Android WebSocket 可靠重连与网络变化

> 日期：2026-08-28
> 状态：DONE
> 前置：NET-01

## 1. 实现

- 新增纯 Dart `XiaozhiReconnectController`，把重连退避从 WebSocket I/O 中拆出。
- 连续失败使用 `1/2/4/8/16/30/30...` 秒指数退避，增加 ±20% 抖动；应用抖动后的最终等待仍不超过 30 秒。
- 每次只允许一个待处理重连计时器，通道 error 与 done 连续到达不会重复排队。
- 服务端 `hello` 使连接进入 READY 后，失败计数归零，下一次断线从基础延迟重新开始。
- 显式重连取消旧计时、清零退避并立即连接；显式 disconnect 停止控制器，后续网络变化不能意外拉起连接。
- 使用 `connectivity_plus 6.1.5` 监听 Android/宿主网络类型变化：无可用网络时取消重连、关闭通道并保持 OFFLINE；网络恢复时清零退避并立即重连。
- 网络类型只用于暂停和恢复尝试，不作为“互联网可用”或“服务已在线”的证据；READY 仍只由 NET-01 的 WebSocket `hello` 握手决定。
- 删除 ChatScreen 原有固定 5 秒 UI 重连计时器，避免 UI 与传输层同时重连；UI 通过服务事件刷新连接状态。
- 增加连接 generation，旧连接遗留的 100/200 ms 认证和 hello timer 无法向新通道重复发送。
- 修复服务层在 HANDSHAKING/OFFLINE 时无法显式断开、重复创建管理器的问题。

## 2. 自动测试

失败优先测试最初因 `xiaozhi_reconnect_controller.dart` 不存在而编译失败；实现后新增 6 项确定性测试：

1. 指数序列与 30 秒上限，重复 schedule 不产生第二个 timer。
2. ±20% 抖动边界，最大等待仍封顶 30 秒。
3. READY 后下一次等待重置为 1 秒。
4. 网络离线取消 timer，恢复时立即重连。
5. 显式重连取消等待、立即执行并重置退避。
6. stop 后自动/网络恢复重连均不再执行。

合并回归命令：

```powershell
D:\flutter\bin\flutter.bat test --no-pub test\xiaozhi_reconnect_controller_test.dart test\xiaozhi_connection_state_machine_test.dart test\pcm_frame_buffer_test.dart test\opus_frame_test.dart test\xiaozhi_websocket_manager_test.dart
```

结果：22/22 通过（NET-02 6、NET-01 5、PCM 5、Opus 3、认证安全 3）。

NET-01/02 定向 `flutter analyze` 无 error/warning；剩余 23 项均为 WebSocket 旧文件的命名和 `print` info。

## 3. Android 构建证据

标准命令：

```powershell
pwsh -NoProfile -File .\tool\build_android_debug.ps1
```

首次构建发现此前 `config_provider.dart` 使用 `md5` 但误删了已有 `crypto` import；补回现有依赖导入后，最终版本构建通过。

- APK：`build/app/outputs/flutter-apk/app-debug.apk`
- 大小：`188046767` bytes
- SHA-256：`176C73602EF03B6763621D8CCA53107A0F30025F902BAF8CD97EF15488BE48AE`
- 构建时间：`2026-08-28 08:02:12 +08:00`
- 临时 `R:` 映射：未创建
- 已知提示：Gradle 8.12.1、AGP 8.7.0、Kotlin 2.1.0 后续需独立升级；本任务不混入工具链升级。

## 4. 人工验证与限制

- 自动测试覆盖退避、抖动、网络事件和显式重连的确定性逻辑，debug APK 覆盖 Android 插件编译集成。
- 后续应在本地服务端与 Android 模拟器执行一次：READY 后关闭服务端、观察离线与退避；恢复服务端或切换模拟器网络、观察自动 READY；显式退出页面后确认不再重连。
- `connectivity_plus` 报告网络接口类型，不保证真实互联网或服务端可达；所有连接仍必须依赖超时和 WebSocket 错误处理。

## 5. Android 模拟器人工验收与修复（2026-09-02）

- 模拟器断网约 10 秒后恢复：通过；当前聊天页立即恢复 READY 并可继续对话。
- 服务端停止：通过；客户端转为离线并停止接收音频。
- 服务端重新启动：首次验收失败；同一聊天页保持未连接，发送后等待图标持续转动，退出重进后恢复。
- 根因之一是 `connect()/reconnect()` 只等待连接尝试启动，没有等待服务端 `hello` 令状态进入 READY；聊天页随后立即检查状态而产生握手竞态。
- 修复为业务层发送前显式等待 READY，设置 12 秒上限；未就绪时返回明确错误，不再进入无界等待。
- READY 临时监听器会在回调中移除自身，测试进一步发现原事件列表直接遍历会触发 concurrent modification；现改为监听器快照分发，保证重连成功事件完整通知聊天页。
- 修复后自动回归 31/31 通过；仍需用新 APK 重做一次“服务端停止→重启→保持当前聊天页→直接发送”的人工验收。

### 第二次人工验收与根因补充

- 第二次 APK 仍未通过：服务重启后当前页持续离线；语音无响应；文字发送已能及时返回未连接错误，不再无限等待。
- 模拟器日志确认：断线后发起一次连接，服务不可用期间进入握手并在 10 秒后超时；超时路径只关闭通道，没有再次调用退避调度，因此后续不再自动尝试。
- 旧通道的 `subscription.cancel/sink.close` 也可能无界等待，使用户触发的显式重连无法开始新连接。
- 修复为：握手超时后有界关闭旧订阅和通道（各 2 秒），并显式安排下一次指数退避；语音入口在 READY 前拒绝启动录音，断线时取消现有录音流，避免离线期间持续发送。
- 新增集成测试验证“连接建立但服务端不返回 hello → 握手超时 → 关闭旧通道 → 调度并发起下一连接”。

### 最终人工验收（2026-09-03）

- 自动回归最终结果：39/39 通过，包含握手超时后继续调度下一次连接的集成测试。
- 最终 debug APK：`189606369` bytes，SHA-256 `B6BEACDC6ED70E41380426EC564D761ABF624AFD0554C9BF487DE79280A38BF6`。
- 保持当前聊天页停止并重新启动服务端后，客户端可自动恢复连接，无需退出并重新进入对话。
- 恢复连接后语音识别和文字发送均可正常得到回复。
- 模拟器断网约 10 秒再恢复时，在线状态和当前对话自动恢复正常。
- Android 阶段提交：`f48a29c0334ef5144c259dd6d5f14eac8b184667`。
- 结论：`PASS`。
