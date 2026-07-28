# Listening Lab Android App

Listening Lab 是 `01tts` 的原生 Android 客户端，使用 Kotlin、Jetpack Compose、Retrofit 和 Media3 构建。主界面采用深色石墨背景与单一翡翠绿色强调色。

## 功能

- 创建云端英语听力课程并轮询生成状态
- 播放课程音频，支持进度拖动、前后 10 秒和倍速
- 完成听力选择题并保存成绩
- 录制口语回答，显示真实麦克风振幅、转写、评分和反馈
- 在本地课程历史中恢复课程及对应学习结果

## 服务地址

默认 Debug 地址为 `http://42.192.62.145:8080/`。可在构建时覆盖：

```bash
./gradlew assembleDebug \
  -PLISTENING_LAB_API_URL=https://api.example.com/
```

生产环境应优先使用 HTTPS。当前网络安全配置只允许默认测试服务器使用明文 HTTP。

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

在 Android Studio 中打开本目录，选择真机或模拟器后运行 `app` 即可。
