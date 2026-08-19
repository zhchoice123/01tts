# Listening Lab 2.8.2 修复与发布优化方案

## 1. 文档目标

本文档基于当前 `2.8.2 (versionCode 14)` 工作区代码评审结果，整理发布前必须修复的问题、建议实施顺序、验收标准和提交策略。

当前版本建议定义为：`2.8.2-rc1`。在 P0 阻断项和回归验证全部通过前，不建议作为正式版本发布。

## 2. 当前结论

1. Python 后端单元测试当前为 `89/89` 通过，但日志中仍出现口语音频生成、评测器调用和异步协程错误，属于“测试通过但核心路径未真正成功”。
2. Android 的单元测试、Lint 和 Debug APK 构建可以完成；当前 APK 版本为 `2.8.2 (14)`，但 TTS 声音值存在重复拼接 provider 的风险。
3. iOS 本轮未完成有效构建验证，原因是本机缺少原构建目标所需的 iOS 26.5 Simulator/设备，因此只能标记为“尚未验证”，不能标记为代码失败或通过。
4. 当前工作区混合了 TTS、词汇、口语、进度、文档和 Jupyter Nginx 配置等多类修改，应修复后按功能拆分提交。

## 3. 必须优先修复的问题

### 3.1 P0：口语对练音频生成的异步调用错误

问题位置：`01tts-worker/src/backend_service.py`。

当前问题：

1. `audio_generator` 接收的目标路径应为 `pathlib.Path`，当前调用传入了 `str(output_path)`。
2. 业务服务内部使用 `asyncio.run(...)`；当 FastAPI 已运行在事件循环中时，会触发 `asyncio.run() cannot be called from a running event loop`。
3. 异常被捕获后接口仍继续返回，可能得到 `aiAudioUrl = null`，测试也没有因此失败。

优化要求：

1. 将创建口语 Session、提交口语轮次等涉及音频生成的方法改为异步方法，并在 API 路由中使用 `await`。
2. 直接执行 `await self.audio_generator(ai_text, output_path, voice=...)`，传递 `Path`，彻底移除该链路中的 `asyncio.run(...)`。
3. 初始化服务时显式创建 `speaking_session_audio_dir`。
4. 音频生成失败时返回明确、可观测的失败状态或错误码，不得静默伪装为成功。
5. 增加回归测试，确认协程被真正等待、音频文件被创建、返回 URL 可访问。

### 3.2 P0：禁止评测失败后写入虚构分数

问题位置：`01tts-worker/src/backend_service.py`。

当前问题：代码预置固定转写文本、85/88 分和固定反馈；当 assessor 不存在或调用失败时，仍可能把这些演示数据保存为真实用户成绩。

优化要求：

1. 删除所有固定转写、固定分数和固定反馈兜底。
2. 引入明确的评测状态，例如 `PENDING`、`COMPLETED`、`FAILED`、`NO_DATA`。
3. assessor 失败时保存失败原因或内部错误码，分数保持 `null`，不得生成看似真实的成绩。
4. 如果产品允许降级转写，必须记录 `evaluationMode` 或 `scoreSource`，让客户端能区分真实 AI 评测和降级结果。
5. 测试必须断言 assessor 异常时不会产生任何虚构分数。

### 3.3 P0：口语音频 URL 与文件名校验不兼容

问题位置：`01tts-worker/api.py`。

当前问题：公共 `audio_response` 只允许 UUID 文件名，但口语文件名采用 `spk_<12hex>_turnN_ai/user.mp3/m4a` 格式，因此生成出的口语 URL 会被文件名校验拒绝。

优化要求：

1. 为口语音频建立独立且严格的白名单正则，不放宽现有内容音频的 UUID 校验。
2. 建议格式：`^spk_[0-9a-f]{12}_turn[1-9][0-9]?_(ai|user)\.(mp3|m4a)$`。
3. 抽取可接收指定 pattern 的安全文件响应函数，继续防止目录穿越。
4. 增加合法文件、非法文件、目录穿越和不存在文件的 API 测试。

### 3.4 P0：Android TTS voice 重复拼接 provider

问题位置：`01tts-app/app/src/main/java/com/example/ttsapp/MainViewModel.kt`。

当前问题：`setTtsVoice()` 无条件执行 `"$provider:$voice"`；若 UI 传入的值已经是 `openai:nova`，最终会变成 `openai:openai:nova`。

优化要求：

1. 统一存储和传输格式为完整值 `provider:voice`。
2. 新增单一规范化函数：已带前缀的合法值保持不变；裸 voice 自动补当前 provider；前缀与当前 provider 不一致时拒绝或明确切换 provider。
3. 后端也应严格校验 provider/voice 组合，非法值返回 4xx，不得静默选默认声音。
4. 补充 OpenAI、Aliyun、裸 voice、重复前缀、跨 provider 值等 Android 单元测试。

