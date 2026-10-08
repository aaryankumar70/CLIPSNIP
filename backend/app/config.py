import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    ffmpeg: str = os.environ.get("FFMPEG_PATH", "ffmpeg")
    ffprobe: str = os.environ.get("FFPROBE_PATH", "ffprobe")
    storage: Path = Path(os.environ.get("STORAGE_PATH", "./storage")).resolve()
    max_video_size: int = int(os.environ.get("MAX_VIDEO_SIZE", 4 * 1024**3))
    whisper_model: str = os.environ.get("WHISPER_MODEL", "small")
    whisper_device: str = os.environ.get("WHISPER_DEVICE", "auto")
    ai_provider: str = os.environ.get("AI_PROVIDER", "anthropic")

def get_settings() -> Settings:
    return Settings()
