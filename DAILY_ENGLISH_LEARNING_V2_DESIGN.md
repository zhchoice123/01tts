# Listening Lab V2 每日英语学习系统设计

## 1. 目标与设计结论

Listening Lab V2 不再以“用户点击后临时生成一节课”为主流程，而是每天在云端提前准备一套可直接学习的内容。用户打开 App 后立即看到当天的阅读、听力、口语、写作、新闻和词汇任务，并能查询历史、重复播放和继续未完成内容。

推荐方案：

- Spring 服务端每天只运行一次“每日计划编排任务”，默认 05:30。
- Python Worker 保持常驻，负责内容生成、新闻清洗、TTS、转写和评分。
- App 的 WorkManager 只负责同步、缓存和通知，不在后台直接调用大模型生成整套课程。
- DeepSeek、Kimi 和 OpenAI 通过统一 Provider 路由使用；每日生成优先 DeepSeek/Kimi，失败时自动切换。
- ChatGPT 定时任务作为可选内容输入，通过受保护的“内容收件箱”接入；服务器自己的每日计划不能依赖 ChatGPT 客户端页面。
- 服务端是跨设备历史的事实来源，Room 是手机离线缓存。

## 2. 每日内容包

每天生成一个 `DailyLearningPack`，建议总时长 25–35 分钟：

| 模块 | 默认内容 | 产物 |
|---|---|---|
| 阅读 | 1 篇 250–500 词短文 | 原文、简化版、中文辅助、理解题 |
| 新闻 | 1–2 条可信来源摘要 | 原文链接、来源、发布时间、摘要 |
| 听力 | 阅读文章或独立材料 | MP3、逐句文本、播放进度 |
| 口语 | 1 个复述或观点题 | 提示词、录音、转写、评分 |
| 写作 | 1 个 80–150 词任务 | 要点、参考结构、AI 反馈 |
| 词汇 | 8–12 个核心词 | 音标、中文释义、例句、搭配、读音 |

生成完成状态采用：

```text
PLANNED → GENERATING → READY → IN_PROGRESS → COMPLETED
                         ↘ FAILED_RETRYABLE / FAILED_FINAL
```

`READY` 前必须同时满足文章 JSON 校验成功、音频可下载、练习题存在。部分模块失败时允许内容包以 `PARTIALLY_READY` 展示，不阻塞其他学习内容。

## 3. 话题与内容选择

话题池分为：

- 技术：Java、Spring、Android、AI、数据库、网络、架构。
- 体育：赛事规则、训练、运动科学、人物故事。
- 社会与文化：历史、城市、教育、工作文化、跨文化沟通。
- 时事与政治文化：只使用可信新闻来源，区分事实、观点和背景。
- 科学与商业：太空、环境、医学常识、产品和公司案例。
- 生活英语：旅行、沟通、健康、消费和日常表达。

每日编排不是纯随机。采用“加权随机 + 去重约束”：

1. 根据用户兴趣权重选择主类别。
2. 最近 14 天不得重复同一具体主题。
3. 最近 7 天至少覆盖 3 个不同类别。
4. 结合最近 20 次成绩调整 CEFR 难度。
5. 新闻与事实型内容保存来源 URL，不允许模型虚构新闻。
6. Provider 路由默认轮换 DeepSeek/Kimi；同一任务失败两次后切换 Provider。

## 4. ChatGPT 定时内容接入

ChatGPT 中创建的定时任务不能被服务器“读取聊天页面”作为稳定生产接口。除非该任务支持向外部 Webhook 主动提交，否则服务器无法可靠知道 ChatGPT 每天推送了什么。

设计一个统一内容收件箱：

```http
POST /api/v2/inbox/items
X-Ingest-Token: <server-secret>
Content-Type: application/json

{
  "source": "CHATGPT_AUTOMATION",
  "externalId": "daily-task-2026-07-26-reading",
  "contentType": "READING",
  "title": "Today's technical reading",
  "body": "...",
  "sourceUrl": null,
  "publishedAt": "2026-07-26T05:00:00+08:00"
}
```

接入优先级：

1. ChatGPT 任务能调用 Webhook：直接投递到收件箱。
2. ChatGPT 任务发送邮件：增加邮箱适配器，只读取指定发件人和标签。
3. 暂时无法自动投递：App/网页提供“粘贴到今日收件箱”。
4. 无 ChatGPT 输入时：服务端照常用 DeepSeek/Kimi 生成每日包。

`externalId` 建立唯一约束，避免同一内容重复导入。外部内容需经过 Schema 校验、事实来源标记和敏感字段清理，再进入每日计划。

## 5. 词汇学习设计

阅读正文中的核心词汇由服务端预先标注，App 通过 token span 渲染为可点击文本。点击后打开词汇底部面板：

- 单词、词性、英美音标。
- 当前句中的中文释义。
- 常用中文释义和英文简明解释。
- 原文例句、额外例句。
- 常见搭配、介词模式、派生词和易错点。
- 美音/英音播放按钮。
- 收藏、生词本、已掌握。

数据结构与本地 `word --rich` 工作流对齐：

```json
{
  "word": "concurrency",
  "lemma": "concurrency",
  "partOfSpeech": "noun",
  "phoneticUs": "...",
  "phoneticUk": "...",
  "meaningZh": "并发；同时发生",
  "definitionEn": "the state of multiple tasks making progress...",
  "contextMeaningZh": "本文中指多个任务交替或同时执行",
  "collocations": ["handle concurrency", "concurrency control"],
  "examples": ["Virtual threads simplify some concurrency code."],
  "usageNotes": "...",
  "audioUsUrl": "...",
  "audioUkUrl": "..."
}
```

