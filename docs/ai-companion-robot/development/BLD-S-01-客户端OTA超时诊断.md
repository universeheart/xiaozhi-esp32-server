# BLD-S-01：py-xiaozhi OTA 连接超时诊断

- 日期：2026-08-25
- 状态：ROOT_CAUSE_CONFIRMED；等待修改客户端配置后复测
- 症状：`py-xiaozhi` 初始化阶段 POST OTA URL，10 秒后 `asyncio.TimeoutError`，程序退出。

## 定位结论

失败发生于设备激活第三阶段 `_fetch_ota_config()`：

```text
POST http://<已脱敏内网主机>:8002/xiaozhi/ota/
```

`aiohttp` 在 TCP 建连阶段超时，尚未收到 HTTP 状态码，因此尚未进入：

- manager-api OTA Controller 业务处理；
- WebSocket/音频协议；
- 长期记忆/SuperBrain；
- JSON 响应解析。

独立读取共享 AppData 配置后，用 .NET `TcpClient` 测试相同主机和 8002 端口，3 秒内也无法连接；独立 HTTP 请求同样不可达。这证明问题不特定于 `aiohttp` 或 Python 插件。

## 已核实

- 客户端配置来自 `C:\Users\Shen\AppData\Local\py-xiaozhi\py-xiaozhi\config\config.json`，不是仓库目录内配置。
- 新旧两个代码目录使用相同 AppData 配置和相同 Conda 环境，因此两边复现不能证明代码更新导致。
- OTA 配置格式正确：HTTP、端口 8002、路径 `/xiaozhi/ota/`。
- manager-api 声明端口 8002、context path `/xiaozhi`，路径设计一致。
- 诊断时本机端口 8002 的监听进程数为 0。

## 原因优先级

1. 客户端测试时 manager-api 未运行，或启动后已经退出。
2. AppData 中保存的内网 IP 已因 DHCP、VPN、网卡切换等变化，不再是 manager-api 主机地址。
3. manager-api 只监听 loopback/特定网卡，配置却使用另一网卡地址。
4. Windows 防火墙或 Docker/WSL 端口映射阻止访问 8002。
5. Python/aiohttp 插件问题：证据不支持，优先级低。
6. 长期记忆或服务端 OTA 接口兼容问题：当前证据排除；只有 TCP 可达后出现 HTTP/JSON 错误才进入该层排查。

## 2026-08-25 复测结论

- `Test-NetConnection 127.0.0.1 -Port 8002`：成功。
- `Test-NetConnection <当前 WLAN 地址> -Port 8002`：成功。
- 用户确认 AppData 配置仍保存上一次热点分配的旧 IP；热点 IP 发生变化。

根因确认：客户端 OTA URL 使用失效的旧热点 IP。manager-api 当前端口、监听和 WLAN 访问均正常；与服务端长期记忆更新、复制目录和 Python 插件无关。

同时确认一个客户端缺陷：OTA 初始化失败会在 GUI 设置页显示前直接退出，用户无法通过图形界面修正错误地址。后续任务 `PYCFG-01` 应提供启动失败设置入口、重试/离线模式或安全配置覆盖。

## 最短复测

1. 启动 manager-api，保持进程窗口不关闭，确认日志显示 Tomcat 已在 8002 启动。
2. 在启动 py-xiaozhi 的同一 PowerShell 执行：

   ```powershell
   Test-NetConnection 127.0.0.1 -Port 8002
   ```

3. 若客户端和 manager-api 在同一台 Windows 电脑，将客户端设置页的 OTA Version URL 临时改为：

   ```text
   http://127.0.0.1:8002/xiaozhi/ota/
   ```

4. 再运行 `python main.py`。
5. 若 localhost 成功但内网地址失败，问题在 IP/监听/防火墙；记录 `Test-NetConnection <配置主机> -Port 8002` 的 `TcpTestSucceeded`，无需提供真实 IP。
6. 若 TCP 成功但客户端失败，提供新的首个完整异常；届时检查 HTTP 状态、OTA payload/response 和激活数据。

当前同机 Windows 测试建议将 `SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL` 配置为 `http://127.0.0.1:8002/xiaozhi/ota/`，避免热点地址变化。Android/其它物理设备不能使用 loopback，应使用稳定局域网地址、局域网 DNS 名称或正式域名。

## 安全说明

诊断未输出配置中的内网地址、数据库密码或 Token。客户端当前会在 DEBUG 日志打印完整 OTA URL，后续安全任务应对主机信息做日志脱敏。
