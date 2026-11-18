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

## Step 3: Clip Selection and Metadata Generation

### Changes Made
- Implemented windowing in `backend/app/providers/ai.py` (`build_windows`):
  - Slices numbered sentences into 300s (`WINDOW_S`) windows with 30s (`WINDOW_OVERLAP_S`) overlap.
  - Pre-scores windows with heuristic (speech rate, questions, exclamations, sponsor penalties) to select the top 12 windows (`MAX_WINDOWS`).
- Local LLM candidate prompt & schema:
  - Prompts Ollama with sentence indices `[i] text` and receives structured JSON `{start_sentence, end_sentence, title, hook_reason, standalone, score}`.
  - Converts indices to timestamps with exact padding: `start = first_word.start - 0.15s`, `end = last_word.end + 0.4s`.
  - Filters candidates by duration `MIN_CLIP_S` (60s) to `MAX_CLIP_S` (120s).
- Implemented `select_clips()`:
  - Calculates composite final score: `0.5*llm + 0.2*audio_energy + 0.15*hook + 0.15*standalone - penalties` (duration outside 75-100s, filler starts, silence > 25%).
  - Audio energy evaluated via RMS on 16kHz mono WAV using numpy and wave.
  - Hook text features extracted from the first 3 seconds / first sentence.
  - Sorts by final score descending first, resolving the earlier overlap bug.
  - Enforces minimum 10s gap between clips and limits first-third of video to at most 40% of clips.
- Implemented `generate_clip_metadata()`:
  - Generates curiosity-driven title (max 90 chars), 3-line description, and 8 tags (under 500 chars, no `<` or `>`).
  - Appends settings footer template (`Clipped from {source_title} by {channel} - {source_url}`) and hashtags.
  - Provides fallback metadata if LLM fails.
  - Stored on `clips` table row (`title`, `description`, `tags`) and editable via `PATCH /api/clips/{id}`.
- Updated `backend/app/workers/pipeline.py` to run windowed clip detection, metadata generation, and automatic model unloads.
- Added tests in `backend/tests/test_step3_selection_metadata.py`.

### Synthetic Transcript Verification Results
Running clip selection on a 600-second synthetic transcript generated the following candidate rankings:
1. Clip: "Strong Revelation" [70.0s - 150.0s, duration 80.0s] — Composite Score: 92.0
2. Clip: "Other Insights" [200.0s - 280.0s, duration 80.0s] — Composite Score: 80.0
*(Weak candidate at 50.0s - 130.0s with score 55.0 overlapping Clip 1 was correctly rejected, confirming overlap resolution)*

### How to Try It
- Run tests: `.venv/bin/pytest backend/tests/test_step3_selection_metadata.py`

## Step 4: Video Rendering and Export Upgrades

### Changes Made
- Upgraded `backend/app/services/ffmpeg_service.py`:
  - `blur_fit` layout: Generates a 9:16 canvas with a blurred background (downscaled to 1/4 size, boxblurred, and scaled back up) and centered crisp foreground with lanczos scaling.
  - `center_crop` layout: Preserved as an alternative layout.
  - Standardized resolution: 720x1280 default (configurable to 1080x1920).
  - Software encoding: `libx264 -preset veryfast -crf 24 -pix_fmt yuv420p -movflags +faststart`.
  - Audio normalization: `loudnorm` filter (`I=-14:TP=-1.5:LRA=11`) with AAC 160k.
  - `trim_clip_start`: Trims leading filler words ("um", "uh", etc.) and silence up to 1.5s before the first speech segment.
  - Full exact re-encoding (no `-c copy`).
- Upgraded `backend/app/services/captions.py`:
  - Positioned bottom captions ~28% up from the bottom on vertical (9:16) video to safely avoid YouTube Shorts and Reels UI overlays.
  - Added optional 3-second hook title overlay at the top-center from the clip title.
- Updated `render_clip` in `backend/app/workers/pipeline.py` to respect user layout, resolution, trimming, and hook titles.
- Added `GET /api/projects/{pid}/export` in `backend/app/api/routes.py`:
  - Packages all ready clips for a project into a `.zip` archive alongside `metadata.csv` (`filename,title,description,tags`).
