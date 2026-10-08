import json, shutil, time, traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from ..config import get_settings
from ..models import db
from ..providers.ai import get_provider, detect_clips, AIError
from ..services import ffmpeg_service as ff
from ..services.captions import CaptionConfig, build_ass
from ..services.ingest import IngestError, LocalFileSource, DirectUrlSource
from ..services.transcribe import transcribe, TranscriptionError

pool = ThreadPoolExecutor(max_workers=1)  # one heavy job at a time (CPU/GPU bound)
STAGES = [("ingesting", 5), ("audio", 15), ("transcribing", 45), ("analyzing", 60), ("clips", 85), ("done", 100)]

def submit(pid: str, source: str):
    pool.submit(run_job, pid, source)

def _stage(pid, name, pct): db.update_project(pid, status="processing", stage=name, progress=pct)

def render_clip(clip: dict, proj: dict, words: list[dict]) -> tuple[Path, Path]:
    s = get_settings()
    src = Path(proj["source_path"]); info = ff.probe(src)
    out = s.storage / "rendered" / f"{clip['id']}.mp4"; thumb = s.storage / "thumbnails" / f"{clip['id']}.jpg"
    ass = None
    if clip["caption_style"] != "off":
        tw, th = ff.FORMATS[clip["aspect"]]
        ass = s.storage / "rendered" / f"{clip['id']}.ass"
        ass.write_text(build_ass(words, clip["start"], clip["end"], tw, th, CaptionConfig(style=clip["caption_style"])), encoding="utf-8")
    ff.cut_clip(src, out, clip["start"], clip["end"], info, clip["aspect"], ass)
    if ass: ass.unlink(missing_ok=True)
    ff.thumbnail(out, thumb, min(1.0, (clip["end"] - clip["start"]) / 2))
    return out, thumb

def run_job(pid: str, source: str):
    s = get_settings(); db.update_project(pid, started_at=time.time())
    try:
        _stage(pid, "ingesting", 5)
        src = DirectUrlSource(source) if source.startswith("http") else LocalFileSource(Path(source))
        path = Path(source) if not source.startswith("http") and Path(source).parent == s.storage / "uploads" else src.fetch(s.storage / "uploads")
        info = ff.probe(path)
        db.update_project(pid, source_path=str(path), duration=info.duration, width=info.width, height=info.height)
        if not info.has_audio: raise ff.FFmpegError("Video has no audio track to transcribe")
        _stage(pid, "audio", 15)
        wav = ff.extract_audio(path, s.storage / "audio" / f"{pid}.wav")
        _stage(pid, "transcribing", 30)
        tpath = s.storage / "transcripts" / f"{pid}.json"
        data = transcribe(wav, tpath); db.update_project(pid, transcript_path=str(tpath))
        wav.unlink(missing_ok=True)
        _stage(pid, "analyzing", 60)
        cands = detect_clips(get_provider(s.ai_provider), data["segments"], info.duration)
        words = [w for g in data["segments"] for w in g["words"]]
        proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        for i, c in enumerate(cands):
            _stage(pid, "clips", 65 + int(25 * i / len(cands)))
            cid = db.new_id()
            db.q("INSERT INTO clips(id,project_id,start,end,title,hook,reason,score,category,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (cid, pid, c.start, c.end, c.title, c.hook, c.reason, c.score, c.category, time.time()))
            clip = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)
            try:
                out, th = render_clip(clip, proj, words)
                db.update_clip(cid, rendered_path=str(out), thumb_path=str(th), render_status="ready")
            except Exception as e:
                db.update_clip(cid, render_status="failed", render_error=str(e))
        db.update_project(pid, status="completed", stage="done", progress=100, finished_at=time.time())
    except (IngestError, ff.FFmpegError, TranscriptionError, AIError) as e:
        db.update_project(pid, status="failed", error=f"{type(e).__name__.replace('Error', '')} failed: {e}", finished_at=time.time())
    except Exception as e:
        traceback.print_exc()
        db.update_project(pid, status="failed", error=f"Unexpected error: {e}", finished_at=time.time())

def rerender(cid: str):
    """Re-render one clip after the user changed boundaries/style/aspect."""
    clip = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)
    try:
        proj = db.q("SELECT * FROM projects WHERE id=?", (clip["project_id"],), one=True)
        data = json.loads(Path(proj["transcript_path"]).read_text(encoding="utf-8"))
        words = [w for g in data["segments"] for w in g["words"]]
        out, th = render_clip(clip, proj, words)
        db.update_clip(cid, rendered_path=str(out), thumb_path=str(th), render_status="ready", render_error=None)
    except Exception as e:
        db.update_clip(cid, render_status="failed", render_error=f"Render failed: {e}")
