import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import db
from app.services.ingest import is_youtube_url, YouTubeSource, IngestError
from app.services.transcript import (
    parse_json3_captions,
    build_sentences,
    get_transcript,
    TranscriptionError,
)

SAMPLE_JSON3 = {
    "wireMagic": "pb3",
    "events": [
        {
            "tStartMs": 1000,
            "dDurationMs": 2000,
            "segs": [
                {"utf8": "Welcome ", "tOffsetMs": 0},
                {"utf8": "back ", "tOffsetMs": 400},
                {"utf8": "everyone.", "tOffsetMs": 800},
            ],
        },
        # Rolling duplicate caption overlap test
        {
            "tStartMs": 1500,
            "dDurationMs": 2500,
            "segs": [
                {"utf8": "back ", "tOffsetMs": 0},
                {"utf8": "everyone. ", "tOffsetMs": 300},
                {"utf8": "Today ", "tOffsetMs": 800},
                {"utf8": "we ", "tOffsetMs": 1100},
                {"utf8": "talk ", "tOffsetMs": 1400},
                {"utf8": "about ", "tOffsetMs": 1700},
                {"utf8": "GTA ", "tOffsetMs": 2000},
                {"utf8": "six!", "tOffsetMs": 2300},
            ],
        },
        # Large pause (> 0.7s) to test sentence splitting
        {
            "tStartMs": 5500,
            "dDurationMs": 1800,
            "segs": [
                {"utf8": "Are ", "tOffsetMs": 0},
                {"utf8": "you ", "tOffsetMs": 400},
                {"utf8": "ready?", "tOffsetMs": 800},
            ],
        },
    ],
}