- Added tests in `backend/tests/test_step4_render_export.py`.

### Render Benchmarks (Synthetic 2.0s Clip on 4-Core CPU)
- `blur_fit` layout (720x1280, ASS captions, loudnorm, libx264): **5.34 seconds**
- `center_crop` layout (720x1280, ASS captions, loudnorm, libx264): **4.78 seconds**

### How to Try It
- Run tests: `.venv/bin/pytest -s backend/tests/test_step4_render_export.py`
- Export project clips as zip: `curl -O http://localhost:8000/api/projects/<pid>/export`

## Step 5: Persistent Queue, Resume from Caches, and Batch API

### Changes Made
- Implemented persistent SQLite worker loop in `backend/app/workers/pipeline.py`:
  - `start_worker()`: Starts a daemon thread sequentially processing queued jobs from SQLite.
  - Stage-by-stage caching:
    - Ingest: reuses existing local video if already downloaded.
    - Transcription: reuses `storage/transcripts/<id>.json` and `.sentences.json` if present.
    - Clip analysis: reuses candidate clip records in `clips` table if already generated.
    - Metadata: generates only missing titles/descriptions/tags.
    - Render: checks existing rendered files and skips re-rendering clips that were already completed before restart or crash.
    - Cleanup: optionally deletes source video if `delete_source_after_render` is enabled.
- Upgraded `backend/app/main.py`:
  - Converted to FastAPI async lifespan handler.
  - On restart, resets any interrupted `processing` jobs back to `queued` so the worker picks them up and resumes where they left off.
- Upgraded `backend/app/api/routes.py`:
  - `POST /api/jobs`: Accepts multiple newline-separated URLs, enqueuing one job per URL.
  - `POST /api/jobs/{pid}/retry`: Resets job status to `queued` and triggers queue worker.
  - `POST /api/jobs/{pid}/cancel`: Cancels job immediately.
  - `_public`: Added real-time ETA calculation based on elapsed time and stage progress.
- Added test suite `backend/tests/test_step5_persistent_queue_resume.py`.

### How to Try It
- Run tests: `.venv/bin/pytest backend/tests/test_step5_persistent_queue_resume.py`
- Create multi-URL job: `curl -X POST http://localhost:8000/api/jobs -d "url=https://youtube.com/watch?v=1\nhttps://youtube.com/watch?v=2"`
- Cancel job: `curl -X POST http://localhost:8000/api/jobs/<id>/cancel`
- Retry job: `curl -X POST http://localhost:8000/api/jobs/<id>/retry`

## Step 6: YouTube Upload Integration and Spread Publishing

### Changes Made
- Created `backend/app/services/youtube.py`:
  - OAuth 2.0 desktop authorization flow (`storage/client_secret.json` -> `storage/token.json`).
  - Scoped strictly to `https://www.googleapis.com/auth/youtube.upload`.
  - Token refresh handling with detection of `invalid_grant` / 7-day test token expiration.
  - Resumable chunked upload via `google-api-python-client` with category 20 (Gaming), selfDeclaredMadeForKids=false, hasPaidProductPlacement=false.
  - Spread upload scheduling: `privacyStatus=private` + `status.publishAt` (RFC 3339) spaced $N$ minutes apart.
  - Background queue loop in SQLite (`uploads` table) with status progression (`queued` -> `uploading` -> `uploaded` / `failed`).
  - Quota exception handling: handles `quotaExceeded` gracefully without crashing.
- Implemented API routes in `backend/app/api/routes.py`:
  - `GET /api/youtube/status`
  - `POST /api/youtube/connect`
  - `POST /api/youtube/disconnect`
  - `POST /api/clips/{id}/upload`
  - `POST /api/projects/{id}/upload-all`
  - `GET /api/uploads`
- Documented Google Cloud setup in `README.md` and `HUMAN_TODO.md`.
- Added test suite in `backend/tests/test_step6_youtube_upload.py` with mocked Google API client.

