# Listening Lab V3 Local Test Report

## Scope

This report verifies the V3 guided learning loop across the unified Python API
and Kotlin/Compose Android client. Tests ran locally on 2026-07-28. No cloud
deployment, production database migration, emulator, or physical-device test was
performed in this iteration.

## Automated Results

### Python API

Command:

```bash
cd 01tts-worker
../venv/bin/python -m compileall -q api.py src tests
../venv/bin/python -m unittest discover -s tests -v
```

Result: **45 tests passed**. Coverage includes progress upsert/read and
validation, dashboard aggregation and streaks, vocabulary state, dialogue audio
timing, daily generation, provider fallback, and legacy API compatibility.

### Android

Command:

```bash
cd 01tts-app
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
  ./gradlew clean testDebugUnitTest assembleDebug
```

Result: **32 tests passed** and the Debug APK assembled successfully. Coverage
includes API serialization, persisted installation UUID/progress, resume and
offline behavior, missing-progress handling, five-step state, transcript timing,
and dialogue selection.

## Contract Verification

- Android and Python use the same progress, dashboard, and vocabulary routes and
  camel-case JSON fields.
- New installations use a standard persisted UUID.
- A missing remote progress record is treated as an empty state; genuine network
  errors retain local progress and show an offline message.
- Dialogue timing is monotonic and derived from generated audio segments.
- No Anki permission or production integration is present.

## Build Artifact

- Version: `2.3.0` (`versionCode` 4)
- File: `01tts-app/app/build/outputs/apk/debug/app-debug.apk`
- Size: approximately 24 MB
- SHA-256:
  `3978171d015ee787706e479bddba6e0d05ab4c8b5e2af63bacdd05d16732cff1`

## Remaining Device Acceptance

Before cloud release, install the APK on an emulator or phone and verify audio
streaming, transcript tap-to-seek, drag behavior, theme/language layout, process
restart resume, and offline recovery against the deployed API. Real dialogue
timing also requires `ffprobe` to be installed on the server.
