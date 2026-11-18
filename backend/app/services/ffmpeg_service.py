"""All FFmpeg/ffprobe access. Commands are always argument lists (never shell strings)."""
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from ..config import get_settings

class FFmpegError(RuntimeError):
    pass

FORMATS = {"9:16": (720, 1280), "1:1": (720, 720), "16:9": (1280, 720)}
FORMATS_1080 = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}

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
    return VideoInfo(
        dur,
        int(v["width"]),
        int(v["height"]),
        any(x.get("codec_type") == "audio" for x in d.get("streams", [])),
    )

def extract_audio(video: Path, out_wav: Path) -> Path:
    """16 kHz mono WAV, the format Whisper and energy analysis require."""
    s = get_settings()
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    _run([
        s.ffmpeg, "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
        "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)
    ])
    return out_wav

def get_dimensions(aspect: str, resolution: str = "720x1280") -> tuple[int, int]:
    table = FORMATS_1080 if resolution == "1080x1920" else FORMATS
    if aspect not in table:
        raise ValueError(f"Unsupported aspect ratio: {aspect}")
    return table[aspect]

def _esc_subtitles_path(ass_path: Path) -> str:
    # Escape path characters for FFmpeg subtitles filter
    return str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

def build_video_filter(
    aspect: str = "9:16",
    layout: str = "blur_fit",
    resolution: str = "720x1280",
    ass: Path | None = None,
) -> tuple[bool, str]:
    """Returns (is_complex, filter_string).

    Layouts:
      - blur_fit: scales video down to 1/4 size, boxblur, scales back up, overlays crisp foreground
      - center_crop: crops center to target aspect ratio
    """
    tw, th = get_dimensions(aspect, resolution)
    sub_filter = f",subtitles='{_esc_subtitles_path(ass)}'" if ass else ""

    if layout == "blur_fit" and aspect == "9:16":
        # Cheap blurred background + crisp centered foreground
        bw, bh = tw // 4, th // 4
        graph = (
            f"[0:v]split=2[bg_raw][fg_raw];"
            f"[bg_raw]scale={bw}:{bh}:flags=fast_bilinear,boxblur=10:5,scale={tw}:{th}:flags=fast_bilinear,setsar=1[bg];"
            f"[fg_raw]scale={tw}:-2:flags=lanczos[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1{sub_filter}[outv]"
        )
        return True, graph
    else:
        # Default center crop
        f = (
            f"crop='if(gt(iw/ih,{tw}/{th}),ih*{tw}/{th},iw)':'if(gt(iw/ih,{tw}/{th}),ih,iw*{th}/{tw})',"
            f"scale={tw}:{th}:flags=lanczos,setsar=1{sub_filter}"
        )
        return False, f

def trim_clip_start(start: float, end: float, words: list[dict[str, Any]] | None) -> float:
    """Trim leading silence or filler words at the clip start (max 1.5s)."""
    if not words:
        return start

    clip_words = [w for w in words if w["end"] > start and w["start"] < end]
    if not clip_words:
        return start

    new_start = start
    first_w_clean = re.sub(r"[^\w]", "", clip_words[0]["word"]).lower()
    FILLER = {"um", "uh", "so", "like", "well", "actually", "yeah", "okay"}

    if first_w_clean in FILLER and len(clip_words) > 1:
        gap = clip_words[1]["start"] - start
        if 0 < gap <= 1.5:
            new_start = max(start, clip_words[1]["start"] - 0.15)
    elif clip_words[0]["start"] - start > 0.3:
        trim_amt = min(1.5, clip_words[0]["start"] - start - 0.15)
        if trim_amt > 0:
            new_start += trim_amt

    return round(new_start, 2)

def cut_clip(
    src: Path,
    out: Path,
    start: float,
    end: float,
    info: VideoInfo,
    aspect: str = "9:16",
    layout: str = "blur_fit",
    resolution: str = "720x1280",
    ass: Path | None = None,
) -> Path:
    if not (0 <= start < end <= info.duration + 0.1):
        raise ValueError(f"Invalid clip range {start}-{end} for {info.duration:.1f}s video")

    s = get_settings()
    out.parent.mkdir(parents=True, exist_ok=True)
    is_complex, vf = build_video_filter(aspect, layout, resolution, ass)

    cmd = [
        s.ffmpeg, "-y", "-v", "error",
        "-ss", f"{start:.3f}",
        "-i", str(src),
        "-t", f"{end - start:.3f}",
    ]

    if is_complex:
        cmd.extend(["-filter_complex", vf, "-map", "[outv]"])
        if info.has_audio:
            cmd.extend(["-map", "0:a"])
    else:
        cmd.extend(["-vf", vf])

    # Video encoding
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "24",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ])

    # Audio encoding: loudnorm filter
    if info.has_audio:
        cmd.extend([
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a", "aac",
            "-b:a", "160k",
        ])
    else:
        cmd.extend(["-an"])

    cmd.append(str(out))
    _run(cmd)
    return out

def thumbnail(video: Path, out_jpg: Path, at: float = 1.0) -> Path:
    s = get_settings()
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    _run([
        s.ffmpeg, "-y", "-v", "error",
        "-ss", f"{at:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-vf", "scale=480:-2",
        str(out_jpg)
    ], timeout=60)
    return out_jpg
