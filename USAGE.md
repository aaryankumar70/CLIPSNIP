# ClipSnip — User Guide (USAGE.md)

Welcome to **ClipSnip**, your local AI video clipping studio. This guide walks you through starting the app, pasting YouTube links, editing clips, scheduling uploads, and maintaining local tools.

---

## 1. How to Start the App

### Option A: Direct Terminal Launch (Interactive)
Run the automated launcher from the project directory:
```bash
./start.sh
```
This checks all dependencies, boots the environment, builds any missing assets, starts the server on `http://127.0.0.1:8000`, and automatically opens your browser.

- To run without launching a browser: `./start.sh --no-browser`
- To run with local network access enabled: `./start.sh --lan`
- To change port: `./start.sh --port=8080`

### Option B: Background System Service (Auto-Start at Boot)
To run ClipSnip continuously in the background on your Arch/Omarchy laptop:
```bash
systemctl --user enable --now clipper.service
```
- Check service status: `systemctl --user status clipper.service`
- Follow real-time logs: `journalctl --user -u clipper.service -f`
- Stop service: `systemctl --user stop clipper.service`

---

## 2. Ingesting Videos

1. Open the Dashboard at **`http://localhost:8000`**.
2. In the **YouTube URLs** box, paste one or more YouTube video links (one URL per line):
   ```text
   https://www.youtube.com/watch?v=VIDEO_ID_1
   https://www.youtube.com/watch?v=VIDEO_ID_2
   ```
3. Click **Start Processing**.
4. The jobs appear in the **Queue & History** table below. You will see:
   - Current stage: `ingesting` → `transcribing` → `analyzing` → `metadata` → `clips` → `done`
   - Progress bar and real-time Estimated Time Remaining (ETA)
   - Action buttons to **Open**, **Retry**, **Cancel**, or **Delete** the project.

---

## 3. Reviewing and Editing Clips

1. Click **Open** on any completed project to navigate to the **Project View** (`#/project/{id}`).
2. **Transcript Viewer:** On the left, review the full timestamped transcript. Click any line to seek the preview.
3. **Clip Grid:** Browse the AI-detected 60–120s vertical clips ranked by composite quality score.
4. **Editor Drawer:** Click any clip card to open the editing drawer:
   - **Video Preview:** Instant player with controls.
   - **Trim Boundaries:** Fine-tune start and end timestamps.
   - **Hook & Title:** Edit the curiosity-driven title.
   - **Description & Tags:** Customize the 3-line description and YouTube tags. The attribution footer (`Clipped from {source_title} by {channel}`) is automatically included.
   - **Visual Styling:** Select layout (`blur_fit` or `center_crop`) and caption style (`highlight`, `bold`, `classic`, `creator`, `minimal`, `off`).
   - Click **Re-render** to apply new trims or styling, or **Download MP4** to save the rendered clip.

---

## 4. Exporting Clips

- **Single Clip:** Click **Download MP4** inside any clip drawer or clip menu.
- **Bulk Download:** Select multiple clips with checkboxes and click **Download Selected**.
- **Full Project Zip:** Click **Export All (.zip)** in the top bar. This downloads a single `.zip` containing all rendered 9:16 vertical MP4s plus a formatted `metadata.csv` (with filename, title, description, tags) for easy archiving.

---

## 5. Direct YouTube Shorts Uploads

ClipSnip can upload directly to your personal YouTube channel:

1. **Connect Channel:** In the project header or settings, click **Connect YouTube**. If authorized, your channel status displays a green checkmark.
2. **Individual Upload:** Inside any clip drawer, click **Upload to YouTube**. You can set privacy (`public`, `unlisted`, `private`) or schedule a release time.
3. **Spread Upload (Recommended):**
   - Click **Spread Upload All** in the project header.
   - Specify the spacing in minutes (e.g., `60` or `120` minutes).
   - ClipSnip uploads the clips as `private` and sets `publishAt` dates spaced $N$ minutes apart, preventing algorithm penalties and notification spam.

---

## 6. Keeping yt-dlp Updated

YouTube frequently updates its internal player formats and bot protection. To keep downloads working smoothly, update `yt-dlp` regularly:

```bash
cd /home/ryu/Projects/ClipSnip
.venv/bin/uv pip install -U yt-dlp
```
*(Or if using standard pip: `.venv/bin/pip install -U yt-dlp`)*

---

## 7. Ethical Clipping & Creator Attribution

> [!IMPORTANT]
> **Always respect creator rights and platform guidelines:**
> 1. Only clip content from creators who explicitly permit shorts/clipping (such as streamers with permissive clipping guidelines).
> 2. Always maintain the source attribution footer in the description:
>    `Clipped from {source_title} by {channel} - {source_url}`
> 3. Use **Spread Uploads** rather than flooding your channel with 15 clips in one minute.