## 4. 第二优先级优化

### 4.1 P1：完善口语 Session 状态机和幂等性

1. 提交轮次时校验 `turnIndex == currentTurn`。
2. 已完成或失败的 Session 禁止继续提交。
3. 数据库增加 `(session_id, turn_index)` 唯一约束。
4. 重复请求应返回已有结果或明确冲突，不得创建重复轮次。
5. 建议状态流：`CREATED -> IN_PROGRESS -> COMPLETED`，异常进入 `FAILED`；每个轮次单独记录音频、转写和评测状态。

### 4.2 P1：明确 SSE 的真实能力边界

当前实现最多轮询 10 次、每次间隔 0.5 秒，约 5 秒后断开，只能视为短轮询式状态通知，并不是真正的长连接任务流或音频分块流。

第一阶段建议：

1. 将其定义为可靠的任务状态流，只发送 `status`、`ready`、`failed` 和 heartbeat。
2. 检测客户端断开并停止循环。
3. 使用合理超时、心跳和终态退出策略。
4. 不对外宣称 `chunk_ready` 或“首段音频可播放”，除非后端确实已经生成并暴露分块资源。

第二阶段如需要真正音频流式播放，再单独设计 chunk 存储、顺序、重连游标和客户端拼接协议。

### 4.3 P1：数据库迁移与索引

1. 不应仅依赖 `Base.metadata.create_all()` 管理生产数据库变更。
2. 为新增表、字段、枚举、唯一约束和索引增加 Alembic 或版本化 SQL migration。
3. 在 staging 数据库验证升级和回滚路径。
4. 为 Session 查询、轮次查询、任务状态轮询等高频条件建立必要索引。

### 4.4 P2：错误可观测性和文档一致性

1. Android 词库保存/加载等路径不要静默吞掉异常；至少写入日志并向 UI 暴露可理解的错误状态。
2. 清理 `backend_service.py` 的尾随空格，使 `git diff --check` 通过。
3. 将产品路线图中的旧版本 `2.7.1 (11)` 更新为当前真实基线，并注明 2.8.2 的验证范围。
4. Jupyter Nginx 配置属于基础设施变更，应与 Listening Lab 产品功能分开提交和审查。

## 5. 测试与验收门槛

### 5.1 自动化测试

1. 后端：`cd 01tts-worker && ../venv/bin/python -m unittest discover -s tests -v`。
2. Android：`cd 01tts-app && ./gradlew testDebugUnitTest lintDebug assembleDebug`。
3. `git diff --check` 必须无输出。
4. 测试日志不得再出现未等待协程、`asyncio.run()` 事件循环冲突、Path 类型错误或 assessor 假失败仍返回分数。

### 5.2 本地 API 验收

1. 创建口语 Session 后，首轮 AI 音频文件真实存在且 URL 返回 200。
2. 上传用户音频后，转写/评测成功时返回真实结果；失败时返回明确状态且 score 为 `null`。
3. 下一轮 AI 音频真实生成并可播放。
4. 重复提交、越序提交、已完成后提交均符合设计的幂等或冲突行为。
5. TTS demo 对 OpenAI 和 Aliyun 的完整 voice 值均能正常工作，非法 voice 返回明确 4xx。

### 5.3 发布前验收

1. 在 staging 数据库执行 migration 并验证数据兼容性。
2. Android 真机验证设置入口、provider/voice 持久化、请求载荷和可听预览。
3. iOS 使用当前可用 Simulator 或真机完成构建与关键路径验证；未验证时必须在发布说明中明确标注。
4. 如使用云端 TTS，需完成一次不暴露凭证的真实云端 E2E，并检查生成 MP3 的时长和可播放性。

## 6. 建议实施顺序

1. 修复口语异步音频生成、文件 URL 和虚构评分三个发布阻断项。
2. 修复 Android TTS voice 规范化，并在后端增加契约校验。
3. 补齐会真实失败的回归测试，消除“绿灯但功能失败”。
4. 完善 Session 状态机、幂等性和数据库唯一约束。
5. 明确 SSE 第一阶段范围并补测试。
6. 增加数据库 migration 和 staging 验证。
7. 完成 Android 真机、iOS 和云端 E2E 验证。
8. 更新版本文档并按功能拆分提交。

## 7. 建议提交拆分

1. `fix(speaking): await audio generation and serve session audio`
2. `fix(speaking): remove fabricated assessment fallback`
3. `fix(tts): normalize provider voice contract`
4. `feat(speaking): enforce session turn state and idempotency`
5. `fix(stream): make task status events reliable`
6. `chore(db): add migrations for learning features`
7. `test(release): cover speaking and tts regressions`
8. `docs(release): update 2.8.2 validation baseline`
9. `chore(infra): add jupyter nginx configuration`（仅在确实需要提交该配置时单独处理）

