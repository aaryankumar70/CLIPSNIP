# HUMAN_TODO.md

List of actions required from the human user. Ordered by importance, with copy-paste commands.

- [ ] **1. Install system packages & start Ollama** (requires `sudo`):
  ```bash
  sudo pacman -S --needed ffmpeg nodejs npm uv ollama git deno && sudo systemctl enable --now ollama
  ```
  *Note: `ollama` and `deno` are not yet installed on this system. After installing and starting ollama, pull the default local model:*
  ```bash
  ollama pull qwen2.5:3b-instruct
  ```

- [ ] **2. Google Cloud setup for YouTube Uploads** (requires browser login):
  1. Go to [Google Cloud Console](https://console.cloud.google.com/), create a new project.
  2. Enable the **YouTube Data API v3**.
  3. Configure OAuth consent screen:
     - User Type: **External**
     - Publishing status: Leave in **Testing**
     - Test users: Add your own Google/YouTube email address.
  4. Create Credentials:
     - Click **Create Credentials** -> **OAuth client ID**.
     - Application type: **Desktop app**.
     - Download the JSON client secret file and save it to the project root at:
       `storage/client_secret.json`

- [ ] **3. Authenticate YouTube in Dashboard**:
  - The first time you click "Connect YouTube" in the Clipper web dashboard, a browser tab will open for OAuth authorization. Click "Allow".
  - *(Note: In Testing mode, refresh tokens expire every 7 days. Click "Reconnect YouTube" if prompted).*

- [ ] **4. Keep the laptop awake during processing**:
  - Disable suspend/lock timeout in Omarchy idle settings.
  - Configure systemd logind to ignore lid close:
    ```bash
    sudo sed -i 's/#HandleLidSwitch=suspend/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
    sudo systemctl restart systemd-logind
    ```

- [ ] **5. (Optional) Paste a test video URL**:
  - Open `CLIPPER_BUILD_PLAN.md` and set `TEST_VIDEO_URL=<url>` at the top with a short YouTube video (under 10 min) from a creator who allows clipping.

- [ ] **6. Creator Permission & Whitelisting**:
  - Ensure you have written permission from video creators to make and publish clips, and ask them to whitelist your channel to avoid Content ID claims.
