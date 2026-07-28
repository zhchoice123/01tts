import argparse
import asyncio
import sys
from pathlib import Path
from src.tts_service import convert_file_to_speech, get_english_voices, POPULAR_ENGLISH_VOICES, DEFAULT_VOICE
from src.utils import ensure_directories, INPUT_DIR, OUTPUT_DIR


def list_voices_command():
    """Print curated and total English voices."""
    print("\n🌟 Recommended English Voices:")
    print("--------------------------------------------------")
    for v_name, desc in POPULAR_ENGLISH_VOICES.items():
        print(f"  • {v_name:<25} - {desc}")
    print("--------------------------------------------------\n")

    print("🔍 Fetching all online English voices from Edge TTS...")
    async def fetch():
        voices = await get_english_voices()
        print(f"Found {len(voices)} English voices:")
        for v in voices:
            short_name = v.get("ShortName", "")
            gender = v.get("Gender", "")
            locale = v.get("Locale", "")
            print(f"  • {short_name:<30} [{gender:<6}] ({locale})")
    
    asyncio.run(fetch())


def main():
    ensure_directories()

    parser = argparse.ArgumentParser(
        description="Edge TTS - Convert text files in input/ directory to English MP3 files."
    )
    
    parser.add_argument(
        "-f", "--file",
        type=str,
        default="sample.txt",
        help="Target text file name inside input/ directory (default: sample.txt)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output MP3 file name inside output/ directory (default: same as text file stem)"
    )
    parser.add_argument(
        "-v", "--voice",
        type=str,
        default=DEFAULT_VOICE,
        help=f"Edge TTS voice name (default: {DEFAULT_VOICE})"
    )
    parser.add_argument(
        "-r", "--rate",
        type=str,
        default="+0%",
        help="Speech rate adjustment, e.g., '+10%%', '-20%%' (default: +0%%)"
    )
    parser.add_argument(
        "-p", "--pitch",
        type=str,
        default="+0Hz",
        help="Pitch adjustment, e.g., '+5Hz', '-5Hz' (default: +0Hz)"
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available English neural voices and exit"
    )

    args = parser.parse_args()

    if args.list_voices:
        list_voices_command()
        sys.exit(0)

    try:
        asyncio.run(
            convert_file_to_speech(
                filename=args.file,
                output_name=args.output,
                voice=args.voice,
                rate=args.rate,
                pitch=args.pitch
            )
        )
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print(f"💡 Please place your text file inside: {INPUT_DIR}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to generate audio: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
