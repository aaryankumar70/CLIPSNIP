import csv, io, json, shutil, time, uuid, zipfile
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from ..config import get_settings
from ..models import db
from ..schemas.clip import ClipUpdate
from ..services.ingest import ALLOWED_EXT
from ..workers import pipeline

router = APIRouter(prefix="/api")

@router.get("/settings")
def get_settings_endpoint():
    return db.get_db_settings().model_dump()

@router.put("/settings")
def update_settings_endpoint(body: dict):
    return db.save_db_settings(body).model_dump()


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
    elapsed = round(end - p["started_at"], 1) if p["started_at"] else 0
    p["elapsed"] = elapsed
    progress = p.get("progress") or 0.0
    if p.get("status") == "processing" and progress > 5.0 and elapsed > 0:
        total_est = elapsed / (progress / 100.0)
        p["eta"] = round(max(0.0, total_est - elapsed), 1)
    else:
        p["eta"] = None
    p.pop("source_path", None)
    p.pop("transcript_path", None)
    return p

@router.post("/jobs", status_code=202)
async def create_job(url: str | None = Form(None), file: UploadFile | None = File(None)):
    s = get_settings()
    if bool(url) == bool(file):
        raise HTTPException(400, "Provide either a video URL or an uploaded file")

    if file:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"Unsupported file type '{ext}'")
        (s.storage / "uploads").mkdir(parents=True, exist_ok=True)
        dest = s.storage / "uploads" / f"{uuid.uuid4().hex}{ext}"
        size = 0
        with open(dest, "wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > s.max_video_size:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, "Video exceeds the maximum allowed size")
                f.write(chunk)
        pid = db.create_project(Path(file.filename).stem[:80], str(dest))
        pipeline.submit(pid, str(dest))
        return {"id": pid, "ids": [pid], "count": 1}

    # URL input: supports multiple newline-separated URLs
    raw_lines = [line.strip() for line in (url or "").splitlines() if line.strip() and not line.strip().startswith("#")]
    if not raw_lines:
        raise HTTPException(400, "Invalid URL input")

    created_ids = []
    for line in raw_lines:
        if not line.startswith(("http://", "https://")):
            raise HTTPException(400, f"Invalid URL: {line}")
        pid = db.create_project(line[:80], line)
        pipeline.submit(pid, line)
        created_ids.append(pid)

    return {"id": created_ids[0], "ids": created_ids, "count": len(created_ids)}

@router.post("/jobs/{pid}/retry", status_code=200)
def retry_job(pid: str):
    _proj(pid)
    db.update_project(pid, status="queued", error=None, started_at=None, finished_at=None)
    pipeline.submit(pid)
    return {"status": "queued", "id": pid}

@router.post("/jobs/{pid}/cancel", status_code=200)
def cancel_job(pid: str):
    _proj(pid)
    db.update_project(pid, status="cancelled", stage="cancelled", finished_at=time.time())
    return {"status": "cancelled", "id": pid}

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
    needs_rerender = any(k in changes for k in ("start", "end", "caption_style", "aspect"))
    if changes:
        if needs_rerender:
            changes["render_status"] = "stale"
        db.update_clip(cid, **changes)
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

@router.get("/projects/{pid}/export")
def export_project_clips(pid: str):
    p = _proj(pid)
    clips = db.q("SELECT * FROM clips WHERE project_id=? AND render_status='ready'", (pid,))
    if not clips:
        raise HTTPException(404, "No rendered clips available to export")

    s = get_settings()
    (s.storage / "uploads").mkdir(parents=True, exist_ok=True)
    zip_path = s.storage / "uploads" / f"{pid}_export.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerow(["filename", "title", "description", "tags"])

        for c in clips:
            rendered_path = Path(c.get("rendered_path") or (s.storage / "rendered" / f"{c['id']}.mp4"))
            if rendered_path.is_file():
                safe_title = "".join(ch for ch in c["title"] if ch.isalnum() or ch in " -_")[:50].strip() or "clip"
                arcname = f"{safe_title}_{c['id']}.mp4"
                zf.write(rendered_path, arcname=arcname)
                csv_writer.writerow([arcname, c.get("title", ""), c.get("description", ""), c.get("tags", "")])

        zf.writestr("metadata.csv", csv_buffer.getvalue())

    safe_proj = "".join(ch for ch in p["name"] if ch.isalnum() or ch in " -_")[:40].strip() or "project"
    return FileResponse(zip_path, media_type="application/zip", filename=f"{safe_proj}_clips.zip")

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
