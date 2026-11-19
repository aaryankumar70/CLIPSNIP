from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    clip_min_s: int = Field(default=60, ge=15, le=300)
    clip_max_s: int = Field(default=120, ge=20, le=600)
    max_clips: int = Field(default=15, ge=1, le=50)
    layout: Literal["blur_fit", "center_crop"] = "blur_fit"
    caption_style: Literal["classic", "bold", "highlight", "creator", "viral", "minimal", "off"] = "highlight"
    output_resolution: Literal["720x1280", "1080x1920"] = "720x1280"
    download_quality: Literal["720p", "1080p"] = "720p"
    caption_language: str = "en"
    upload_privacy: Literal["public", "unlisted", "private"] = "public"
    spread_minutes: int = Field(default=60, ge=1, le=1440)
    default_tags: list[str] = Field(default_factory=lambda: ["gaming", "gta6", "shorts", "gamingclips"])
    default_hashtags: list[str] = Field(default_factory=lambda: ["#gaming", "#shorts"])
    footer_template: str = "Clipped from {source_title} by {channel} - {source_url}"
    delete_source_after_render: bool = False
    cleanup_days: int = Field(default=7, ge=0, le=365)
    lan_mode: bool = False
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_num_ctx: int = 4096
    whisper_model: str = "base.en"
