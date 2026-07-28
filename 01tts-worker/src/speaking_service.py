import json
import os
from pathlib import Path
from typing import Any

import requests


class SpeakingAssessmentService:
    """Transcribe a recording, then score its content with an LLM."""

    def __init__(
        self,
        openai_api_key: str,
        deepseek_api_key: str,
        openai_base_url: str = "https://api.openai.com/v1",
        deepseek_base_url: str = "https://api.deepseek.com",
    ):
        self.openai_api_key = openai_api_key
        self.deepseek_api_key = deepseek_api_key
        self.openai_base_url = openai_base_url.rstrip("/")
        self.deepseek_base_url = deepseek_base_url.rstrip("/")

    def transcribe(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio:
            response = requests.post(
                f"{self.openai_base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.openai_api_key}"},
                files={"file": (audio_path.name, audio, "audio/mp4")},
                data={"model": os.getenv("TRANSCRIPTION_MODEL", "whisper-1")},
                timeout=90,
            )
        response.raise_for_status()
        transcript = response.json().get("text", "").strip()
        if not transcript:
            raise ValueError("transcription was empty")
        return transcript

    def score(self, transcript: str, question: str) -> dict[str, Any]:
        response = requests.post(
            f"{self.deepseek_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.deepseek_api_key}"},
            json={
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Evaluate the spoken answer for relevance, clarity, grammar, and "
                            "vocabulary. Return JSON only: score (integer 0-100) and concise "
                            "feedback with one strength and one improvement."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\nTranscript: {transcript}",
                    },
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        result = json.loads(response.json()["choices"][0]["message"]["content"])
        score = int(result["score"])
        if not 0 <= score <= 100:
            raise ValueError("score must be between 0 and 100")
        feedback = result["feedback"]
        if isinstance(feedback, dict):
            strength = feedback.get("strength", "")
            improvement = feedback.get("improvement", "")
            feedback = f"Strength: {strength} Improvement: {improvement}".strip()
        return {"score": score, "feedback": str(feedback)}

    def assess(self, audio_path: Path, question: str) -> dict[str, Any]:
        transcript = self.transcribe(audio_path)
        result = self.score(transcript, question)
        return dict(result, transcript=transcript)
