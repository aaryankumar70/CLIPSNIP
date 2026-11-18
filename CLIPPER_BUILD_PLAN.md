# CLIPPER BUILD PLAN (for Antigravity)

> Put this file in the root of the existing `clipper` project and tell the agent:
> **"Read CLIPPER_BUILD_PLAN.md completely, then execute it from Step 0 to Step 9. Follow section 0 exactly."**

TEST_VIDEO_URL=<paste one SHORT YouTube URL of a creator who allows clipping, or leave empty>

---

## 0. Instructions to the agent (read first, obey always)

You are the autonomous builder of this project. The human is not a programmer and wants you to do everything that can be done by an agent, and to clearly tell them what only they can do.

**How to work**
1. Read this whole file, then read the whole repo (README, `backend/app/**`, `frontend/src/**`, tests) before changing anything.
2. Execute Steps 0 to 9 in order. Do not skip steps. Do not ask the human questions unless you are blocked on a human-only action. For anything else make a reasonable assumption and record it in `BUILD_LOG.md`.
3. After each step: run the tests, fix failures, `git commit` with a clear message, and append a short entry to `BUILD_LOG.md` (what changed, how to try it, what was assumed).
4. Install everything you can yourself (Python packages in the venv, `npm install`, `ollama pull`, etc.).
5. **Never run `sudo`, never type passwords, never log into websites.** If something needs sudo, a password, a website login, or a click by the human, do NOT stop the whole build. Add it to `HUMAN_TODO.md` with the exact command or steps, work around it (mocks, stubs, skipped real-world test), and continue.
6. Never try the same fix more than 3 times. After 3 failed attempts, write the problem and what you tried into `HUMAN_TODO.md`, and move on.
7. Stay inside this project folder. Do not delete files outside it. Ask before any destructive command.
8. Keep `HUMAN_TODO.md` as the single list of things the human must do, with checkboxes, ordered by importance, each with exact copy-paste commands. Print it at the end.
9. If a step needs real data (a real YouTube video, a real Ollama model) and that is unavailable, test with mocks plus a synthetic video made with ffmpeg (`testsrc` video + `sine` audio) and note what could not be verified.

---

## 1. What the human must do (summary; the agent keeps `HUMAN_TODO.md` in sync with this)

- [ ] **Install system packages** (needs sudo; agent cannot):
  `sudo pacman -S --needed ffmpeg nodejs npm uv ollama git deno && sudo systemctl enable --now ollama`
- [ ] **Google Cloud setup** (website login; agent cannot):
  1. Create a project, enable **YouTube Data API v3**.
  2. OAuth consent screen: External, leave in **Testing**, add your own Gmail as a test user.
  3. Credentials: create an **OAuth client ID**, type **Desktop app**, download the JSON, save as `storage/client_secret.json` in the project.
- [ ] **Click "Allow"** in the browser the first time you press "Connect YouTube" in the dashboard. In Testing mode the login expires about every 7 days: press "Reconnect YouTube" then.
- [ ] **Keep the laptop awake**: disable suspend/lock timeout in Omarchy's idle settings, and set `HandleLidSwitch=ignore` in `/etc/systemd/logind.conf` (sudo), then reboot or restart logind.
- [ ] **Paste a test video URL** at the top of this file (optional).
- [ ] **Get permission from creators** whose videos you clip, ideally in writing, and ask them to whitelist your channel so Content ID does not claim your clips.

---

## 2. Product and hard rules (the agent writes this into `AGENTS.md` in Step 0)

**Product:** a personal tool on a Linux laptop (Omarchy/Arch, 4-core i7, 8 GB RAM, integrated graphics only, no GPU). The human pastes YouTube links of creators who allow clipping. The tool makes 10 to 15 vertical 9:16 clips of 60 to 120 seconds per long video, with burned-in captions, writes titles/descriptions/tags, and uploads the clips to the human's own YouTube channel from the dashboard. First target content: GTA 6 related videos, but it must work for any video.

