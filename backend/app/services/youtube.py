"""YouTube upload service via YouTube Data API v3 and OAuth2 desktop flow."""
import datetime
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any
from ..config import get_settings
from ..models import db

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

_upload_thread: threading.Thread | None = None
_upload_wake = threading.Event()
_quota_exceeded_until: float | None = None

class YouTubeAuthError(RuntimeError):
    pass

class YouTubeUploadError(RuntimeError):
    pass

def get_client_secret_path() -> Path:
    s = get_settings()
    return s.storage / "client_secret.json"

def get_token_path() -> Path:
    s = get_settings()
    return s.storage / "token.json"

def get_auth_status() -> dict[str, Any]:
    cs_path = get_client_secret_path()
    t_path = get_token_path()

    has_secret = cs_path.is_file()
    has_token = t_path.is_file()

    if not has_token:
        return {
            "authenticated": False,
            "reconnect_needed": False,
            "has_client_secret": has_secret,
            "error": "Not authenticated with YouTube",
        }

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(t_path), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    t_path.write_text(creds.to_json(), encoding="utf-8")
                except Exception as e:
                    err_str = str(e)
                    if "invalid_grant" in err_str:
                        return {
                            "authenticated": False,
                            "reconnect_needed": True,
                            "has_client_secret": has_secret,
                            "error": "Refresh token expired (7 days in Testing mode). Reconnect needed.",
                        }
                    return {
                        "authenticated": False,
                        "reconnect_needed": True,
                        "has_client_secret": has_secret,
                        "error": f"Token refresh failed: {e}",
                    }
            else:
                return {
                    "authenticated": False,
                    "reconnect_needed": True,
                    "has_client_secret": has_secret,
                    "error": "Credentials are invalid or expired without refresh token",
                }

        return {
            "authenticated": True,
            "reconnect_needed": False,
            "has_client_secret": has_secret,
            "error": None,
        }
    except Exception as e:
        return {
            "authenticated": False,
            "reconnect_needed": True,
            "has_client_secret": has_secret,
            "error": f"Auth check failed: {e}",
        }

def start_oauth_flow() -> dict[str, Any]:
    cs_path = get_client_secret_path()
    if not cs_path.is_file():
        raise YouTubeAuthError(
            "storage/client_secret.json is missing. Please create OAuth client ID credentials (Desktop app) in Google Cloud Console."
        )

    import webbrowser
    import wsgiref.simple_server
    from google_auth_oauthlib.flow import (
        InstalledAppFlow,
        _RedirectWSGIApp,
        _ExclusiveWSGIServer,
        _WSGIRequestHandler,
    )

    flow = InstalledAppFlow.from_client_secrets_file(str(cs_path), SCOPES)
    wsgi_app = _RedirectWSGIApp("ClipSnip authorization complete! You may return to the dashboard.")
    local_server = wsgiref.simple_server.make_server(
        "localhost",
        0,
        wsgi_app,
        server_class=_ExclusiveWSGIServer,
        handler_class=_WSGIRequestHandler,
    )

    port = local_server.server_port
    flow.redirect_uri = f"http://localhost:{port}/"
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    def _listen():
        try:
            local_server.timeout = 300
            local_server.handle_request()
            try:
                auth_resp = wsgi_app.last_request_uri.replace("http", "https")
                flow.fetch_token(authorization_response=auth_resp)
                creds = flow.credentials
                t_path = get_token_path()
                t_path.parent.mkdir(parents=True, exist_ok=True)
                t_path.write_text(creds.to_json(), encoding="utf-8")
            except Exception as e:
                print(f"OAuth token fetch error: {e}")
        finally:
            local_server.server_close()

    t = threading.Thread(target=_listen, daemon=True)
    t.start()

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    return {"status": "authorizing", "auth_url": auth_url}

def disconnect_youtube() -> dict[str, Any]:
    t_path = get_token_path()
    t_path.unlink(missing_ok=True)
    return {"authenticated": False}

