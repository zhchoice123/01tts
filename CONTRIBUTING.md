# Contributing

Thanks for helping improve Listening Lab.

## Local setup

The repository has three independently useful parts:

- `01tts-worker/`: Python API and background worker.
- `01tts-app/`: Kotlin and Jetpack Compose Android client.
- `main.py` and `src/`: the standalone Edge TTS command-line tool.

Copy only the safe example configuration before running the backend:

```bash
cp 01tts-worker/config.example.yaml 01tts-worker/config.yaml
```

Put provider credentials in environment variables or the ignored local file;
never place real values in a pull request. See [SECURITY.md](SECURITY.md).

## Validation

Run the checks relevant to your change:

```bash
bash scripts/security-scan.sh

cd 01tts-worker
python -m unittest discover -s tests -v

cd ../01tts-app
./gradlew testDebugUnitTest lintDebug assembleDebug
```

The standalone Edge TTS tool can be checked with:

```bash
python main.py --list-voices
python main.py -f ../input/sample.txt
```

## Pull requests

- Keep changes focused and explain user-visible behavior.
- Add or update tests for behavior changes.
- Do not commit generated APKs, audio, local configuration, credentials, or
  private deployment details.
- Describe which commands passed and call out checks that were not run.
- Preserve provider-qualified voices such as `aliyun:loongdavid_v2` when
  changing TTS selection logic.

By submitting a contribution, you agree that it may be distributed under the
MIT License in this repository.
