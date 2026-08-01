# Listening Lab 个性化复盘 V1 开发与测试计划

## 目标

V1 在不新增数据库表的前提下，使用现有学习进度、词汇状态和口语评分完成两个闭环：

1. 课程完成后展示听力、理解、词汇、口语四维报告。
2. 每日生成最多 10 项、约 5–10 分钟的复习队列。

当前数据只保存选择题总正确数，因此 V1 只能指出“理解维度偏弱”，不能虚构具体错题或错误原因。

## V1 数据契约

### LessonReviewReport

```json
{
  "clientId": "uuid",
  "contentUuid": "uuid",
  "overallScore": 78,
  "dimensions": [
    {"key": "listening", "label": "Listening", "score": 86, "status": "STRONG"}
  ],
  "weakPoints": [
    {
      "kind": "VOCABULARY",
      "title": "Review learning words",
      "detail": "3 words still need review",
      "priority": 1
    }
  ],
  "nextActions": ["Review today's learning words"],
  "generatedAt": "2026-08-01T08:00:00Z"
}
```

缺少数据的维度使用 `score: null`、`status: NO_DATA`，且不纳入总分。

### ReviewQueue

```json
{
  "clientId": "uuid",
  "date": "2026-08-01",
  "totalCount": 2,
  "estimatedMinutes": 2,
  "items": [
    {
      "id": "stable-id",
      "type": "VOCABULARY",
      "contentUuid": "uuid",
      "title": "Review connection pool",
      "reason": "Learning word is due",
      "priority": 1,
      "dueAt": "2026-08-01T08:00:00Z",
      "word": "connection pool",
      "status": "LEARNING",
      "action": "REVIEW_WORD"
    }
  ]
}
```

## 独立开发单元

### U1 课程报告计算引擎

- 范围：纯 Python，无数据库、Redis、网络依赖。
- 输入：学习进度、该课程词汇状态、可选口语详细评分。
- 输出：`LessonReviewReport`。
- 独立测试：无数据、满分、部分数据、零题目、低口语、分数裁剪、稳定排序。
- 命令：`cd 01tts-worker && ../venv/bin/python -m unittest tests.test_lesson_review -v`

### U2 每日复习队列算法

- 范围：纯 Python，无数据库、Redis、网络依赖。
- 规则：`NEW` 立即复习，`LEARNING` 1 天后，`KNOWN` 7 天后。
- 排序：逾期程度、状态优先级、更新时间、稳定 ID。
- 独立测试：空队列、去重、时区、未来时间、数量限制、稳定排序、非法状态。
- 命令：`cd 01tts-worker && ../venv/bin/python -m unittest tests.test_review_queue -v`

### U3 Android 独立模型与 Compose 组件

- 范围：新增模型和可嵌入组件，不修改导航或 ViewModel。
- 状态：loading、empty、error、data。
- 独立测试：JSON 解析、可选字段、排序、状态文案、空态。
- 命令：`cd 01tts-app && ./gradlew testDebugUnitTest`

### U4 后端数据库与 API 接线

- `GET /api/v1/learning/reports/{clientId}/{contentUuid}`
- `GET /api/v1/learning/review-queue/{clientId}?date=YYYY-MM-DD&limit=10`
- 只读取现有 `learning_progress`、`vocabulary_progress`、`speaking_answers`、课程内容表。
- 独立测试：404、空数据、正常报告、队列限制、UUID/日期校验、跨用户隔离。
- 完成门槛：后端全量 unittest 通过。

### U5 Android App 接线

- `TaskApi` 增加两个 GET 契约。
- `MainViewModel` 增加报告/队列独立状态和刷新动作。
- 课程完成后显示报告；Today 页面显示每日复习队列。
- 点击复习项可打开对应课程或定位到词汇复习动作。
- 独立测试：成功、加载、空数据、API 失败、离线不影响已有课程播放。
- 完成门槛：Android 全量单元测试、Lint、Debug APK 构建通过。

### U6 契约与回归测试

- 用同一份 JSON fixture 同时验证 Python 输出和 Kotlin 解析。
- 回归课程生成、播放、进度同步、词汇状态、口语评分和在线更新。
- 不允许因为复盘接口失败阻断课程播放或本地进度保存。

### U7 云端端到端验收

- 部署后端并检查服务健康。
- 使用真实 `clientId/contentUuid` 完成：保存进度、获取报告、更新词汇、获取队列。
- 核对数据库持久化和公网 JSON。
- Android 真机验收报告可见、队列可点击；若无连接设备，必须明确标注未完成真机视觉验收。

## 集成顺序

```text
U1 + U2 + U3（并行）
        ↓
       U4
        ↓
       U5
        ↓
       U6
        ↓
       U7
```

每个单元只有在自己的独立测试通过后才能进入下一层；集成单元不得修改纯算法规则来绕过失败测试。

## V1 暂不包含

- AI 推测具体错题原因。
- 新增间隔重复数据库字段或迁移。
- 自动生成新的复习音频课程。
- 高亮、自动滚动和播放动效继续优化。

这些能力在 V1 获得真实使用数据后再评估。

## 执行结果（2026-08-01）

- U1 课程报告引擎：完成，独立测试 10/10 通过。
- U2 每日复习队列：完成，独立测试 12/12 通过；词汇动作统一为 `REVIEW_WORD`。
- U3 Android 独立组件：完成，独立测试 5/5 通过。
- U4 后端 API 集成：完成，接口测试 4/4、后端全量测试 80/80 通过。
- U5 Android App 接线：完成，Android 全量测试 57/57、Lint 0 error、Debug APK 构建通过。
- U6 共享契约回归：完成，同一份 JSON fixture 已在 Python 和 Kotlin 两端通过。
- U7 云端验收：完成，生产服务健康、公网报告与队列闭环通过，版本 `2.7.0 (10)` 已发布。

发布产物：仓库根目录 `Listening-Lab-2.7.0.apk`。当前没有连接 Android 真机，手机安装与视觉验收仍需在真实设备上完成。
