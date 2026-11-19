import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app
from app.models import db
from app.services import youtube
from app.services.youtube import upload_clip_to_youtube, YouTubeUploadError, YouTubeAuthError

class TestStep6YouTubeUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        s = get_settings()
        for d in ("uploads", "audio", "transcripts", "clips", "rendered", "thumbnails"):
            (s.storage / d).mkdir(parents=True, exist_ok=True)

    def test_youtube_status_unauthenticated(self):
        res = self.client.get("/api/youtube/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["authenticated"])

    def test_disconnect_endpoint(self):
        s = get_settings()
        token_path = s.storage / "token.json"
        token_path.write_text("{}", encoding="utf-8")
        self.assertTrue(token_path.exists())

        res = self.client.post("/api/youtube/disconnect")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["authenticated"])
        self.assertFalse(token_path.exists())

    def test_upload_single_clip_enqueue(self):
        pid = db.create_project("yt_upload_proj", "/tmp/fake.mp4")
        cid = db.new_id()
        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (cid, pid, 0.0, 60.0, "Clip 1", 90.0, "gaming", "Desc", "tag1, tag2", "ready", time.time()),
        )

        res = self.client.post(f"/api/clips/{cid}/upload", json={"privacy_status": "unlisted"})
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(data["status"], "queued")

        up = db.q("SELECT * FROM uploads WHERE clip_id=?", (cid,), one=True)
        self.assertIsNotNone(up)
        clip = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)
        self.assertIn(clip["youtube_status"], ("queued", "uploading", "failed"))

    def test_upload_all_with_spread_minutes(self):
        pid = db.create_project("yt_spread_proj", "/tmp/fake.mp4")
        cid1 = db.new_id()
        cid2 = db.new_id()
        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (cid1, pid, 0.0, 60.0, "Spread 1", 90.0, "gaming", "D1", "t1", "ready", time.time()),
        )
        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (cid2, pid, 65.0, 125.0, "Spread 2", 85.0, "gaming", "D2", "t2", "ready", time.time()),
        )

        res = self.client.post(f"/api/projects/{pid}/upload-all", json={"spread_minutes": 60})
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["spread_minutes"], 60)

        # Verify scheduled publish_at timestamps
        c1 = db.q("SELECT * FROM clips WHERE id=?", (cid1,), one=True)
        c2 = db.q("SELECT * FROM clips WHERE id=?", (cid2,), one=True)
        self.assertIsNotNone(c1["publish_at"])
        self.assertIsNotNone(c2["publish_at"])
        self.assertIn("Z", c1["publish_at"])
        self.assertNotEqual(c1["publish_at"], c2["publish_at"])

    @patch("app.services.youtube.get_auth_status")
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_file")
    @patch("googleapiclient.discovery.build")
    def test_upload_clip_mocked_success(self, mock_build, mock_creds, mock_auth):
        mock_auth.return_value = {"authenticated": True, "reconnect_needed": False}
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        # Setup mock insert request and next_chunk
        mock_request = MagicMock()
        mock_request.next_chunk.return_value = (None, {"id": "yt_video_12345"})
        mock_youtube.videos().insert.return_value = mock_request

        tmp_mp4 = Path(tempfile.mktemp(suffix=".mp4"))
        tmp_mp4.write_bytes(b"dummy video")

        clip = {
            "id": "c1",
            "title": "Exciting GTA 6 Moment",
            "description": "Full details here",
            "tags": "gta6, gaming, vicecity",
            "rendered_path": str(tmp_mp4),
        }

        result = upload_clip_to_youtube(clip, privacy_status="public")
        self.assertEqual(result["video_id"], "yt_video_12345")
        self.assertEqual(result["youtube_url"], "https://youtube.com/shorts/yt_video_12345")

        # Verify payload parameters
        call_kwargs = mock_youtube.videos().insert.call_args[1]
        body = call_kwargs["body"]
        self.assertEqual(body["snippet"]["title"], "Exciting GTA 6 Moment")
        self.assertEqual(body["snippet"]["categoryId"], "20")
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertFalse(body["status"]["selfDeclaredMadeForKids"])
        self.assertFalse(body["status"]["paidProductPlacementDetails"]["hasPaidProductPlacement"])

    @patch("app.services.youtube.get_auth_status")
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_file")
    @patch("googleapiclient.discovery.build")
    def test_upload_clip_quota_exceeded(self, mock_build, mock_creds, mock_auth):
        from googleapiclient.errors import HttpError
        mock_auth.return_value = {"authenticated": True, "reconnect_needed": False}
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.reason = "quotaExceeded"
        mock_youtube.videos().insert.side_effect = HttpError(resp=mock_resp, content=b"quotaExceeded")

        tmp_mp4 = Path(tempfile.mktemp(suffix=".mp4"))
        tmp_mp4.write_bytes(b"dummy video")

        clip = {"id": "c_quota", "title": "Title", "description": "D", "tags": "t", "rendered_path": str(tmp_mp4)}

        with self.assertRaises(YouTubeUploadError) as ctx:
            upload_clip_to_youtube(clip)
        self.assertIn("quota exceeded", str(ctx.exception).lower())

    def test_schedule_single_clip_and_cancel(self):
        pid = db.create_project("yt_sched_proj", "/tmp/fake.mp4")
        cid = db.new_id()
        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (cid, pid, 0.0, 35.0, "Scheduled Clip", 92.0, "funny", "Desc", "shorts, funny", "ready", time.time()),
        )

        future_iso = "2026-11-20T18:00:00Z"
        res = self.client.post(f"/api/clips/{cid}/upload", json={"privacy_status": "private", "publish_at": future_iso})
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["publish_at"], future_iso)

        clip = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)
        self.assertEqual(clip["publish_at"], future_iso)
        self.assertEqual(clip["youtube_status"], "queued")

        # Now test cancel endpoint
        res_cancel = self.client.post(f"/api/clips/{cid}/cancel-upload")
        self.assertEqual(res_cancel.status_code, 200)
        self.assertEqual(res_cancel.json()["status"], "cancelled")

        clip_after = db.q("SELECT * FROM clips WHERE id=?", (cid,), one=True)
        self.assertEqual(clip_after["youtube_status"], "ready")
        self.assertIsNone(clip_after["publish_at"])

if __name__ == "__main__":
    unittest.main()
