# HUMAN_TODO.md

List of actions required from the human user. Ordered by importance, with exact copy-paste commands.

- [ ] **1. Install system packages & start Ollama** (requires `sudo`):
  ```bash
  sudo pacman -S --needed ollama && sudo systemctl enable --now ollama
  ```
  *After starting Ollama, pull the default local language model:*
  ```bash
  ollama pull qwen2.5:3b-instruct
  ```

- [ ] **2. Google Cloud Setup for YouTube Uploads** (requires browser login):
  1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project.
  2. Enable the **YouTube Data API v3** in APIs & Services.
  3. Configure OAuth consent screen:
     - User Type: **External**
     - Publishing status: Leave in **Testing**
     - Test users: Add your personal Google / YouTube account email.
  4. Create Credentials:
     - Click **Create Credentials** → **OAuth client ID**.
     - Application type: **Desktop app**.
     - Download the JSON client secret file and save it to:
       `/home/ryu/Projects/ClipSnip/storage/client_secret.json`

- [ ] **3. Connect YouTube Channel in Dashboard**:
  - Start the app with `./start.sh` and open `http://localhost:8000`.
  - In the top header or settings, click **Connect YouTube**.
  - A browser window will open for OAuth authorization. Log into your YouTube channel and click "Allow".
  - *(Note: In Google Cloud Testing mode, refresh tokens expire every 7 days. Click "Reconnect YouTube" when prompted).*

- [ ] **4. Enable Systemd User Service (Auto-Start at Boot)**:
  Run without sudo to keep ClipSnip running as a background service:
  ```bash
  systemctl --user enable --now clipper.service
  ```
  Check status and logs anytime:
  ```bash
  systemctl --user status clipper.service
  journalctl --user -u clipper.service -f
  ```

- [ ] **5. Keep Laptop Awake During Long Jobs**:
  Configure systemd logind to ignore laptop lid close while on AC power:
  ```bash
  sudo sed -i 's/#HandleLidSwitch=suspend/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
  sudo systemctl restart systemd-logind
  ```

- [ ] **6. (Optional) Open Port 8000 for LAN Mode**:
  If you enable LAN mode in Settings to control ClipSnip from your phone or tablet on home Wi-Fi:
  ```bash
  sudo ufw allow 8000/tcp
  ```

- [ ] **7. Maintain yt-dlp Updates**:
  YouTube frequently updates player mechanics. Run this update command regularly:
  ```bash
  cd /home/ryu/Projects/ClipSnip
  .venv/bin/uv pip install -U yt-dlp
  ```

- [ ] **8. Creator Permission & Attribution**:
  - Only clip content from creators who explicitly permit shorts/clipping.
  - Ask creators to whitelist your YouTube channel handle to avoid automated Content ID claims.
  - ClipSnip automatically appends source attribution to all clip descriptions (`Clipped from {source_title} by {channel} - {source_url}`).
