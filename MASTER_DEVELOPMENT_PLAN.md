# 🎯 AI 听力与口语学习系统 - 模块化开发计划与测试规范文档 (Master Plan)

> 本文档定义了项目的整体架构拆分、基础模块验证情况以及新增扩展模块（BYOK 直连、AI 角色扮演口语对练、划词生词本、双人播客等）的开发路线图。

项目分为三个完全独立的子工程：
1. **`01tts-worker/`**：本地 AI 与 Edge TTS 消费处理引擎（Python/Java）。
2. **`01tts-server/`**：云端后端服务（Java 8 + Maven + Spring Boot）。
3. **`01tts-app/`**：移动端客户端（Kotlin + Jetpack Compose）。

所有模块均遵循 **“小步快跑、开发即测试”** 原则，完成每个模块后必须执行并通过对应的测试用例。

---

## 目录结构蓝图 (Project Blueprint)

```
01tts/
├── 📄 MASTER_DEVELOPMENT_PLAN.md           # 本主开发计划与测试规范文档
│
├── 💻 01tts-worker/                        # 模块 1：本地 Worker 消费与 AI/TTS 引擎
│   ├── input/                             # 待转换文本
│   ├── output/                            # 生成的 MP3 音频输出
│   ├── venv/                              # Python 3.14 虚拟环境
│   ├── main.py                            # Edge TTS 生成逻辑
│   ├── worker.py                          # Redis 监听与 DeepSeek/GPT 处理入口
│   └── tests/                             # 模块 1 单元测试集合
│
├── ☁️ 01tts-server/                       # 模块 2：云端 Java 后端网关 (Java 8 + Spring Boot)
│   ├── src/main/java/com/example/tts/     # REST API 接口、TaskService、Redis 队列
│   └── pom.xml                            # Maven 依赖配置
│
└── 📱 01tts-app/                          # 模块 3：Android Kotlin 客户端
    ├── app/src/main/java/com/example/ttsapp/
    │   ├── ui/                             # Jetpack Compose 深空暗黑毛玻璃 UI
    │   ├── network/                        # Retrofit2 网络层
    │   └── player/                         # ExoPlayer 音频播放层
    └── build.gradle.kts
```

---

## 📋 一、 基础模块开发计划与完成状态

---

### 模块一：本地 Worker 消费与 AI/TTS 引擎 (`01tts-worker`)

#### 1.1 模块目标
建立本地常驻 Worker，从 Redis 队列中拉取 `task_uuid`，调用 DeepSeek/GPT API 生成文章与练习题，调用 Edge TTS 生成 MP3 音频，并将生成结果上传回云端。

#### 1.2 开发任务完成状态
- [x] **任务 1.1**：创建 Python 虚拟环境，集成 `edge-tts` 服务。（已完成并验证）
- [x] **任务 1.2**：编写 `src/deepseek_service.py`，实现结构化生成听力原文与练习题 JSON（模型默认调整为 `deepseek-chat`，支持 3 次指数退避重试）。
- [x] **任务 1.3**：编写 `worker.py`，实现 `BRPOP queue:tts_tasks` 阻塞拉取任务。
- [x] **任务 1.4**：实现结果上传与失败异常回调 (`POST /api/v1/tasks/{uuid}/fail`)。

#### 1.3 自动化测试用例 (Test Cases) - 100% PASS
- `python3 -m unittest discover -s tests -v` (9 个单元测试全部通过)

---

### 模块二：云端 Java 后端网关与数据库 (`01tts-server`)

#### 2.1 模块目标
基于 **Java 1.8 + Maven 3.8.9 + Spring Boot 2.7.x** 搭建云端 REST API 服务。提供任务创建、状态查询、本地 Worker 数据回传接口，以及 Redis 队列写入。

#### 2.2 开发任务完成状态
- [x] **任务 2.1**：创建 Spring Boot 工程框架与 `pom.xml` 依赖（Data JPA, Spring Web, Redis, MySQL/H2）。
- [x] **任务 2.2**：设计并实现 `Task` 数据实体与数据库 Repository。
- [x] **任务 2.3**：开发 `POST /api/v1/tasks` 接口（生成 `task_uuid`，保存数据库，推入 Redis 队列）。
- [x] **任务 2.4**：开发 `GET /api/v1/tasks/{taskUuid}` 接口。
- [x] **任务 2.5**：开发 `POST /api/v1/tasks/{taskUuid}/complete` 与 `/fail` 接口。

#### 2.3 自动化测试用例 (Test Cases) - 100% PASS
- `mvn test` (控制器与服务层 3 个 JUnit 测试套件全部 BUILD SUCCESS)

---

### 模块三：Android 客户端工程 (`01tts-app`)

#### 3.1 模块目标
基于 **Android Studio + Kotlin + Jetpack Compose** 开发手机 App，实现深空暗黑毛玻璃 UI、结合抗网络抖动轮询拉取、ExoPlayer 音频播放、单选题交互与麦克风口语跟读评测。

