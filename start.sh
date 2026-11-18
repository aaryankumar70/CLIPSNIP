#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== ClipSnip Startup Check ==="

# 1. Check Python / uv
if command -v uv >/dev/null 2>&1; then
    PYTHON_CMD="uv"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo "ERROR: Neither 'uv' nor 'python3' found on PATH." >&2
    exit 1
fi

# 2. Check FFmpeg and ffprobe
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "WARNING: ffmpeg or ffprobe is not installed! Video rendering will fail." >&2
    echo "Install via: sudo pacman -S ffmpeg" >&2
fi

# 3. Check yt-dlp
if ! command -v yt-dlp >/dev/null 2>&1; then
    echo "WARNING: yt-dlp is not on system PATH. The venv copy will be used." >&2
fi

# 4. Check Ollama service
if command -v ollama >/dev/null 2>&1; then
    if systemctl --user is-active --quiet ollama 2>/dev/null; then
        echo "Ollama user service is running."
    elif ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Attempting to start Ollama user service..."
        systemctl --user start ollama 2>/dev/null || true
    fi
else
    echo "WARNING: ollama is not installed. AI features will require Ollama." >&2
    echo "Install via: sudo pacman -S ollama" >&2
fi

# 5. Bootstrap virtualenv if missing
if [ ! -d ".venv" ]; then
    echo "Creating Python 3.12 virtual environment..."
    if command -v uv >/dev/null 2>&1; then
        uv venv --python 3.12 .venv
    else
        python3 -m venv .venv
    fi
fi

# Install/verify dependencies
if [ ! -f ".venv/installed.tag" ] || [ backend/requirements.txt -nt .venv/installed.tag ]; then
    echo "Installing/updating Python dependencies..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install -r backend/requirements.txt --python .venv/bin/python
    else
        .venv/bin/pip install -r backend/requirements.txt
    fi
    touch .venv/installed.tag
fi

# 6. Build frontend if missing
if [ ! -f "frontend/dist/index.html" ]; then
    echo "Building frontend..."
    if command -v npm >/dev/null 2>&1; then
        (cd frontend && npm install && npm run build)
    else
        echo "WARNING: npm is missing, cannot build frontend! Install with: sudo pacman -S npm" >&2
    fi
fi

# 7. Determine Host / Port / LAN mode
HOST="127.0.0.1"
PORT="8000"
NO_BROWSER=0

for arg in "$@"; do
    case "$arg" in
        --lan)
            HOST="0.0.0.0"
            ;;
        --no-browser)
            NO_BROWSER=1
            ;;
        --port=*)
            PORT="${arg#*=}"
            ;;
    esac
done

# Also check database setting for lan_mode
DB_LAN=$(.venv/bin/python -c "from backend.app.models import db; print(getattr(db.get_db_settings(), 'lan_mode', False))" 2>/dev/null || echo "False")
if [ "$DB_LAN" = "True" ]; then
    HOST="0.0.0.0"
fi

if [ "$HOST" = "0.0.0.0" ]; then
    echo "======================================================================"
    echo "  SECURITY WARNING: LAN MODE IS ENABLED - NO AUTHENTICATION"
    echo "  ClipSnip is listening on all network interfaces (http://0.0.0.0:$PORT)."
    echo "  Anyone on your local network can access the dashboard and upload clips."
    echo "======================================================================"
else
    echo "ClipSnip running on http://127.0.0.1:$PORT (local only)"
fi

# 8. Open browser if requested
if [ "$NO_BROWSER" -eq 0 ]; then
    (
        sleep 2
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true
        elif command -v open >/dev/null 2>&1; then
            open "http://localhost:$PORT" >/dev/null 2>&1 || true
        fi
    ) &
fi

# 9. Start uvicorn
exec .venv/bin/uvicorn backend.app.main:app --host "$HOST" --port "$PORT"
