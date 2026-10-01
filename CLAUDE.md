# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See also `AGENTS.md` (style/commit conventions), `CONTRIBUTING.md`, `SECURITY.md`, and
`LISTENING_LAB_PRODUCT_AND_TECHNICAL_DESIGN.md` (authoritative product + architecture design).

## Repository layout

Three independent parts share one repo and one root `venv/`:

- `01tts-worker/` — FastAPI backend ("Listening Lab Python API"): lesson generation, TTS, speaking evaluation, learning progress. SQLAlchemy (MySQL in prod, SQLite in tests) + Redis queues.
- `01tts-app/` — Kotlin / Jetpack Compose Android client (package `com.example.ttsapp`, single `:app` module).
- Root `main.py` + `src/` — standalone Edge TTS CLI (text → MP3 in `output/`). Unrelated to the backend's `src/` package despite the same name.
- `contracts/learning_review/` — JSON fixtures consumed by **both** `01tts-worker/tests/test_learning_review_contract.py` and the Android `LearningReviewSharedContractTest`. Changing review-queue/lesson-review output shapes requires updating these fixtures and both sides.

## Commands

Backend (run from `01tts-worker/`; modules import as `src.*` and config defaults to `./config.yaml`):

```bash
../venv/bin/python -m unittest discover -s tests -v                       # all tests
../venv/bin/python -m unittest tests.test_backend_api -v                  # one file
../venv/bin/python -m unittest tests.test_backend_api.BackendApiTest.test_x -v  # one test
../venv/bin/uvicorn api:app --host 0.0.0.0 --port 8080                    # local API (needs MySQL/DATABASE_URL + Redis)
```

Android (run from `01tts-app/`; use Android Studio's JBR as JAVA_HOME on macOS):

```bash
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' ./gradlew testDebugUnitTest lintDebug assembleDebug
./gradlew testDebugUnitTest --tests 'com.example.ttsapp.MainViewModelTest'   # single test class
./gradlew assembleDebug -PLISTENING_LAB_API_URL=https://api.example.com/     # override backend URL (BuildConfig)
```

Security scan (also run by GitHub Actions on every push/PR — the only CI job):

```bash
bash scripts/security-scan.sh
```

It fails if credential-shaped strings or files named `config.yaml`, `api-keys.properties`, `.env*`, keystores, etc. are tracked. Those files exist locally (gitignored) — never `git add` them.

## Backend architecture

- `api.py` is a `create_app(config, service, start_background)` factory; all routes are defined inline and delegate to a single `BackendService` (`src/backend_service.py`, ~2.4k lines) held on `app.state.backend`. Keep routes thin; logic goes in the service.
- On startup (lifespan) the service runs `Base.metadata.create_all` (schema is created/extended additively at startup; `migrations/` holds manual SQL for older upgrades), pings Redis, starts **in-process daemon consumer threads** (`_lesson_loop`, `_speaking_loop`) that `BRPOP` the `queue:python:*` queues, and an APScheduler job for the daily plan (`run_daily_generation` at `DAILY_PLAN_HOUR:MINUTE` in `APP_TIMEZONE`, default 06:00 Asia/Shanghai, plus a startup compensation run via `ensure_daily_generation`).
- `worker.py` is the older standalone worker: it consumes different queue names (`queue:tts_tasks`, `queue:content_tasks`, `queue:speaking_answers`) and talks to the API over HTTP. Production deploys both (`deploy/systemd/`), but new generation logic lives in `BackendService`.
- Config: `src/config.py` (`WorkerConfig`, YAML + env) is wrapped by `src/backend_config.py` (`BackendConfig`). Env vars override YAML: `DATABASE_URL`, `REDIS_URL`, `REDIS_PASSWORD`, `STORAGE_DIR`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `TTS_PROVIDER`, `*_QUEUE`, etc. Copy `config.example.yaml` → `config.yaml` for local runs.
- Generation pipeline: content ingestion (`content_ingestion.py`, news feeds) → DeepSeek lesson generation (`deepseek_service.py`, routed through `provider_router.py`) → schema validation/repair (`schema_validator.py`) → novelty gate (`content_diversity.py`) → TTS (`tts_service.py`) → audio files under `STORAGE_DIR`.
- TTS voices are provider-qualified strings like `aliyun:loongdavid_v2` or `openai:nova`; unprefixed voices (e.g. the default `en-US-AvaNeural`) are mapped to the `TTS_PROVIDER` default (aliyun). Preserve this format when touching voice selection. Audio concat/duration uses `ffmpeg`/`ffprobe`.
- Speaking evaluation (`speaking_service.py`): OpenAI transcription + DeepSeek/OpenAI scoring.
- Learning review: `review_queue.py` and `lesson_review.py` are pure functions producing the shapes pinned by `contracts/learning_review/`.

### Lesson diversity and archives

- Daily technical lessons pick from a catalog of 60 backend problems × 4 objectives with cooldowns (14 days per problem, 60 days per problem/objective). Reservation hashes must not include the date; display titles do not affect identity.
- Auto-generated technical lessons are rejected on strong lexical overlap with prior lessons (failed record with `CONTENT_NOVELTY` diagnostic) before TTS runs. Manual lessons outside the catalog skip this gate.
- Duplicates are hidden via the `content_archives` table (`content_archive.py`) — original rows, audio, and progress are never deleted. `scripts/archive_duplicates.py` takes a reviewed manifest (UUIDs, representative, reason, SHA-256 of both payloads); dry run by default, `--apply --backup <file>` writes a backup first, `--restore <file>` reverts. Audio-only imported courses must not be deduplicated by their placeholder text.

## Backend tests

- `tests/test_backend_api.py` builds the app with a temp SQLite `database_url`, the in-file `FakeRedis` / `FakeGenerator` / `FakeAssessor` helpers, and `start_background=False`, then uses FastAPI's `TestClient`. Follow that pattern for new endpoint tests.
- External AI/TTS calls are always mocked (`unittest.mock.patch`). Network-backed end-to-end checks are separate: `deploy/smoke-python-api.sh` / `deploy/smoke_python_api_full.py`.

## Android architecture

- Most UI lives in `MainActivity.kt` (~4k lines of Compose) driven by a single `MainViewModel`. Networking is Retrofit in `network/` (`ApiClient`, `TaskApi`); feature code under `core/` (`ai`, `anki` — AnkiDroid integration, `notifications`) and `review/`.
- Local persistence is a set of `*Store.kt` preference stores (progress, history, TTS, theme, language, onboarding).
- The API base URL comes from `BuildConfig` (Gradle property `LISTENING_LAB_API_URL`, default `https://api.zhchoice.xyz/`). Cleartext HTTP is blocked by network security config.
- **No provider credentials in the app** — not in Gradle properties, `BuildConfig`, resources, or assets. All AI/TTS calls go through the backend.
- Releases: bump `versionCode`/`versionName` in `app/build.gradle.kts`, then `scripts/publish-update.sh` builds, copies `Listening-Lab-<version>.apk` to the repo root, and uploads it with `latest.json` (SHA-256 + size) for in-app updates. Releases use the debug signing key; don't commit generated APKs.
