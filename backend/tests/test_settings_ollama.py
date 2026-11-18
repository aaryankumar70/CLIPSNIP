import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.models import db
from app.providers.ai import OllamaProvider, AIError, parse_candidates, get_provider
from app.schemas.clip import ClipCandidate

class TestSettingsAndOllama(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_settings_get_and_put(self):
        # 1. GET default settings
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["layout"], "blur_fit")
        self.assertEqual(data["clip_min_s"], 60)
        self.assertEqual(data["clip_max_s"], 120)

        # 2. PUT updated settings (including ignoring unknown keys)
        updates = {
            "layout": "center_crop",
            "clip_min_s": 70,
            "max_clips": 10,
            "unknown_custom_key": "should_be_ignored",
        }
        res_put = self.client.put("/api/settings", json=updates)
        self.assertEqual(res_put.status_code, 200)
        put_data = res_put.json()
        self.assertEqual(put_data["layout"], "center_crop")
        self.assertEqual(put_data["clip_min_s"], 70)
        self.assertEqual(put_data["max_clips"], 10)
        self.assertNotIn("unknown_custom_key", put_data)

        # 3. Verify persistence in GET
        res_after = self.client.get("/api/settings")
        self.assertEqual(res_after.json()["layout"], "center_crop")
        self.assertEqual(res_after.json()["clip_min_s"], 70)

    @patch("httpx.Client.post")
    def test_ollama_successful_complete(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "content": json.dumps([
                    {
                        "start": 10.0,
                        "end": 80.0,
                        "title": "Exciting Moment",
                        "hook": "Check this out",
                        "reason": "Very exciting",
                        "score": 92.0,
                        "category": "surprising",
                    }
                ])
            }
        }
        mock_post.return_value = mock_resp

        provider = OllamaProvider(model="qwen2.5:3b-instruct")
        result = provider.complete("system prompt", "user prompt")
        self.assertIn("Exciting Moment", result)

        # Check call arguments
        mock_post.assert_called()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["model"], "qwen2.5:3b-instruct")
        self.assertEqual(call_kwargs["json"]["keep_alive"], "10m")
        self.assertEqual(call_kwargs["json"]["options"]["temperature"], 0.2)

    @patch("httpx.Client.post")
    def test_ollama_unload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        provider = OllamaProvider(model="qwen2.5:3b-instruct")
        provider.unload()
        mock_post.assert_called_with(
            "http://localhost:11434/api/chat",
            json={"model": "qwen2.5:3b-instruct", "keep_alive": 0},
        )

    @patch("httpx.Client.post")
    def test_ollama_not_running_error(self, mock_post):
        import httpx
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        provider = OllamaProvider()
        with self.assertRaises(AIError) as ctx:
            provider.complete("sys", "usr")
        self.assertIn("sudo systemctl enable --now ollama", str(ctx.exception))

    @patch("httpx.Client.post")
    def test_ollama_missing_model_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "model 'qwen2.5:3b-instruct' not found"
        mock_post.return_value = mock_resp
        provider = OllamaProvider(model="qwen2.5:3b-instruct")
        with self.assertRaises(AIError) as ctx:
            provider.complete("sys", "usr")
        self.assertIn("ollama pull qwen2.5:3b-instruct", str(ctx.exception))

    def test_default_provider_is_ollama(self):
        provider = get_provider()
        self.assertIsInstance(provider, OllamaProvider)

    def test_overlap_resolution_prefers_higher_score(self):
        # candidate A appears first with score 50 (10s - 70s)
        # candidate B appears second with score 90 (20s - 80s)
        # B overlaps A. parse_candidates must keep candidate B (score 90) rather than A!
        raw = json.dumps([
            {"start": 10.0, "end": 70.0, "title": "A", "score": 50.0, "category": "opinion"},
            {"start": 20.0, "end": 80.0, "title": "B", "score": 90.0, "category": "surprising"},
        ])
        cands = parse_candidates(raw, 100.0)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].title, "B")
        self.assertEqual(cands[0].score, 90.0)

if __name__ == "__main__":
    unittest.main()
