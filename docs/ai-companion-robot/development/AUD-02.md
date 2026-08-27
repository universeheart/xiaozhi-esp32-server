# AUD-02：Android PCM 连续分帧修复

> 日期：2026-08-28
> 状态：DONE
> 前置：AUD-01

## 1. 实现

- 新增纯 Dart `PcmFrameBuffer`，接收任意长度 PCM byte chunk，按 1920 bytes 输出完整 60 ms 帧。
- 所有完整帧按输入顺序输出；不足一帧的尾部跨 recorder chunk 保留。
- 新录音开始和停止时 reset，禁止跨录音轮次复用尾部。
- `AudioUtil` 对同一 chunk 中的每个完整帧逐个调用 Opus encoder，不再只编码首帧。
- `encodeToOpus` 只接受精确一帧；短输入不再补静音，多帧输入不再静默裁剪。

## 2. 数据不变量

对任意输入 chunk 序列：

```text
concat(已输出完整帧) + pending tail == concat(全部输入 chunk)
```

且每个已输出帧恒为 1920 bytes，pending tail 恒小于 1920 bytes。

## 3. 验证与限制

- AUD-01 PCM/Opus 测试全部通过；SEC-01 WebSocket 安全回归同时通过。
- 本任务验证字节守恒、60 ms 帧边界和本机 libopus 编解码，不以单元测试替代 Android 14 真机录音、AEC、权限、音频焦点和网络弱网测试。
- 当前 `AudioUtil` 仍为静态大类；后续应继续拆分 Capture、Encoder、发送队列和 Playback，避免真机资源生命周期与纯算法耦合。

