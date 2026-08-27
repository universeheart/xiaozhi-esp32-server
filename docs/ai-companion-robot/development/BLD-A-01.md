# BLD-A-01：Android 可重复构建基线

> 日期：2026-08-27  
> Android 基线：`459d79de7d1b` + 已确认保留的本地构建配置修改  
> 结论：PASS（英文根路径复验）

## 1. 已验证环境

- Windows 11 25H2
- Flutter 3.44.9 stable / Dart 3.12.2
- Android SDK 36.0.0；Android licenses 全部通过
- JDK 17.0.20（Flutter 全局配置）
- Gradle 8.12.1
- Android Gradle Plugin 8.7.0
- Kotlin 2.1.0
- NDK 28.2.13676358

## 2. 问题与处理

1. 原 `android/gradle.properties` 固定本机 JDK 路径，已移除；JDK 改由 Flutter 环境配置提供。
2. Gradle wrapper 原指向 `D:/Libs/gradle-8.12.1-all.zip`，已改为官方 Gradle 8.12.1 URL。
3. 当前共享工作区父路径包含中文。AGP 会直接拒绝，绕过检查后 Kotlin 缓存和 CMake JSON 仍会失败，因此不能把 `android.overridePathCheck` 作为正式方案。
4. 新增 `tool/build_android_debug.ps1`：路径含非 ASCII 字符时，把同一仓库临时映射到空闲英文盘符 `R:`，构建结束自动删除映射，不复制仓库。
5. 禁用 Kotlin 增量缓存，规避 Pub Cache 与项目跨盘符时的相对路径异常。
6. `android/build/` 和 `.artifacts/` 已加入 ignore，避免提交生成物。
7. 工作区已迁至纯英文根路径 `D:\CodexWorking\AICompanionRobot`；脚本现在直接在仓库执行，不创建临时盘符映射。

## 3. 验证

标准入口：

```powershell
pwsh -NoProfile -File .\tool\build_android_debug.ps1
```

结果：

- 清理 `build/`、`.dart_tool/`、`android/.gradle/` 和 `android/build/`（保留 `.artifacts/`）后，在英文根路径执行 `flutter clean`、`flutter pub get` 与标准脚本；
- Gradle `assembleDebug` 成功；脚本直接使用仓库路径，构建前后 `R:` 均不存在；
- APK：`build/app/outputs/flutter-apk/app-debug.apk`；
- 大小：164,560,103 bytes；
- SHA-256：`8BF0EBCA11235F3FABDD4ACAC6E78F3B08905DF910E55BD5FF5292597DD84F36`。

已进行 `kotlin.incremental=false` 移除的对照构建尝试，但 Gradle/NDK 构建超过首次全量构建时长仍未完成，未获得可接受的成功证据；该设置已恢复，留待独立性能/稳定性任务复测。

仓库内使用说明：`BUILDING_ANDROID.md`。

## 4. 已知限制

- Flutter 提示后续需升级 Gradle 8.14+、AGP 8.11.1+、Kotlin 2.2.20+；本任务不混入高风险工具链升级。
- 40 个依赖存在不兼容当前约束的更新版本；不在基线任务中批量升级。
- Android 真机安装、启动、录音和网络会话不属于本任务，进入 `AUD-01` 后逐项验证。
- 当前英文绝对路径已验证稳定；脚本仍兼容旧中文路径时的临时盘符映射，但不再是本工作区的常规流程。

## 5. 回滚

- 删除 `tool/build_android_debug.ps1` 和 `BUILDING_ANDROID.md`；
- 恢复 wrapper URL与 Gradle 属性即可回到原本机专用配置；
- 脚本不保留盘符映射，也不修改全局 Flutter/JDK 配置。
