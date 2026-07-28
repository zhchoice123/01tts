# Listening Lab V3 Learning Loop Development Plan

## Objective

Turn the existing content generator and player into a daily technical-English
learning loop:

`Today → blind listen → transcript → comprehension → spoken summary → feedback`

This iteration keeps the existing Python unified API, MySQL/Redis deployment, and
Kotlin/Compose application. It does not reintroduce Anki or the retired Java API.

## Product Scope

### Android

1. Present dialogue lessons as HOST/EXPERT turns with distinct visual identity.
2. Add transcript visibility, playback speed, and ±10-second controls.
3. Persist playback position and resume the latest lesson.
4. Show a five-step Today journey: vocabulary, listening, reading, quiz, speaking.
5. Show a compact seven-day learning summary on Today.
6. Provide loading, empty, error, generating, resumed, and completed states.

### Python API

1. Persist per-client playback and learning completion in MySQL.
2. Persist vocabulary familiarity without depending on Anki.
3. Return a seven-day dashboard with minutes, completed lessons, quiz accuracy,
   speaking average, streak, and words reviewed.
4. Add start/end timing metadata to every generated dialogue turn.
5. Keep the 06:00 daily dialogue generation and existing asynchronous queue.

## Shared API Contract

The App creates and stores one opaque installation UUID as `clientId`.

### Learning progress

`PUT /api/v1/learning/progress`

```json
{
  "clientId": "installation-uuid",
  "contentUuid": "lesson-uuid",
  "positionMs": 245000,
  "durationMs": 592000,
  "vocabularyDone": true,
  "listeningDone": true,
  "readingDone": false,
  "quizCorrect": 4,
  "quizTotal": 5,
  "speakingScore": 86,
  "completed": false
}
```

`GET /api/v1/learning/progress/{clientId}/{contentUuid}` returns the same shape
plus `updatedAt`.

### Dashboard

`GET /api/v1/learning/dashboard/{clientId}?days=7`

```json
{
  "days": 7,
  "listeningMinutes": 47,
  "completedLessons": 4,
  "quizCorrect": 17,
  "quizTotal": 20,
  "speakingAverage": 84,
  "currentStreak": 3,
  "wordsReviewed": 26,
  "latestContentUuid": "lesson-uuid",
  "latestPositionMs": 245000
}
```

### Vocabulary

`PUT /api/v1/learning/vocabulary`

```json
{
  "clientId": "installation-uuid",
  "contentUuid": "lesson-uuid",
  "word": "backpressure",
  "status": "LEARNING"
}
```

`GET /api/v1/learning/vocabulary/{clientId}?status=LEARNING` returns saved words.

### Dialogue timing

Each item in `lessonContent.dialogue` includes:

```json
{
  "speaker": "HOST",
  "text": "What caused the incident?",
  "startMs": 0,
  "endMs": 4280
}
```

## Module Ownership

- Android agent: only `01tts-app/`.
- Python agent: only `01tts-worker/`.
- Root agent: Git baseline, contract coordination, integration review, full tests,
  and local commits.

## Test and Acceptance Plan

### Python

- Unit tests for progress upsert/read, validation, dashboard aggregation, streak,
  vocabulary idempotency, and dialogue timing.
- `python -m unittest discover -s tests -v`

### Android

- DTO parsing and API request tests.
- ViewModel tests for resume, five-step completion, dashboard, and offline/error
  behavior.
- Player tests for speed, transcript mode, and timed speaker selection where
  practical.
- `./gradlew clean testDebugUnitTest assembleDebug`

### Integration

1. Existing lesson/library/task contracts remain compatible.
2. A generated dialogue has alternating speakers and monotonic timing.
3. Progress written by the App contract is readable from the API.
4. Dashboard totals match stored progress.
5. No Anki production code or permission returns.
6. Android and Python full local suites pass.

## Git Iterations

1. `chore(repo): initialize safe baseline`
2. `feat(api): persist learning progress and dialogue timing`
3. `feat(android): add guided daily learning loop`
4. `test(integration): verify learning loop contracts`