**Hard rules for every change**
- Zero paid APIs and no cloud AI. Only local tools: faster-whisper, Ollama, FFmpeg, yt-dlp. Allowed network: YouTube (download and upload) and one-time model downloads (Ollama registry, Hugging Face for the Whisper model).
- Must fit 8 GB RAM: Whisper, the LLM and FFmpeg never run at the same time. One job at a time.
- Linux only. Use `pathlib`. No Windows paths, no `.bat` files. Python 3.12 venv created with `uv venv --python 3.12`.
- Secrets (`client_secret.json`, `token.json`, `.env`) never go to git or logs.
- Keep the existing style: Pydantic validation, FFmpeg arguments as lists (no shell strings).
- Every task: write or adjust tests, run them, commit.
- Never run `sudo` (see section 0).
- Always keep source attribution on every uploaded clip (description footer with source title, channel and URL).

---

## 3. Verified facts (checked 2026-11-18; re-check the official YouTube Data API docs if you have web access)

- Since 2026-11-02, videos uploaded with `videos.insert` from unverified API projects are **no longer forced private**. If `privacyStatus` is not set, the video defaults to public. Always set it explicitly anyway.
- Uploads now have their own quota bucket and cost far less than the old 1,600 units. The default may be around 100 uploads per day; the real number is shown in Google Cloud Console under Quotas. Do not hardcode a daily limit; handle `quotaExceeded` gracefully.
- The OAuth app is in Testing mode: only listed test users can log in, and refresh tokens expire after about 7 days, so detect `invalid_grant` and show "Reconnect YouTube".
- `status.paidProductPlacementDetails.hasPaidProductPlacement` no longer defaults to false: set it explicitly to false.
- YouTube Shorts can be up to 3 minutes, so 60 to 120 s vertical clips qualify.
- yt-dlp may need a JavaScript runtime for YouTube; `deno` is installed for that.
- YouTube auto-captions in `json3` format include per-word timing; use them instead of Whisper whenever possible (saves a lot of time on this CPU).

---

## STEP 0: Bootstrap

1. Read this file and the whole repo.
2. Create `AGENTS.md` (section 2 content + section 0 rules), `BUILD_LOG.md`, `HUMAN_TODO.md` (start it from section 1).
3. Set up the environment yourself: `uv venv --python 3.12`, install the backend requirements, `npm install` in `frontend/`, check that `ffmpeg`, `ffprobe`, `ollama`, `yt-dlp` and `deno` exist (if not, add the install command to `HUMAN_TODO.md`), and if Ollama is running run `ollama pull qwen2.5:3b-instruct`. Remove Windows-only assumptions from the requirements.
4. Create a proper `.gitignore` (`.venv`, `node_modules`, `storage`, `.env`, `client_secret.json`, `token.json`, `dist`). Make sure no secret is tracked by git; if `.env` contains a key, tell the human in `HUMAN_TODO.md` to rotate it.
5. Run the existing tests and fix failures.
6. Write in `BUILD_LOG.md` the architecture you found and any bugs you noticed. Known issues of the original code: overlap removal happens before sorting by score; clip times come straight from the LLM as floats and are never snapped to sentence boundaries; whole transcript sent in one LLM prompt; center-crop only; captions placed too low for Shorts UI; `DirectUrlSource` rejects normal YouTube links; default AI providers are paid cloud APIs.

---

## STEP 1: Settings and local AI

**1) Central settings.** Add constants in `config.py` with these defaults: `MIN_CLIP_S=60`, `MAX_CLIP_S=120` (ideal 75 to 100), number of clips = `clamp(floor(video_minutes / 2.5), 3, 15)`, `WINDOW_S=300`, `WINDOW_OVERLAP_S=30`, `MAX_WINDOWS=12`, output 720x1280, `WHISPER_MODEL=base.en`, `OLLAMA_MODEL=qwen2.5:3b-instruct`, `OLLAMA_NUM_CTX=4096`.

Add a `settings` key/value table in SQLite plus `GET/PUT /api/settings`, so these user-editable values override the defaults at runtime: clip length range, max clips, layout (`blur_fit` or `center_crop`), caption style, output resolution, download quality (720p or 1080p), caption language, default upload privacy, spread-minutes between uploads, default tags, default hashtags, description footer template, delete-source-after-render, LAN mode. Validate with Pydantic and ignore unknown keys.

