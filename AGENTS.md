# Repository Guidelines

## Project Structure & Module Organization

This repository contains a three-part listening and speaking practice system plus the original lightweight TTS CLI.

- `01tts-worker/` consumes Redis queues, generates lessons/audio, and evaluates speaking answers.
- `01tts-server/` is the Spring Boot API, H2 persistence layer, Redis publisher, and audio store.
- `01tts-app/` is the Kotlin/Compose Android client.
- Root `main.py`, `src/`, `input/`, and `output/` retain the standalone text-to-MP3 CLI.
- `MASTER_DEVELOPMENT_PLAN.md` defines module responsibilities and acceptance flows.

Do not commit `venv/`, `__pycache__/`, or generated audio. These are excluded by `.gitignore`.

## Build, Test, and Development Commands

Create and activate an isolated environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

Run each module from its own directory:

```bash
cd 01tts-worker && ../venv/bin/python -m unittest discover -s tests -v
cd 01tts-server && mvn test
cd 01tts-app && ./gradlew testDebugUnitTest assembleDebug
```

For local integration, start Redis and the server, then run `worker.py --once` for lessons or `worker.py --speaking --once` for answer evaluation. Required secrets are read from `DEEPSEEK_API_KEY` and `OPENAI_API_KEY`; never commit them.

## Coding Style & Naming Conventions

Follow PEP 8 for Python, standard Java conventions for Spring classes, and Kotlin style for Android. Use four-space indentation throughout. Name Python functions `snake_case`, Java/Kotlin types `UpperCamelCase`, and constants `UPPER_SNAKE_CASE`. Keep controllers thin; place persistence and queue logic in services. Prefer typed request/response models and `pathlib.Path` or `java.nio.file.Path`.

## Testing Guidelines

Python tests use `unittest`, Spring tests use JUnit 5/MockMvc, and Android local tests use JUnit 4. Mock external AI/TTS calls in routine tests. Add a regression test with every bug fix. Network-backed end-to-end checks are separate and require Redis plus API credentials.

## Commit & Pull Request Guidelines

This directory has no Git history, so no established commit convention can be inferred. Use concise imperative subjects, optionally with a scope, for example `feat(cli): add volume option` or `test(utils): cover GBK fallback`. Pull requests should explain behavior changes, list verification commands, link related issues, and note generated-audio or network checks. Include sample CLI output when user-visible behavior changes.
