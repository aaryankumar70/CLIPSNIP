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
