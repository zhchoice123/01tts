# 01tts / Listening Lab

Listening Lab is an open-source English listening, reading, vocabulary, and
speaking practice project. It includes a Kotlin/Jetpack Compose Android app,
a Python API and background worker, and a small standalone Edge TTS command
line tool.

## What is included

- `01tts-app/` — Android client with course playback, reading exercises,
  speaking practice, AnkiDroid integration, TTS provider/voice selection, and
  update checks.
- `01tts-worker/` — FastAPI backend and worker for lesson generation, TTS,
  transcription, scoring, and audio storage.
- `main.py` and `src/` — independent Edge TTS command-line utility.
- `contracts/` — cross-component API contract examples.
- `LISTENING_LAB_PRODUCT_AND_TECHNICAL_DESIGN.md` — consolidated product and
  technical design.

## Architecture and security boundary

```text
Android app --HTTPS--> FastAPI backend --> Redis / AI / TTS providers
                                      \--> audio storage
```

Provider credentials belong on the backend only. The Android app contains a
public API endpoint, not OpenAI, DeepSeek, or Aliyun credentials. Never put a
provider key in Gradle properties, `BuildConfig`, resources, assets, or an APK:
an APK should be assumed to be inspectable by its user.

The repository owner may operate a public demo at `https://api.zhchoice.xyz/`.
It is an optional demonstration service, not a required dependency or an SLA
for self-hosted deployments.

## Quick start: standalone Edge TTS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py --list-voices
python main.py -f input/sample.txt
```

Generated audio is written to `output/`, which is ignored by Git.

## Run the backend locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r 01tts-worker/requirements.txt
cp 01tts-worker/config.example.yaml 01tts-worker/config.yaml

# Use environment variables for real credentials.
export DEEPSEEK_API_KEY='your-local-key'
export OPENAI_API_KEY='your-local-key'

cd 01tts-worker
python -m unittest discover -s tests -v
python api.py
```

`01tts-worker/config.yaml` is intentionally ignored. Environment variables
take precedence over file values. Redis, provider accounts, and any production
proxy/TTS service must be configured separately.

## Backend lesson diversity and duplicate archives

Daily technical lessons use 60 concrete backend problems with four objectives:
diagnosis, design decisions, verification, and recovery. A problem has a 14-day
cooldown, and the same problem/objective has a 60-day cooldown. Reservation hashes
do not contain the date, and generated display titles do not change their identity.
Daily technical dialogues use AI-original cases rather than unrelated news feeds;
the separate source-article recommendation remains available.

Dialogue scripts aim for roughly 800-950 spoken words, and long passages aim for
roughly 1200-1450 words. These ranges guide generation, with no hard upper word
limit: longer complete cases can proceed to audio synthesis. Minimum lengths
(700 words for dialogues and 1200 for long passages), structure checks, and
duplicate detection still apply. Word counts and estimated durations reflect the
generated text rather than the suggested range.

Automatic technical generation includes previous lesson excerpts and rejects
strong wording overlap before synthesizing audio. This lexical check complements
selection cooldowns; it does not detect all semantic repetitions. Rejected drafts
remain failed records with a `CONTENT_NOVELTY` diagnostic. Manual lessons outside
the catalog are not automatically rejected by this gate.

Reviewed duplicates are hidden using `content_archives`. Original lesson rows,
audio, progress, historical daily plans, and direct lesson links remain available.
Audio-only imported courses must not be deduplicated from their placeholder text.

Run these commands from `01tts-worker` using the intended service environment.
The manifest must specify UUIDs, representatives, reasons, and SHA-256 hashes of
both lesson payloads. The tool validates the whole manifest and protects today's
main lesson. The apply command writes an exclusive backup before inserting archives.

```bash
../venv/bin/python scripts/archive_duplicates.py --manifest reviewed.json
../venv/bin/python scripts/archive_duplicates.py --manifest reviewed.json \
  --apply --backup archive-backup.json
../venv/bin/python scripts/archive_duplicates.py --restore archive-backup.json
```

The API startup creates the additive archive table. Start the updated API before
running a dry run. Keep production backups outside the public audio directory.

## Deploy the backend from GitHub

Use `main` as the release branch and have the cloud server pull it directly.
The deployment script tests each commit in an isolated release and Python
environment, restarts the existing systemd API, and restores the previous
release if its health check fails. Production configuration, credentials, and
audio stay outside Git. See [the deployment guide](deploy/README.md) for initial
setup, daily publishing, and rollback commands.

## Build and test the Android app

```bash
cd 01tts-app
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
  ./gradlew clean testDebugUnitTest lintDebug assembleDebug
```

The APK is produced at `app/build/outputs/apk/debug/app-debug.apk`. Override
the backend endpoint at build time when needed:

```bash
./gradlew assembleDebug -PLISTENING_LAB_API_URL=https://api.example.com/
```

The app uses the backend for provider-backed generation. Do not add provider
keys to the Android project or create a personal APK containing them.

## Security checks

Run the local scanner before every public push:

```bash
bash scripts/security-scan.sh
```

The scanner checks tracked files for common credential formats and forbidden
credential/config file names. GitHub Actions runs the same check on pushes and
pull requests. See [SECURITY.md](SECURITY.md) for reporting and deployment
guidance.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, validation, and pull-request
guidelines. Please keep credentials, production configuration, generated APKs,
and generated audio out of commits.

## License

This project is released under the [MIT License](LICENSE).
