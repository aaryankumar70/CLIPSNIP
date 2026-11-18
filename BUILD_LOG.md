# BUILD_LOG.md

## Step 0: Bootstrap & Initial Analysis

### Architecture Found
- **Backend:** FastAPI application (`backend/app/main.py`) with:
  - `api/routes.py`: Endpoints for jobs, clips, media serving, and project management.
  - `workers/pipeline.py`: In-process ThreadPoolExecutor running pipeline stages: ingest -> audio extraction -> Whisper transcription -> LLM clip detection -> rendering & thumbnails.
  - `models/db.py`: SQLite repository storing `projects` and `clips` tables.
  - `services/`: `ffmpeg_service.py` (video cutting, probing, audio extraction, thumbnailing), `captions.py` (word-synced ASS subtitle builder), `ingest.py` (local files and direct URL downloading), `transcribe.py` (faster-whisper wrapper).
  - `providers/ai.py`: Cloud LLM completion abstractions (OpenAI, Anthropic) and clip parsing/ranking.
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS with Lucide icons (`frontend/src/`):
  - `pages/Home.tsx`: Dashboard with URL input / file upload and project list.
  - `pages/Project.tsx`: Project view with status tracking, clip cards, and transcript viewer.
  - `components/Editor.tsx`: Modal for editing clip start/end boundaries, caption style, and aspect ratio.

### Bugs & Architectural Limitations Identified
1. **Overlap removal before sorting by score**: `parse_candidates()` in `providers/ai.py` filtered overlaps in the order items appeared from LLM output, potentially discarding higher-scoring clips that overlapped with earlier, lower-scoring items.
2. **Floats from LLM without sentence boundary snapping**: LLM provided start/end floating timestamps directly, leading to awkward mid-word or mid-sentence cuts.
3. **Single monolithic LLM prompt**: Entire transcript was concatenated into one prompt, which fails or degrades on long videos and small local LLMs.
4. **Reframing limited to center crop**: Only center-cropped to 9:16/1:1 without background blur option (`blur_fit`), which cuts off critical visual information from 16:9 videos.
5. **Captions positioned too low**: Bottom margin was 12% of height, which gets obscured by YouTube Shorts and Reels UI elements (likes, comments, share, description overlay).
6. **DirectUrlSource rejects YouTube URLs**: Direct URL ingest strictly validated file extensions (`.mp4`, `.mov`, etc.), failing on standard YouTube or youtu.be links.
7. **Cloud AI dependency**: Default providers required paid OpenAI or Anthropic API keys rather than local Ollama models.
8. **Transient / in-memory job handling**: Restarting the backend immediately marked incomplete jobs as failed, lacking stage caching and persistent resume capabilities.

### Environment & Bootstrap Actions
- Initialized Python 3.12 virtual environment (`.venv`) using `uv`.
- Configured `.gitignore` to prevent tracking of secrets, storage, builds, and virtual environments.
- Recorded missing system tools (`ollama`, `deno`) into `HUMAN_TODO.md`.
- Completed `npm install` for frontend.

## Step 1: Settings and Local AI

### Changes Made
- Centralized configuration constants in `backend/app/config.py`: `MIN_CLIP_S=60`, `MAX_CLIP_S=120`, `IDEAL_CLIP_MIN_S=75`, `IDEAL_CLIP_MAX_S=100`, clip count calculation `clamp(floor(video_minutes / 2.5), 3, 15)`, `WINDOW_S=300`, `WINDOW_OVERLAP_S=30`, `MAX_WINDOWS=12`, `WHISPER_MODEL=base.en`, `OLLAMA_MODEL=qwen2.5:3b-instruct`, `OLLAMA_NUM_CTX=4096`.
- Added Pydantic schema in `backend/app/schemas/settings.py` for user settings (layout, clip lengths, max clips, resolution, caption style, default tags, upload privacy, etc.) ignoring unknown keys.
- Added persistent `settings` key/value table in SQLite (`backend/app/models/db.py`) and implemented `GET /api/settings` and `PUT /api/settings` routes.
- Added `OllamaProvider` to `backend/app/providers/ai.py` with temperature 0.2, configurable `num_ctx`, structured output support, `keep_alive="10m"` during jobs and `unload()` (`keep_alive=0`). Made `ollama` default provider and removed API key requirements from the default path.
- Added friendly error messages if Ollama is not running (`sudo systemctl enable --now ollama`) or if model is missing (`ollama pull <model>`).
- Resolved the overlap filtering bug in candidate parsing: candidates are sorted by score descending before greedy non-overlapping selection.
- Added tests in `backend/tests/test_settings_ollama.py`.

### How to Try It
- Run tests: `.venv/bin/pytest backend/tests/test_settings_ollama.py`
- Query settings: `curl http://localhost:8000/api/settings`
- Update settings: `curl -X PUT http://localhost:8000/api/settings -H "Content-Type: application/json" -d '{"layout":"blur_fit","max_clips":10}'`

### Assumptions
- Ollama endpoint defaults to `http://localhost:11434` with model `qwen2.5:3b-instruct`.
- Cloud providers (OpenAI, Anthropic) remain available as optional configurations if API keys are provided.

## Step 2: YouTube Links, Captions, and Transcript Processing

### Changes Made
- Added `YouTubeSource` in `backend/app/services/ingest.py` powered by `yt-dlp`:
  - Detects YouTube URLs (standard, shortened `youtu.be`, and shorts).
  - Enforces maximum duration check (default 3 hours) and available disk space check (> 2 GB).
  - Fetches auto-captions and manual subtitles in `json3` format during the video download pass.
  - Formats quality up to 720p/1080p from user settings merged into MP4 container.
  - Automatically moves subtitles to `storage/transcripts/<id>.captions.json`.
  - Maps common YouTube errors (private, deleted, age-restricted, live streams, geo-blocks) into clear human-readable messages.
  - Preserves source metadata on project rows: `source_title`, `channel_name`, `channel_url`, `video_url`, `duration`, `upload_date`.
- Created `backend/app/services/transcript.py`:
  - `parse_json3_captions`: Parses YouTube `json3` subtitles, performs rolling-caption deduplication, estimates missing word offsets, and structures word-level timestamps.
  - `transcribe_with_whisper`: Faster-whisper fallback with int8 quantization on CPU (`base.en` or `base`), freeing memory immediately after transcription.
  - `build_sentences`: Splits transcript into numbered sentences on punctuation or pauses > 0.7s, merging fragments with fewer than 3 words.
  - Transcripts with under 50 words per 5 minutes are rejected.
  - Saves both `storage/transcripts/<id>.json` and `storage/transcripts/<id>.sentences.json`.
- Integrated `YouTubeSource` and `get_transcript` into `backend/app/workers/pipeline.py`.
- Added test suite `backend/tests/test_step2_ingest_transcript.py`.

### How to Try It
- Run tests: `.venv/bin/pytest backend/tests/test_step2_ingest_transcript.py`
- Ingest a YouTube URL via API: `curl -X POST http://localhost:8000/api/jobs -F "url=https://www.youtube.com/watch?v=..."`

### Assumptions
- Deno is used automatically by yt-dlp when installed for JavaScript extraction.
- Auto-captions in json3 format are preferred for speed and CPU resource conservation over full Whisper inference.
- `TEST_VIDEO_URL` in `CLIPPER_BUILD_PLAN.md` was not set, so tests ran against synthetic/mocked data.
