from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api.routes import router
from .config import get_settings
from .models import db

app = FastAPI(title="Clipper")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

@app.on_event("startup")
def startup():
    s = get_settings()
    for d in ("uploads", "audio", "transcripts", "clips", "rendered", "thumbnails"):
        (s.storage / d).mkdir(parents=True, exist_ok=True)
    # interrupted jobs (server restarted mid-run) must not stay "processing" forever
    db.q("UPDATE projects SET status='failed', error='Server restarted while processing; please re-run' WHERE status IN ('queued','processing')")

@app.on_event("startup")
def mount_media():
    s = get_settings()
    app.mount("/media/rendered", StaticFiles(directory=s.storage / "rendered"), name="rendered")
    app.mount("/media/thumbnails", StaticFiles(directory=s.storage / "thumbnails"), name="thumbs")

@app.get("/api/health")
def health(): return {"ok": True}