第一版复习间隔：当天、1 天、3 天、7 天、14 天、30 天。练习包含识义、听音、拼写、完形填空和造句。每个词保留来源文章，复习时优先展示原始语境。

## 6. App 信息架构

### Today

- 今日学习包及准备状态。
- 一个主按钮：“开始今日学习”或“继续”。
- 阅读、听力、口语、写作、词汇的独立完成进度。
- 内容未准备好时显示最后同步时间和明确失败原因。

### Discover / Read

- 今日新闻、技术文章和随机话题。
- 类别、难度、Provider 和日期筛选。
- 原文、简化英文、中英辅助三种阅读模式。
- 点击词汇、长按句子解释或朗读。

### Practice

- 听力全文、逐句循环、0.75–1.5 倍速、盲听。
- 阅读理解、听写、口语复述、写作。
- 语音可选择 Ava、Andrew 等，并支持美音/英音。

### Library

- 按日期、类别、难度、完成状态搜索历史。
- 文章、音频、题目、答案、口语和写作反馈完整保存。
- 重复播放、从上次进度继续、重新练习但保留每次成绩。
- 生词本、错题本、收藏和离线下载。

### Settings

- UI 语言：中文、English、跟随系统。
- 学习辅助：纯英文、中英辅助、自动翻译。
- 默认 CEFR、每日时长、兴趣权重、周末策略。
- TTS 声音、口音、语速。
- 通知时间和网络条件。
- Provider 优先级、模型、Base URL、连接测试和每日额度。
- 个人 Key 新增、修改、删除；不显示完整 Key。

## 7. BYOK 与多用户演进

个人版本使用一个默认 `local-profile`。未来上线时引入真实用户账号，但数据模型从第一版就带 `ownerId`，避免再次重构。

Key 存储分为两类：

- 手机直连 Key：使用 Android Keystore 包装后保存在本机，适合即时翻译、句子解释和对话。
- 服务端生成 Key：仅存服务器环境变量或 Secret Manager，适合每日预生成。App 不上传明文 Key。

未来如果允许用户把自己的 Key 保存到服务器，必须使用服务端主密钥加密、按用户隔离，并提供删除与密钥轮换；第一版不实现云端用户 Key 托管。

## 8. 服务端与数据模型

当前 H2 适合原型，但每日历史、多用户和并发任务应迁移到 PostgreSQL。音频第一阶段继续使用服务器磁盘，第二阶段迁移腾讯云 COS。

核心表：

- `user_profile`
- `user_learning_preference`
- `provider_preference`
- `daily_learning_pack`
- `learning_content`
- `content_source`
- `exercise`
- `exercise_attempt`
- `vocabulary_entry`
- `user_vocabulary`
- `review_schedule`
- `listening_progress`
- `speaking_attempt`
- `writing_attempt`
- `content_inbox`
- `generation_job`

关键唯一约束：

```text
daily_learning_pack(owner_id, plan_date)
content_inbox(source, external_id)
user_vocabulary(owner_id, lemma)
generation_job(idempotency_key)
```

推荐 API：

```text
GET  /api/v2/daily-packs/today
GET  /api/v2/daily-packs/{date}
POST /api/v2/daily-packs/{date}/regenerate
GET  /api/v2/library
GET  /api/v2/library/{contentUuid}
GET  /api/v2/vocabulary/{word}
POST /api/v2/vocabulary/{word}/save
POST /api/v2/vocabulary/{word}/review
POST /api/v2/progress
GET  /api/v2/settings
PUT  /api/v2/settings
POST /api/v2/inbox/items
```

## 9. 每日调度

服务器只保留一个业务定时入口：

```text
05:30 DailyPackOrchestrator
  ├─ 读取 ChatGPT/邮件收件箱
  ├─ 选择当天类别和难度
  ├─ 创建唯一 DailyLearningPack
  ├─ 创建 2–4 个 GenerationJob
  ├─ 推入 Redis
  └─ Worker 生成文章、词汇、题目和音频
```

单服务器第一版采用 Spring `@Scheduled` + 数据库唯一约束 + ShedLock。应用启动时执行一次补偿检查：如果当天无计划或任务卡死，重新创建缺失任务。Worker 保持常驻，不属于“每日定时任务”。

App 在通知时间调用同步接口；若内容已 READY 则通知“今日学习已准备好”，否则使用 WorkManager 延迟重试。App 不重复触发服务器生成。

## 10. 安全、版权与可观测性

- 新闻保存来源、作者、发布时间和原文链接。
- 不公开分发抓取的完整付费文章。
- API Key、Redis 密码和 Authorization Header 永不进入日志。
- Inbox 使用独立 Token、请求签名、时间戳和幂等键。
- 每个生成任务记录 Provider、模型、耗时、状态、重试次数和错误分类。
- 指标至少包括：每日包准备成功率、平均准备时间、队列深度、AI/TTS 失败率、App 同步失败率。
- 对外上线前必须将 HTTP 公网接口升级为 HTTPS，并增加身份认证。

## 11. 验收场景

1. 05:30 后服务器只有一份当天计划，重复调度不会重复生成。
2. App 冷启动后 2 秒内显示已准备的 Today 数据，不调用生成接口。
3. 一篇内容可完成阅读、听力、口语、写作和词汇学习。
4. 点击核心词显示中文释义、音标、搭配、例句和英美发音。
5. 重启或重装 App 后，登录同一用户仍能查询服务端历史。
6. 历史音频可以重复播放，并恢复上次播放位置。
7. Provider 失败时切换备用 Provider，用户看到可理解的状态。
8. 中文/英文 UI、阅读辅助模式、声音与语速切换后立即生效。
9. 用户修改或删除本机 Key 后，连接测试结果正确且日志不泄露 Key。

