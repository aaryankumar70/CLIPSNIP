# AGENTS.md

## Product and Hard Rules

**Product:**
A personal tool on a Linux laptop (Omarchy/Arch, 4-core i7, 8 GB RAM, integrated graphics only, no GPU). The human pastes YouTube links of creators who allow clipping. The tool makes 10 to 15 vertical 9:16 clips of 60 to 120 seconds per long video, with burned-in captions, writes titles/descriptions/tags, and uploads the clips to the human's own YouTube channel from the dashboard. First target content: GTA 6 related videos, but it must work for any video.

**Hard Rules for Every Change:**
- Zero paid APIs and no cloud AI. Only local tools: faster-whisper, Ollama, FFmpeg, yt-dlp. Allowed network: YouTube (download and upload) and one-time model downloads (Ollama registry, Hugging Face for the Whisper model).
- Must fit 8 GB RAM: Whisper, the LLM and FFmpeg never run at the same time. One job at a time.
- Linux only. Use `pathlib`. No Windows paths, no `.bat` files. Python 3.12 venv created with `uv venv --python 3.12`.
- Secrets (`client_secret.json`, `token.json`, `.env`) never go to git or logs.
- Keep the existing style: Pydantic validation, FFmpeg arguments as lists (no shell strings).
- Every task: write or adjust tests, run them, commit.
- Never run `sudo` (see instructions below).
- Always keep source attribution on every uploaded clip (description footer with source title, channel and URL).

## Operational Rules (from Section 0)
1. Read the build plan completely and the whole repo before changing anything.
2. Execute Steps 0 to 9 in order. Do not skip steps. Do not ask the human questions unless blocked on a human-only action. For anything else make a reasonable assumption and record it in `BUILD_LOG.md`.
3. After each step: run the tests, fix failures, `git commit` with a clear message, and append a short entry to `BUILD_LOG.md` (what changed, how to try it, what was assumed).
4. Install everything you can yourself (Python packages in the venv, `npm install`, `ollama pull`, etc.).
5. **Never run `sudo`, never type passwords, never log into websites.** If something needs sudo, a password, a website login, or a click by the human, do NOT stop the whole build. Add it to `HUMAN_TODO.md` with the exact command or steps, work around it (mocks, stubs, skipped real-world test), and continue.
6. Never try the same fix more than 3 times. After 3 failed attempts, write the problem and what you tried into `HUMAN_TODO.md`, and move on.
7. Stay inside this project folder. Do not delete files outside it. Ask before any destructive command.
8. Keep `HUMAN_TODO.md` as the single list of things the human must do, with checkboxes, ordered by importance, each with exact copy-paste commands. Print it at the end.
9. If a step needs real data (a real YouTube video, a real Ollama model) and that is unavailable, test with mocks plus a synthetic video made with ffmpeg (`testsrc` video + `sine` audio) and note what could not be verified.
