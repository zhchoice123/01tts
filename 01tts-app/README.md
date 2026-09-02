# Listening Lab Android App

Listening Lab 是 `01tts` 的原生 Android 客户端，使用 Kotlin、Jetpack Compose、Retrofit 和 Media3 构建。主界面采用深色石墨背景与翡翠绿色强调色。

## 📱 核心功能

- **课程与听力**：创建/获取云端英语听力课程，播放音频，支持进度拖动、前后 10 秒跳跃与倍速调节。
- **阅读与做题**：技术文章阅读理解、划词查询上下文释义与音标、选择题提交与错题解析。
- **口语对话与评分**：录制口语回答，展示麦克风振幅波形、Whisper 转写、AI 语法/发音评分与针对性反馈。
- **Anki 词汇联动**：绑定 AnkiDroid 本地 Deck，读取今日到期卡片生成定制复习课程，支持生词回写与查重。
- **在线自动更新**：支持与云端版本校验、后台下载、SHA-256 校验与应用内安全升级。

---

## 🌐 服务地址配置

默认 API、音频和在线更新地址统一使用 `https://api.zhchoice.xyz/`。可在构建时覆盖地址：

```bash
./gradlew assembleDebug -PLISTENING_LAB_API_URL=https://api.example.com/
```

当前网络安全配置禁止明文 HTTP，生产请求统一使用 HTTPS。

---

## 🛠️ 本地开发、测试与打包

在本目录运行：

```bash
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
  ./gradlew clean testDebugUnitTest assembleDebug
```

生成的 APK 位于：`app/build/outputs/apk/debug/app-debug.apk`。

在 Android Studio 中打开本目录，选择真机或模拟器后运行 `app` 即可。

---

## 🚀 在线更新与发版操作指南

### 1. 用户侧更新流程
- App 启动时会自动检查云端版本，用户也可在“设置 → 应用更新”手动检查。
- 发现更高版本时，App 自动下载 APK，核对文件大小与 SHA-256，校验通过后调用系统安装器。
- 首次从 App 安装时，系统会要求授予“安装未知应用”权限；授权后后续升级无需重新卸载。

### 2. 开发者发布流程
1. 修改 `app/build.gradle.kts`，递增 `versionCode` 和 `versionName`。
2. 运行发布脚本：

```bash
./scripts/publish-update.sh \
  "更新说明 1：优化播放稳定性" \
  "更新说明 2：支持口语多轮对话"
```

该脚本将自动执行：
- 运行 Android 单元测试并构建 Debug APK；
- 复制为仓库根目录下 `Listening-Lab-版本号.apk`；
- 计算 APK 的 SHA-256 与文件大小；
- 原子更新云端 `latest.json` 并上传 APK 到发布目录；
- 调用公网最新版本接口进行验收。

**可选环境变量配置：**
- `LISTENING_LAB_DEPLOY_HOST`：SSH 主机名（默认 `tecent-server`）
- `LISTENING_LAB_RELEASE_DIR`：云端发布目录
- `LISTENING_LAB_PUBLIC_API_URL`：公网 API 根地址
- `MANDATORY_UPDATE=true`：标记为强制更新
- `MINIMUM_VERSION_CODE=10`：声明最低兼容版本号

### 3. 签名与兼容性说明
Android 只允许“包名相同、签名相同、versionCode 更高”的 APK 覆盖安装。目前发布脚本沿用本地 Debug 签名，以兼容测试设备。若切换为正式 Release 签名，需备份好 keystore，切换时只需手机端重新安装一次即可。
