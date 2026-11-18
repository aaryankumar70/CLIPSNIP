"""Ingestion service: local files, direct media URLs, and YouTube videos via yt-dlp."""
import glob
import os
import shutil
import urllib.request
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlparse
from ..config import get_settings
from ..models import db
from ..utils.paths import safe_join

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

class IngestError(RuntimeError):
    pass

def is_youtube_url(url: str) -> bool:
    try:
        u = urlparse(url)
        return any(h in u.netloc.lower() for h in ("youtube.com", "youtu.be"))
    except Exception:
        return False

class VideoSource(ABC):
    @abstractmethod
    def fetch(self, dest_dir: Path) -> Path: ...

class LocalFileSource(VideoSource):
    def __init__(self, path: Path):
        self.path = Path(path)

    def fetch(self, dest_dir: Path) -> Path:
        if self.path.suffix.lower() not in ALLOWED_EXT:
            raise IngestError(f"Unsupported file type: {self.path.suffix or 'none'}")
        if not self.path.is_file():
            raise IngestError("Video file not found")
        size = self.path.stat().st_size
        if size > get_settings().max_video_size:
            raise IngestError("Video exceeds the maximum allowed size")
        if shutil.disk_usage(dest_dir).free < size * 2:
            raise IngestError("Insufficient disk space")
        dest = safe_join(dest_dir, f"{uuid.uuid4().hex}{self.path.suffix.lower()}")
        shutil.copyfile(self.path, dest)
        return dest

class DirectUrlSource(VideoSource):
    """Downloads a direct http(s) link to a media file."""
    def __init__(self, url: str):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.netloc:
            raise IngestError("Invalid URL")
        if Path(u.path).suffix.lower() not in ALLOWED_EXT:
            raise IngestError("URL must point directly to a video file (mp4, mov, mkv, webm...)")
        self.url = url

    def fetch(self, dest_dir: Path) -> Path:
        dest = safe_join(dest_dir, f"{uuid.uuid4().hex}{Path(urlparse(self.url).path).suffix.lower()}")
        limit, size = get_settings().max_video_size, 0
        try:
            with urllib.request.urlopen(self.url, timeout=30) as r, open(dest, "wb") as f:
                while chunk := r.read(1 << 20):
                    size += len(chunk)
                    if size > limit:
                        raise IngestError("Video exceeds the maximum allowed size")
                    f.write(chunk)
        except IngestError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise IngestError(f"Source unavailable: {e}") from e
        return dest

class YouTubeSource(VideoSource):
    """Downloads a YouTube video and its json3 captions via yt-dlp."""
    def __init__(self, url: str, project_id: str | None = None, progress_hook=None):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not is_youtube_url(url):
            raise IngestError(f"Invalid YouTube URL: {url}")
        self.url = url
        self.project_id = project_id
        self.progress_hook = progress_hook

    def fetch(self, dest_dir: Path) -> Path:
        import yt_dlp

        s = get_settings()
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Check free disk space first (min 2 GB)
        if shutil.disk_usage(dest_dir).free < 2 * (1024**3):
            raise IngestError("Insufficient disk space (< 2 GB free)")

        stem = self.project_id or uuid.uuid4().hex[:12]
        out_tmpl = str(dest_dir / f"{stem}.%(ext)s")

        try:
            db_s = db.get_db_settings()
            quality = getattr(db_s, "download_quality", "720p") or "720p"
            caption_lang = getattr(db_s, "caption_language", "en") or "en"
        except Exception:
            quality = "720p"
            caption_lang = "en"

        max_h = 1080 if quality == "1080p" else 720
        format_str = f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]/best"

        def _hook(d):
            if d.get("status") == "downloading" and self.progress_hook:
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                pct = (downloaded / total * 100.0) if total > 0 else 0
                self.progress_hook(pct, f"Downloading video: {pct:.0f}%")

        ydl_opts = {
            "format": format_str,
            "outtmpl": out_tmpl,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "playlist_items": "1",
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "json3",
            "subtitleslangs": [caption_lang, "en", "en-US", "en-GB"],
            "ignoreerrors": True,
            "js_runtimes": {"node": {}},
            "progress_hooks": [_hook],
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    raise IngestError("Could not retrieve YouTube video metadata")

                if "entries" in info and info["entries"]:
                    info = info["entries"][0]

                # Check max duration (3 hours)
                dur = float(info.get("duration") or 0.0)
                if dur > 3 * 3600:
                    raise IngestError(f"Video duration ({dur/60:.1f} min) exceeds maximum limit of 3 hours")

                # Store metadata on project
                if self.project_id:
                    db.update_project(
                        self.project_id,
                        source_title=info.get("title", "")[:120],
                        channel_name=(info.get("uploader", "") or info.get("channel", ""))[:80],
                        channel_url=info.get("uploader_url", "") or info.get("channel_url", ""),
                        video_url=info.get("webpage_url", self.url),
                        duration=dur,
                        upload_date=str(info.get("upload_date", "")),
                    )

                # Execute download
                ydl.download([self.url])

        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if "subtitles" in err.lower() or "429" in err:
                # If YouTube rate limits subtitle download (HTTP 429), download video without subtitles;
                # faster-whisper will automatically handle speech-to-text in Stage 2.
                ydl_opts_no_sub = dict(ydl_opts)
                ydl_opts_no_sub["writesubtitles"] = False
                ydl_opts_no_sub["writeautomaticsub"] = False
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_no_sub) as ydl_retry:
                        ydl_retry.download([self.url])
                except Exception as retry_err:
                    raise IngestError(f"YouTube download failed: {retry_err}") from retry_err
            elif "Private video" in err:
                raise IngestError("YouTube video is private") from e
            elif "Video unavailable" in err or "removed" in err:
                raise IngestError("YouTube video has been removed or is unavailable") from e
            elif "Sign in to confirm your age" in err:
                raise IngestError("YouTube video is age-restricted") from e
            elif "Premieres in" in err or "Live event" in err or "This live event" in err:
                raise IngestError("YouTube video is an unfinished live stream or premiere") from e
            elif "not available in your country" in err or "blocked" in err.lower():
                raise IngestError("YouTube video is geo-blocked in this region") from e
            else:
                raise IngestError(f"YouTube download failed: {err}") from e
        except IngestError:
            raise
        except Exception as e:
            raise IngestError(f"YouTube download failed: {e}") from e

        # Locate downloaded MP4 file
        dest_mp4 = dest_dir / f"{stem}.mp4"
        if not dest_mp4.is_file():
            candidates = list(dest_dir.glob(f"{stem}.*"))
            video_cands = [c for c in candidates if c.suffix.lower() in ALLOWED_EXT]
            if video_cands:
                dest_mp4 = video_cands[0]
            else:
                raise IngestError("Downloaded video file was not found")

        # Move json3 subtitles to storage/transcripts/<id>.captions.json
        if self.project_id:
            caption_target = s.storage / "transcripts" / f"{self.project_id}.captions.json"
            caption_target.parent.mkdir(parents=True, exist_ok=True)
            for sub_file in dest_dir.glob(f"{stem}*.json3"):
                shutil.move(str(sub_file), str(caption_target))
                break

        # Clean up any leftover subtitle files
        for leftover in dest_dir.glob(f"{stem}*.json3"):
            try:
                leftover.unlink(missing_ok=True)
            except Exception:
                pass

        return dest_mp4
