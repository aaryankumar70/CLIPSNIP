"""All FFmpeg/ffprobe access. Commands are always argument lists (never shell strings)."""
import json, subprocess
from dataclasses import dataclass
from pathlib import Path
from ..config import get_settings

class FFmpegError(RuntimeError):
    pass

FORMATS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}

@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    has_audio: bool

def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise FFmpegError(f"{Path(cmd[0]).name} timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise FFmpegError(f"{cmd[0]} not found; install FFmpeg or set FFMPEG_PATH") from e
    if r.returncode != 0:
        raise FFmpegError(f"{Path(cmd[0]).name} failed: {r.stderr.strip()[-600:]}")
    return r

def probe(path: Path) -> VideoInfo:
    s = get_settings()
    r = _run([s.ffprobe, "-v", "error", "-print_format", "json", "-show_format",
              "-show_streams", str(path)], timeout=60)
    d = json.loads(r.stdout)
    v = next((x for x in d.get("streams", []) if x.get("codec_type") == "video"), None)
    if not v:
        raise FFmpegError("File has no video stream (unsupported or corrupted)")
    dur = float(d.get("format", {}).get("duration") or v.get("duration") or 0)
    if dur <= 0:
        raise FFmpegError("Could not determine video duration (corrupted file?)")
    return VideoInfo(dur, int(v["width"]), int(v["height"]),
                     any(x.get("codec_type") == "audio" for x in d["streams"]))

def extract_audio(video: Path, out_wav: Path) -> Path:
    """16 kHz mono WAV, the format Whisper wants."""
    s = get_settings()
    _run([s.ffmpeg, "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
          "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)])
    return out_wav

def build_video_filter(aspect: str, ass: Path | None = None) -> str:
    """Center-crop to target aspect, scale, optionally burn ASS captions."""
    if aspect not in FORMATS:
        raise ValueError(f"Unsupported aspect ratio: {aspect}")
    tw, th = FORMATS[aspect]
    f = (f"crop='if(gt(iw/ih,{tw}/{th}),ih*{tw}/{th},iw)':'if(gt(iw/ih,{tw}/{th}),ih,iw*{th}/{tw})',"
         f"scale={tw}:{th}:flags=lanczos,setsar=1")
    if ass:
        esc = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        f += f",subtitles='{esc}'"
    return f

def cut_clip(src: Path, out: Path, start: float, end: float, info: VideoInfo,
             aspect: str = "9:16", ass: Path | None = None) -> Path:
    if not (0 <= start < end <= info.duration + 0.05):
        raise ValueError(f"Invalid clip range {start}-{end} for {info.duration:.1f}s video")
    s = get_settings()
    _run([s.ffmpeg, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src),
          "-t", f"{end - start:.3f}", "-vf", build_video_filter(aspect, ass),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    return out

def thumbnail(video: Path, out_jpg: Path, at: float = 1.0) -> Path:
    s = get_settings()
    _run([s.ffmpeg, "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", str(video),
          "-frames:v", "1", "-vf", "scale=480:-2", str(out_jpg)], timeout=60)
    return out_jpg
