import base64
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger("tts-python-api.speaking")


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

    @staticmethod
    def _json_object(raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1)
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("audio evaluation must be a JSON object")
        return parsed

    @staticmethod
    def _score_value(payload: dict[str, Any], key: str) -> int:
        try:
            return max(0, min(100, round(float(payload[key]))))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"audio evaluation is missing {key}") from error

    @staticmethod
    def _string_list(payload: dict[str, Any], key: str) -> list[str]:
        value = payload.get(key)
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:5]

    def evaluate_audio(
        self,
        audio_path: Path,
        question: str,
        transcript: str,
    ) -> dict[str, Any]:
        model = os.getenv("OPENAI_SPEAKING_MODEL", "gpt-audio-1.5")
        with tempfile.TemporaryDirectory(prefix="speaking-evaluation-") as directory:
            wav_path = Path(directory) / "recording.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(audio_path),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(wav_path),
                ],
                check=True,
            )
            encoded_audio = base64.b64encode(wav_path.read_bytes()).decode("ascii")

        system_prompt = (
            "You are a strict but supportive spoken-English coach. Listen to the "
            "ACTUAL USER AUDIO and evaluate the speaker; never answer the speaking "
            "prompt yourself. Use the provided transcript only as supporting evidence. "
            "Return exactly one compact JSON object with integer scores from 0 to 100: "
            "pronunciationScore, fluencyScore, intonationScore, pacingScore, "
            "relevanceScore, grammarScore, vocabularyScore. Also return summary as a "
            "concise string, and strengths, improvements, practicePlan as arrays of "
            "specific actionable strings. Do not use Markdown."
        )
        user_text = (
            f"Speaking prompt: {question}\n"
            f"Separate transcript: {transcript}\n"
            "Evaluate this recording now. Output JSON only."
        )
        response = requests.post(
            f"{self.openai_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": encoded_audio,
                                    "format": "wav",
                                },
                            },
                        ],
                    },
                ],
                "max_completion_tokens": 1200,
            },
            timeout=180,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        payload = self._json_object(raw)
        scores = {
            key: self._score_value(payload, key)
            for key in (
                "pronunciationScore",
                "fluencyScore",
                "intonationScore",
                "pacingScore",
                "relevanceScore",
                "grammarScore",
                "vocabularyScore",
            )
        }
        overall = round(
            scores["pronunciationScore"] * 0.20
            + scores["fluencyScore"] * 0.20
            + scores["intonationScore"] * 0.10
            + scores["pacingScore"] * 0.10
            + scores["relevanceScore"] * 0.15
            + scores["grammarScore"] * 0.15
            + scores["vocabularyScore"] * 0.10
        )
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise ValueError("audio evaluation is missing summary")
        return {
            **scores,
            "overallScore": overall,
            "summary": summary,
            "strengths": self._string_list(payload, "strengths"),
            "improvements": self._string_list(payload, "improvements"),
            "practicePlan": self._string_list(payload, "practicePlan"),
            "mode": "AUDIO_AND_TRANSCRIPT",
            "model": model,
        }

    @staticmethod
    def _fallback_evaluation(result: dict[str, Any]) -> dict[str, Any]:
        score = int(result["score"])
        feedback = str(result["feedback"])
        return {
            "overallScore": score,
            "pronunciationScore": score,
            "fluencyScore": score,
            "intonationScore": score,
            "pacingScore": score,
            "relevanceScore": score,
            "grammarScore": score,
            "vocabularyScore": score,
            "summary": feedback,
            "strengths": [],
            "improvements": [feedback],
            "practicePlan": [
                "Record the answer again and compare it with the transcript."
            ],
            "mode": "TRANSCRIPT_FALLBACK",
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        }

    def assess(self, audio_path: Path, question: str) -> dict[str, Any]:
        transcript = self.transcribe(audio_path)
        try:
            evaluation = self.evaluate_audio(audio_path, question, transcript)
            result = {
                "score": evaluation["overallScore"],
                "feedback": evaluation["summary"],
            }
        except Exception as error:
            LOGGER.warning(
                "Direct audio evaluation failed; using transcript fallback: %s",
                error,
            )
            result = self.score(transcript, question)
            evaluation = self._fallback_evaluation(result)
        return dict(result, transcript=transcript, evaluation=evaluation)
