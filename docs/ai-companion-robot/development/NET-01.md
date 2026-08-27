# NET-01：Android WebSocket 显式连接状态机

> 日期：2026-08-28
> 状态：DONE
> 前置：BLD-A-01

## 1. 问题与目标

原实现把 WebSocket channel 对象创建视为“连接成功”，尚未收到服务端 `hello` 就向业务层派发 `connected`。这会让 UI、录音和消息发送在协议握手尚未完成时误判在线；握手也没有确定性超时。

本任务将状态明确为：

```text
OFFLINE -> CONNECTING -> HANDSHAKING -> READY
              |              |
              +--------------+-> OFFLINE
```

## 2. 实现

- 新增纯 Dart `XiaozhiConnectionStateMachine`，集中管理 `CONNECTING/HANDSHAKING/READY/OFFLINE`。
- channel 创建后进入 `HANDSHAKING`；只有收到可解析且 `type=hello` 的服务端消息才进入 `READY`。
- 默认握手超时为 10 秒；超时后先切换 `OFFLINE`、报告握手超时，再关闭底层通道。
- 显式断开、通道关闭和通道错误都会取消握手计时并回到 `OFFLINE`。
- 业务层 `connected` 事件只在进入 `READY` 时派发；文本、音频等普通业务发送继续由 `isConnected` 门禁，因此握手前不会发送。
- 客户端 `hello` 和 Web 平台回退认证使用握手期内部发送入口，不会被 READY 门禁误拦截。
- 保留既有固定延迟重连行为；指数退避、抖动和网络变化属于后续 `NET-02`。

## 3. 自动验证

状态机测试 5 项：

1. 未收到服务端 `hello` 时保持 `HANDSHAKING`，不报告 READY。
2. 合法 `hello` 完成握手并取消超时。
3. 非 JSON 与无关消息不能完成握手。
4. 可控假计时器触发后确定性进入 `OFFLINE`，晚到 `hello` 无效。
5. 显式离线取消待处理超时，不重复报告超时。

合并回归命令：

```powershell
D:\flutter\bin\flutter.bat test --no-pub test\xiaozhi_connection_state_machine_test.dart test\pcm_frame_buffer_test.dart test\opus_frame_test.dart test\xiaozhi_websocket_manager_test.dart
```

结果：16/16 通过（NET-01 5、PCM 5、Opus 3、认证安全 3）。

定向静态分析无编译错误；报告 95 个 warning/info，均来自既有 `xiaozhi_service.dart`/WebSocket 管理器的未用成员、命名和 `print` 技术债，本任务没有新增 analyzer error。

## 4. 限制与后续

- 本任务用确定性单元测试关闭状态语义和超时验收；本地服务端与 Android 模拟器的真实握手仍应作为阶段性人工冒烟测试。
- 当前自动重连仍是固定 3 秒，且尚未感知网络变化；由 `NET-02` 实现并用假时钟验证指数退避上限和成功后重置。
- 回滚时可移除状态机文件与对应测试，并恢复管理器以 channel 存在判断连接的旧行为；该旧行为会重新引入 hello 前假在线风险。
