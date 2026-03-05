import os
import re
from pathlib import Path
from functools import lru_cache
from typing import Dict, List

FONT_DIRS = [
    r"C:/Windows/Fonts",
    os.path.expanduser(r"~/AppData/Local/Microsoft/Windows/Fonts"),
]

# Thai-compatible fonts — shown first in the list
_THAI_KEYS = {
    "tahoma", "leelawadeeui", "leelawadee", "cordianew", "angsananew",
    "browallianew", "notosansthai", "thsarabuniupsk", "sarabun",
    "dbhelvethaicax", "kinnari", "norasi", "garuda", "loma",
}


@lru_cache(maxsize=1)
def get_font_map() -> Dict[str, str]:
    """Return {display_name: file_path} for all .ttf/.otf fonts found on system."""
    found: Dict[str, str] = {}
    for d in FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for f in Path(d).iterdir():
            if f.suffix.lower() not in (".ttf", ".otf"):
                continue
            # Use filename stem as display name (cleaned up)
            name = re.sub(r"[-_]+", " ", f.stem).strip()
            name = re.sub(r"\s+", " ", name)
            if name not in found:
                found[name] = str(f).replace("\\", "/")
    return dict(sorted(found.items()))


def font_names() -> List[str]:
    """Return font list with Thai-compatible fonts at the top."""
    m = get_font_map()
    thai, other = [], []
    for name in m:
        key = re.sub(r"\W", "", name).lower()
        (thai if any(t in key for t in _THAI_KEYS) else other).append(name)
    return thai + other


def font_path_for(name: str) -> str:
    """Return escaped file path for ffmpeg fontfile, or empty string."""
    path = get_font_map().get(name, "")
    if not path:
        # Fuzzy fallback: match by normalised stem
        target = re.sub(r"\W", "", name).lower()
        for n, p in get_font_map().items():
            stem = re.sub(r"\W", "", n).lower()
            if stem.startswith(target) or target in stem:
                path = p
                break
    return path.replace(":", "\\:") if path else ""