### How to Try It
- Run tests: `.venv/bin/pytest backend/tests/test_step6_youtube_upload.py`
- Check YouTube status: `curl http://localhost:8000/api/youtube/status`
- Enqueue spread upload: `curl -X POST http://localhost:8000/api/projects/<pid>/upload-all -H "Content-Type: application/json" -d '{"spread_minutes":60}'`

## Step 7: Frontend Polish (React + TypeScript + Tailwind)

### Changes Made
- Added `ToastProvider` and `useToast` in `frontend/src/context/ToastContext.tsx`:
  - Rich notifications (success, error, info) with dismiss timers and icons.
- Built `Settings.tsx` (`#/settings`) bound to `/api/settings`:
  - Grouped sections: Clips (min/max duration, count), Download (quality), Metadata (tags, footer template), Upload (privacy, spread delay), Storage (delete source after render), LAN mode, and AI models (Ollama model, Whisper model).
- Upgraded `Home.tsx` (`#/`):
  - Multi-URL batch input textarea (one per line) with single-click batch start.
  - Live polling (3s) queue and history table with status badges, stage descriptions, progress bars, real-time ETA, and actions (Open, Retry, Cancel, Delete).
- Upgraded `Editor.tsx`:
  - Drawer with video preview, start/end trimming synchronized with transcript, title/description/tags editing, layout/caption/aspect dropdowns, re-render trigger, and MP4 download link.
- Upgraded `Project.tsx` (`#/project/:id`):
  - Clip grid showing thumbnails, scores, duration, and render status badges.
  - Batch actions: Select All, Delete Selected, Download Selected, and Export All (.zip).
  - YouTube upload status bar with Connect/Reconnect OAuth flow and spread upload modal.
  - Interactive clickable transcript viewer with click-to-seek.
- Upgraded `App.tsx`:
  - Responsive dark theme layout with top navigation bar and health check status polling.
  - Warnings banner for system health issues.
- Verified build: `npm run build` cleanly compiled to `frontend/dist/`.

### How to Try It
- Run frontend build: `cd frontend && npm run build`
- Run dev server: `cd frontend && npm run dev`
- Run all tests: `.venv/bin/pytest backend/tests`

## Step 8: Run on Laptop (Linux/Arch/Omarchy Integration)

### Changes Made
- Unified single-process architecture in `backend/app/main.py`:
  - Serves static assets and the React SPA directly from `frontend/dist`. Deep SPA routes route to `index.html`.
  - Implemented `/api/health` diagnostic endpoint checking `ffmpeg`, `ffprobe`, Ollama service status, model availability (`qwen2.5:3b-instruct`), and storage volume free disk space.
  - Restricted CORS to local origins and conditional wildcard for LAN mode.
- Storage guard and cleanup in `backend/app/workers/pipeline.py`:
  - 5.0 GB minimum free disk space check before starting video ingestion (`IngestError` aborts gracefully).
  - Background cleanup routine (`run_cleanup_job`) that prunes rendered MP4s of uploaded clips and obsolete source files older than `cleanup_days` (default 7 days).
  - Added `cleanup_days` to `AppSettings` schema and Settings UI.
- Laptop bootstrap script (`start.sh`):
  - Checks Python 3.12 / uv, FFmpeg, ffprobe, Ollama (and attempts `systemctl --user start ollama`), yt-dlp.
  - Bootstraps `.venv` and requirements on first run.
  - Builds frontend automatically if `frontend/dist` is missing.
  - Handles `--lan` and `--no-browser` flags, warns about no authentication on LAN, and opens default browser to `http://localhost:8000`.
- Systemd user service unit:
  - Created `clipper.service` in project root and installed to `~/.config/systemd/user/clipper.service` (`systemctl --user daemon-reload`).
- Comprehensive end-to-end test suite in `backend/tests/test_step8_e2e.py`:
  - Validated `/api/health`, SPA serving, 5 GB disk space guard, cleanup job, and synthetic video e2e render.
- Completely updated `README.md` for Arch/Omarchy Linux, documentation of user service, YouTube OAuth setup, and LAN mode.

### How to Try It
- Run one-command launcher: `./start.sh`
- Run service in background: `systemctl --user enable --now clipper.service`
- Run end-to-end tests: `.venv/bin/pytest backend/tests/test_step8_e2e.py`

