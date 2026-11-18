import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ["STORAGE_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import db
from app.providers.ai import (
    AIProvider,
    build_windows,
    compute_hook_features,
    detect_clips_windowed,
    generate_clip_metadata,
    parse_window_candidates,
    score_clip,
    select_clips,
)

class TestStep3ClipSelectionAndMetadata(unittest.TestCase):
    def setUp(self):
        # Generate synthetic sentences covering 600s
        self.sentences = []
        cur_time = 0.0
        for i in range(1, 61):
            dur = 9.0
            words = [
                {"word": f"Sentence{i}", "start": round(cur_time, 2), "end": round(cur_time + 2.0, 2)},
                {"word": "wordA", "start": round(cur_time + 2.1, 2), "end": round(cur_time + 4.0, 2)},
                {"word": "wordB", "start": round(cur_time + 4.1, 2), "end": round(cur_time + 6.0, 2)},
                {"word": "end.", "start": round(cur_time + 6.1, 2), "end": round(cur_time + dur, 2)},
            ]
            self.sentences.append({
                "i": i,
                "start": round(cur_time, 2),
                "end": round(cur_time + dur, 2),
                "text": f"This is sentence {i} with some key details.",
                "words": words,
            })
            cur_time += dur + 1.0  # 1s pause

    def test_windowing(self):
        # 600s video with 300s window and 30s overlap -> should yield 2 or 3 windows
        windows = build_windows(self.sentences, window_s=300, overlap_s=30, max_windows=12)
        self.assertGreaterEqual(len(windows), 2)
        for w in windows:
            self.assertGreater(len(w), 0)
            self.assertLessEqual(w[-1]["end"] - w[0]["start"], 315.0)

    def test_index_to_time_conversion(self):
        s_map = {s["i"]: s for s in self.sentences}
        # Pick sentences 1 to 8: length = ~80s
        raw = json.dumps({
            "clips": [
                {
                    "start_sentence": 1,
                    "end_sentence": 8,
                    "title": "Huge Revelation",
                    "hook_reason": "Exciting start",
                    "standalone": True,
                    "score": 9,
                }
            ]
        })
        cands = parse_window_candidates(raw, s_map, min_len=60, max_len=120)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        # start = first word start - 0.15s (0.0 - 0.15 clamped to 0.0)
        self.assertEqual(c["start"], 0.0)
        # end = last word end + 0.4s
        expected_end = round(s_map[8]["words"][-1]["end"] + 0.4, 2)
        self.assertEqual(c["end"], expected_end)
        self.assertTrue(60 <= c["duration"] <= 120)

    def test_hook_features_and_penalties(self):
        # Good hook with question, number, "you", and hook word
        hook_text = "Did you know that 5 secret methods exist?"
        words = [{"word": "Did", "start": 0.0, "end": 0.3}]
        score, penalty = compute_hook_features(hook_text, words)
        self.assertGreaterEqual(score, 0.75)
        self.assertEqual(penalty, 0.0)

        # Bad hook with filler start
        filler_text = "Um so basically nothing happened."
        words_filler = [{"word": "Um", "start": 0.0, "end": 0.3}]
        score_f, penalty_f = compute_hook_features(filler_text, words_filler)
        self.assertGreater(penalty_f, 0.1)

    def test_overlap_handling_prefers_higher_score(self):
        # Candidate 1: 50s to 130s, low score 55.0
        # Candidate 2: 70s to 150s (overlaps C1), high score 92.0
        # Candidate 3: 200s to 280s (non-overlapping), score 80.0
        cands = [
            {"start": 50.0, "end": 130.0, "duration": 80.0, "final_score": 55.0, "title": "Weak"},
            {"start": 70.0, "end": 150.0, "duration": 80.0, "final_score": 92.0, "title": "Strong"},
            {"start": 200.0, "end": 280.0, "duration": 80.0, "final_score": 80.0, "title": "Other"},
        ]
        selected = select_clips(cands, video_duration=600.0, target_count=2, min_gap_s=10.0)
        titles = [c["title"] for c in selected]
        self.assertIn("Strong", titles)
        self.assertIn("Other", titles)
        self.assertNotIn("Weak", titles)

    def test_first_third_distribution_limit(self):
        # Video length: 300s. First third: < 100s.
        # Target count: 4. Max from first third: floor(4 * 0.40) = 1.
        cands = [
            {"start": 10.0, "end": 75.0, "duration": 65.0, "final_score": 95.0, "title": "FT1"},
            {"start": 80.0, "end": 95.0, "duration": 70.0, "final_score": 90.0, "title": "FT2"},
            {"start": 120.0, "end": 195.0, "duration": 75.0, "final_score": 85.0, "title": "Mid1"},
            {"start": 210.0, "end": 285.0, "duration": 75.0, "final_score": 80.0, "title": "Late1"},
        ]
        selected = select_clips(cands, video_duration=300.0, target_count=3, min_gap_s=10.0)
        first_third_selected = [c for c in selected if c["start"] < 100.0]
        # At most 1 clip allowed from first third
        self.assertLessEqual(len(first_third_selected), 1)
        self.assertEqual(first_third_selected[0]["title"], "FT1")

    def test_metadata_generation(self):
        class MockAI(AIProvider):
            def complete(self, sys, usr, *args, **kwargs):
                return json.dumps({
                    "title": "GTA 6 Map Leaks Are Crazy!",
                    "description": "Insane new Vice City details discovered.\nCheck out the full breakdown.\nSubscribe for daily GTA 6 leaks!",
                    "tags": ["gta6", "gaming", "vicecity", "rockstar", "gta", "shorts", "leak", "trailer"],
                })

        meta = generate_clip_metadata(
            provider=MockAI(),
            clip_text="Vice City map is twice as big as Los Santos.",
            source_title="GTA 6 Full Breakdown",
            channel_name="GamerChannel",
            video_url="https://youtube.com/watch?v=12345",
        )
        self.assertIn("GTA 6 Map Leaks", meta["title"])
        self.assertIn("Clipped from GTA 6 Full Breakdown by GamerChannel", meta["description"])
        self.assertIn("vicecity", meta["tags"])

    def test_candidate_expansion_for_short_llm_ranges(self):
        s_map = {s["i"]: s for s in self.sentences}
        # Model only selected sentences 1 to 2 (approx 20s), which is < 60s
        raw = json.dumps({
            "clips": [
                {
                    "start_sentence": 1,
                    "end_sentence": 2,
                    "title": "Short Hook",
                    "hook_reason": "Exciting start",
                    "standalone": True,
                    "score": 9,
                }
            ]
        })
        cands = parse_window_candidates(raw, s_map, min_len=60, max_len=120)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertGreaterEqual(c["duration"], 60.0)
        self.assertLessEqual(c["duration"], 120.0)
        self.assertGreater(c["end_sentence"], 2)

if __name__ == "__main__":
    unittest.main()
