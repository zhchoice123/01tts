# 01tts / Listening Lab

Listening Lab 是面向英语听力、阅读、词汇和口语训练的学习项目。仓库同时保留一个轻量的 Edge TTS 文本转语音命令行工具。

## 项目结构

- `01tts-worker/`：FastAPI 后端与任务 Worker，负责课程生成、TTS、口语转写和评分。
- `01tts-app/`：Kotlin、Jetpack Compose Android 客户端。
- `contracts/`：跨端接口契约样例。
- `main.py`、`src/`、`input/`：独立 Edge TTS 命令行工具。
- `LISTENING_LAB_PRODUCT_AND_TECHNICAL_DESIGN.md`：当前统一的产品与技术设计文档。

历史开发计划和阶段性测试报告已合并到统一设计文档或由 Git 历史保存，不再在仓库根目录重复维护。

## 服务地址与模型

- 公网 API：`https://api.zhchoice.xyz/`
- 文本生成：DeepSeek
- 默认语音合成：阿里云 CosyVoice；显式声音仍可选择 Edge TTS 或 OpenAI TTS
- 口语转写与部分口语能力：OpenAI

API Key 只通过本地忽略文件或环境变量配置，不得提交到 Git。

## Android

```bash
cd 01tts-app
./gradlew testDebugUnitTest assembleDebug lintDebug
```

详细开发、签名和在线更新说明见 `01tts-app/README.md`。

## 后端

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r 01tts-worker/requirements.txt
cd 01tts-worker
python -m unittest discover -s tests -v
python api.py
```

生产环境通过 systemd 运行 FastAPI，并由 Nginx 将 `api.zhchoice.xyz` 转发至后端。生产密钥、数据库配置与代理配置均留在服务器环境中。

## 独立 Edge TTS 工具

```bash
source venv/bin/activate
pip install -r requirements.txt
python main.py -f sample.txt
python main.py --list-voices
```

输入文本位于 `input/`，生成音频位于 `output/`。`output/*.mp3` 属于生成物，不提交 Git。

## 发布前检查

1. 后端单元测试通过。
2. Android 单元测试、Lint 和 APK 构建通过。
3. 确认版本号、HTTPS API 地址、APK 签名与 SHA-256。
4. 扫描仓库，确认没有 API Key、密码、代理订阅或私钥。
5. 上传版本化 APK，更新云端 `latest.json`，再验证公网下载和真实业务接口。