**2) Local AI.** In `providers/ai.py` add an `OllamaProvider` that calls `http://localhost:11434/api/chat` with temperature 0.2, `options.num_ctx` from settings and Ollama's structured-output `format` (JSON schema). Use `keep_alive` "10m" during a job and unload the model (`keep_alive` 0) at the end of the job. Make `ollama` the default provider and remove API-key requirements from the default path (cloud providers may stay as optional, never default). Errors: if Ollama is not running say "run `sudo systemctl enable --now ollama`"; if the model is missing say "run `ollama pull <model>`". On invalid JSON retry up to 3 times, including the validation error in the retry prompt. Update the README and add tests with a mocked Ollama.

**Done when:** tests pass, a mocked Ollama call returns validated JSON, `/api/settings` works.

---

## STEP 2: YouTube links, captions, transcript

**1) `services/ingest.py`:** add `YouTubeSource` using the `yt_dlp` Python package for youtube.com / youtu.be links.
- Download the best video up to 720p (setting: 1080p) with audio, merged to mp4.
- Check max duration (default 3 h), max size and free disk space first.
- Store source title, channel name, channel URL, video URL, duration and upload date on the project (migrate the DB).
- In the same pass fetch captions: manual subtitles if available, otherwise auto-captions, in `json3` format, language from settings, saved to `storage/transcripts/<id>.captions.json`.
- Report download progress into the job stage.
- Friendly errors for private, removed, age-restricted, geo-blocked, unfinished live/premiere and network failures.
- Only use the first video of a playlist URL. If yt-dlp needs a JavaScript runtime, use deno. Keep `LocalFileSource`.

**2) `services/transcript.py`:** `get_transcript(project)`.
- Convert json3 captions into `{language, source, segments[{start,end,text,words[{word,start,end}]}]}`, handling rolling/overlapping events and missing per-word offsets (estimate them).
- If there are no usable captions, fall back to faster-whisper: `base.en` (`base` if not English), int8, `beam_size=1`, `cpu_threads=4`, `vad_filter=True`, and free the model right after use.
- Build numbered sentences from the word timings (split on `. ? !` or pauses over 0.7 s, merge fragments under 3 words) and save `storage/transcripts/<id>.sentences.json` as `[{i,start,end,text,words}]`.
- Reject transcripts with under 50 words per 5 minutes.

**Tests:** mocked yt_dlp and a sample json3 file. If `TEST_VIDEO_URL` is set, also run it for real and write the first 10 sentences to `BUILD_LOG.md`.

---

## STEP 3: Clip selection and metadata

Rewrite clip detection for small local LLMs (`providers/ai.py`, `workers/pipeline.py`).

1. Split the numbered sentences into `WINDOW_S` windows with `WINDOW_OVERLAP_S` overlap. If there are more than `MAX_WINDOWS` windows, pre-score each with a cheap heuristic (speech rate, questions, exclamations, no sponsor or "subscribe" phrases) and keep the top `MAX_WINDOWS`.
2. Per window ask the LLM for up to 3 candidates. It returns SENTENCE INDEXES, never timestamps. Code converts to times: `start = first word start - 0.15 s`, `end = last word end + 0.4 s`. Candidates must be `MIN_CLIP_S` to `MAX_CLIP_S` long. Retry on bad JSON as in AGENTS.md. Merge and dedupe across windows.

   System prompt to use:

   ```
   You find short-video clips in a numbered transcript like [12] text. Choose runs of consecutive
   sentences (60-120 seconds long) that (a) open with a hook in the first sentence: a bold claim,
   question, surprise or strong emotion; (b) make sense with no earlier context; (c) end on a
   completed thought or punchline. Reject intros, sponsor reads, small talk, filler and rambling.
   Return JSON only: {"clips":[{"start_sentence":int,"end_sentence":int,"title":str (max 8 words),
   "hook_reason":str,"standalone":bool,"score":int 1-10}]}. Fewer is better than weak ones.
   10=exceptional, 7=good, 5 or below=skip.
   ```

