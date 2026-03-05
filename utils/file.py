import os
import re
from pathlib import Path
from typing import List

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def safe_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    return name or "output"


def get_video_files(folder: str) -> List[str]:
    """Return list of video file paths in the given folder."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return []
    files = []
    for f in folder_path.iterdir():
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(str(f))
    return sorted(files)
