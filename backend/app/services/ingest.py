"""Ingestion abstraction. Only authorized/accessible sources: local files and direct media URLs."""
import shutil, urllib.request, uuid
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlparse
from ..config import get_settings
from ..utils.paths import safe_join

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

class IngestError(RuntimeError):
    pass

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
    """Downloads a direct http(s) link to a media file you are authorized to use."""
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
            dest.unlink(missing_ok=True); raise
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise IngestError(f"Source unavailable: {e}") from e
        return dest
