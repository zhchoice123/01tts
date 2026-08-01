# Listening Lab 在线更新发布说明

## 用户侧流程

App 启动时会自动检查云端版本，也可以进入“设置 → 应用更新”手动检查。
发现更高的 `versionCode` 后，App 会下载 APK，核对文件大小和 SHA-256，校验通过后调用 Android 系统安装界面。

第一次从 App 安装时，Android 会要求允许 Listening Lab “安装未知应用”。这是 Android 的系统安全限制；授权一次后，后续发布不需要重新卸载 App。

域名完成备案前，App 使用 `http://42.192.62.145:8080/` 获取 API、音频和更新包；Android 仅对白名单中的这个 IP 开放明文流量。

## 开发发布流程

1. 修改 `01tts-app/app/build.gradle.kts`，确保 `versionCode` 比云端版本大。
2. 执行：

```bash
cd 01tts-app
./scripts/publish-update.sh \
  "本次更新说明一" \
  "本次更新说明二"
```

脚本完成以下动作：

- 运行 Android 单元测试并构建 Debug APK；
- 复制成仓库根目录下容易识别的 `Listening-Lab-版本号.apk`；
- 计算 APK 的 SHA-256 与大小；
- 原子更新云端 `latest.json`；
- 调用公网最新版本接口进行验收。

可选环境变量：

- `LISTENING_LAB_DEPLOY_HOST`：SSH 主机，默认 `tecent-server`；
- `LISTENING_LAB_RELEASE_DIR`：云端发布目录；
- `LISTENING_LAB_PUBLIC_API_URL`：公网 API 根地址；
- `LISTENING_LAB_FALLBACK_API_URL`：主地址验收失败时使用的备用直连地址；
- `MANDATORY_UPDATE=true`：标记为强制更新；
- `MINIMUM_VERSION_CODE=7`：声明最低支持版本。

## 签名要求

Android 只允许“包名相同、签名相同、versionCode 更高”的 APK 覆盖安装。目前发布脚本沿用这台 Mac 的 Debug 签名，以兼容已经安装的测试版本。若以后改为正式 Release 签名，需要先固定并备份 keystore；从 Debug 签名切换到 Release 签名时，手机只需要卸载重装一次。
