"""Compatibility wrapper delegating to transcript.py."""
import json
from pathlib import Path
from .transcript import transcribe_with_whisper, TranscriptionError

def transcribe(wav: Path, out_json: Path) -> dict:
    data = transcribe_with_whisper(wav)
    if not data["segments"]:
        raise TranscriptionError("No speech detected in this video")
    out_json.write_text(json.dumps(data), encoding="utf-8")
    return data
