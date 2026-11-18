# HUMAN_TODO.md

List of actions required from the human user. Ordered by importance, with exact copy-paste commands.

- [x] **1. Install system packages & start Ollama**:
  - Ollama installed to `~/.local/bin/ollama` and running via `systemctl --user enable --now ollama.service`.
  - Model `qwen2.5:3b-instruct` pulled and ready.

- [x] **2. Google Cloud Setup for YouTube Uploads**:
  - Saved OAuth client secrets to `/home/ryu/Projects/ClipSnip/storage/client_secret.json`.

- [ ] **3. Connect YouTube Channel in Dashboard**:
  - Start the app with `./start.sh` and open `http://localhost:8000`.
  - In the top header or settings, click **Connect YouTube**.
  - A browser window will open for OAuth authorization. Log into your YouTube channel and click "Allow".
  - *(Note: In Google Cloud Testing mode, refresh tokens expire every 7 days. Click "Reconnect YouTube" when prompted).*

- [x] **4. Enable Systemd User Service (Auto-Start at Boot)**:
  - Enabled and active: `systemctl --user enable --now clipper.service`.
  - Service automatically starts `start.sh --no-browser` and depends on `ollama.service`.

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

- [x] **7. Maintain yt-dlp Updates**:
  - Up-to-date in `.venv`. To update again in the future:
    ```bash
    cd /home/ryu/Projects/ClipSnip
    uv pip install -U yt-dlp --python .venv
    ```

- [ ] **8. Creator Permission & Attribution**:
  - Only clip content from creators who explicitly permit shorts/clipping.
  - Ask creators to whitelist your YouTube channel handle to avoid automated Content ID claims.
  - ClipSnip automatically appends source attribution to all clip descriptions (`Clipped from {source_title} by {channel} - {source_url}`).
