# Listening Lab V2.1 Integration Test Report

**Date:** 2026-07-26  
**Architecture:** Android + unified Python FastAPI/MySQL/Redis service + Edge TTS

## Automated verification

- Python: `../venv/bin/python -m unittest discover -s tests -v` — **32 passed** locally and in the cloud staging directory.
- Android: `./gradlew clean testDebugUnitTest lintDebug connectedDebugAndroidTest assembleDebug` — **BUILD SUCCESSFUL**, 86 tasks executed.
- AnkiDroid instrumentation: **2 passed** against AnkiDroid 2.24.0 on the Pixel 8 Android 17 emulator, including an exact **5 added + 2 duplicates + 0 failed** batch that cleans up its test notes.
- Android Lint: **0 errors, 20 non-blocking version/KTX warnings**.
- APK metadata: `com.example.ttsapp`, version code `2`, version name `2.1.0`, label `Listening Lab`.

## AnkiDroid verification

1. Granted `com.ichi2.anki.permission.READ_WRITE_DATABASE`.
2. Listed the real `Default` Deck and Anki note types.
3. Bound `Default · Basic`, mapped `Front` and `Back`, restarted the App, and confirmed the binding persisted.
4. Answered a dedicated test card in AnkiDroid and confirmed Listening Lab returned **1 unique `is:due` word** without changing its schedule.
5. Generated a cloud lesson containing the exact target word.
6. Played the returned MP3 in the emulator; playback advanced to `0:05 / 1:09`.
7. Played word pronunciation through Android TTS.
8. Added the existing vocabulary item and received `0 added · 1 duplicate · 0 failed`.
9. Verified the “Review cards in AnkiDroid” action opens `com.ichi2.anki/.DeckPicker`.

The test used only the dedicated `listening-lab-gateway-proof` card.

## Cloud end-to-end verification

- Service: `01tts-python-api.service` active on `42.192.62.145:8080`; Java service inactive.
- New OpenAPI routes return successfully for Anki review lessons, topics, and daily generation.
- Daily generation for `2026-07-27` produced **3 READY items**: one attributable BBC source article and two AI-original lessons.
- All three audio files returned HTTP `206`, `audio/mpeg`, and valid MP3 frame headers.
- Anki review UUID `8a485a6c-01d8-4302-a991-94304667dd0e` completed with **2/2 target words**, three questions, no missing words, and a playable MP3.
- Repeating the same request returned the same UUID and did not regenerate the lesson.
- Startup recovery requeued one interrupted `GENERATING` content item; it changed to READY after restart.
- Daily-source repair added a missing source article to an already generated day; the visible three recommendations became one `SOURCE_ARTICLE` plus two `AI_ORIGINAL`, all READY.
- Kimi K3 now times out after 20 seconds and falls back to DeepSeek instead of blocking for 60 seconds.

## Network note

The certificate and Nginx configuration for `api.zhchoice.xyz` are valid on the
server, but Tencent Cloud WebBlock currently intercepts external domain traffic.
API calls therefore try the domain and fall back to `http://42.192.62.145:8080`;
relative MP3 URLs use the verified IP until the domain is filed or proxied.

## APK delivery

- File: `/Users/zhcho/Desktop/ListeningLab-v2.1.0-Anki.apk`
- Size: approximately 24 MB
- SHA-256: `fae137c1e235e42fba26ca3f85da77c90defe436eb256003c2f38eb7aa2ae952`

Previous APKs were moved to the macOS Trash. The final package was installed and
tested on the emulator; a separate physical-phone installation was not performed.
