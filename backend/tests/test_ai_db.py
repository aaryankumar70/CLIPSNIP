import os, sys, tempfile, unittest
from pathlib import Path
os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import db
try:
    from app.providers.ai import parse_candidates, detect_clips, AIError, AIProvider
except ImportError:
    parse_candidates = None

class TestDB(unittest.TestCase):
    def test_project_lifecycle(self):
        pid = db.create_project("x", "/tmp/x.mp4")
        db.update_project(pid, status="failed", error="Transcription failed: boom")
        self.assertEqual(db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)["error"], "Transcription failed: boom")

@unittest.skipIf(parse_candidates is None, "pydantic not installed")
class TestAI(unittest.TestCase):
    good = '{"start":10,"end":50,"title":"A","hook":"h","reason":"r","score":88,"category":"funny"}'
    def test_valid_with_fences(self):
        self.assertEqual(len(parse_candidates(f"```json\n[{self.good}]\n```", 100)), 1)
    def test_rejects_bad_items(self):
        bad = ['{"start":50,"end":10,"title":"B","score":50}', '{"start":0,"end":500,"title":"C","score":50}',
               '{"start":0,"end":30,"title":"D","score":150}', '{"start":0,"end":5,"title":"E","score":50}']
        with self.assertRaises(AIError): parse_candidates("[" + ",".join(bad) + "]", 100)
        self.assertEqual(len(parse_candidates("[" + ",".join(bad) + "," + self.good + "]", 100)), 1)
    def test_malformed_json(self):
        with self.assertRaises(AIError): parse_candidates("not json", 100)
    def test_retry_then_success(self):
        class P(AIProvider):
            n = 0
            def complete(s, a, b): P.n += 1; return "garbage" if P.n < 3 else f"[{TestAI.good}]"
        self.assertEqual(len(detect_clips(P(), [{"start": 0, "end": 60, "text": "hi"}], 100)), 1)

if __name__ == "__main__": unittest.main()
