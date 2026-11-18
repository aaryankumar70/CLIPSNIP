"""Persistent single-worker queue with stage caching and restart resumption."""
import gc
import json
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..config import calculate_clip_count, get_settings
from ..models import db
from ..providers.ai import AIError, detect_clips_windowed, generate_clip_metadata, get_provider
from ..services import ffmpeg_service as ff
from ..services.captions import CaptionConfig, build_ass
from ..services.ingest import DirectUrlSource, IngestError, LocalFileSource, YouTubeSource, is_youtube_url
from ..services.transcript import TranscriptionError, get_transcript

# Pool for rerender requests or worker dispatch
pool = ThreadPoolExecutor(max_workers=1)

_worker_thread: threading.Thread | None = None
_wake_event = threading.Event()
_running = True

STAGES = [
    ("ingesting", 10),
    ("transcribing", 35),
    ("analyzing", 55),
    ("metadata", 65),
    ("clips", 90),
    ("done", 100),
]

def _stage(pid: str, name: str, pct: float):
    db.update_project(pid, status="processing", stage=name, progress=pct)

def _is_cancelled(pid: str) -> bool:
    p = db.q("SELECT status FROM projects WHERE id=?", (pid,), one=True)
    return bool(p and p["status"] == "cancelled")

def render_clip(clip: dict, proj: dict, words: list[dict]) -> tuple[Path, Path]:
    s = get_settings()
    src = Path(proj["source_path"])
    info = ff.probe(src)
    db_s = db.get_db_settings()

    res = getattr(db_s, "output_resolution", "720x1280") or "720x1280"
    layout = getattr(db_s, "layout", "blur_fit") or "blur_fit"
    tw, th = ff.get_dimensions(clip["aspect"], resolution=res)

    out = s.storage / "rendered" / f"{clip['id']}.mp4"
    thumb = s.storage / "thumbnails" / f"{clip['id']}.jpg"

    # Trim leading silence / filler words (max 1.5s)
    effective_start = ff.trim_clip_start(clip["start"], clip["end"], words)

    ass = None
    if clip.get("caption_style") != "off":
        ass = s.storage / "rendered" / f"{clip['id']}.ass"
        ass.write_text(
            build_ass(
                words=words,
                clip_start=effective_start,
                clip_end=clip["end"],
                width=tw,
                height=th,
                cfg=CaptionConfig(
                    style=clip.get("caption_style", "highlight"),
                    hook_title=clip.get("title"),
                ),
            ),
            encoding="utf-8",
        )

    try:
        ff.cut_clip(
            src=src,
            out=out,
            start=effective_start,
            end=clip["end"],
            info=info,
            aspect=clip.get("aspect", "9:16"),
            layout=layout,
            resolution=res,
            ass=ass,
        )
    finally:
        if ass:
            ass.unlink(missing_ok=True)

    ff.thumbnail(out, thumb, min(1.0, (clip["end"] - effective_start) / 2))
    return out, thumb