def upload_clip_to_youtube(
    clip: dict[str, Any],
    privacy_status: str = "public",
    publish_at: str | None = None,
) -> dict[str, Any]:
    """Upload a single clip MP4 to YouTube using resumable chunked upload."""
    global _quota_exceeded_until

    if _quota_exceeded_until and time.time() < _quota_exceeded_until:
        raise YouTubeUploadError("YouTube upload quota exceeded. Waiting for daily quota reset.")

    auth_stat = get_auth_status()
    if not auth_stat["authenticated"]:
        raise YouTubeAuthError(auth_stat.get("error") or "YouTube authentication required")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    t_path = get_token_path()
    creds = Credentials.from_authorized_user_file(str(t_path), SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    mp4_path = Path(clip.get("rendered_path") or "")
    if not mp4_path.is_file():
        raise YouTubeUploadError(f"Rendered video file not found at {mp4_path}")

    # Prepare tags
    raw_tags = clip.get("tags") or ""
    tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    # Status body
    final_privacy = "private" if publish_at else privacy_status
    status_dict = {
        "privacyStatus": final_privacy,
        "selfDeclaredMadeForKids": False,
        "paidProductPlacementDetails": {
            "hasPaidProductPlacement": False,
        },
    }
    if publish_at:
        status_dict["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": (clip.get("title") or "Video Clip")[:100],
            "description": clip.get("description") or "",
            "tags": tags[:15],
            "categoryId": "20",  # Gaming
        },
        "status": status_dict,
    }

    media = MediaFileUpload(
        str(mp4_path),
        mimetype="video/mp4",
        chunksize=1024 * 1024 * 2,  # 2 MB chunks
        resumable=True,
    )

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response.get("id")
        video_url = f"https://youtube.com/shorts/{video_id}"

        return {
            "video_id": video_id,
            "youtube_url": video_url,
            "status": "uploaded",
        }

    except HttpError as e:
        err_content = str(e)
        if "quotaExceeded" in err_content:
            # Mark quota exceeded for 12 hours
            _quota_exceeded_until = time.time() + (12 * 3600)
            raise YouTubeUploadError("YouTube Data API quota exceeded. Resets at midnight Pacific Time.") from e
        if "invalid_grant" in err_content:
            raise YouTubeAuthError("OAuth token invalid or expired. Please reconnect YouTube.") from e
        raise YouTubeUploadError(f"YouTube upload failed: {e}") from e
    except Exception as e:
        raise YouTubeUploadError(f"YouTube upload error: {e}") from e

# ---------------- Persistent Upload Queue Loop ----------------

def _upload_worker_loop():
    global _upload_wake
    while True:
        task = db.q("SELECT * FROM uploads WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1", one=True)
        if not task:
            _upload_wake.wait(timeout=3.0)
            _upload_wake.clear()
            continue

        uid = task["id"]
        cid = task["clip_id"]
        clip = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)

        if not clip or clip.get("render_status") != "ready":
            db.q("UPDATE uploads SET status='failed', error='Clip not ready for upload', updated_at=? WHERE id=?", (time.time(), uid))
            db.update_clip(cid, youtube_status="failed", youtube_error="Clip not ready")
            continue

        try:
            db.q("UPDATE uploads SET status='uploading', updated_at=? WHERE id=?", (time.time(), uid))
            db.update_clip(cid, youtube_status="uploading")

            res = upload_clip_to_youtube(
                clip=clip,
                privacy_status="public",
                publish_at=clip.get("publish_at"),
            )

            vid = res["video_id"]
            vurl = res["youtube_url"]

            db.q(
                "UPDATE uploads SET status='uploaded', youtube_video_id=?, youtube_url=?, updated_at=? WHERE id=?",
                (vid, vurl, time.time(), uid),
            )
            db.update_clip(
                cid,
                youtube_status="uploaded",
                youtube_video_id=vid,
                youtube_url=vurl,
                youtube_error=None,
            )

        except (YouTubeAuthError, YouTubeUploadError) as e:
            err_msg = str(e)
            db.q("UPDATE uploads SET status='failed', error=?, updated_at=? WHERE id=?", (err_msg, time.time(), uid))
            db.update_clip(cid, youtube_status="failed", youtube_error=err_msg)
        except Exception as e:
            err_msg = f"Unexpected upload failure: {e}"
            db.q("UPDATE uploads SET status='failed', error=?, updated_at=? WHERE id=?", (err_msg, time.time(), uid))
            db.update_clip(cid, youtube_status="failed", youtube_error=err_msg)

def start_upload_worker():
    global _upload_thread
    if _upload_thread is None or not _upload_thread.is_alive():
        _upload_thread = threading.Thread(target=_upload_worker_loop, daemon=True)
        _upload_thread.start()

def trigger_upload_queue():
    start_upload_worker()
    _upload_wake.set()
