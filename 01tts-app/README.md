# Listening Lab Android App

Listening Lab 是 `01tts` 的原生 Android 客户端，使用 Kotlin、Jetpack Compose、Retrofit 和 Media3 构建。主界面采用深色石墨背景与单一翡翠绿色强调色。

## 功能

- 创建云端英语听力课程并轮询生成状态
- 播放课程音频，支持进度拖动、前后 10 秒和倍速
- 完成听力选择题并保存成绩
- 录制口语回答，显示真实麦克风振幅、转写、评分和反馈
- 在本地课程历史中恢复课程及对应学习结果
- 从自己的云服务器检查、下载、校验并安装新版本

## 服务地址

域名完成备案前，默认 API、音频和在线更新地址统一使用
`http://42.192.62.145:8080/`。可在构建时覆盖地址：

```bash
./gradlew assembleDebug \
  -PLISTENING_LAB_API_URL=http://192.0.2.10:8080/
```

当前网络安全配置只允许 `42.192.62.145` 使用明文 HTTP，其他地址仍禁止明文流量。

## 测试与打包

在本目录运行：

```bash
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
  ./gradlew clean testDebugUnitTest assembleDebug
```

生成的 APK 位于：

```text
app/build/outputs/apk/debug/app-debug.apk
```

## 发布在线更新

先递增 `app/build.gradle.kts` 中的 `versionCode` 和 `versionName`，然后运行：

```bash
./scripts/publish-update.sh \
  "新增课程功能" \
  "优化播放稳定性"
```

脚本会执行测试与打包、生成 SHA-256 版本清单、上传 APK 到
`tecent-server:/opt/01tts/storage-python/app-releases/`，再通过公网接口验证。
当前 2.6.0 是在线更新基线版，需要手动安装一次；以后的更高版本可在“设置 → 应用更新”内完成。

在 Android Studio 中打开本目录，选择真机或模拟器后运行 `app` 即可。
