# Security Policy

## Scope

This repository contains the Listening Lab Android client, the Python API and
worker, and a small local Edge TTS command-line tool.

## Secret-handling rules

- Never commit API keys, access-key secrets, passwords, bearer tokens, private
  keys, proxy subscriptions, or production configuration.
- Keep server credentials in the server's environment or in an ignored local
  configuration file. The worker accepts `DEEPSEEK_API_KEY` and
  `OPENAI_API_KEY` from environment variables; environment variables take
  precedence over file configuration.
- The Android app must call the project backend over HTTPS. Provider keys must
  not be placed in Gradle properties, `BuildConfig`, resources, assets, or any
  APK. Anything inside an APK should be treated as public.
- `01tts-worker/config.yaml`, `.env*`, Android local properties, generated APKs,
  and local audio output are ignored by Git. Ignoring a file is not a
  substitute for rotating a credential that was already exposed.
- Before publishing, run `bash scripts/security-scan.sh` and inspect the Git
  history as well as the current files.

## Reporting a vulnerability

Please do not open a public issue containing a credential or an exploitable
security detail. Contact the repository owner privately through the GitHub
profile for `zhchoice123`, including:

1. A short description and affected component.
2. Reproduction steps or a minimal proof of concept.
3. The potential impact and any suggested mitigation.

If a credential may have been exposed, revoke or rotate it immediately, then
report the affected provider and commit without including the secret value.

## Security limitations

The public demo API and release service are operated separately from this
repository. Their availability, rate limits, authentication policy, and data
retention are not guarantees of this open-source project. Deployers are
responsible for putting authentication, rate limiting, HTTPS, logging, and
secret management in front of their own instance.
