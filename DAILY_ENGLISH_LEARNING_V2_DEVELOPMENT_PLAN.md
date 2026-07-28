# Listening Lab V2 开发与测试计划

## 1. 实施原则

本计划以可独立验收的垂直切片推进，不同时重写三个工程。优先完成“服务器提前生成、App 打开即学、历史可恢复”，再增加词汇、BYOK 和多语言。

每一阶段必须满足：

- 数据库迁移可回滚。
- API 契约有测试。
- 外部 AI/TTS 在单元测试中使用 Mock，阶段验收再进行真实调用。
- 失败状态可见、可重试，不允许永久 `PENDING`。
- 不提交 Key、密码、生成音频和用户录音。

## 2. Phase 0：契约与生产基线

目标：把当前可运行原型变成可以安全扩展的基线。

### Server

- 引入 Flyway 和 PostgreSQL，保留 H2 仅用于测试。
- 为 Task、Content、DailyPlan 增加 `ownerId`、时间戳和版本字段。
- 所有 Redis 消息在数据库事务提交后发布。
- 增加任务超时扫描、幂等键和失败原因。
- 将 Spring 服务、Worker、Redis 配置纳入 `systemd` 和健康检查。
- 公网入口升级 HTTPS。

### 验收

- `mvn clean test` 全部通过。
- 服务重启后历史数据不丢失。
- 连续创建 100 个任务，无 Redis UUID 对应数据库 404。
- Worker 中断后任务可恢复或进入明确失败状态。

## 3. Phase 1：每日预生成垂直切片

目标：App 打开时直接看到已准备的当天课程。

### Server

- 新增 `DailyLearningPack`、`GenerationJob` 和用户偏好表。
- 实现 `DailyPackOrchestrator`，每天只触发一次。
- 使用唯一约束保证同一用户同一天只有一份计划。
- 实现启动补偿、失败重试和手动重新生成。
- 新增 `/api/v2/daily-packs/today`。

### Worker

- 支持一条 Job 生成文章、核心词汇、阅读题、口语题和写作题。
- 同一文章生成全文 MP3。
- Provider 路由支持 DeepSeek/Kimi 轮换和失败切换。
- 输出统一 `LessonContentV2` JSON Schema。

### Android

- Today 页面改为拉取今日包，不再默认调用 `POST /tasks`。
- 显示 READY、PARTIALLY_READY、GENERATING 和 FAILED。
- WorkManager 只同步和通知。

### 测试

- 调度执行两次仍只有一份计划。
- App 冷启动 2 秒内渲染缓存，并后台刷新。
- 05:30 生成、通知时间打开、当天课程可播放。
- Provider A 失败后 Provider B 成功。

## 4. Phase 2：历史、进度和重复播放

目标：所有学习行为可以查询、恢复和重复练习。

### Server

- 实现 Library 分页、筛选和详情 API。
- 保存每次答题、口语、写作和听力进度，而不是覆盖旧结果。
- 音频增加稳定资源 ID、大小、时长和缓存头。

### Android

- 引入 Room：
  - `DailyPackEntity`
  - `ContentEntity`
  - `AttemptEntity`
  - `PlaybackProgressEntity`
- 将 SharedPreferences 历史迁移到 Room。
- Library 支持日期、类别、难度和状态筛选。
- 重复播放、断点续播、重新答题；历史成绩使用时间线显示。

### 测试

- Room migration、分页和离线缓存测试。
- 播放到 40% 后退出，重新进入恢复位置。
- 同一课程练习三次，三条成绩均保留。
- 服务端暂时不可用时可打开已缓存历史。

## 5. Phase 3：词汇与 `word --rich` 能力

目标：核心词可点击、可播放、可收藏和复习。

### Worker

- 从文章提取 8–12 个核心词，并生成结构化词汇详情。
- 生成或缓存美音、英音单词音频。
- 对词义、词性、例句和搭配进行 Schema 校验。

### Server

- 新增词条、生词本和复习计划 API。
- 同一 lemma 全局复用基础词条，用户掌握度独立保存。
- 词汇音频使用缓存，避免重复生成。

### Android

- 阅读器基于 token span 渲染可点击词。
- 实现词汇详情 Bottom Sheet。
- 新增 Vocabulary 页面和五种复习题型。
- 实现当天、1、3、7、14、30 天的间隔复习。

### 测试

- 点击核心词显示正确上下文释义。
- 美音/英音均能播放。
- 收藏后重启 App 仍存在。
- 错误答案会缩短下一次复习间隔。

## 6. Phase 4：ChatGPT 收件箱与新闻

目标：将外部定时内容与服务器自动生成内容合并。

