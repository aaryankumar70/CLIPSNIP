from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api.routes import router
from .config import get_settings
from .models import db
from .services import youtube
from .workers import pipeline

@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    for d in ("uploads", "audio", "transcripts", "clips", "rendered", "thumbnails"):
        (s.storage / d).mkdir(parents=True, exist_ok=True)
    # Interrupted jobs resume from last finished stage: reset 'processing' to 'queued'
    db.q("UPDATE projects SET status='queued' WHERE status='processing'")
    pipeline.start_worker()
    youtube.start_upload_worker()
    yield

app = FastAPI(title="Clipper", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
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
    return {"ok": True}
