import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger("tts-python-api.audio")

OPENAI_AUDIO_BASE_URL = "https://api.openai.com/v1/audio"
DEFAULT_TTS_MODEL = "tts-1-hd"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
OPENAI_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
}

ALIYUN_VOICES = {
    "loongdavid_v2": "David · American male",
    "loongabby_v2": "Abby · American female",
    "loongannie_v2": "Annie · American female",
    "loongeric_v2": "Eric · British male",
    "loongemily_v2": "Emily · British female",
}
ALIYUN_TTS_BASE_URL = os.getenv("ALIYUN_TTS_BASE_URL", "http://127.0.0.1:8088").rstrip("/")


def _tts_provider_voice(requested_voice: str) -> tuple[str, str]:
    """Accept provider-prefixed voices, e.g. aliyun:loongdavid_v2 or openai:nova.

    Raises ValueError on unknown provider or unknown voice for a declared provider.
    """
    value = (requested_voice or "").strip()
    if ":" in value:
        parts = [part.strip() for part in value.split(":")]
        if len(parts) != 2 or not all(parts):
            raise ValueError("TTS voice must use provider:voice format")
        provider, voice_name = parts
        provider = provider.lower()
        if provider not in {"aliyun", "openai"}:
            raise ValueError(f"Unsupported TTS provider: {provider}")
        if provider == "aliyun":
            if voice_name not in ALIYUN_VOICES:
                raise ValueError(f"Unknown Aliyun voice: {voice_name}")
            return provider, voice_name
        else:
            if voice_name.lower() in OPENAI_VOICES:
                return provider, voice_name.lower()
            mapped = _openai_voice(voice_name)
            if (
                voice_name.lower() not in OPENAI_VOICES
                and not any(
                    marker in voice_name.lower()
                    for marker in (
                        "neural",
                        "alloy",
                        "ash",
                        "ballad",
                        "coral",
                        "echo",
                        "fable",
                        "nova",
                        "onyx",
                        "sage",
                        "shimmer",
                    )
                )
            ):
                raise ValueError(f"Unknown OpenAI voice: {voice_name}")
            return provider, mapped

    default_provider = os.getenv("TTS_PROVIDER", "aliyun").strip().lower()
    provider = default_provider if default_provider in {"aliyun", "openai"} else "aliyun"
    if provider == "aliyun":
        if value in ALIYUN_VOICES:
            return provider, value
        mapped = {
            "en-US-AvaNeural": "loongdavid_v2",
            "en-US-AndrewNeural": "loongabby_v2",
            "en-GB-SoniaNeural": "loongeric_v2",
        }.get(value)
        if mapped:
            return provider, mapped
        if not value:
            return provider, "loongdavid_v2"
        raise ValueError(f"Unknown Aliyun voice: {value}")
    else:
        if not value:
            return provider, "nova"
        return provider, _openai_voice(value)


def _probe_duration_ms(path: Path) -> int:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration_ms = round(float(completed.stdout.strip()) * 1000)
    if duration_ms <= 0:
        raise RuntimeError(f"invalid audio duration for {path.name}")
    return duration_ms


def _require_api_key(api_key: str | None) -> str:
    resolved = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not resolved:
        raise RuntimeError("OPENAI_API_KEY is required for speech generation")
    return resolved


def _openai_voice(requested_voice: str) -> str:
    normalized = requested_voice.strip().lower()
    if normalized in OPENAI_VOICES:
        return normalized
    male_markers = (
        "andrew",
        "brian",
        "christopher",
        "eric",
        "guy",
        "roger",
        "stefan",
        "steffan",
    )
    return "onyx" if any(marker in normalized for marker in male_markers) else "nova"


def _split_text(text: str, max_chars: int = 3500) -> list[str]:
    """Split long speech input at sentence/whitespace boundaries."""
    normalized = text.strip()
    if not normalized:
        raise ValueError("speech text must not be blank")
    if len(normalized) <= max_chars:
        return [normalized]

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        remaining = sentence.strip()
        while len(remaining) > max_chars:
            split_at = remaining.rfind(" ", 0, max_chars + 1)
            if split_at <= 0:
                split_at = max_chars
            piece = remaining[:split_at].strip()
            if current:
                chunks.append(current)
                current = ""
            if piece:
                chunks.append(piece)
            remaining = remaining[split_at:].strip()
        if not remaining:
            continue
        candidate = f"{current} {remaining}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = remaining
    if current:
        chunks.append(current)
    return chunks