class TestIngestAndTranscript(unittest.TestCase):
    def test_is_youtube_url(self):
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(is_youtube_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertTrue(is_youtube_url("https://youtube.com/shorts/abcd1234efg"))
        self.assertTrue(is_youtube_url("http://m.youtube.com/watch?v=123"))
        self.assertFalse(is_youtube_url("https://vimeo.com/123456"))
        self.assertFalse(is_youtube_url("https://example.com/video.mp4"))

    @patch("yt_dlp.YoutubeDL")
    def test_youtube_source_mocked_success(self, mock_ydl_cls):
        dest_dir = Path(tempfile.mkdtemp())
        pid = db.create_project("yt-test", "https://youtube.com/watch?v=test1234")

        mock_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance

        mock_instance.extract_info.return_value = {
            "title": "GTA 6 Gameplay Trailer",
            "uploader": "Rockstar Games",
            "uploader_url": "https://youtube.com/@rockstar",
            "webpage_url": "https://youtube.com/watch?v=test1234",
            "duration": 180,
            "upload_date": "20241201",
        }

        # Simulate creating the target mp4 and json3 files during download
        def fake_download(urls):
            (dest_dir / f"{pid}.mp4").write_bytes(b"dummy mp4")
            (dest_dir / f"{pid}.en.json3").write_text(json.dumps(SAMPLE_JSON3), encoding="utf-8")

        mock_instance.download.side_effect = fake_download

        yt_src = YouTubeSource("https://youtube.com/watch?v=test1234", project_id=pid)
        out_file = yt_src.fetch(dest_dir)

        self.assertTrue(out_file.is_file())
        proj = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        self.assertEqual(proj["source_title"], "GTA 6 Gameplay Trailer")
        self.assertEqual(proj["channel_name"], "Rockstar Games")
        self.assertEqual(proj["duration"], 180.0)

        # Captions should have been moved to storage/transcripts/<pid>.captions.json
        from app.config import get_settings
        cap_file = get_settings().storage / "transcripts" / f"{pid}.captions.json"
        self.assertTrue(cap_file.is_file())

    @patch("yt_dlp.YoutubeDL")
    def test_youtube_source_rejects_over_3_hours(self, mock_ydl_cls):
        dest_dir = Path(tempfile.mkdtemp())
        mock_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {"duration": 4 * 3600, "title": "Too Long"}

        yt_src = YouTubeSource("https://youtube.com/watch?v=long")
        with self.assertRaises(IngestError) as ctx:
            yt_src.fetch(dest_dir)
        self.assertIn("exceeds maximum limit of 3 hours", str(ctx.exception))

    def test_parse_json3_captions(self):
        tmp_json = Path(tempfile.mktemp(suffix=".json3"))
        tmp_json.write_text(json.dumps(SAMPLE_JSON3), encoding="utf-8")

        parsed = parse_json3_captions(tmp_json)
        self.assertEqual(parsed["source"], "youtube_captions")
        words = [w for seg in parsed["segments"] for w in seg["words"]]
        self.assertGreater(len(words), 5)
        # Check deduplication: "back" shouldn't be duplicated twice within 0.5s
        back_words = [w for w in words if w["word"].lower() == "back"]
        self.assertEqual(len(back_words), 1)

    def test_build_sentences(self):
        words = [
            {"word": "Hello", "start": 0.0, "end": 0.4},
            {"word": "to", "start": 0.45, "end": 0.6},
            {"word": "the", "start": 0.65, "end": 0.8},
            {"word": "world.", "start": 0.85, "end": 1.1},
            # Pause > 0.7s
            {"word": "This", "start": 2.0, "end": 2.3},
            {"word": "is", "start": 2.4, "end": 2.6},
            {"word": "great!", "start": 2.7, "end": 3.0},
            # Fragment under 3 words to be merged into previous sentence
            {"word": "Indeed.", "start": 3.1, "end": 3.4},
        ]
        sents = build_sentences(words)
        self.assertEqual(len(sents), 2)
        self.assertEqual(sents[0]["i"], 1)
        self.assertEqual(sents[0]["text"], "Hello to the world.")
        self.assertEqual(sents[1]["i"], 2)
        self.assertEqual(sents[1]["text"], "This is great! Indeed.")

    def test_get_transcript_with_json3(self):
        from app.config import get_settings
        pid = db.new_id()
        proj = {
            "id": pid,
            "duration": 60.0,
            "source_path": "/tmp/fake.mp4",
        }
        s = get_settings()
        cap_file = s.storage / "transcripts" / f"{pid}.captions.json"
        cap_file.parent.mkdir(parents=True, exist_ok=True)
        # Write valid transcript with enough words
        test_events = {
            "events": [
                {
                    "tStartMs": i * 1000,
                    "dDurationMs": 900,
                    "segs": [{"utf8": f"word{i} ", "tOffsetMs": 0}],
                }
                for i in range(25)
            ]
        }
        cap_file.write_text(json.dumps(test_events), encoding="utf-8")

        data = get_transcript(proj)
        self.assertEqual(data["source"], "youtube_captions")
        sent_file = s.storage / "transcripts" / f"{pid}.sentences.json"
        self.assertTrue(sent_file.is_file())

    def test_youtube_subtitle_429_fallback(self):
        """When YouTube returns HTTP 429 on subtitles, fallback downloads video without subtitles."""
        import yt_dlp
        from yt_dlp.utils import DownloadError

        src = YouTubeSource("https://www.youtube.com/watch?v=mock429", project_id="mock_429_proj")
        temp_dir = Path(tempfile.mkdtemp())
        target_mp4 = temp_dir / "mock_429_proj.mp4"

        first_call = True

        def mock_extract(self_ydl, url, download=False):
            return {"title": "Test Title", "duration": 120, "uploader": "Channel"}

        def mock_download(self_ydl, urls):
            nonlocal first_call
            if first_call:
                first_call = False
                raise DownloadError("ERROR: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests")
            target_mp4.write_text("dummy video")
            return 0

        with patch.object(yt_dlp.YoutubeDL, "extract_info", mock_extract), \
             patch.object(yt_dlp.YoutubeDL, "download", mock_download):
            res_path = src.fetch(temp_dir)
            self.assertEqual(res_path, target_mp4)
            self.assertTrue(res_path.is_file())

if __name__ == "__main__":
    unittest.main()
