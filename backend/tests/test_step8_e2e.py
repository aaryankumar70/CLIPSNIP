import os
import sys
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models import db
from app.services import ffmpeg_service as ff
from app.services.ingest import IngestError
from app.workers import pipeline

class TestStep8E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.storage = Path(cls.temp_dir) / "storage"
        for d in ("uploads", "audio", "transcripts", "clips", "rendered", "thumbnails"):
            (cls.storage / d).mkdir(parents=True, exist_ok=True)
        os.environ["STORAGE_PATH"] = str(cls.storage)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        self.client = TestClient(app)

    def test_api_health(self):
        """Test /api/health returns system status and diagnostics."""
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("ok", data)
        self.assertIn("ffmpeg", data)
        self.assertIn("ffprobe", data)
        self.assertIn("ollama", data)
        self.assertIn("disk_free_gb", data)
        self.assertIn("warnings", data)
        self.assertTrue(data["ffmpeg"])
        self.assertTrue(data["ffprobe"])

    def test_spa_serving(self):
        """Test serving frontend SPA from root and deep paths."""
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("html", r.headers["content-type"])
        self.assertIn('<div id="root">', r.text)

        # Deep path should also return index.html for SPA router
        r = self.client.get("/project/proj_123")
        self.assertEqual(r.status_code, 200)
        self.assertIn('<div id="root">', r.text)

        # Unmatched API endpoint should return 404, not index.html
        r = self.client.get("/api/nonexistent_route")
        self.assertEqual(r.status_code, 404)

    def test_disk_space_guard(self):
        """Pipeline must refuse to start a download if free disk is under 5 GB."""
        pid = f"proj_disk_guard_{db.new_id()}"
        db.q(
            "INSERT INTO projects(id, name, status, source_path, created_at) VALUES(?,?,?,?,?)",
            (pid, "Disk Guard Test", "queued", "https://youtube.com/watch?v=fakevideo", time.time())
        )

        with patch("shutil.disk_usage") as mock_usage:
            # Simulate 2 GB free (less than 5 GB)
            mock_usage.return_value = MagicMock(free=2 * 1024 * 1024 * 1024)
            pipeline.process_project(pid)

        p = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        self.assertEqual(p["status"], "failed")
        self.assertIn("Free disk space is 2.0 GB", p["error"])

    def test_cleanup_job(self):
        """Cleanup job deletes old rendered files of uploaded clips and unreferenced uploads."""
        s = get_settings()
        # Create an uploaded clip older than cleanup cutoff
        old_time = time.time() - (10 * 86400) # 10 days ago
        clip_id = f"clip_cleanup_{db.new_id()}"
        rendered_file = s.storage / "rendered" / f"{clip_id}.mp4"
        rendered_file.write_text("dummy video")

        db.q(
            "INSERT INTO clips(id, project_id, start, end, title, render_status, youtube_status, rendered_path, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (clip_id, "p1", 0.0, 60.0, "Old Clip", "ready", "uploaded", str(rendered_file), old_time)
        )

        self.assertTrue(rendered_file.is_file())
        pipeline.run_cleanup_job()
        self.assertFalse(rendered_file.is_file())

    def test_synthetic_video_e2e_render(self):
        """End-to-end rendering of a synthetic video clip with captions and loudnorm."""
        s = get_settings()
        video_path = self.storage / "uploads" / "e2e_synth.mp4"
        
        # Generate 3-second testsrc video + sine audio using ffmpeg
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
            "-t", "3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(video_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 0)

        clip = {
            "id": "e2e_clip_1",
            "start": 0.5,
            "end": 2.5,
            "aspect": "9:16",
            "caption_style": "highlight",
            "title": "GTA 6 INSANE MOMENT",
            "hook": "Wait for the ending",
        }
        proj = {
            "id": "proj_e2e",
            "source_path": str(video_path),
        }
        words = [
            {"word": "GTA", "start": 0.5, "end": 1.0},
            {"word": "SIX", "start": 1.0, "end": 1.5},
            {"word": "INSANE", "start": 1.5, "end": 2.0},
            {"word": "MOMENT", "start": 2.0, "end": 2.5},
        ]

        out_path, thumb_path = pipeline.render_clip(clip, proj, words)
        self.assertTrue(out_path.is_file())
        self.assertTrue(thumb_path.is_file())

        info = ff.probe(out_path)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.5)
        self.assertEqual(info.width, 720)
        self.assertEqual(info.height, 1280)
