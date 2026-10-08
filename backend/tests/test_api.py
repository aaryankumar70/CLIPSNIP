import os, sys, tempfile, unittest
from pathlib import Path
os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import db
    from app.workers import pipeline
    pipeline.submit = lambda *a, **k: None  # never start real jobs in API tests
except ImportError:
    TestClient = None

@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.c = TestClient(app).__enter__()
    def test_needs_exactly_one_source(self):
        self.assertEqual(self.c.post("/api/jobs").status_code, 400)
    def test_bad_url_and_file_type(self):
        self.assertEqual(self.c.post("/api/jobs", data={"url": "ftp://x/a.mp4"}).status_code, 400)
        self.assertEqual(self.c.post("/api/jobs", files={"file": ("a.exe", b"x")}).status_code, 400)
    def test_missing_resources(self):
        self.assertEqual(self.c.get("/api/jobs/nope").status_code, 404)
        self.assertEqual(self.c.get("/api/clips/nope/download").status_code, 404)
    def test_clip_patch_download_delete(self):
        pid = db.create_project("t", "x"); db.update_project(pid, duration=60.0, status="completed")
        db.q("INSERT INTO clips(id,project_id,start,end,title,score,category,created_at) VALUES('c1',?,5,30,'T',80,'funny',0)", (pid,))
        self.assertEqual(self.c.patch("/api/clips/c1", json={"start": 40, "end": 30}).status_code, 422)
        self.assertEqual(self.c.patch("/api/clips/c1", json={"end": 999}).status_code, 422)
        self.assertEqual(self.c.patch("/api/clips/c1", json={"caption_style": "nope"}).status_code, 422)
        self.assertEqual(self.c.patch("/api/clips/c1", json={"start": 6}).json()["render_status"], "stale")
        self.assertEqual(self.c.get("/api/clips/c1/download").status_code, 409)
        self.assertEqual(self.c.get(f"/api/jobs/{pid}/clips").json()[0]["id"], "c1")
        self.assertEqual(self.c.delete(f"/api/projects/{pid}").status_code, 204)
        self.assertEqual(self.c.get(f"/api/jobs/{pid}").status_code, 404)

if __name__ == "__main__": unittest.main()