### Server

- 实现 `POST /api/v2/inbox/items`。
- 增加 Ingest Token、签名、时间戳、限流和幂等校验。
- 建立 ChatGPT Webhook、邮件和手动粘贴三种适配路径。
- RSS/Atom 新闻源白名单、去重和来源元数据。
- DailyPack 优先消费当天收件箱，再补充 AI 生成内容。

### Android

- 新闻卡显示来源、发布时间和“查看原文”。
- 支持将文本或 URL 分享到 Listening Lab 收件箱。
- 外部内容与 AI 生成内容使用不同来源标签。

### 测试

- 相同 `externalId` 重复投递只保存一次。
- 无 ChatGPT 输入时仍能生成完整今日包。
- RSS 条目保留来源 URL，失败源不阻塞其他内容。
- 未授权 Inbox 请求返回 401。

## 7. Phase 5：阅读、听力、口语和写作闭环

目标：围绕同一篇文章完成四项训练。

### Android

- 阅读：原文、简化版、中英辅助。
- 听力：全文、盲听、逐句循环、变速和听写。
- 口语：复述、观点题、真实振幅和评分详情。
- 写作：草稿、提交、逐句建议和修改后版本。

### Server / Worker

- 保存写作多版本和反馈维度。
- 口语任务失败必须回写 FAILED，不能永久 PENDING。
- 通过代理或本地 Whisper 保证云端转写可用。
- 分数包含可解释维度：内容、语法、词汇、流利度。

### 测试

- 口语网络失败后显示可重试错误。
- 写作修改前后两个版本均保留。
- 同一文章四项训练完成后 Today 状态为 COMPLETED。

## 8. Phase 6：多语言、声音和用户配置

目标：用户可在最后一页自行修改全部个人设置。

### Android

- 使用资源文件实现 `zh-CN`、`en`，禁止 UI 文案硬编码。
- 支持跟随系统、中文、英文即时切换。
- 阅读辅助模式独立于 UI 语言。
- 声音选择包含试听、口音、语速和默认值。
- Provider 设置支持：
  - DeepSeek、Kimi、OpenAI、Server
  - Base URL、模型、优先级
  - Key 新增、修改、删除
  - 连接测试、错误分类、用量提示
- Key 使用 Android Keystore 加密，不进入 Room、日志或备份。

### Server

- 用户设置 API 只保存非敏感偏好。
- 第一版服务端生成继续使用管理员 Key。
- 预留 OAuth/OIDC 和用户级加密 Key 托管接口，但不提前实现。

### 测试

- 中英文切换后所有五个页面正确刷新。
- 修改声音后下一次音频任务使用新声音。
- 401、429、超时和错误模型都有明确提示。
- 日志扫描不存在完整 API Key。

## 9. 推荐模块顺序

```text
Phase 0 生产基线
  → Phase 1 每日预生成
  → Phase 2 历史与断点播放
  → Phase 3 词汇闭环
  → Phase 4 ChatGPT/新闻收件箱
  → Phase 5 四项训练
  → Phase 6 多语言与BYOK
```

不建议先开发复杂的手机端大模型随机生成页面。它会再次形成“点击后等待”，与本次目标冲突。手机直连 AI 应优先用于即时解释、翻译和对话；每日完整课程应在服务器提前生成。

## 10. 第一迭代建议

第一迭代控制在一个可完整验收的版本：

1. PostgreSQL/Flyway 与任务幂等。
2. 每天 05:30 生成一份 `DailyLearningPack`。
3. DeepSeek/Kimi 轮换生成一篇阅读、10 个词、3 道题和 MP3。
4. Today 打开直接显示当天内容。
5. Library 保存最近 30 天内容并支持重复播放。
6. App 中支持日期筛选、断点播放和手动刷新。

暂不加入：

- ChatGPT 自动 Webhook。
- 多用户登录。
- 用户 Key 上传服务器。
- 复杂口语对话和写作多版本。

第一迭代通过后，再实现词汇详情与 ChatGPT 收件箱，可显著降低同时修改三端造成的集成风险。

## 11. 完成定义

版本可交付必须同时满足：

```text
Server: mvn clean test
Worker: ../venv/bin/python -m unittest discover -s tests -v
Android: ./gradlew clean testDebugUnitTest assembleDebug
Android: ./gradlew lintDebug
```

并提供以下真实证据：

- 云端调度日志。
- 当天唯一计划记录。
- Redis 任务消费记录。
- READY 内容 JSON。
- HTTP 200 MP3 下载。
- App Today 页面截图。
- 历史重复播放视频或日志。
- 重启 App 后数据恢复。
- 最终 APK SHA-256。

