#!/usr/bin/env python3
import sys
import time
from pathlib import Path

import requests


BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8081").rstrip("/")


def wait_for(path: str, ready_status: str, timeout: int = 240) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = requests.get(f"{BASE_URL}{path}", timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload["status"] != "PENDING" and payload["status"] != "GENERATING":
            if payload["status"] != ready_status:
                raise RuntimeError(f"{path} ended with {payload['status']}")
            return payload
        time.sleep(2)
    raise TimeoutError(path)


health = requests.get(f"{BASE_URL}/health", timeout=20)
health.raise_for_status()
print(f"HEALTH={health.json()['status']}")

task_response = requests.post(
    f"{BASE_URL}/api/v1/tasks",
    json={
        "prompt": "Explain Java structured concurrency for a B1 English learner.",
        "voice": "en-US-AvaNeural",
        "difficulty": "B1",
    },
    timeout=20,
)
task_response.raise_for_status()
task_uuid = task_response.json()["taskUuid"]
task = wait_for(f"/api/v1/tasks/{task_uuid}", "COMPLETED")
task_audio = requests.get(f"{BASE_URL}{task['audioUrl']}", timeout=60)
task_audio.raise_for_status()
audio_path = Path("/tmp/01tts-python-full-smoke.mp3")
audio_path.write_bytes(task_audio.content)
print(f"TASK={task_uuid} STATUS={task['status']} AUDIO_BYTES={len(task_audio.content)}")

daily_response = requests.get(f"{BASE_URL}/api/v1/daily-plans/today", timeout=20)
daily_response.raise_for_status()
daily = daily_response.json()
content_uuid = daily["contentUuid"]
content = wait_for(f"/api/v1/content/{content_uuid}", "READY")
content_audio = requests.get(f"{BASE_URL}{content['audioUrl']}", timeout=60)
content_audio.raise_for_status()
library = requests.get(f"{BASE_URL}/api/v1/library", timeout=20)
library.raise_for_status()
if content_uuid not in {item["uuid"] for item in library.json()}:
    raise RuntimeError("daily content missing from library")
print(
    f"DAILY={daily['planDate']} CONTENT={content_uuid} "
    f"STATUS={content['status']} AUDIO_BYTES={len(content_audio.content)}"
)

with audio_path.open("rb") as audio:
    answer_response = requests.post(
        f"{BASE_URL}/api/v1/tasks/{task_uuid}/answers",
        files={"audio": ("answer.m4a", audio, "audio/mp4")},
        timeout=60,
    )
answer_response.raise_for_status()
answer_uuid = answer_response.json()["answerUuid"]
answer = wait_for(f"/api/v1/answers/{answer_uuid}", "COMPLETED")
print(
    f"ANSWER={answer_uuid} STATUS={answer['status']} SCORE={answer['score']} "
    f"TRANSCRIPT_PRESENT={bool(answer['transcript'])}"
)
