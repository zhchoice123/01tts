import asyncio
import edge_tts
from pathlib import Path
from typing import Optional, List, Dict
from src.utils import get_input_file_path, read_text_file, get_output_file_path

# Popular English Neural Voices in Edge TTS
DEFAULT_VOICE = "en-US-AvaNeural"

POPULAR_ENGLISH_VOICES = {
    "en-US-AvaNeural": "Female, US (Expressive & Natural)",
    "en-US-AndrewNeural": "Male, US (Warm & Professional)",
    "en-US-EmmaNeural": "Female, US (Friendly & Conversational)",
    "en-US-BrianNeural": "Male, US (Young & Energetic)",
    "en-US-ChristopherNeural": "Male, US (Newsreader / Deep)",
    "en-GB-SoniaNeural": "Female, UK (Standard British Accent)",
    "en-GB-RyanNeural": "Male, UK (Clear British Tone)",
    "en-AU-NatashaNeural": "Female, Australia",
    "en-CA-ClaraNeural": "Female, Canada",
}


async def generate_audio(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%"
) -> Path:
    """
    Call Edge TTS API to generate an MP3 file from text.

    :param text: Text string to convert to speech
    :param output_path: Destination path for the generated MP3
    :param voice: Voice model name (e.g., en-US-AvaNeural)
    :param rate: Speed adjustment (e.g., '+10%', '-20%')
    :param pitch: Pitch adjustment (e.g., '+5Hz', '-5Hz')
    :param volume: Volume adjustment (e.g., '+0%')
    :return: Path to the generated output file
    """
    communicator = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
        volume=volume
    )
    
    await communicator.save(str(output_path))
    return output_path


async def convert_file_to_speech(
    filename: str,
    output_name: Optional[str] = None,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%"
) -> Path:
    """
    Read text from input directory file and generate MP3 file in output directory.
    """
    input_file_path = get_input_file_path(filename)
    text = read_text_file(input_file_path)
    output_path = get_output_file_path(output_name, filename)

    print(f"📄 Reading text file: {input_file_path}")
    print(f"🎙️ Voice: {voice} | Rate: {rate} | Pitch: {pitch}")
    print(f"⏳ Generating speech with Edge TTS...")

    await generate_audio(
        text=text,
        output_path=output_path,
        voice=voice,
        rate=rate,
        pitch=pitch,
        volume=volume
    )

    print(f"✅ Success! Audio saved to: {output_path}")
    return output_path


async def get_english_voices() -> List[Dict[str, str]]:
    """List all available English voices from Edge TTS."""
    voices = await edge_tts.VoicesManager.create()
    english_voices = voices.find(Language="en")
    return english_voices