def _post_speech(
    text: str,
    output_path: Path,
    *,
    api_key: str,
    model: str,
    voice: str,
    speed: float = 1.0,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.post(
                f"{OPENAI_AUDIO_BASE_URL}/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": text,
                    "voice": voice,
                    "speed": speed,
                    "response_format": "mp3",
                },
                timeout=180,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"OpenAI speech request failed ({response.status_code}): "
                    f"{response.text[:500]}"
                )
            output_path.write_bytes(response.content)
            if output_path.stat().st_size == 0:
                raise RuntimeError("OpenAI speech request returned an empty audio file")
            return
        except Exception as error:
            last_error = error
            if attempt == 3:
                break
            LOGGER.warning("Speech synthesis attempt %d/3 failed: %s", attempt, error)
            time.sleep(attempt)
    raise RuntimeError(f"OpenAI speech generation failed after 3 attempts: {last_error}")


def _post_aliyun_speech(
    text: str,
    output_path: Path,
    *,
    voice: str,
    speed: float = 1.0,
) -> None:
    rate = round((speed - 1.0) * 100)
    response = requests.post(
        f"{ALIYUN_TTS_BASE_URL}/api/synthesize",
        json={"text": text, "voice": voice, "speechRate": rate},
        timeout=300,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Aliyun Java TTS request failed ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    audio_url = payload.get("audioUrl")
    if not audio_url:
        raise RuntimeError("Aliyun Java TTS response did not include audioUrl")
    audio = requests.get(f"{ALIYUN_TTS_BASE_URL}{audio_url}", timeout=300)
    audio.raise_for_status()
    output_path.write_bytes(audio.content)
    if output_path.stat().st_size == 0:
        raise RuntimeError("Aliyun Java TTS returned an empty audio file")


def _concat_mp3(segment_paths: list[Path], output_path: Path, work_dir: Path) -> None:
    if not segment_paths:
        raise ValueError("at least one audio segment is required")
    if len(segment_paths) == 1:
        shutil.copyfile(segment_paths[0], output_path)
        return
    concat_file = work_dir / "segments.txt"
    concat_file.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in segment_paths),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ],
        check=True,
    )


