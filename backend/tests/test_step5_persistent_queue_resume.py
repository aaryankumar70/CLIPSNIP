import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app
from app.models import db
from app.workers import pipeline

TMP = Path(tempfile.mkdtemp())
SAMPLE_VID = TMP / "step5_sample.mp4"

subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
    "-f", "lavfi", "-i", "sine=frequency=440",
    "-t", "3",
    "-c:v", "libx264", "-c:a", "aac",
    "-pix_fmt", "yuv420p",
    str(SAMPLE_VID)
], check=True)

class TestStep5PersistentQueueResume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        s = get_settings()
        for d in ("uploads", "audio", "transcripts", "clips", "rendered", "thumbnails"):
            (s.storage / d).mkdir(parents=True, exist_ok=True)

    def test_multi_url_batch_job_creation(self):
        urls = "https://www.youtube.com/watch?v=video1\nhttps://www.youtube.com/watch?v=video2\n# comment\nhttps://www.youtube.com/watch?v=video3"
        res = self.client.post("/api/jobs", data={"url": urls})
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["ids"]), 3)
        self.assertIn("id", data)

    def test_retry_and_cancel_endpoints(self):
        pid = db.create_project("test_cancel", "https://youtube.com/watch?v=xyz")
        # Cancel
        res_cancel = self.client.post(f"/api/jobs/{pid}/cancel")
        self.assertEqual(res_cancel.status_code, 200)
        proj = db.q("SELECT status FROM projects WHERE id=?", (pid,), one=True)
        self.assertEqual(proj["status"], "cancelled")

        # Retry
        res_retry = self.client.post(f"/api/jobs/{pid}/retry")
        self.assertEqual(res_retry.status_code, 200)
        proj_retried = db.q("SELECT status FROM projects WHERE id=?", (pid,), one=True)
        self.assertEqual(proj_retried["status"], "queued")

    def test_resume_preserves_already_rendered_clips(self):
        s = get_settings()
        # Stage a source video in uploads
        upload_src = s.storage / "uploads" / "resume_test_source.mp4"
        upload_src.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SAMPLE_VID, upload_src)

        pid = db.create_project("resume_test", str(upload_src))
        db.update_project(pid, duration=3.0, source_path=str(upload_src))

        # Stage transcripts so transcription is skipped
        tpath = s.storage / "transcripts" / f"{pid}.json"
        sentences_path = s.storage / "transcripts" / f"{pid}.sentences.json"
        transcript_data = {
            "language": "en",
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": "Hello world.",
                    "words": [{"word": "Hello", "start": 0.5, "end": 1.0}, {"word": "world.", "start": 1.1, "end": 2.0}],
                }
            ],
        }
        tpath.write_text(json.dumps(transcript_data), encoding="utf-8")
        sentences_path.write_text(
            json.dumps([{"i": 1, "start": 0.0, "end": 3.0, "text": "Hello world.", "words": transcript_data["segments"][0]["words"]}]),
            encoding="utf-8",
        )
        db.update_project(pid, transcript_path=str(tpath))

        # Insert 2 clips: Clip 1 is already 'ready' and has a rendered file
        cid1 = db.new_id()
        cid2 = db.new_id()
        clip1_mp4 = s.storage / "rendered" / f"{cid1}.mp4"
        shutil.copyfile(SAMPLE_VID, clip1_mp4)
        mtime_clip1_orig = clip1_mp4.stat().st_mtime

        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,rendered_path,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid1, pid, 0.0, 1.5, "Clip One", 90.0, "gaming", "Desc 1", "tag1", str(clip1_mp4), "ready", time.time()),
        )
        # Clip 2 is pending
        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (cid2, pid, 1.0, 2.5, "Clip Two", 85.0, "gaming", "Desc 2", "tag2", "pending", time.time()),
        )

        # Run process_project (simulating resumed worker after interruption)
        pipeline.process_project(pid)

        # Clip 1 must NOT have been re-rendered
        self.assertEqual(clip1_mp4.stat().st_mtime, mtime_clip1_orig)

        # Clip 2 must now be rendered and ready
        clip2 = db.q("SELECT * FROM clips WHERE id=?", (cid2,), one=True)
        self.assertEqual(clip2["render_status"], "ready")
        self.assertTrue(Path(clip2["rendered_path"]).is_file())

        # Project should be completed
        final_proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        self.assertEqual(final_proj["status"], "completed")

    def test_delete_source_after_render_setting(self):
        s = get_settings()
        # Enable delete_source_after_render in settings
        db.save_db_settings({"delete_source_after_render": True})

        upload_src = s.storage / "uploads" / "cleanup_test.mp4"
        shutil.copyfile(SAMPLE_VID, upload_src)

        pid = db.create_project("cleanup_test", str(upload_src))
        db.update_project(pid, duration=3.0, source_path=str(upload_src))

        # Insert 1 clip and pre-render it
        cid = db.new_id()
        mp4_out = s.storage / "rendered" / f"{cid}.mp4"
        shutil.copyfile(SAMPLE_VID, mp4_out)
        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,rendered_path,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, pid, 0.0, 2.0, "Clip", 80.0, "gaming", "D", "T", str(mp4_out), "ready", time.time()),
        )
        tpath = s.storage / "transcripts" / f"{pid}.json"
        sentences_path = s.storage / "transcripts" / f"{pid}.sentences.json"
        tpath.write_text(json.dumps({"language": "en", "segments": []}), encoding="utf-8")
        sentences_path.write_text("[]", encoding="utf-8")
        db.update_project(pid, transcript_path=str(tpath))

        pipeline.process_project(pid)

        # Verify source file was removed
        self.assertFalse(upload_src.exists())
        proj = db.q("SELECT status FROM projects WHERE id=?", (pid,), one=True)
        self.assertEqual(proj["status"], "completed")

        # Revert setting back
        db.save_db_settings({"delete_source_after_render": False})

if __name__ == "__main__":
    unittest.main()