#### 3.2 开发任务完成状态
- [x] **任务 3.1**：在 Android Studio 中新建 Kotlin Jetpack Compose 工程。
- [x] **任务 3.2**：搭建 Retrofit2 网络请求层，封装 `TaskApiClient`。
- [x] **任务 3.3**：实现深空暗黑毛玻璃 UI、炫彩按压动效按钮与友好提示 Banner。
- [x] **任务 3.4**：实现具备网络单次断开重试容错（允许 5 次重试）的 1.5 秒轮询逻辑。
- [x] **任务 3.5**：集成 `ExoPlayer` 实现音频播放器组件。
- [x] **任务 3.6**：实现单选题交互与麦克风口语跟读录音上传。

---

### 模块四：端到端 (End-to-End) 全链路闭环集成测试
- [x] 手机端输入 Prompt ➔ 云端生成 UUID 入队 ➔ 本地 Worker 消费并生成 ➔ 上传云端 ➔ 手机端轮询获取播放与答题 ➔ 提交口语录音评分的全闭环验证通过。

---

## 🚀 二、 新增功能扩展模块计划 (Advanced Feature Roadmap)

为了解决产品功能单一、增加实时响应速度与打造完整英语学习闭环，新增以下 4 个扩展开发模块：

---

### ⚡ 模块五：App 端侧直连 API 模式 (BYOK - Bring Your Own Key)

#### 5.1 模块目标
允许用户在 App 设置中配置个人的 **DeepSeek** (`https://api.deepseek.com/v1`)、**Kimi/Moonshot** (`https://api.moonshot.cn/v1`) 或 **ChatGPT** API Key，直接由手机发起 HTTP 请求秒级出题（响应延迟 < 1 秒），同时保留“云端队列模式”。

#### 5.2 开发任务拆分
- [ ] **任务 5.1**：在 Android App 中建立【设置/API Key 配置】界面，使用 `EncryptedSharedPreferences` 安全加密存储秘钥。
- [ ] **任务 5.2**：在 App 端集成 DeepSeek / Kimi 直连 Retrofit 客户端。
- [ ] **任务 5.3**：实现【云端异步模式】与【客户端直连模式】的双模式一键切换 Toggle。

#### 5.3 测试规范
- **测试 TC-5.1**：输入正确的 DeepSeek Key，点击生成后 1 秒内完成文章与题目渲染。
- **测试 TC-5.2**：测试无网络或 Key 无效时的错误提示与安全回退逻辑。

---

### 🎙️ 模块六：AI 实时情景口语角色扮演 (Voice Roleplay Tutor)

#### 6.1 模块目标
从单轮问答拓展为多轮语音情景对话（如星巴克点餐、Java 模拟面试官、雅思口语 Part 3 对谈），提供实时语法与发音纠错建议。

#### 6.2 开发任务拆分
- [ ] **任务 6.1**：设计情景剧本对话状态机与多轮对话系统 Prompt。
- [ ] **任务 6.2**：实现 App 端的“AI 播报 ➔ 麦克风录音 ➔ 文本转写 ➔ 实时纠错提示”多轮循环界面。
- [ ] **任务 6.3**：支持在对话结束后生成完整对话评估总结报告。

---

### 📖 模块七：划词查词 + 个人生词本 + 艾宾浩斯复习卡 (Flashcards)

#### 7.1 模块目标
支持在听力原文中长按划词查询音标与释义，一键加入生词本，并基于艾宾浩斯遗忘曲线进行卡片复习。

#### 7.2 开发任务拆分
- [ ] **任务 7.1**：实现听力原文文本长按划词查词弹窗（集成免费词典 API，显示美音/英音音标与例句）。
- [ ] **任务 7.2**：集成 Android **Room 数据库**，建立 `Vocabulary` 实体与“个人生词本”。
- [ ] **任务 7.3**：开发基于艾宾浩斯遗忘曲线的翻牌复习卡片 (Flashcards) 交互组件。

---

### 📻 模块八：双人英文播客 (Podcast Studio) & 自定义文件导入

#### 8.1 模块目标
支持生成双人对谈播客听力，并支持导入本地英文 PDF / TXT 文件生成配音与题目。

#### 8.2 开发任务拆分
- [ ] **任务 8.1**：实现双人英文播客生成（Host 女声 Ava 与 Guest 男声 Andrew 交互对谈）。
- [ ] **任务 8.2**：支持导入本地 PDF / TXT 英文文章，由 AI 自动提取 5 个核心生词与 3 道理解题，并生成 TTS 音频。

---

## 🏁 执行准则

1. 基础模块（模块 1~4）已 100% 开发完成并通过自动化测试。
2. 扩展模块（模块 5~8）将按照“模块五（BYOK直连） ➔ 模块七（生词本） ➔ 模块六（AI对练） ➔ 模块八（双人播客）”的顺序迭代开发。
3. 任何新模块提交代码前，必须编写对应的单元测试并确保 **100% PASS**。
