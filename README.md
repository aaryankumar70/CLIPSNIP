# ClipSnip — Local AI Video Clipping Studio

ClipSnip is a personal tool built for Linux laptops (Arch / Omarchy, 4-core i7, 8 GB RAM, integrated graphics). Paste YouTube video URLs (from creators who allow clipping), and ClipSnip automatically transcribes the audio, detects the best 10–15 moments (60–120s vertical 9:16 clips), burns in word-synchronized animated captions, generates SEO titles/descriptions/tags, and uploads or schedules them to your YouTube channel.

**Zero paid cloud APIs. Zero subscriptions.** Runs 100% locally using `faster-whisper`, `Ollama`, `FFmpeg`, and `yt-dlp`.

---

## Hardware & System Requirements

- **Operating System:** Linux (Arch Linux / Omarchy recommended)
- **CPU:** 4-core Intel/AMD x86_64
- **RAM:** 8 GB RAM (Whisper, Ollama, and FFmpeg execute in strictly sequential stages and automatically unload from memory)
- **GPU:** None required (CPU int8 Whisper and software FFmpeg encoding)
- **Disk:** At least 5 GB free disk space

### Arch Linux System Packages
Install FFmpeg, Node.js, and Ollama:
```bash
sudo pacman -S ffmpeg nodejs npm ollama
```

### Pull Ollama Model
Start Ollama and download the instruction-tuned model:
```bash
systemctl --user enable --now ollama
ollama pull qwen2.5:3b-instruct
```

---

## Quick Start (One Command)

From the project root:
```bash
./start.sh
```
`start.sh` automatically:
1. Verifies prerequisites (FFmpeg, Ollama, yt-dlp, uv/python3).
2. Creates the Python 3.12 virtual environment (`.venv`) and installs all dependencies.
3. Builds the production frontend (`frontend/dist`) if not already built.
4. Starts the unified FastAPI server on `http://127.0.0.1:8000` (serving both backend API and frontend SPA).
5. Opens `http://localhost:8000` in your default browser.

---

## Systemd User Service (Auto-Start at Boot)

To run ClipSnip continuously in the background and restart automatically on failure:

1. Copy the provided user service unit:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp clipper.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   ```

2. Enable and start the service:
   ```bash
   systemctl --user enable --now clipper.service
   ```

3. Check service status:
   ```bash
   systemctl --user status clipper.service
   ```

4. View live logs:
   ```bash
   journalctl --user -u clipper.service -f
   ```

---

## YouTube Upload Integration (Google OAuth Desktop App)

ClipSnip can directly upload rendered clips to your YouTube channel as Shorts and spread publications over time.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **YouTube Data API v3**.
3. Configure the **OAuth Consent Screen**:
   - User Type: **External**
   - Publishing status: **Testing**
   - Add your Google account email under **Test Users**.
4. Create **Credentials** → **OAuth client ID** → Application type: **Desktop App**.
5. Download the JSON credentials file and save it to:
   ```bash
   storage/client_secret.json
   ```
6. In the ClipSnip UI, click **Connect YouTube** to authorize your channel.

---

## LAN Mode (Access from Local Network)

To access ClipSnip from your phone or another computer on the same Wi-Fi:

1. Enable **LAN Mode** in **Settings** (`#/settings`), or start with:
   ```bash
   ./start.sh --lan
   ```
2. > [!WARNING]
   > **LAN mode has NO AUTHENTICATION.** Anyone on your local network can access the dashboard, download videos, and upload clips to your channel. Use only on trusted home networks.

3. *(Optional)* If you run `ufw` firewall, allow inbound traffic on port 8000:
   ```bash
   sudo ufw allow 8000/tcp
   ```

---

## Storage & Auto-Cleanup

- **Low Disk Guard:** ClipSnip verifies free disk space before starting any video download. If free space is below 5.0 GB, downloads are aborted to prevent system lockups.
- **Auto-Cleanup:** Old source videos and rendered MP4 files of successfully uploaded clips are automatically deleted after N days (default: 7 days, configurable in Settings).
- **Export All:** Easily download all ready clips and `metadata.csv` as a `.zip` archive from the project page.

---

## Running the Test Suite

Run the full automated test suite (56 tests):
```bash
.venv/bin/pytest backend/tests
```
