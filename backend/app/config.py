import math
import os
from dataclasses import dataclass
from pathlib import Path

MIN_CLIP_S: int = 60
MAX_CLIP_S: int = 120
IDEAL_CLIP_MIN_S: int = 75
IDEAL_CLIP_MAX_S: int = 100
WINDOW_S: int = 300
WINDOW_OVERLAP_S: int = 30
MAX_WINDOWS: int = 12
DEFAULT_WIDTH: int = 720
DEFAULT_HEIGHT: int = 1280
DEFAULT_RESOLUTION: str = "720x1280"
DEFAULT_LAYOUT: str = "blur_fit"
DEFAULT_CAPTION_STYLE: str = "highlight"
DEFAULT_WHISPER_MODEL: str = "base.en"
DEFAULT_OLLAMA_MODEL: str = "qwen2.5:3b-instruct"
DEFAULT_OLLAMA_NUM_CTX: int = 4096
DEFAULT_AI_PROVIDER: str = "ollama"
DEFAULT_DOWNLOAD_QUALITY: str = "720p"
DEFAULT_CAPTION_LANGUAGE: str = "en"
DEFAULT_UPLOAD_PRIVACY: str = "public"
DEFAULT_SPREAD_MINUTES: int = 60
DEFAULT_FOOTER_TEMPLATE: str = "Clipped from {source_title} by {channel} - {source_url}"
DEFAULT_DELETE_SOURCE_AFTER_RENDER: bool = False
DEFAULT_LAN_MODE: bool = False

def calculate_clip_count(video_seconds: float, override_max: int | None = None) -> int:
    video_minutes = max(0.0, video_seconds) / 60.0
    calc = math.floor(video_minutes / 2.5)
    clamped = max(3, min(15, calc))
    if override_max is not None and override_max > 0:
        return min(clamped, override_max)
    return clamped

@dataclass(frozen=True)
class Settings:
    ffmpeg: str = os.environ.get("FFMPEG_PATH", "ffmpeg")
    ffprobe: str = os.environ.get("FFPROBE_PATH", "ffprobe")
    storage: Path = Path(os.environ.get("STORAGE_PATH", "./storage")).resolve()
    max_video_size: int = int(os.environ.get("MAX_VIDEO_SIZE", 4 * 1024**3))
    whisper_model: str = os.environ.get("WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    whisper_device: str = os.environ.get("WHISPER_DEVICE", "auto")
    ai_provider: str = os.environ.get("AI_PROVIDER", DEFAULT_AI_PROVIDER)
    ollama_model: str = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    ollama_num_ctx: int = int(os.environ.get("OLLAMA_NUM_CTX", str(DEFAULT_OLLAMA_NUM_CTX)))
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")

def get_settings() -> Settings:
    return Settings()