def process_project(pid: str):
    """Execute pipeline for a project with resume support at each stage."""
    s = get_settings()
    proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not proj or proj["status"] in ("completed", "cancelled"):
        return

    if not proj.get("started_at"):
        db.update_project(pid, started_at=time.time())

    provider = get_provider(s.ai_provider)

    try:
        source = proj["source_path"] or ""

        # ---------------- Stage 1: Ingest ----------------
        if _is_cancelled(pid):
            return
        _stage(pid, "ingesting", 10)

        # Check if source already exists locally (from previous interrupted run)
        local_src = Path(source)
        if local_src.is_file() and local_src.parent in (s.storage / "uploads", Path("/tmp")):
            path = local_src
        else:
            if is_youtube_url(source):
                src = YouTubeSource(
                    source,
                    project_id=pid,
                    progress_hook=lambda pct, msg: db.update_project(
                        pid, progress=5 + int(pct * 0.1), stage=f"ingesting: {msg}"
                    ),
                )
            elif source.startswith("http"):
                src = DirectUrlSource(source)
            else:
                src = LocalFileSource(Path(source))

            path = (
                Path(source)
                if not source.startswith("http") and Path(source).parent == s.storage / "uploads"
                else src.fetch(s.storage / "uploads")
            )

        info = ff.probe(path)
        db.update_project(
            pid,
            source_path=str(path),
            duration=info.duration,
            width=info.width,
            height=info.height,
        )

        if not info.has_audio:
            raise ff.FFmpegError("Video has no audio track to transcribe")

        # ---------------- Stage 2: Transcription ----------------
        if _is_cancelled(pid):
            return
        _stage(pid, "transcribing", 30)

        tpath = s.storage / "transcripts" / f"{pid}.json"
        sentences_file = s.storage / "transcripts" / f"{pid}.sentences.json"

        # Check if already transcribed in a previous run
        if tpath.is_file() and sentences_file.is_file():
            data = json.loads(tpath.read_text(encoding="utf-8"))
            sentences = json.loads(sentences_file.read_text(encoding="utf-8"))
        else:
            proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
            data = get_transcript(proj)
            sentences = (
                json.loads(sentences_file.read_text(encoding="utf-8"))
                if sentences_file.is_file()
                else []
            )

        # ---------------- Stage 3: Candidate Detection & Selection ----------------
        if _is_cancelled(pid):
            return
        _stage(pid, "analyzing", 50)

        db_settings = db.get_db_settings()
        existing_clips = db.q("SELECT * FROM clips WHERE project_id=?", (pid,))

        if not existing_clips:
            wav_path = s.storage / "audio" / f"{pid}.wav"
            if not wav_path.is_file():
                ff.extract_audio(path, wav_path)

            target_n = calculate_clip_count(info.duration, override_max=db_settings.max_clips)
            cands = detect_clips_windowed(
                provider=provider,
                sentences=sentences,
                duration=info.duration,
                target_count=target_n,
                wav_path=wav_path,
                min_clip_s=db_settings.clip_min_s,
                max_clip_s=db_settings.clip_max_s,
            )

            # Insert candidates into DB
            for c in cands:
                cid = db.new_id()
                db.q(
                    "INSERT INTO clips(id,project_id,start,end,title,hook,reason,score,category,caption_style,aspect,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        cid,
                        pid,
                        c["start"],
                        c["end"],
                        c["title"],
                        c.get("hook_reason", ""),
                        c.get("hook_reason", ""),
                        c.get("final_score", 80.0),
                        "gaming",
                        db_settings.caption_style,
                        "9:16",
                        time.time(),
                    ),
                )
            wav_path.unlink(missing_ok=True)
            existing_clips = db.q("SELECT * FROM clips WHERE project_id=?", (pid,))

        # ---------------- Stage 4: Metadata Generation ----------------
        if _is_cancelled(pid):
            return
        _stage(pid, "metadata", 65)

        proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        s_map = {s["i"]: s.get("text", "") for s in sentences}

        for c in existing_clips:
            if not c.get("description") or not c.get("tags"):
                # Generate missing metadata
                clip_text = c.get("title", "")
                meta = generate_clip_metadata(
                    provider=provider,
                    clip_text=clip_text,
                    source_title=proj.get("source_title") or proj.get("name") or "",
                    channel_name=proj.get("channel_name") or "",
                    video_url=proj.get("video_url") or "",
                    default_tags=db_settings.default_tags,
                    default_hashtags=db_settings.default_hashtags,
                    footer_template=db_settings.footer_template,
                )
                db.update_clip(
                    c["id"],
                    title=meta["title"],
                    description=meta["description"],
                    tags=meta["tags"],
                )

        # Free AI model before rendering
        provider.unload()
        gc.collect()

        # ---------------- Stage 5: Render Clips ----------------
        if _is_cancelled(pid):
            return

        words = [w for g in data.get("segments", []) for w in g.get("words", [])]
        all_clips = db.q("SELECT * FROM clips WHERE project_id=?", (pid,))
        total_clips = len(all_clips)

        for i, clip in enumerate(all_clips):
            if _is_cancelled(pid):
                return

            _stage(pid, "clips", 70 + int(28 * i / max(1, total_clips)))

            # Resume: check if clip is already rendered and file exists
            rendered_file = (
                Path(clip["rendered_path"])
                if clip.get("rendered_path")
                else (s.storage / "rendered" / f"{clip['id']}.mp4")
            )
            if clip.get("render_status") == "ready" and rendered_file.is_file():
                continue

            try:
                db.update_clip(clip["id"], render_status="rendering")
                out, th = render_clip(clip, proj, words)
                db.update_clip(
                    clip["id"],
                    rendered_path=str(out),
                    thumb_path=str(th),
                    render_status="ready",
                    render_error=None,
                )
            except Exception as e:
                db.update_clip(clip["id"], render_status="failed", render_error=str(e))

        # ---------------- Stage 6: Finalize & Cleanup ----------------
        if _is_cancelled(pid):
            return

        # Optional setting: delete source video after successful render
        if db_settings.delete_source_after_render:
            source_file = Path(proj["source_path"])
            if source_file.is_file() and source_file.parent == s.storage / "uploads":
                source_file.unlink(missing_ok=True)

        db.update_project(
            pid,
            status="completed",
            stage="done",
            progress=100,
            finished_at=time.time(),
        )

    except (IngestError, ff.FFmpegError, TranscriptionError, AIError) as e:
        db.update_project(
            pid,
            status="failed",
            error=f"{type(e).__name__.replace('Error', '')} failed: {e}",
            finished_at=time.time(),
        )
    except Exception as e:
        traceback.print_exc()
        db.update_project(
            pid,
            status="failed",
            error=f"Unexpected error: {e}",
            finished_at=time.time(),
        )
    finally:
        # Guarantee unloading AI model and freeing memory on 8 GB RAM laptop
        try:
            provider.unload()
        except Exception:
            pass
        gc.collect()

def _queue_worker_loop():
    """Background persistent queue processor: runs jobs sequentially."""
    global _running
    while _running:
        job = db.q("SELECT id FROM projects WHERE status = 'queued' ORDER BY created_at ASC", one=True)
        if job:
            process_project(job["id"])
        else:
            _wake_event.wait(timeout=2.0)
            _wake_event.clear()

def start_worker():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_queue_worker_loop, daemon=True)
        _worker_thread.start()

def submit(pid: str, source: str | None = None):
    """Enqueue a job and wake the worker."""
    start_worker()
    _wake_event.set()

def run_job(pid: str, source: str):
    """Direct runner for backwards compatibility / testing."""
    process_project(pid)

def rerender(cid: str):
    """Re-render one clip after parameter adjustments."""
    clip = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)
    if not clip:
        return
    try:
        proj = db.q("SELECT * FROM projects WHERE id=?", (clip["project_id"],), one=True)
        data = json.loads(Path(proj["transcript_path"]).read_text(encoding="utf-8"))
        words = [w for g in data.get("segments", []) for w in g.get("words", [])]
        out, th = render_clip(clip, proj, words)
        db.update_clip(cid, rendered_path=str(out), thumb_path=str(th), render_status="ready", render_error=None)
    except Exception as e:
        db.update_clip(cid, render_status="failed", render_error=f"Render failed: {e}")