def _synthesize_text(
    text: str,
    output_path: Path,
    *,
    api_key: str | None,
    model: str,
    voice: str,
    work_dir: Path,
    speed: float = 1.0,
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    chunks = _split_text(text)
    segment_paths: list[Path] = []
    for index, chunk in enumerate(chunks):
        segment_path = work_dir / f"speech-{index:03d}.mp3"
        provider, provider_voice = _tts_provider_voice(voice)
        if provider == "aliyun":
            _post_aliyun_speech(chunk, segment_path, voice=provider_voice, speed=speed)
        else:
            _post_speech(
                chunk, segment_path, api_key=_require_api_key(api_key), model=model,
                voice=_openai_voice(provider_voice), speed=speed,
            )
        segment_paths.append(segment_path)
    _concat_mp3(segment_paths, output_path, work_dir)


def _locate_word(text: str, word: str, cursor: int) -> tuple[int, int]:
    candidate = word.strip()
    if not candidate:
        return cursor, cursor
    exact = text.casefold().find(candidate.casefold(), cursor)
    if exact >= 0:
        return exact, exact + len(candidate)

    tokens = re.findall(r"[\w]+(?:['’-][\w]+)*", candidate, flags=re.UNICODE)
    needle = tokens[0] if tokens else candidate
    match = re.search(re.escape(needle), text[cursor:], flags=re.IGNORECASE)
    if match:
        start = cursor + match.start()
        return start, start + len(match.group(0))
    return cursor, min(len(text), cursor + len(candidate))


def _transcribe_word_timings(
    audio_path: Path,
    original_text: str,
    *,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            with audio_path.open("rb") as audio:
                response = requests.post(
                    f"{OPENAI_AUDIO_BASE_URL}/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, audio, "audio/mpeg")},
                    data=[
                        ("model", model),
                        ("response_format", "verbose_json"),
                        ("timestamp_granularities[]", "word"),
                    ],
                    timeout=300,
                )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"OpenAI transcription request failed ({response.status_code}): "
                    f"{response.text[:500]}"
                )
            try:
                payload = response.json()
            except (requests.JSONDecodeError, json.JSONDecodeError) as error:
                raise RuntimeError("OpenAI transcription returned invalid JSON") from error

            timings: list[dict[str, Any]] = []
            cursor = 0
            for item in payload.get("words") or []:
                word = str(item.get("word") or "").strip()
                if not word:
                    continue
                char_start, char_end = _locate_word(original_text, word, cursor)
                cursor = max(cursor, char_end)
                start_ms = max(0, round(float(item.get("start") or 0) * 1000))
                end_ms = max(
                    start_ms + 1,
                    round(float(item.get("end") or 0) * 1000),
                )
                timings.append(
                    {
                        "text": original_text[char_start:char_end] or word,
                        "startMs": start_ms,
                        "endMs": end_ms,
                        "charStart": char_start,
                        "charEnd": char_end,
                    }
                )
            if not timings:
                raise RuntimeError("OpenAI transcription returned no word timestamps")
            return timings
        except Exception as error:
            last_error = error
            if attempt == 2:
                break
            LOGGER.warning("Word alignment attempt 1/2 failed: %s", error)
            time.sleep(1)
    raise RuntimeError(f"OpenAI word alignment failed after 2 attempts: {last_error}")


def _estimate_word_timings(
    text: str,
    start_ms: int,
    end_ms: int,
) -> list[dict[str, Any]]:
    """Create a playable fallback timeline when Whisper is temporarily unavailable."""
    matches = list(re.finditer(r"[\w]+(?:['’-][\w]+)*", text, flags=re.UNICODE))
    if not matches:
        return []
    duration = max(len(matches), end_ms - start_ms)
    weights = [max(1, len(match.group(0))) for match in matches]
    total_weight = sum(weights)
    timings: list[dict[str, Any]] = []
    elapsed_weight = 0
    cursor_ms = start_ms
    for index, (match, weight) in enumerate(zip(matches, weights)):
        elapsed_weight += weight
        remaining = len(matches) - index - 1
        word_end = (
            end_ms
            if not remaining
            else start_ms + round(duration * elapsed_weight / total_weight)
        )
        word_end = max(cursor_ms + 1, min(word_end, end_ms - remaining))
        timings.append(
            {
                "text": match.group(0),
                "startMs": cursor_ms,
                "endMs": word_end,
                "charStart": match.start(),
                "charEnd": match.end(),
                "estimated": True,
            }
        )
        cursor_ms = word_end
    return timings


async def generate_audio(
    text: str,
    output_path: Path,
    voice: str,
    word_timings: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
) -> Path:
    """Generate OpenAI speech and align it with Whisper word timestamps."""
    provider, _ = _tts_provider_voice(voice)
    resolved_key = api_key if provider == "aliyun" else _require_api_key(api_key)
    tts_model = os.getenv("OPENAI_TTS_MODEL", DEFAULT_TTS_MODEL)
    transcription_model = os.getenv(
        "OPENAI_TRANSCRIPTION_MODEL",
        DEFAULT_TRANSCRIPTION_MODEL,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="openai-tts-", dir=output_path.parent) as temporary:
        temporary_dir = Path(temporary)
        await asyncio.to_thread(
            _synthesize_text,
            text,
            output_path,
            api_key=resolved_key,
            model=tts_model,
            voice=voice,
            work_dir=temporary_dir,
        )
        try:
            if not resolved_key:
                raise RuntimeError("OpenAI key unavailable; using estimated timings")
            boundaries = await asyncio.to_thread(
                _transcribe_word_timings,
                output_path,
                text,
                api_key=resolved_key,
                model=transcription_model,
            )
        except Exception as error:
            LOGGER.warning(
                "Whisper alignment unavailable for %s; using estimated timings: %s",
                output_path.name,
                error,
            )
            duration_ms = await asyncio.to_thread(_probe_duration_ms, output_path)
            boundaries = _estimate_word_timings(text, 0, duration_ms)
    if word_timings is not None:
        word_timings.extend(boundaries)
    return output_path


async def generate_dialogue_audio(
    turns: list[dict[str, Any]],
    output_path: Path,
    host_voice: str = "en-US-AvaNeural",
    expert_voice: str = "en-US-AndrewNeural",
    api_key: str | None = None,
) -> Path:
    """Generate two-voice OpenAI speech and one global Whisper timeline."""
    if not turns:
        raise ValueError("dialogue must contain at least one turn")
    host_provider, _ = _tts_provider_voice(host_voice)
    expert_provider, _ = _tts_provider_voice(expert_voice)
    if host_provider == "openai" or expert_provider == "openai":
        resolved_key = _require_api_key(api_key)
    else:
        resolved_key = api_key
    tts_model = os.getenv("OPENAI_TTS_MODEL", DEFAULT_TTS_MODEL)
    transcription_model = os.getenv(
        "OPENAI_TRANSCRIPTION_MODEL",
        DEFAULT_TRANSCRIPTION_MODEL,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="openai-dialogue-",
        dir=output_path.parent,
    ) as temporary:
        temporary_dir = Path(temporary)
        segment_paths: list[Path] = []
        segment_durations: list[int] = []
        original_parts: list[str] = []
        character_ranges: list[tuple[int, int]] = []
        character_cursor = 0
        for index, turn in enumerate(turns):
            speaker = str(turn.get("speaker", "")).strip().upper()
            text = str(turn.get("text", "")).strip()
            if speaker not in {"HOST", "EXPERT"} or not text:
                raise ValueError(f"invalid dialogue turn at index {index}")
            segment_path = temporary_dir / f"turn-{index:03d}.mp3"
            voice = host_voice if speaker == "HOST" else expert_voice
            await asyncio.to_thread(
                _synthesize_text,
                text,
                segment_path,
                api_key=resolved_key,
                model=tts_model,
                voice=voice,
                work_dir=temporary_dir / f"turn-{index:03d}",
                speed=0.9,
            )
            segment_paths.append(segment_path)
            segment_durations.append(
                await asyncio.to_thread(_probe_duration_ms, segment_path)
            )
            if original_parts:
                character_cursor += 1
            start = character_cursor
            original_parts.append(text)
            character_cursor += len(text)
            character_ranges.append((start, character_cursor))

        await asyncio.to_thread(
            _concat_mp3,
            segment_paths,
            output_path,
            temporary_dir,
        )
        output_duration = await asyncio.to_thread(_probe_duration_ms, output_path)
        full_text = "\n".join(original_parts)
        measured_total = sum(segment_durations)
        start_ms = 0
        cumulative_measured = 0
        turn_ranges: list[tuple[int, int, int, int]] = []
        for index, (turn, segment_duration) in enumerate(
            zip(turns, segment_durations)
        ):
            cumulative_measured += segment_duration
            if index == len(turns) - 1:
                end_ms = output_duration
            else:
                remaining_turns = len(turns) - index - 1
                end_ms = round(cumulative_measured * output_duration / measured_total)
                end_ms = max(start_ms + 1, end_ms)
                end_ms = min(end_ms, output_duration - remaining_turns)
            turn["startMs"] = start_ms
            turn["endMs"] = end_ms
            char_start, char_end = character_ranges[index]
            turn_ranges.append((start_ms, end_ms, char_start, char_end))
            start_ms = end_ms

        try:
            if not resolved_key:
                raise RuntimeError("OpenAI key unavailable; using estimated timings")
            all_words = await asyncio.to_thread(
                _transcribe_word_timings,
                output_path,
                full_text,
                api_key=resolved_key,
                model=transcription_model,
            )
        except Exception as error:
            LOGGER.warning(
                "Whisper alignment unavailable for %s; using per-turn estimated timings: %s",
                output_path.name,
                error,
            )
            all_words = []
            for turn, (turn_start, turn_end, char_start, _) in zip(
                turns,
                turn_ranges,
            ):
                for word in _estimate_word_timings(
                    str(turn["text"]),
                    turn_start,
                    turn_end,
                ):
                    all_words.append(
                        {
                            **word,
                            "charStart": word["charStart"] + char_start,
                            "charEnd": word["charEnd"] + char_start,
                        }
                    )

        for turn, (_, _, char_start, char_end) in zip(turns, turn_ranges):
            turn["words"] = [
                {
                    **word,
                    "charStart": word["charStart"] - char_start,
                    "charEnd": word["charEnd"] - char_start,
                }
                for word in all_words
                if char_start <= word["charStart"] and word["charEnd"] <= char_end
            ]
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("dialogue audio output was not created")
    return output_path
