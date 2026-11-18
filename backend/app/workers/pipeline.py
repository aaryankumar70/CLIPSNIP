import json, shutil, time, traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from ..config import get_settings, calculate_clip_count
from ..models import db
from ..providers.ai import get_provider, detect_clips_windowed, generate_clip_metadata, AIError
from ..services import ffmpeg_service as ff
from ..services.captions import CaptionConfig, build_ass
from ..services.ingest import IngestError, LocalFileSource, DirectUrlSource, YouTubeSource, is_youtube_url
from ..services.transcript import get_transcript, TranscriptionError

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
        if is_youtube_url(source):
            src = YouTubeSource(source, project_id=pid, progress_hook=lambda pct, msg: db.update_project(pid, progress=5 + int(pct * 0.1), stage=f"ingesting: {msg}"))
        elif source.startswith("http"):
            src = DirectUrlSource(source)
        else:
            src = LocalFileSource(Path(source))

        path = Path(source) if not source.startswith("http") and Path(source).parent == s.storage / "uploads" else src.fetch(s.storage / "uploads")
        info = ff.probe(path)
        db.update_project(pid, source_path=str(path), duration=info.duration, width=info.width, height=info.height)
        if not info.has_audio:
            raise ff.FFmpegError("Video has no audio track to transcribe")

        _stage(pid, "transcribing", 25)
        proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        data = get_transcript(proj)

        _stage(pid, "analyzing", 50)
        sentences_file = s.storage / "transcripts" / f"{pid}.sentences.json"
        sentences = json.loads(sentences_file.read_text(encoding="utf-8")) if sentences_file.is_file() else []

        db_settings = db.get_db_settings()
        target_n = calculate_clip_count(info.duration, override_max=db_settings.max_clips)
        provider = get_provider(s.ai_provider)

        wav_path = s.storage / "audio" / f"{pid}.wav"
        if not wav_path.is_file():
            ff.extract_audio(path, wav_path)

        cands = detect_clips_windowed(
            provider=provider,
            sentences=sentences,
            duration=info.duration,
            target_count=target_n,
            wav_path=wav_path,
            min_clip_s=db_settings.clip_min_s,
            max_clip_s=db_settings.clip_max_s,
        )

        words = [w for g in data.get("segments", []) for w in g.get("words", [])]
        proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)

        _stage(pid, "metadata", 65)
        clips_to_render = []
        for i, c in enumerate(cands):
            meta = generate_clip_metadata(
                provider=provider,
                clip_text=c.get("text", c["title"]),
                source_title=proj.get("source_title") or proj.get("name") or "",
                channel_name=proj.get("channel_name") or "",
                video_url=proj.get("video_url") or "",
                default_tags=db_settings.default_tags,
                default_hashtags=db_settings.default_hashtags,
                footer_template=db_settings.footer_template,
            )
            cid = db.new_id()
            db.q(
                "INSERT INTO clips(id,project_id,start,end,title,hook,reason,score,category,caption_style,aspect,description,tags,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    pid,
                    c["start"],
                    c["end"],
                    meta["title"],
                    c.get("hook_reason", ""),
                    c.get("hook_reason", ""),
                    c["final_score"],
                    "gaming",
                    db_settings.caption_style,
                    "9:16",
                    meta["description"],
                    meta["tags"],
                    time.time(),
                ),
            )
            clips_to_render.append(cid)

        # Free LLM and audio wav before heavy FFmpeg rendering (respect 8 GB RAM rule)
        provider.unload()
        wav_path.unlink(missing_ok=True)

        for i, cid in enumerate(clips_to_render):
            _stage(pid, "clips", 70 + int(28 * i / max(1, len(clips_to_render))))
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
