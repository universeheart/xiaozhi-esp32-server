# AUD-01：Android PCM/Opus 固定向量测试

> 日期：2026-08-28
> 状态：DONE
> Android 基线：`459d79de7d1b` + 已确认保留的本地修改

## 1. 目标

- 用纯 Dart 测试固定 16 kHz、mono、PCM16、60 ms（960 samples / 1920 bytes）音频帧约束。
- 覆盖 recorder 任意 chunk 长度下的数据守恒、顺序、尾部保留和录音轮次重置。
- 建立本机 libopus 固定 PCM 向量的编码/解码测试。

## 2. 失败基线

首次执行 `flutter test test/pcm_frame_buffer_test.dart` 时，测试因 `lib/audio/pcm_frame_buffer.dart` 尚不存在而失败；这证明现有代码没有可独立测试的连续分帧边界。

现有 `AudioUtil.encodeToOpus` 的代码审计同时确认：

- 少于 1920 bytes 的 chunk 会立即补静音并编码；
- 多于 1920 bytes 的 chunk 只编码第一帧，其余数据丢弃；
- 每个 recorder chunk 独立处理，不能跨 chunk 保留尾部。

## 3. 新增测试

- 精确一帧：输出一帧且无尾部。
- 短 chunk：不输出、不补静音，全部保留。
- 三帧加尾部：输出三帧，只保留 127 bytes。
- 固定随机种子 `20260828`：19 帧加 911 bytes，以 1–3000 bytes 随机切块，输出帧与尾部拼接后逐字节等于输入。
- reset：新录音轮次不继承旧尾部。
- Opus 固定向量：960 samples 编码后可解码为 960 samples；短帧和多帧输入均被拒绝。

## 4. 验证

合并命令：

```powershell
flutter test test\pcm_frame_buffer_test.dart test\opus_frame_test.dart test\xiaozhi_websocket_manager_test.dart
```

结果：11 项全部通过，其中 PCM 5 项、Opus 3 项、SEC-01 WebSocket 安全回归 3 项。

Opus 单元测试在 Windows 上直接加载锁定依赖 `opus_flutter_windows` 包内的 libopus 1.3.1；Android ABI 仍由 debug APK 构建和后续真机测试覆盖。