3. `select_clips()`: sort by final score FIRST, then greedily keep non-overlapping clips with a 10 s minimum gap (this fixes the old overlap bug).
   Final score = `0.5*llm/10 + 0.2*audio energy and pace` (cheap numpy RMS from a 16 kHz mono wav made with ffmpeg) `+ 0.15*hook text features` (first 3 s: question, number, "you", strong claim, no filler start) `+ 0.15*standalone`, minus penalties for duration outside 75 to 100 s, a leading filler word, and silence ratio over 25%.
   At most 40% of the clips may come from the first third of the video. Take the top N from the clip-count formula, relaxing thresholds step by step if fewer pass. All weights go in config.
4. Metadata per clip via the local LLM (JSON schema): title (max 90 characters, creates curiosity without lying about the content), description (3 short lines), 8 tags (no `<` or `>`, under 500 characters total). Fall back to a template if the LLM fails. Append the settings footer, by default `Clipped from {source_title} by {channel} - {source_url}` plus the default hashtags. Store title/description/tags on the clip row (migrate the DB) and allow editing through the clip update route.

**Tests:** windowing, index-to-time conversion, merging, overlap handling (a weaker earlier clip overlapping a better later one), scoring. Run on a real or synthetic transcript and log the selected clips in `BUILD_LOG.md`.

---

## STEP 4: Rendering and export

Upgrade `services/ffmpeg_service.py` and the render step.
- Layouts: `blur_fit` (default for 16:9 sources): the full frame scaled to the width and centered over a blurred background made cheaply (scale the video down to 1/4 size, boxblur, scale back up). Keep `center_crop` as an option.
- Output 720x1280 by default (setting for 1080x1920). `libx264 -preset veryfast -crf 24`, plus `loudnorm` (`I=-14:TP=-1.5:LRA=11`). No hardware encoding.
- Burned-in ASS captions, positioned about 28% up from the bottom on 9:16 so they clear the Shorts/Reels UI. Default style "highlight".
- Optional hook-title overlay for the first 3 seconds from the clip title (setting).
- Trim leading silence/filler words at the clip start (max 1.5 s).
- Re-encode every clip (no `-c copy`), so cuts are exact.
- Render clips one at a time with per-clip progress and delete temp files.
- Export: an endpoint to download one project's clips as a zip with the MP4s plus `metadata.csv` (`filename,title,description,tags`).

**Tests:** render a 2-second clip for each layout. Log how long a render took.

---

## STEP 5: Persistent queue, resume, API

Make the job queue persistent in SQLite with one worker processing jobs one after another. Each stage (ingest, transcript, candidates, selection, metadata, render) caches its output, so after a crash or restart the job RESUMES from the last finished stage instead of failing.

Add `POST /api/jobs/{id}/retry` and `/cancel`, and let `POST /api/jobs` accept several URLs (newline-separated), creating one job per URL. Add per-stage ETA estimates. After each job unload Whisper and Ollama and free memory. Add the optional delete-source-after-render setting.

**Tests:** resume logic, including killing the worker mid-render.

---

## STEP 6: YouTube upload (backend plus minimal UI)

Add YouTube upload with `google-api-python-client` and `google-auth-oauthlib`.
- **Auth:** OAuth "Desktop app" client from `storage/client_secret.json` (gitignored), `InstalledAppFlow.run_local_server` on localhost (no domain needed), scope `https://www.googleapis.com/auth/youtube.upload` only, token in `storage/token.json`. The app is in Testing mode, so refresh tokens expire after about 7 days: detect `invalid_grant` and report "reconnect needed". If `client_secret.json` is missing, return a friendly error with the setup steps. Never log tokens. Because only the upload scope is used, the status endpoint can only report whether a usable token exists, not the channel name.
- **Endpoints:** `GET /api/youtube/status`, `POST /api/youtube/connect`, `POST /api/youtube/disconnect`, `POST /api/clips/{id}/upload`, `POST /api/projects/{id}/upload-all`, `GET /api/uploads`.
- **Upload:** `videos.insert` with a resumable chunked `MediaFileUpload`. Body: `snippet.title/description/tags`, `categoryId` 20 (Gaming), `status.privacyStatus` from settings (default public), `status.selfDeclaredMadeForKids=false`, `status.paidProductPlacementDetails.hasPaidProductPlacement=false`.
- **Spread uploads mode:** `privacyStatus=private` plus `status.publishAt` (RFC 3339), one clip every N minutes.
- **Queue:** a single background upload queue persisted in SQLite with per-clip status (`ready`, `queued`, `uploading`, `uploaded`, `failed`), the resulting YouTube URL, and retry on transient errors. On `quotaExceeded` stop the queue and report when it resets.
- **Minimal frontend:** on the project page a "Connect YouTube" button (and "Reconnect needed"), per-clip checkboxes, editable title/description/tags, privacy select, "Spread uploads every N minutes" toggle, "Upload selected" and "Upload all" buttons, per-clip status with a link to the uploaded video.
- README: the Google Cloud steps (also in `HUMAN_TODO.md`).

