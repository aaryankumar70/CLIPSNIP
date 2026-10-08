import json, shutil, time, uuid
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from ..config import get_settings
from ..models import db
from ..schemas.clip import ClipUpdate
from ..services.ingest import ALLOWED_EXT
from ..workers import pipeline

router = APIRouter(prefix="/api")

def _proj(pid: str) -> dict:
    p = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not p: raise HTTPException(404, "Project not found")
    return p

def _clip(cid: str) -> dict:
    c = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)
    if not c: raise HTTPException(404, "Clip not found")
    return c

def _public(p: dict) -> dict:
    end = p["finished_at"] or time.time()
    p["elapsed"] = round(end - p["started_at"], 1) if p["started_at"] else 0
    p.pop("source_path", None); p.pop("transcript_path", None)
    return p

@router.post("/jobs", status_code=202)
async def create_job(url: str | None = Form(None), file: UploadFile | None = File(None)):
    s = get_settings()
    if bool(url) == bool(file):
        raise HTTPException(400, "Provide either a video URL or an uploaded file")
    if file:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT: raise HTTPException(400, f"Unsupported file type '{ext}'")
        (s.storage / "uploads").mkdir(parents=True, exist_ok=True)
        dest = s.storage / "uploads" / f"{uuid.uuid4().hex}{ext}"
        size = 0
        with open(dest, "wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > s.max_video_size:
                    f.close(); dest.unlink(missing_ok=True); raise HTTPException(413, "Video exceeds the maximum allowed size")
                f.write(chunk)
        pid, source, name = db.create_project(Path(file.filename).stem[:80], str(dest)), str(dest), Path(file.filename).stem[:80]
    else:
        if not url.startswith(("http://", "https://")): raise HTTPException(400, "Invalid URL")
        pid, source = db.create_project(url[:80], url), url
    pipeline.submit(pid, source)
    return {"id": pid}

@router.get("/jobs")
def list_jobs():
    return [_public(p) for p in db.q("SELECT * FROM projects ORDER BY created_at DESC")]

@router.get("/jobs/{pid}")
def get_job(pid: str): return _public(_proj(pid))

@router.get("/jobs/{pid}/transcript")
def get_transcript(pid: str):
    p = _proj(pid)
    if not p["transcript_path"]: raise HTTPException(409, "Transcript not ready yet")
    return json.loads(Path(p["transcript_path"]).read_text(encoding="utf-8"))

def _clip_public(c: dict) -> dict:
    c["video_url"] = f"/media/rendered/{c['id']}.mp4" if c["render_status"] == "ready" else None
    c["thumb_url"] = f"/media/thumbnails/{c['id']}.jpg" if c["render_status"] == "ready" else None
    c.pop("rendered_path", None); c.pop("thumb_path", None)
    return c

@router.get("/jobs/{pid}/clips")
def get_clips(pid: str, sort: str = "score"):
    _proj(pid)
    order = {"score": "score DESC", "newest": "created_at DESC", "longest": "(end-start) DESC", "shortest": "(end-start) ASC"}.get(sort, "score DESC")
    return [_clip_public(c) for c in db.q(f"SELECT * FROM clips WHERE project_id=? ORDER BY {order}", (pid,))]

@router.patch("/clips/{cid}")
def patch_clip(cid: str, body: ClipUpdate):
    c = _clip(cid); p = _proj(c["project_id"])
    changes = body.model_dump(exclude_none=True)
    start, end = changes.get("start", c["start"]), changes.get("end", c["end"])
    if not (0 <= start < end <= (p["duration"] or 0) + 0.05):
        raise HTTPException(422, f"Invalid range: end must be after start and within the {p['duration']:.1f}s video")
    if changes: db.update_clip(cid, **changes, render_status="stale")
    return _clip_public(_clip(cid))

@router.post("/clips/{cid}/render", status_code=202)
def render(cid: str):
    _clip(cid); db.update_clip(cid, render_status="rendering", render_error=None)
    pipeline.pool.submit(pipeline.rerender, cid)
    return {"status": "rendering"}

@router.get("/clips/{cid}")
def get_clip(cid: str): return _clip_public(_clip(cid))

@router.get("/clips/{cid}/download")
def download(cid: str):
    c = _clip(cid)
    if c["render_status"] != "ready" or not c["rendered_path"] or not Path(c["rendered_path"]).is_file():
        raise HTTPException(409, "Clip is not rendered yet")
    safe = "".join(ch for ch in c["title"] if ch.isalnum() or ch in " -_")[:60].strip() or "clip"
    return FileResponse(c["rendered_path"], media_type="video/mp4", filename=f"{safe}.mp4")

@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str):
    p = _proj(pid); s = get_settings()
    for c in db.q("SELECT id FROM clips WHERE project_id=?", (pid,)):
        for f in (s.storage / "rendered" / f"{c['id']}.mp4", s.storage / "rendered" / f"{c['id']}.ass", s.storage / "thumbnails" / f"{c['id']}.jpg"):
            f.unlink(missing_ok=True)
    for f in (s.storage / "audio" / f"{pid}.wav", s.storage / "transcripts" / f"{pid}.json"):
        f.unlink(missing_ok=True)
    if p["source_path"] and Path(p["source_path"]).parent == s.storage / "uploads":
        Path(p["source_path"]).unlink(missing_ok=True)
    db.q("DELETE FROM clips WHERE project_id=?", (pid,)); db.q("DELETE FROM projects WHERE id=?", (pid,))

@router.get("/jobs/{pid}/source")
def source_video(pid: str):
    p = _proj(pid)
    if not p["source_path"] or not Path(p["source_path"]).is_file(): raise HTTPException(404, "Source video not available")
    return FileResponse(p["source_path"])  # supports HTTP range requests, so seeking works