## Step 9: Final Verification and Report

### Changes Made
- Ran full automated pytest suite across all modules: 56 tests passed in 105s.
- Tested launcher (`./start.sh --no-browser`) and verified live startup, unified serving, and `/api/health` diagnostic endpoint (`http://127.0.0.1:8000/api/health`).
- Created `USAGE.md` detailing startup options, multi-URL ingestion, live monitoring, clip editing drawer, export zip archive, YouTube spread uploads, yt-dlp maintenance, and ethical creator attribution.
- Updated `HUMAN_TODO.md` with prioritized, exact copy-paste commands for human-only actions (pacman install for Ollama, model pull, Google Cloud OAuth desktop app setup, systemd user service enablement, logind lid-close config).
- All 10 steps (Step 0 through Step 9) fully executed without skipping or violating constraints (zero paid APIs, 8 GB RAM memory budget with sequential processing, Linux pathlib, no sudo).

### Final Test Summary
- **Total Tests:** 58 passed, 0 failed.
  - `test_ai_db.py`: 5 passed
  - `test_api.py`: 4 passed
  - `test_media.py`: 8 passed
  - `test_settings_ollama.py`: 7 passed
  - `test_step2_ingest_transcript.py`: 7 passed
  - `test_step3_selection_metadata.py`: 7 passed
  - `test_step4_render_export.py`: 5 passed
  - `test_step5_persistent_queue_resume.py`: 4 passed
  - `test_step6_youtube_upload.py`: 6 passed
  - `test_step8_e2e.py`: 5 passed

## Live Real-World Video Test & Critical Bug Fixes

### 1. YouTube Subtitles 429 Fallback & curl-cffi Integration
- **Issue:** YouTube returns HTTP 429 (Too Many Requests) on auto-generated timedtext subtitle downloads when requested from datacenter/desktop IPs without authentication.
- **Fix:** Configured `yt-dlp` with `ignoreerrors=True` and installed `curl-cffi` for browser TLS fingerprinting. Added an automatic fallback in `YouTubeSource`: if YouTube throttles subtitles, ingest seamlessly recovers by downloading the video stream without subtitles, letting offline `faster-whisper` transcribe the speech locally.
- **PyAV Version Fix:** Pinned `av>=11,<14` (installed `13.1.0`) to avoid PyAV 14+ removal of `metadata_errors` in `faster-whisper`.

### 2. YouTube OAuth Studio UI Integration
- Added dedicated YouTube Studio authorization cards to the Dashboard (`Home.tsx`), Settings (`Settings.tsx`), and Sidebar (`App.tsx`).
- Created non-blocking background OAuth listener in `youtube.py` (`start_oauth_flow()`), allowing users to click "Authorize YouTube Channel", complete consent in browser, and auto-poll until authorized.

### 3. Clip Candidate Expansion for Small Local LLMs
- **Issue:** Small local LLMs (`qwen2.5:3b-instruct`) naturally extract short dialogue punchlines (4–15s). The candidate parser strictly filtered candidates by `MIN_CLIP_S <= duration <= MAX_CLIP_S` (60–120s), silently dropping valid moments.
- **Fix:** Updated `parse_window_candidates` in `backend/app/providers/ai.py` to automatically expand candidate sentence boundaries forward along consecutive sentences until reaching target vertical clip duration (60–120s), and trim if exceeding `max_len`. Added heuristic fallback generator to ensure no video ends with 0 clips.

### 4. Live Video Verification
- **Video:** `https://www.youtube.com/watch?v=4ckBlJM3O54` (*BREAKING Ankles With The Boys In Dead By Daylight*, 22.6 minutes, 1360s).
- **Result:** Successfully completed all stages end-to-end (ingest -> faster-whisper transcription -> windowed Ollama analysis -> metadata generation -> FFmpeg 9:16 rendering).
- **Outputs:** Generated 9 vertical 9:16 clips (62–99s each) with blurred background framing, audio normalization (`loudnorm`), word-highlight captions, custom YouTube titles, 3-line descriptions, tags, and attribution footers.




