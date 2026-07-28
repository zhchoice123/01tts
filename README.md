# Edge TTS 文本转英文语音 (Text-to-Speech) 工程

本项目是一个轻量、高效且免费的语音生成工程。只需将 `.txt` 文本文件放入项目的 `input/` 目录下，运行对应命令即可自动调用 **Microsoft Edge TTS** 的神经网络高品质发音模型，生成英文 MP3 音频文件到 `output/` 目录。

---

## 📁 目录结构

```
01tts/
├── input/                  # 存放待转换的文本文件 (.txt)
│   └── sample.txt          # 示例英文文本
├── output/                 # 生成的 MP3 音频输出目录
│   └── sample.mp3
├── venv/                   # Python 虚拟环境 (自动生成/管理)
├── src/
│   ├── __init__.py
│   ├── tts_service.py      # Edge TTS 服务逻辑封装
│   └── utils.py            # 文件与路径管理辅助模块
├── main.py                 # CLI 命令行主程序
├── requirements.txt        # 项目依赖配置
├── README.md               # 项目使用说明
└── .gitignore              # Git 忽略规则
```

---

## ⚡ 快速开始

### 1. 环境准备与激活

项目已配置 Python 虚拟环境。在终端激活虚拟环境：

```bash
# macOS / Linux:
source venv/bin/activate
```

### 2. 转换默认示例文本

默认读取 `input/sample.txt` 并生成 `output/sample.mp3`：

```bash
python main.py
```

### 3. 读取指定文本文件生成 MP3

假设你在 `input/` 目录下放置了一个新文件 `my_article.txt`：

```bash
python main.py -f my_article.txt
```
生成的结果将自动存入 `output/my_article.mp3`。

---

## 🎙️ 常用命令与参数说明

| 参数 | 缩写 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `--file` | `-f` | `sample.txt` | `input/` 目录下的文本文件名 |
| `--output` | `-o` | `自动同名` | 指定输出在 `output/` 目录下的 MP3 文件名 |
| `--voice` | `-v` | `en-US-AvaNeural` | Edge TTS 声音模型（支持多国发音） |
| `--rate` | `-r` | `+0%` | 语速调节，如 `+15%` 或 `-10%` |
| `--pitch` | `-p` | `+0Hz` | 音调调节，如 `+5Hz` 或 `-5Hz` |
| `--list-voices` | | | 查看所有可用的 Edge 英文发音人列表 |

### 使用示例：

1. **指定发音人（如英音女声 Sonia）：**
   ```bash
   python main.py -f sample.txt -v en-GB-SoniaNeural -o output_uk.mp3
   ```

2. **加快语速 15%：**
   ```bash
   python main.py -f sample.txt -r "+15%"
   ```

3. **查看所有内置与在线英文发音人：**
   ```bash
   python main.py --list-voices
   ```

---

## 🌟 推荐的优秀英文神经网络发音人 (Voices)

| 声音模型 ID | 发音人描述 | 语言/方言 |
| :--- | :--- | :--- |
| `en-US-AvaNeural` *(默认)* | 自然生动女声 (Expressive & Natural) | 美式英语 (US) |
| `en-US-AndrewNeural` | 沉稳男声 (Warm & Professional) | 美式英语 (US) |
| `en-US-EmmaNeural` | 亲切女声 (Friendly & Conversational) | 美式英语 (US) |
| `en-US-BrianNeural` | 活力男声 (Young & Energetic) | 美式英语 (US) |
| `en-US-ChristopherNeural` | 新播专业男声 (Newsreader / Deep) | 美式英语 (US) |
| `en-GB-SoniaNeural` | 标准英音女声 (Standard British Accent) | 英式英语 (UK) |
| `en-GB-RyanNeural` | 清晰英音男声 (Clear British Tone) | 英式英语 (UK) |
| `en-AU-NatashaNeural` | 澳洲发音女声 | 澳式英语 (AU) |

---

## 🐍 Python 代码直接调用

除了命令行，你也可以在自己的 Python 模块中直接引入使用：

```python
import asyncio
from src.tts_service import convert_file_to_speech

# 将 input/demo.txt 转换为 output/demo.mp3
asyncio.run(
    convert_file_to_speech(
        filename="demo.txt",
        voice="en-US-AvaNeural",
        rate="+5%"
    )
)
```

---

## 三工程系统

仓库现已实现开发计划中的三个独立工程：

- `01tts-worker/`：消费 Redis 任务，调用 DeepSeek 生成课程、Edge TTS 生成 MP3，并使用 OpenAI 转写与 DeepSeek 完成口语评分。
- `01tts-server/`：Spring Boot 2.7 API，使用 H2 保存任务与口语答案，通过 Redis 分发任务，并提供音频访问地址。
- `01tts-app/`：Kotlin + Jetpack Compose 客户端，支持创建课程、轮询状态、播放音频、录音上传和显示口语评分。

### 本地运行

```bash
# 终端 1：Redis
redis-server --save '' --appendonly no

# 终端 2：服务端
cd 01tts-server && mvn spring-boot:run

# 终端 3：课程 Worker
cd 01tts-worker
../venv/bin/python worker.py

# 终端 4：口语评分 Worker
cd 01tts-worker
../venv/bin/python worker.py --speaking
```

Worker 需要环境变量 `DEEPSEEK_API_KEY`；口语评分还需要 `OPENAI_API_KEY`。Android 模拟器通过 `http://10.0.2.2:8080/` 访问本机服务。

### 完整测试

```bash
cd 01tts-worker && ../venv/bin/python -m unittest discover -s tests -v
cd 01tts-server && mvn test
cd 01tts-app && ./gradlew testDebugUnitTest assembleDebug
```
