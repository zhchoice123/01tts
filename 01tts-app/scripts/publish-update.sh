#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$APP_DIR/.." && pwd)"
BUILD_FILE="$APP_DIR/app/build.gradle.kts"
REMOTE_HOST="${LISTENING_LAB_DEPLOY_HOST:-tecent-server}"
REMOTE_RELEASE_DIR="${LISTENING_LAB_RELEASE_DIR:-/opt/01tts/storage-python/app-releases}"
PUBLIC_API_URL="${LISTENING_LAB_PUBLIC_API_URL:-https://api.zhchoice.xyz}"
MANDATORY_UPDATE="${MANDATORY_UPDATE:-false}"

VERSION_CODE="$(sed -n 's/^[[:space:]]*versionCode = \([0-9][0-9]*\).*/\1/p' "$BUILD_FILE" | head -n 1)"
VERSION_NAME="$(sed -n 's/^[[:space:]]*versionName = "\([^"]*\)".*/\1/p' "$BUILD_FILE" | head -n 1)"
MINIMUM_VERSION_CODE="${MINIMUM_VERSION_CODE:-$VERSION_CODE}"

if [[ -z "$VERSION_CODE" || -z "$VERSION_NAME" ]]; then
  echo "Unable to read versionCode/versionName from $BUILD_FILE" >&2
  exit 1
fi
if [[ "$MANDATORY_UPDATE" != "true" && "$MANDATORY_UPDATE" != "false" ]]; then
  echo "MANDATORY_UPDATE must be true or false" >&2
  exit 1
fi

if [[ "$#" -eq 0 ]]; then
  set -- "Performance and stability improvements"
fi

cd "$APP_DIR"
./gradlew testDebugUnitTest assembleDebug

SOURCE_APK="$APP_DIR/app/build/outputs/apk/debug/app-debug.apk"
APK_NAME="Listening-Lab-${VERSION_NAME}.apk"
DELIVERY_APK="$REPO_DIR/$APK_NAME"
cp "$SOURCE_APK" "$DELIVERY_APK"

APK_SHA256="$(shasum -a 256 "$DELIVERY_APK" | awk '{print $1}')"
APK_SIZE="$(stat -f '%z' "$DELIVERY_APK")"
PUBLISHED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
MANIFEST_FILE="$(mktemp "${TMPDIR:-/tmp}/listening-lab-release.XXXXXX.json")"
trap 'rm -f "$MANIFEST_FILE"' EXIT

export VERSION_CODE VERSION_NAME MINIMUM_VERSION_CODE MANDATORY_UPDATE APK_NAME
export APK_SHA256 APK_SIZE PUBLISHED_AT MANIFEST_FILE
python3 - "$@" <<'PY'
import json
import os
import sys

manifest = {
    "versionCode": int(os.environ["VERSION_CODE"]),
    "versionName": os.environ["VERSION_NAME"],
    "minimumVersionCode": int(os.environ["MINIMUM_VERSION_CODE"]),
    "mandatory": os.environ["MANDATORY_UPDATE"] == "true",
    "title": f"Listening Lab {os.environ['VERSION_NAME']}",
    "changelog": sys.argv[1:],
    "apkUrl": f"/api/v1/app/releases/{os.environ['APK_NAME']}",
    "sha256": os.environ["APK_SHA256"],
    "sizeBytes": int(os.environ["APK_SIZE"]),
    "publishedAt": os.environ["PUBLISHED_AT"],
}
with open(os.environ["MANIFEST_FILE"], "w", encoding="utf-8") as output:
    json.dump(manifest, output, ensure_ascii=False, indent=2)
    output.write("\n")
PY

REMOTE_APK_TMP="/tmp/${APK_NAME}.uploading"
REMOTE_MANIFEST_TMP="/tmp/listening-lab-latest.json.uploading"
ssh "$REMOTE_HOST" "install -d -o 01tts -g 01tts -m 0750 '$REMOTE_RELEASE_DIR'"
scp "$DELIVERY_APK" "$REMOTE_HOST:$REMOTE_APK_TMP"
scp "$MANIFEST_FILE" "$REMOTE_HOST:$REMOTE_MANIFEST_TMP"
ssh "$REMOTE_HOST" \
  "install -o 01tts -g 01tts -m 0640 '$REMOTE_APK_TMP' '$REMOTE_RELEASE_DIR/$APK_NAME' && \
   install -o 01tts -g 01tts -m 0640 '$REMOTE_MANIFEST_TMP' '$REMOTE_RELEASE_DIR/latest.json.new' && \
   mv '$REMOTE_RELEASE_DIR/latest.json.new' '$REMOTE_RELEASE_DIR/latest.json' && \
   rm -f '$REMOTE_APK_TMP' '$REMOTE_MANIFEST_TMP'"

curl --fail --silent --show-error "$PUBLIC_API_URL/api/v1/app/releases/latest"
echo
echo "Published $APK_NAME (versionCode $VERSION_CODE, sha256 $APK_SHA256)"
echo "Local APK: $DELIVERY_APK"