**Tests:** with the YouTube client mocked. Never run a real upload during the build.

---

## STEP 7: Frontend polish (React + TS + Tailwind, existing `api.ts` and types)

Clean, dark, mobile-friendly UI.
1. **Home:** a large textarea for several YouTube links (one per line) with a Start button, plus the existing file upload. Below it a live queue/history table: thumbnail, title, status badge, stage, progress bar, ETA, clip count, and buttons for open, retry, cancel, delete. Poll every 3 s.
2. **Settings page** bound to `/api/settings`, grouped: Clips, Download, Metadata, Upload, Storage, LAN mode.
3. **Project page:** source info, job status, clip grid (thumbnail, title, score, duration, render status). Clicking a clip opens an editor drawer: video preview, start/end trim over the transcript, title/description/tags, layout/caption/aspect selectors, "Re-render", and failed-render error with retry. Multi-select with "Select all", "Delete selected", "Download selected" and "Export all" (the zip endpoint). Keep the transcript viewer with click-to-seek.
4. Toasts for errors, loading and empty states, and a top navigation bar.

Run the app, click through every page in the browser, and fix what breaks. Report anything you could not test.

---

## STEP 8: Run it on the laptop

1. Build the frontend and serve `frontend/dist` from FastAPI so only one process runs. Restrict CORS.
2. Add `start.sh` that checks python/uv, ffmpeg, ollama (and its systemd service) and yt-dlp, creates the venv on first run, installs requirements, builds the frontend if `dist` is missing, starts uvicorn on 127.0.0.1 (0.0.0.0 only when LAN mode is enabled), and opens `http://localhost:8000`.
3. Add a systemd USER unit (`clipper.service`) plus README steps to enable it so the app starts at boot and restarts on failure, with logs via `journalctl --user`. Install and enable it yourself if no sudo is needed.
4. LAN mode with a clear no-authentication warning and a note about `sudo ufw allow 8000/tcp` (add to `HUMAN_TODO.md` as optional).
5. A cleanup job that deletes old source videos and rendered files of uploaded clips after N days (setting) and refuses to start a download when free disk is under 5 GB.
6. `/api/health` reporting ffmpeg, ollama and model status, with a warning banner in the UI.
7. Update the README for Linux (Arch/Omarchy) and add an end-to-end test with a short sample video.

---

## STEP 9: Final verification and report

1. Run the full test suite, then run the app via `start.sh` and check `/api/health`.
2. If `TEST_VIDEO_URL` is set and Ollama and the model are ready, run one real job end to end (download, transcript, selection, render) and record timings per stage in `BUILD_LOG.md`. Do NOT upload anything for real.
3. Write `USAGE.md`: how to start the app, paste links, review clips, upload, and update yt-dlp (`uv pip install -U yt-dlp`).
4. Final `git commit`.
5. **Print the final report:**
   - What works (verified) and what is untested.
   - The complete, ordered `HUMAN_TODO.md` checklist with exact commands.
   - Known limitations and suggested next improvements (for example face-tracking reframing, cut-aware captions styles).
   - A reminder: get written permission from the creators, keep the credit footer, use "spread uploads", and do not upload all clips of a video at once.
