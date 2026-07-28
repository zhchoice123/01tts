import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import edge_tts


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


async def generate_audio(text: str, output_path: Path, voice: str) -> Path:
    """Generate an MP3 using Edge TTS."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text=text, voice=voice).save(str(output_path))
    return output_path


async def generate_dialogue_audio(
    turns: list[dict[str, Any]],
    output_path: Path,
    host_voice: str = "en-US-AvaNeural",
    expert_voice: str = "en-US-AndrewNeural",
) -> Path:
    """Generate alternating speaker segments and concatenate them into one MP3."""
    if not turns:
        raise ValueError("dialogue must contain at least one turn")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="dialogue-",
        dir=output_path.parent,
    ) as temporary:
        temporary_dir = Path(temporary)
        segment_paths: list[Path] = []
        segment_durations: list[int] = []
        for index, turn in enumerate(turns):
            speaker = str(turn.get("speaker", "")).strip().upper()
            text = str(turn.get("text", "")).strip()
            if speaker not in {"HOST", "EXPERT"} or not text:
                raise ValueError(f"invalid dialogue turn at index {index}")
            voice = host_voice if speaker == "HOST" else expert_voice
            segment_path = temporary_dir / f"segment-{index:03d}.mp3"
            await edge_tts.Communicate(
                text=text,
                voice=voice,
                rate="-5%",
            ).save(str(segment_path))
            segment_paths.append(segment_path)
            segment_durations.append(
                await asyncio.to_thread(_probe_duration_ms, segment_path)
            )

        concat_file = temporary_dir / "segments.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in segment_paths),
            encoding="utf-8",
        )
        await asyncio.to_thread(
            subprocess.run,
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
        output_duration = await asyncio.to_thread(_probe_duration_ms, output_path)
        measured_total = sum(segment_durations)
        if measured_total <= 0:
            raise RuntimeError("dialogue segments have no measurable duration")
        start_ms = 0
        cumulative_measured = 0
        for index, (turn, segment_duration) in enumerate(
            zip(turns, segment_durations)
        ):
            cumulative_measured += segment_duration
            if index == len(turns) - 1:
                end_ms = output_duration
            else:
                remaining_turns = len(turns) - index - 1
                end_ms = round(
                    cumulative_measured * output_duration / measured_total
                )
                end_ms = max(start_ms + 1, end_ms)
                end_ms = min(end_ms, output_duration - remaining_turns)
            turn["startMs"] = start_ms
            turn["endMs"] = end_ms
            start_ms = end_ms
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("dialogue audio output was not created")
    return output_path
