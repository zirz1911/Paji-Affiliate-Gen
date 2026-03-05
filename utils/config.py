import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Any
import uuid


CONFIG_DIR = Path.home() / ".paji-affiliate"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class Config:
    api_key: str = ""
    model: str = "gemini-2.5-flash-preview-tts"
    default_voice: str = "Kore"
    default_clip_duration: float = 5.0
    max_concurrent: int = 2

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()


@dataclass
class TextOverlay:
    text: str = "New Text"
    x: int = 100
    y: int = 100
    font_size: int = 72
    color: str = "#ffffff"
    bold: bool = False
    font_family: str = "Tahoma"
    align: str = "left"   # "left" | "center" | "right"
    uid: str = field(default_factory=lambda: str(uuid.uuid4())[:6])
    type: str = "text"


@dataclass
class ImageOverlay:
    path: str = ""
    x: int = 100
    y: int = 100
    width: int = 300
    height: int = 200
    uid: str = field(default_factory=lambda: str(uuid.uuid4())[:6])
    type: str = "image"


@dataclass
class AffiliateTask:
    name: str
    folder: str
    scripts: List[str]
    voice: str = "Kore"
    clip_duration: float = 5.0
    uid: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: str = "pending"  # pending / processing / done / error
    overlays: List[Any] = field(default_factory=list)
    overlay_ratio: str = "9:16"  # "9:16" | "16:9"
