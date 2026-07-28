#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-http://127.0.0.1:8081}"
response="$(
  curl -fsS -X POST "${base_url}/api/v1/tasks" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Explain Java structured concurrency for a B1 English learner.","voice":"en-US-AvaNeural","difficulty":"B1"}'
)"
task_uuid="$(
  printf "%s" "${response}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["taskUuid"])'
)"
echo "TASK_UUID=${task_uuid}"

for _ in $(seq 1 160); do
  current="$(curl -fsS "${base_url}/api/v1/tasks/${task_uuid}")"
  status="$(
    printf "%s" "${current}" |
      python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])'
  )"
  if [[ "${status}" != "PENDING" ]]; then
    echo "FINAL_STATUS=${status}"
    audio_url="$(
      printf "%s" "${current}" |
        python3 -c 'import json,sys; print(json.load(sys.stdin).get("audioUrl") or "")'
    )"
    echo "AUDIO_URL=${audio_url}"
    if [[ -n "${audio_url}" ]]; then
      curl -fsS -o /tmp/01tts-python-e2e.mp3 \
        -w "AUDIO_HTTP=%{http_code} AUDIO_BYTES=%{size_download}\n" \
        "${base_url}${audio_url}"
    fi
    [[ "${status}" == "COMPLETED" ]]
    exit
  fi
  sleep 2
done

echo "FINAL_STATUS=TIMEOUT"
exit 1
