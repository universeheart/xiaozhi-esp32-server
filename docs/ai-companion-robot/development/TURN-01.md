# TURN-01：会话/轮次边界与有界播放队列

> 日期：2026-08-28
> 状态：DONE
> 前置：NET-01

## 1. 协议调查

当前服务端在同一个 WebSocket 中按顺序发送：

```text
tts:start(session_id)
tts:sentence_start(session_id, text)
binary Opus frames...
tts:sentence_start(session_id, text)  # 同一回复的后续句子
binary Opus frames...
tts:stop(session_id)
```

服务端内部有 `sentence_id` 用于阻止旧 TTS 继续发送，但当前二进制 Opus 帧不携带 `session_id/turn_id`，文本 TTS 消息也尚未发送 `turn_id`。客户端不能从不存在的字段恢复真实服务端轮次，因此采用兼容边界：

- `session_id` 变化时清空旧会话队列。
- `tts:start` 开始一个本地 turn。
- 同一 start→stop 窗口内的多个 `sentence_start` 属于同一 turn。
- `tts:stop` 后不再接受二进制帧，但已经按 WebSocket 顺序入队的帧可以排完。
- 若未来文本协议提供 `turn_id` 或 `turnId`，现有队列直接使用并校验该值。

## 2. 实现

- 新增纯 Dart `TurnAudioQueue`，每个音频帧保存 `sessionId/turnId` 标签和数据副本。
- 队列上限为 50 个 60 ms Opus 帧，约 3 秒；不会随网络或播放器阻塞无限增长。
- 容量满时丢弃最旧帧并保留最新帧，使播放延迟有界；累计记录丢帧数。
- 非当前 session、非当前 turn、尚未 start 和 stop 后晚到的音频均拒绝入队。
- 新 session 或新 turn 会清除旧队列，避免上一回复排队音频继续进入播放入口。
- `XiaozhiService` 使用单一异步 playback pump 按 FIFO 顺序调用 Opus 播放，不再为每个二进制事件并发调用播放器。
- WebSocket 断开和显式 `stopPlayback` 会关闭当前 turn 并清空待播放队列。
- 删除未使用且会绕过队列直接播放的 `_handleWebSocketMessage` 旧入口。

## 3. 自动验证

失败优先测试最初因 `turn_audio_queue.dart` 不存在而编译失败；实现后新增 8 项测试：

1. 无活动 session/turn 时拒绝音频。
2. 当前 turn 内保持 FIFO。
3. 新 session 清除旧 session 队列。
4. 拒绝旧 turn ID。
5. 拒绝另一 session 的帧。
6. stop 后拒绝晚到帧，但已入队帧仍可排空。
7. 新 turn 清除上一 turn 的待播放帧。
8. 容量恒定，溢出丢最旧并保留最新。

合并回归命令：

```powershell
D:\flutter\bin\flutter.bat test --no-pub test\turn_audio_queue_test.dart test\xiaozhi_reconnect_controller_test.dart test\xiaozhi_connection_state_machine_test.dart test\pcm_frame_buffer_test.dart test\opus_frame_test.dart test\xiaozhi_websocket_manager_test.dart
```

结果：30/30 通过（TURN-01 8、NET-02 6、NET-01 5、PCM 5、Opus 3、认证安全 3）。

## 4. Android 构建证据

标准 debug APK 构建通过：

- APK：`build/app/outputs/flutter-apk/app-debug.apk`
- 大小：`187890919` bytes
- SHA-256：`661F3699487B389E8AE1D45C042432AFC4CC4CE298599D4CF9D92B3A54CAE17C`
- 构建时间：`2026-08-28 08:22:45 +08:00`
- 临时 `R:` 映射：未创建

## 5. 限制与后续

- WebSocket 在单连接内保证文本和二进制消息顺序，因此 stop 之前收到的帧可以绑定当前本地 turn；协议未携带二进制 frame 的 turn 元数据，客户端无法识别“新 turn start 之后才从外部乱序到达”的旧帧。彻底解决需要服务端扩展带 turn ID 的音频 envelope。
- 本任务阻止旧帧进入队列或从队列继续取出，但无法撤回已经 feed 给原生 PCM 播放器的缓冲；本地停止、服务端 abort 和播放器资源的原子切换属于 `TURN-02`。
- 50 帧是当前 60 ms 协议下约 3 秒的保护上限，真机弱网验收后可根据听感调整，但不得取消上限。

## 6. Android 模拟器人工验收（2026-09-02）

- 连续 3 次多句回复均按顺序播放，没有句子并发播放。
- 开始下一次回复后，上一回复未完成的排队音频没有继续播放。
- 回复播放期间停止服务端，客户端立即转为离线、停止接收新音频，已进入播放器的声音也立即停止。
- 模拟器断网约 10 秒后恢复，当前对话立即恢复已连接并可继续对话。
- 退出聊天页后切换网络，已退出会话没有播放声音或重新拉起通话。
- 首轮服务端进程重启测试暴露 NET-02 重连恢复缺陷；补充握手超时重试和有界通道清理后，于 2026-09-03 使用最终 APK 复验通过，同一聊天页可自动恢复，语音和文字对话均正常。
- Android 阶段提交：`f48a29c0334ef5144c259dd6d5f14eac8b184667`；本任务最终结论：`PASS`。
