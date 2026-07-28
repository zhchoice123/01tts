import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"


def ensure_directories():
    """Ensure input and output directories exist."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_input_file_path(filename: str) -> Path:
    """
    Resolve the file path inside the input directory or direct path.
    If only a filename is passed (e.g., 'sample.txt'), resolve to 'input/sample.txt'.
    """
    ensure_directories()
    path = Path(filename)
    if not path.is_absolute() and not path.exists():
        path = INPUT_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path} (Checked in {INPUT_DIR})")
    
    return path


def read_text_file(filepath: Path) -> str:
    """Read text from a given file with automatic UTF-8 fallback."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        # Fallback to gbk if UTF-8 fails
        with open(filepath, "r", encoding="gbk") as f:
            content = f.read()

    text = content.strip()
    if not text:
        raise ValueError(f"File '{filepath}' is empty!")
    return text


def get_output_file_path(output_name: str | None, input_filename: str) -> Path:
    """Determine output MP3 filepath in output directory."""
    ensure_directories()
    if not output_name:
        base_name = Path(input_filename).stem
        output_name = f"{base_name}.mp3"
    
    out_path = Path(output_name)
    if not out_path.is_absolute():
        out_path = OUTPUT_DIR / out_path.name
        
    if not out_path.name.endswith(".mp3"):
        out_path = out_path.with_suffix(".mp3")

    return out_path
