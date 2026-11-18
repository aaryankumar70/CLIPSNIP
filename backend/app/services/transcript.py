"""Transcript processing: json3 YouTube captions with faster-whisper fallback."""
import gc
import json
import re
from pathlib import Path
from typing import Any
from ..config import get_settings
from ..models import db

class TranscriptionError(RuntimeError):
    pass

def _clean_word(w: str) -> str:
    return re.sub(r"[^\w]", "", w).lower()

def parse_json3_captions(json3_path: Path) -> dict[str, Any]:
    """Parse YouTube json3 format into standardized segments and words."""
    try:
        raw = json.loads(json3_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise TranscriptionError(f"Failed to read json3 captions: {e}") from e

    events = raw.get("events", [])
    if not events:
        raise TranscriptionError("json3 caption file contains no events")

    all_words: list[dict[str, Any]] = []

    for ev in events:
        t_start_ms = ev.get("tStartMs", 0)
        d_dur_ms = ev.get("dDurationMs", 0)
        segs = ev.get("segs", [])
        if not segs:
            continue

        valid_segs = []
        for s in segs:
            text = s.get("utf8", "").replace("\n", " ").strip()
            if text:
                valid_segs.append((text, s.get("tOffsetMs")))

        if not valid_segs:
            continue

        seg_count = len(valid_segs)
        dur_s = max(0.2, d_dur_ms / 1000.0)

        for idx, (word_text, offset_ms) in enumerate(valid_segs):
            if offset_ms is not None:
                w_start = (t_start_ms + offset_ms) / 1000.0
            else:
                w_start = (t_start_ms / 1000.0) + (idx / seg_count) * dur_s

            if idx + 1 < seg_count and valid_segs[idx + 1][1] is not None:
                w_end = (t_start_ms + valid_segs[idx + 1][1]) / 1000.0
            else:
                w_end = w_start + (dur_s / seg_count)

            w_start = round(max(0.0, w_start), 2)
            w_end = round(max(w_start + 0.05, w_end), 2)

            cleaned = _clean_word(word_text)
            if not cleaned:
                continue

            # Rolling caption deduplication:
            # Check recent words (within last 4 seconds)
            is_dup = False
            for recent in reversed(all_words[-15:]):
                if abs(recent["start"] - w_start) < 1.2 and _clean_word(recent["word"]) == cleaned:
                    is_dup = True
                    break

            if is_dup:
                continue

            all_words.append({"word": word_text, "start": w_start, "end": w_end})

    if not all_words:
        raise TranscriptionError("No words could be extracted from json3 captions")

    # Group words into segments (breaking on pause > 1.5s or ~12 words)
    segments: list[dict[str, Any]] = []
    cur_seg_words: list[dict[str, Any]] = []

    for w in all_words:
        if cur_seg_words:
            pause = w["start"] - cur_seg_words[-1]["end"]
            if pause > 1.5 or len(cur_seg_words) >= 12 or cur_seg_words[-1]["word"].rstrip().endswith((".", "!", "?")):
                seg_text = " ".join(sw["word"] for sw in cur_seg_words)
                segments.append({
                    "start": cur_seg_words[0]["start"],
                    "end": cur_seg_words[-1]["end"],
                    "text": seg_text,
                    "words": cur_seg_words,
                })
                cur_seg_words = []
        cur_seg_words.append(w)

    if cur_seg_words:
        seg_text = " ".join(sw["word"] for sw in cur_seg_words)
        segments.append({
            "start": cur_seg_words[0]["start"],
            "end": cur_seg_words[-1]["end"],
            "text": seg_text,
            "words": cur_seg_words,
        })

    return {
        "language": "en",
        "source": "youtube_captions",
        "segments": segments,
    }

def build_sentences(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build numbered sentences from word timings, splitting on punctuation or pauses > 0.7s,

    and merging fragments under 3 words.
    """
    if not words:
        return []

    raw_sentences: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for idx, w in enumerate(words):
        current.append(w)
        is_last = idx == len(words) - 1
        ends_punct = bool(re.search(r"[.?!]$", w["word"].strip()))
        pause = (words[idx + 1]["start"] - w["end"]) if not is_last else 0.0

        if is_last or ends_punct or pause > 0.7:
            raw_sentences.append(current)
            current = []

    if current:
        raw_sentences.append(current)

    merged = [s for s in raw_sentences if s]
    if not merged:
        return []

    # Merge fragments with fewer than 3 words
    i = 0
    while i < len(merged) and len(merged) > 1:
        if len(merged[i]) < 3:
            if i > 0:
                merged[i - 1].extend(merged[i])
                merged.pop(i)
            else:
                merged[i + 1] = merged[i] + merged[i + 1]
                merged.pop(i)
        else:
            i += 1

    result: list[dict[str, Any]] = []
    for idx, s_words in enumerate(merged, start=1):
        text = " ".join(w["word"] for w in s_words).strip()
        result.append({
            "i": idx,
            "start": round(s_words[0]["start"], 2),
            "end": round(s_words[-1]["end"], 2),
            "text": text,
            "words": s_words,
        })

    return result

def transcribe_with_whisper(wav_path: Path, language: str = "en") -> dict[str, Any]:
    """Fallback to faster-whisper on CPU with int8 and free model memory immediately."""
    s = get_settings()
    model_name = s.whisper_model
    if language != "en" and model_name.endswith(".en"):
        model_name = model_name.replace(".en", "")

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )
        segs, info = model.transcribe(
            str(wav_path),
            word_timestamps=True,
            vad_filter=True,
            beam_size=1,
            language=language if language != "en" else None,
        )
        data = {
            "language": info.language or language,
            "source": "faster_whisper",
            "segments": [
                {
                    "start": round(g.start, 2),
                    "end": round(g.end, 2),
                    "text": g.text.strip(),
                    "words": [
                        {"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
                        for w in (g.words or [])
                        if w.word.strip()
                    ],
                }
                for g in segs
            ],
        }
    except Exception as e:
        raise TranscriptionError(f"Whisper transcription failed: {e}") from e
    finally:
        # Free model from RAM immediately
        try:
            del model
        except Exception:
            pass
        gc.collect()

    return data

def get_transcript(project: dict[str, Any]) -> dict[str, Any]:
    """Fetch or generate transcript for project: check json3 captions first, fallback to faster-whisper."""
    s = get_settings()
    pid = project["id"]
    duration = float(project.get("duration") or 0.0)
    caption_path = s.storage / "transcripts" / f"{pid}.captions.json"
    transcript_path = s.storage / "transcripts" / f"{pid}.json"
    sentences_path = s.storage / "transcripts" / f"{pid}.sentences.json"

    data = None
    if caption_path.is_file():
        try:
            data = parse_json3_captions(caption_path)
        except Exception:
            data = None

    if not data or not data.get("segments"):
        # Fall back to faster-whisper on extracted WAV
        wav_path = s.storage / "audio" / f"{pid}.wav"
        if not wav_path.is_file():
            from . import ffmpeg_service as ff
            src_path = Path(project["source_path"])
            ff.extract_audio(src_path, wav_path)

        db_settings = db.get_db_settings()
        lang = getattr(db_settings, "caption_language", "en") or "en"
        data = transcribe_with_whisper(wav_path, language=lang)
        wav_path.unlink(missing_ok=True)

    # Collect all words across segments
    all_words = [w for seg in data.get("segments", []) for w in seg.get("words", [])]

    # Validate word count: reject transcripts with under 50 words per 5 minutes
    if duration > 0:
        min_words = max(15, int((duration / 300.0) * 50))
        if len(all_words) < min_words:
            raise TranscriptionError(
                f"Transcript has insufficient speech ({len(all_words)} words for {duration:.0f}s video; minimum required is {min_words} words per 5m)"
            )

    # Build numbered sentences
    sentences = build_sentences(all_words)
    if not sentences:
        raise TranscriptionError("No valid sentences could be constructed from transcript")

    # Persist outputs
    transcript_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    sentences_path.write_text(json.dumps(sentences, indent=2), encoding="utf-8")

    db.update_project(pid, transcript_path=str(transcript_path))
    return data
