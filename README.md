# Clipper — AI video clipping studio (personal use)

Upload a video you own or are authorized to process; Clipper transcribes it (faster-whisper), asks an LLM for the best
self-contained moments, cuts them with FFmpeg, burns in word-synced captions, and lets you preview, trim, re-style and download MP4s.

## Features
- Real job pipeline with live progress: ingest → audio → transcription → AI analysis → clips → captions → render
- Word-level captions in 5 styles (classic, bold, highlight, creator, minimal) or off, rendered as ASS via FFmpeg
- Formats: 9:16, 1:1, 16:9. **Reframing is a center crop only; subject tracking is not implemented.**
- AI Clip Score (0–100) = the model's estimate of content quality, **not** a virality prediction
- Clip editor (start/end/title/caption style/aspect), transcript viewer with click-to-seek, delete project (removes all files)
- LLM output is validated with Pydantic (ranges, score, length 15–90s, no overlaps) and retried on failure
- Provider-agnostic AI layer (OpenAI, Anthropic). Everything is stored locally.

## Architecture
`frontend/` React+Vite+TS+Tailwind · `backend/app/` FastAPI (`api/` routes, `services/` ffmpeg/captions/ingest/transcribe,
`providers/` AI, `workers/` pipeline, `models/` SQLite) · `storage/` uploads, audio, transcripts, rendered, thumbnails.
Jobs run one at a time on a background thread; the UI polls `/api/jobs/{id}`.

## Requirements
Python 3.10+, Node 18+, FFmpeg (with libass, included in standard builds), an OpenAI or Anthropic API key.

## Installation (Windows)
1. **FFmpeg:** `winget install Gyan.FFmpeg` (or download from ffmpeg.org and add `bin` to PATH). Check: `ffmpeg -version`.
2. **Backend:**
   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy ..\.env.example ..\.env   # then edit .env: set the API key
   ```
3. **Frontend:** `cd frontend && npm install`

Linux/macOS: same steps with `source .venv/bin/activate`, `cp`, and `sudo apt install ffmpeg` (or `brew install ffmpeg`).

## Environment variables (`.env` in project root)
`AI_PROVIDER` (openai|anthropic), `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `WHISPER_MODEL` (tiny…large-v3; `small` is a good CPU default),
`WHISPER_DEVICE` (auto|cpu|cuda), `FFMPEG_PATH`, `FFPROBE_PATH`, `STORAGE_PATH`, `MAX_VIDEO_SIZE` (bytes). Optional: `OPENAI_MODEL`, `ANTHROPIC_MODEL`.
Never commit `.env`. Load it before starting the backend: in PowerShell run `Get-Content ..\.env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1].Trim(), ($matches[2] -replace '\s+#.*$','').Trim()) } }`, or use `uvicorn ... --env-file ../.env`.

## Running
```powershell
# terminal 1
cd backend; uvicorn app.main:app --reload --env-file ../.env
# terminal 2
cd frontend; npm run dev        # open http://localhost:5173
```
Or `docker compose up --build` (CPU only).

## Tests
```powershell
cd backend
python tests\test_media.py   # FFmpeg/captions/ingest (needs only FFmpeg)
pytest                                  # everything incl. AI validation and API (needs requirements.txt)
python ..\scripts\make_sample.py        # makes storage/sample.mp4 (20s) for manual end-to-end runs
```

## Troubleshooting
- *"ffmpeg not found"*: set `FFMPEG_PATH` to the full path of ffmpeg.exe.
- *"Whisper model could not be loaded"*: first run downloads the model (needs internet); try `WHISPER_MODEL=base`.
- *"AI_PROVIDER key not set"*: check `.env` and that it was loaded into the backend's environment.
- *Captions missing*: ensure your FFmpeg build has `libass` (`ffmpeg -filters | findstr subtitles`).
- A sample test video has no speech, so full pipeline runs need a video with real talking.
- Jobs interrupted by a server restart are marked failed; re-upload to retry.

## Production considerations
Single-user, no auth. Before exposing it: add authentication, restrict CORS, use a real queue (RQ/Celery) and PostgreSQL,
put storage behind S3/R2 (the paths are centralized in `config.py`), and add rate limits and cleanup of old projects.
