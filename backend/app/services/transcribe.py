import json
from pathlib import Path
from ..config import get_settings

class TranscriptionError(RuntimeError):
    pass

_model = None

def transcribe(wav: Path, out_json: Path) -> dict:
    global _model
    s = get_settings()
    try:
        from faster_whisper import WhisperModel
        if _model is None:
            dev = s.whisper_device
            if dev == "auto":
                try:
                    import ctranslate2
                    dev = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                except Exception: dev = "cpu"
            _model = WhisperModel(s.whisper_model, device=dev, compute_type="float16" if dev == "cuda" else "int8")
    except Exception as e:
        raise TranscriptionError(f"The selected Whisper model could not be loaded: {e}")
    try:
        segs, info = _model.transcribe(str(wav), word_timestamps=True, vad_filter=True)
        data = {"language": info.language, "segments": [
            {"start": round(g.start, 2), "end": round(g.end, 2), "text": g.text.strip(),
             "words": [{"word": w.word, "start": round(w.start, 2), "end": round(w.end, 2)} for w in (g.words or [])]}
            for g in segs]}
    except Exception as e:
        raise TranscriptionError(f"Transcription failed: {e}")
    if not data["segments"]:
        raise TranscriptionError("No speech detected in this video")
    out_json.write_text(json.dumps(data), encoding="utf-8")
    return data