## 8. 给 Gemini 的修复提示词

```text
你正在修复仓库 /Users/zhcho/Desktop/GoogleProject/01tts 的 Listening Lab 2.8.2 候选版本。

请先完整阅读：
1. /Users/zhcho/Desktop/GoogleProject/01tts/AGENTS.md
2. /Users/zhcho/Desktop/GoogleProject/01tts/LISTENING_LAB_2_8_2_FIX_AND_RELEASE_PLAN.md
3. 当前 git diff 和相关测试，不要假设工作区是干净的。

目标：按照修复方案完成代码修复和回归测试，使 2.8.2 达到可发布候选状态。优先修复真实功能问题，不要只让测试变绿。

必须完成：
1. 修复口语对练中的异步音频生成：服务方法改为 async，API 正确 await；向 audio_generator 传 pathlib.Path；移除该链路中的 asyncio.run；确保目录存在；失败必须可观测。
2. 删除固定转写、85/88 分和固定反馈等虚构兜底。评测失败时分数为 null，并返回/保存明确的 evaluation status 和安全错误码。
3. 为 speaking session 音频建立独立严格的文件名校验，使 spk_<12hex>_turnN_ai.mp3 和 spk_<12hex>_turnN_user.m4a 可安全访问，同时继续阻止目录穿越。
4. 修复 Android MainViewModel 的 provider 前缀重复问题。统一 voice 为 provider:voice，兼容裸 voice，拒绝或明确处理 provider 不一致；后端同步做严格校验。
5. 为口语 Session 增加状态和轮次完整性校验：只允许当前轮次、禁止完成后提交、数据库增加 (session_id, turn_index) 唯一约束，并处理重复请求。
6. 将 SSE 明确定义并实现为可靠的状态事件流：支持终态、心跳、断开检测和合理超时；除非真正实现音频 chunk，否则不要声称 chunk streaming。
7. 为新增数据库结构提供 Alembic 或版本化 SQL migration，不要只依赖 create_all。
8. 更新过期版本文档，清理尾随空格。不要把 deploy/nginx/jupyter-public-18888.conf 混入产品功能提交。

测试要求：
- 每个 bug 都新增回归测试，测试必须能在旧实现上失败、修复后通过。
- assessor 抛异常时必须断言没有虚构 transcript/score/feedback。
- 异步音频测试必须断言协程被 await、文件存在、URL 返回 200。
- 覆盖合法/非法 speaking 文件名和目录穿越。
- Android 覆盖 openai:nova、aliyun:loongdavid_v2、裸 voice、重复前缀、跨 provider 值。
- 覆盖重复轮次、越序轮次和已完成 Session。

完成后运行：
cd /Users/zhcho/Desktop/GoogleProject/01tts/01tts-worker && ../venv/bin/python -m unittest discover -s tests -v
cd /Users/zhcho/Desktop/GoogleProject/01tts/01tts-app && ./gradlew testDebugUnitTest lintDebug assembleDebug
cd /Users/zhcho/Desktop/GoogleProject/01tts && git diff --check

工作约束：
- 保留用户当前所有未提交修改，不得 reset、checkout 或覆盖无关改动。
- 不提交密钥、凭证、生成音频、venv、缓存、构建产物或本地 IDE 配置。
- API route 保持轻量，逻辑放 service；Python 使用类型标注和 pathlib.Path。
- 不要 push，不要部署，不要创建正式发布；除非我随后明确授权，也不要 commit。
- 如果模型或 API 契约需要变化，先同步更新后端模型、Android DTO、测试和文档，避免单端修改。

交付时请报告：
1. 修改了什么，以及对应解决了哪个问题；
2. 所有测试/构建命令的真实结果；
3. 尚未完成或未能验证的项目（尤其是真机、iOS、云端 E2E）；
4. 当前 git status 和建议的拆分提交清单；
5. 不要把“单元测试通过”描述成“真机或生产环境验证通过”。
```

## 9. 完成定义

只有以下条件全部满足，才可把 `2.8.2-rc1` 升级为正式发布候选：

1. 所有 P0 问题关闭并有有效回归测试。
2. 后端、Android 测试和构建通过，且日志无上述隐藏异常。
3. 口语音频、评测失败语义、TTS voice 契约完成 API 级真实验证。
4. 数据库 migration 在 staging 验证通过。
5. Android 真机关键路径通过；iOS 验证结果明确记录。
6. 文档、版本号、APK 元数据和发布说明一致。
7. 变更按产品功能、测试、文档和基础设施拆分清楚。
