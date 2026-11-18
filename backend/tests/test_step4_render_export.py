import csv
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app
from app.models import db
from app.services import ffmpeg_service as ff
from app.services.captions import CaptionConfig, build_ass

TMP = Path(tempfile.mkdtemp())
SAMPLE_VID = TMP / "test_sample_step4.mp4"

# Create a 4-second 1280x720 video with sine audio
subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
    "-f", "lavfi", "-i", "sine=frequency=440",
    "-t", "4",
    "-c:v", "libx264", "-c:a", "aac",
    "-pix_fmt", "yuv420p",
    str(SAMPLE_VID)
], check=True)

WORDS = [
    {"word": "Welcome", "start": 0.5, "end": 0.9},
    {"word": "to", "start": 1.0, "end": 1.2},
    {"word": "ClipSnip", "start": 1.3, "end": 1.8},
]

class TestStep4RenderAndExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.info = ff.probe(SAMPLE_VID)

    def test_captions_safe_zone_margin(self):
        # On a 720x1280 (9:16) video, bottom margin should be ~28% (358px)
        ass_text = build_ass(WORDS, 0.0, 2.0, 720, 1280, CaptionConfig(style="highlight", position="bottom"))
        self.assertIn("Style: Default", ass_text)
        # MarginV on 1280h should be int(1280 * 0.28) = 358
        self.assertIn(",358,1", ass_text)

    def test_trim_leading_silence_and_filler(self):
        filler_words = [
            {"word": "Um", "start": 0.1, "end": 0.4},
            {"word": "actually", "start": 0.5, "end": 0.9},
            {"word": "hello", "start": 1.2, "end": 1.5},
        ]
        # First word is "Um", second word "actually" starts at 0.5s -> should trim filler
        trimmed = ff.trim_clip_start(0.0, 3.0, filler_words)
        self.assertGreater(trimmed, 0.1)

    def test_render_blur_fit_timed(self):
        out_blur = TMP / "clip_blur_fit.mp4"
        ass_path = TMP / "captions_blur.ass"
        ass_path.write_text(build_ass(WORDS, 0.0, 2.0, 720, 1280, CaptionConfig(style="highlight", hook_title="Epic Moment")), encoding="utf-8")

        t0 = time.time()
        ff.cut_clip(
            src=SAMPLE_VID,
            out=out_blur,
            start=0.0,
            end=2.0,
            info=self.info,
            aspect="9:16",
            layout="blur_fit",
            resolution="720x1280",
            ass=ass_path,
        )
        elapsed = time.time() - t0
        self.assertTrue(out_blur.is_file())
        self.assertGreater(out_blur.stat().st_size, 5000)

        probe_out = ff.probe(out_blur)
        self.assertEqual(probe_out.width, 720)
        self.assertEqual(probe_out.height, 1280)
        self.assertAlmostEqual(probe_out.duration, 2.0, delta=0.3)
        print(f"\n[BENCHMARK] blur_fit render of 2.0s clip took: {elapsed:.2f}s")

    def test_render_center_crop_timed(self):
        out_crop = TMP / "clip_center_crop.mp4"
        ass_path = TMP / "captions_crop.ass"
        ass_path.write_text(build_ass(WORDS, 0.0, 2.0, 720, 1280, CaptionConfig(style="bold")), encoding="utf-8")

        t0 = time.time()
        ff.cut_clip(
            src=SAMPLE_VID,
            out=out_crop,
            start=0.0,
            end=2.0,
            info=self.info,
            aspect="9:16",
            layout="center_crop",
            resolution="720x1280",
            ass=ass_path,
        )
        elapsed = time.time() - t0
        self.assertTrue(out_crop.is_file())
        self.assertGreater(out_crop.stat().st_size, 5000)

        probe_out = ff.probe(out_crop)
        self.assertEqual(probe_out.width, 720)
        self.assertEqual(probe_out.height, 1280)
        print(f"\n[BENCHMARK] center_crop render of 2.0s clip took: {elapsed:.2f}s")

    def test_export_zip_endpoint(self):
        s = get_settings()
        pid = db.create_project("export_test", str(SAMPLE_VID))
        cid = db.new_id()
        mp4_path = s.storage / "rendered" / f"{cid}.mp4"
        mp4_path.parent.mkdir(parents=True, exist_ok=True)
        # Copy a real sample mp4 so zip has valid content
        import shutil
        shutil.copyfile(SAMPLE_VID, mp4_path)

        db.q(
            "INSERT INTO clips(id,project_id,start,end,title,score,category,description,tags,rendered_path,render_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, pid, 0.0, 2.0, "Awesome Moment", 90.0, "gaming", "Line 1\nLine 2\nLine 3", "gaming, gta6", str(mp4_path), "ready", time.time())
        )

        res = self.client.get(f"/api/projects/{pid}/export")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/zip")

        # Inspect zip content
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        file_list = zf.namelist()
        self.assertIn("metadata.csv", file_list)
        mp4_files = [f for f in file_list if f.endswith(".mp4")]
        self.assertEqual(len(mp4_files), 1)

        csv_content = zf.read("metadata.csv").decode("utf-8")
        reader = list(csv.reader(io.StringIO(csv_content)))
        self.assertEqual(reader[0], ["filename", "title", "description", "tags"])
        self.assertEqual(reader[1][1], "Awesome Moment")

if __name__ == "__main__":
    unittest.main()
