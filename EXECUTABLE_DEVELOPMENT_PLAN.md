# Listening Lab 可执行开发与测试计划

## 1. 冻结基线

本计划基于 2026-07-25 14:51（Asia/Shanghai）连续观察稳定的文档版本：

| 文档 | SHA-256 |
|---|---|
| `LISTENING_LAB_PRODUCT_AND_TECHNICAL_DESIGN.md` | `bb1b1c4b79d10d43ac093e8612867b3f5d92480b69232395c02779e00cf7e00e` |
| `MASTER_DEVELOPMENT_PLAN.md` | `cf95e72dd37df4f2ce77049cc0b8fe6e6ab11e80753334e9370dd71c4b512d5f` |

本轮交付目标是完成一个可安装、可每天使用的个人英语学习垂直切片：在 App 中导入或生成英文内容，完成阅读理解、收藏生词、生成并播放听力音频、提交口语练习，并在重启后恢复记录。新闻定时推送、技术文档、Provider 直连和云端异步任务共用同一数据契约。

## 2. 跨模块契约（冻结）

所有新增接口使用 `/api/v1`，JSON 字段使用 `lowerCamelCase`，时间使用 UTC ISO-8601，主键使用 UUID。

### 2.1 核心状态

- `ContentStatus`: `DRAFT | GENERATING | READY | FAILED`
- `LessonStatus`: `READY | READING | QUIZ_COMPLETED | LISTENING_COMPLETED | SPEAKING_COMPLETED | REVIEWED`
- `SourceType`: `TEXT | URL | NEWS | TECH_DOC`
- 异步错误返回：`{"code":"...","message":"...","retryable":true}`

### 2.2 内容契约

`LessonContent` 必须包含：

```json
{
  "uuid": "uuid",
  "title": "Understanding Virtual Threads",
  "sourceType": "TECH_DOC",
  "sourceUrl": "https://example.com/article",
  "level": "B1",
  "passage": "...",
  "simplifiedPassage": "...",
  "audioUrl": "https://host/api/v1/audio/file.mp3",
  "vocabulary": [{"word":"concurrency","phonetic":"","definition":"","example":""}],
  "questions": [{"type":"INFERENCE","prompt":"...","options":["A","B"],"answer":"A","explanation":"..."}],
  "speakingPrompts": ["Summarize the main idea."]
}
```

普通测试不得访问真实 AI、新闻或 TTS 服务。三模块只能修改各自目录；跨模块契约变更先记录到本文件，不得直接修改其他模块。

## 3. 独立任务 A：Android App（TRAE Work）

**写入范围：** `01tts-app/`

1. 将现有单页面重构为 `Today / Read / Practice / Library / Settings` 五个入口，品牌统一为 Listening Lab。
2. 引入 Room，保存文章、题目作答、生词、听力进度和口语成绩；迁移现有 SharedPreferences 历史，重启后可恢复。
3. 实现文本导入阅读课、三道阅读题、生词收藏及 Library 回看。
4. 建立统一 `AiProvider`，支持 DeepSeek、Moonshot/Kimi、OpenAI 和 Server；至少实现连接测试、结构化生成、401/429/超时/损坏 JSON 分类。
5. 增加 WorkManager 每日唯一任务、通知权限、通知渠道和打开 Today 的 Deep Link。
6. 修复播放器拖拽竞争；录音 UI 使用真实振幅；异步页面包含加载、空态、失败原因和重试。
7. API Key 构建方案：
   - 读取不入库的 `api-keys.properties`；
   - 提供 `api-keys.properties.example`；
   - 通过 `BuildConfig` 注入个人 APK，首次启动复制到 Keystore 支持的本地存储；
   - 设置页允许覆盖内置默认值，日志不得输出 Key。

**测试门禁：**

```bash
cd 01tts-app
./gradlew clean testDebugUnitTest assembleDebug
./gradlew lintDebug
```

新增 Room migration、Provider MockWebServer、复习算法、ViewModel 恢复测试。交付 APK 路径和 SHA-256，但最终发布包由集成阶段重建。

## 4. 独立任务 B：Spring Boot API（WorkBuddy）

**写入范围：** `01tts-server/`

1. 新增文章、练习、生词、作答、每日计划和学习进度实体及 Repository。
2. 提供：
   - `POST /api/v1/content/import`
   - `GET /api/v1/content/{uuid}`
   - `POST /api/v1/content/{uuid}/attempts`
   - `GET /api/v1/daily-plans/{date}`
   - `POST /api/v1/daily-plans/{date}/generate`
   - `GET /api/v1/library`
3. 内容生成继续通过 Redis 发布 UUID；幂等键防止重复生成同一天计划。
4. 音频 URL 必须能由手机公网下载，返回正确 `Content-Type`，阻止路径穿越。
5. 保持现有 task/speaking API 兼容；统一错误 JSON，不在日志记录 Authorization 或 Key。
6. H2 测试与现有部署配置兼容；生产配置仅引用环境变量。

**测试门禁：**

```bash
cd 01tts-server
mvn clean test
mvn -DskipTests package
```

新增 Controller/Service/Repository 测试，覆盖幂等、404、非法输入、音频 Range/Content-Type 与路径穿越。交付可执行 JAR 路径和 SHA-256。

## 5. 独立任务 C：Python Worker（Antigravity）

**写入范围：** `01tts-worker/`

1. 扩展配置模型：Redis URL/密码、Server URL、音频输出、新闻源、DeepSeek/OpenAI/Moonshot 模型；Key 优先读取环境变量，配置文件仅允许可选覆盖。
2. 实现文本、URL、RSS/Atom 和技术文档内容获取；保留来源、原始 URL、发布时间与抓取时间。
3. 生成符合 `LessonContent` 的固定 JSON，执行 Schema 校验；仅自动修复一次，失败调用 fail 接口。
4. 对文章生成 Edge TTS 音频并上传；双人播客作为可选任务类型，不阻塞基础文章流程。
5. 保持 lesson 与 speaking 队列兼容；Redis 断线重连、外部请求超时、临时文件清理和脱敏日志。

**测试门禁：**

```bash
cd 01tts-worker
../venv/bin/python -m unittest discover -s tests -v
../venv/bin/python worker.py --config config.yaml --once
```

普通单测 Mock Redis、HTTP、AI 和 TTS，覆盖网页清洗、RSS、Schema、重试、失败回调、上传和配置优先级。`--once` 作为集成检查，可在队列为空时正常退出并输出明确日志。

## 6. 集成顺序与验收证据

1. 三模块独立测试全部通过后，先审查跨模块字段和状态，再合并修正。
2. 从环境变量生成本地 `01tts-app/api-keys.properties`，确认被 `.gitignore` 排除；构建产物中允许包含个人 Key，但控制台、测试报告和提交内容不得出现其值。
3. 启动 Redis、Server、Worker，创建一篇技术英语课并轮询至 `READY`。
4. 用公网或局域网可达 URL 下载 MP3，验证 HTTP 200、`audio/mpeg` 和非零文件。
5. 安装 APK：完成阅读题、收藏两个生词、播放音频、提交口语；杀进程重启后数据仍存在。
6. 最终执行三模块全量测试，生成：
   - `01tts-server/target/tts-server-*.jar`
   - `01tts-app/app/build/outputs/apk/debug/app-debug.apk`
   - 桌面个人 APK 副本及 SHA-256
   - `INTEGRATION_TEST_REPORT.md`

任何一步只返回 `PENDING`、只通过编译、或仅由智能体声称成功，都不视为完整验收。
