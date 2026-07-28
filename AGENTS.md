# Repository Guidelines

## Project Structure & Module Organization

This repository contains a unified Python backend, an Android learning client,
and the original lightweight TTS CLI.

- `01tts-worker/` hosts the FastAPI API, MySQL/Redis persistence, lesson/audio
  generation, and speaking evaluation.
- `01tts-app/` is the Kotlin/Compose Android client.
- Root `main.py`, `src/`, `input/`, and `output/` retain the standalone text-to-MP3 CLI.
- `LEARNING_LOOP_V3_DEVELOPMENT_PLAN.md` defines the current learning-loop
  contract and acceptance flow.

Do not commit `venv/`, `__pycache__/`, or generated audio. These are excluded by `.gitignore`.

## Build, Test, and Development Commands

Create and activate an isolated environment, then install backend dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r 01tts-worker/requirements.txt
```

Run each module from its own directory:

```bash
cd 01tts-worker && ../venv/bin/python -m unittest discover -s tests -v
cd 01tts-app && ./gradlew testDebugUnitTest assembleDebug
```

For local integration, start MySQL and Redis, then run
`cd 01tts-worker && ../venv/bin/uvicorn api:app --host 0.0.0.0 --port 8080`.
Required secrets are read from environment variables; never commit them.

## Coding Style & Naming Conventions

Follow PEP 8 for Python and Kotlin style for Android. Use four-space
indentation. Name Python functions `snake_case`, Kotlin types `UpperCamelCase`,
and constants `UPPER_SNAKE_CASE`. Keep API routes thin; place persistence and
generation logic in services. Prefer typed request/response models and
`pathlib.Path`.

## Testing Guidelines

Python tests use `unittest`, and Android local tests use JUnit 4. Mock external
AI/TTS calls in routine tests. Add a regression test with every bug fix.
Network-backed end-to-end checks are separate and require MySQL, Redis, and API
credentials.

## Commit & Pull Request Guidelines

Use concise imperative subjects with an optional scope, for example
`feat(api): add learning profile` or `test(android): cover offline resume`.
Pull requests should explain behavior changes, list verification commands, link
related issues, and note generated-audio or network checks. Include sample output
when user-visible behavior changes.
