import logging
import shutil
import urllib.request
import json
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import get_settings
from .models import db
from .services import youtube
from .workers import pipeline

logger = logging.getLogger("uvicorn")

@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    for d in ("uploads", "audio", "transcripts", "clips", "rendered", "thumbnails"):
        (s.storage / d).mkdir(parents=True, exist_ok=True)

    # Interrupted jobs resume from last finished stage: reset 'processing' to 'queued'
    db.q("UPDATE projects SET status='queued' WHERE status='processing'")

    # Run cleanup of expired uploaded files on startup
    pipeline.run_cleanup_job()

    pipeline.start_worker()
    youtube.start_upload_worker()
    yield

app = FastAPI(title="ClipSnip", lifespan=lifespan)

# Allow local origins and dev server
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# If LAN mode is configured in DB settings, log warning and allow LAN requests
try:
    db_settings = db.get_db_settings()
    if getattr(db_settings, "lan_mode", False):
        allowed_origins = ["*"]
        logger.warning(
            "*** WARNING: LAN MODE IS ENABLED. ClipSnip has NO AUTHENTICATION. "
            "Anyone on your local network can access the dashboard. ***"
        )
except Exception:
    pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

s = get_settings()
(s.storage / "rendered").mkdir(parents=True, exist_ok=True)
(s.storage / "thumbnails").mkdir(parents=True, exist_ok=True)
app.mount("/media/rendered", StaticFiles(directory=s.storage / "rendered"), name="rendered")
app.mount("/media/thumbnails", StaticFiles(directory=s.storage / "thumbnails"), name="thumbs")

@app.get("/api/health")
def health():
    warnings: list[str] = []
    
    # Check FFmpeg & ffprobe
    has_ffmpeg = shutil.which("ffmpeg") is not None
    has_ffprobe = shutil.which("ffprobe") is not None
    if not has_ffmpeg:
        warnings.append("FFmpeg is missing. Install with: sudo pacman -S ffmpeg")
    if not has_ffprobe:
        warnings.append("ffprobe is missing. Install with: sudo pacman -S ffmpeg")

    # Check Ollama status & model
    has_ollama = False
    has_model = False
    db_s = db.get_db_settings()
    model_name = getattr(db_s, "ollama_model", "qwen2.5:3b-instruct") or "qwen2.5:3b-instruct"

    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", headers={"User-Agent": "ClipSnip"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                has_ollama = True
                data = json.loads(resp.read().decode())
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check for exact or prefix match (e.g. 'qwen2.5:3b-instruct' or 'qwen2.5:3b-instruct:latest')
                has_model = any(m == model_name or m.startswith(f"{model_name}:") for m in models)
                if not has_model:
                    warnings.append(f"Ollama model '{model_name}' not downloaded. Run: ollama pull {model_name}")
    except Exception:
        has_ollama = False
        warnings.append("Ollama is not running. Start with: systemctl --user start ollama or ollama serve")

    # Check free disk space
    try:
        free_bytes = shutil.disk_usage(s.storage).free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < 5.0:
            warnings.append(f"Low disk space: {free_gb:.1f} GB free (minimum 5.0 GB required for downloads)")
    except Exception:
        free_gb = 0.0

    return {
        "ok": has_ffmpeg and has_ffprobe,
        "ffmpeg": has_ffmpeg,
        "ffprobe": has_ffprobe,
        "ollama": has_ollama,
        "ollama_model": has_model,
        "model_name": model_name,
        "disk_free_gb": round(free_gb, 2),
        "warnings": warnings,
    }

# Serve frontend/dist SPA when built
dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if dist_dir.exists() and (dist_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(dist_dir / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Do not swallow API or media calls
        if full_path.startswith("api/") or full_path.startswith("media/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        target = dist_dir / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(dist_dir / "index.html")
