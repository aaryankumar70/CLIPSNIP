import subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import ffmpeg_service as ff
from app.services.captions import CaptionConfig, build_ass
from app.services.ingest import LocalFileSource, DirectUrlSource, IngestError
from app.utils.paths import safe_join

TMP = Path(tempfile.mkdtemp())
SAMPLE = TMP / "sample.mp4"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-c:a", "aac",
                "-pix_fmt", "yuv420p", str(SAMPLE)], check=True)
WORDS = [{"word": w, "start": i * .5 + 1, "end": i * .5 + 1.45} for i, w in enumerate("this is a test of captions burned in".split())]

class T(unittest.TestCase):
    def test_probe(self):
        i = ff.probe(SAMPLE)
        self.assertAlmostEqual(i.duration, 6, delta=.3); self.assertEqual((i.width, i.height), (1280, 720)); self.assertTrue(i.has_audio)
    def test_formats_and_sync(self):
        i = ff.probe(SAMPLE)
        for asp, (w, h) in ff.FORMATS.items():
            out = ff.cut_clip(SAMPLE, TMP / f"c{asp[0]}{asp[-1]}.mp4", 1, 4, i, asp)
            o = ff.probe(out); self.assertEqual((o.width, o.height), (w, h)); self.assertAlmostEqual(o.duration, 3, delta=.2)
    def test_captions_burn(self):
        i = ff.probe(SAMPLE)
        for st in ("classic", "bold", "highlight", "creator", "minimal"):
            ass = TMP / f"{st}.ass"; ass.write_text(build_ass(WORDS, 1, 4, 1080, 1920, CaptionConfig(style=st)), encoding="utf-8")
            out = ff.cut_clip(SAMPLE, TMP / f"cap_{st}.mp4", 1, 4, i, "9:16", ass)
            self.assertGreater(out.stat().st_size, 1000)
    def test_thumb(self):
        self.assertTrue(ff.thumbnail(SAMPLE, TMP / "t.jpg").stat().st_size > 500)
    def test_invalid_range(self):
        i = ff.probe(SAMPLE)
        for a, b in ((-1, 3), (4, 3), (1, 99)):
            with self.assertRaises(ValueError): ff.cut_clip(SAMPLE, TMP / "x.mp4", a, b, i)
    def test_corrupt(self):
        bad = TMP / "bad.mp4"; bad.write_bytes(b"not a video")
        with self.assertRaises(ff.FFmpegError): ff.probe(bad)
    def test_ingest_validation(self):
        with self.assertRaises(IngestError): DirectUrlSource("ftp://x/y.mp4")
        with self.assertRaises(IngestError): DirectUrlSource("https://x.com/page")
        with self.assertRaises(IngestError): LocalFileSource(TMP / "a.exe").fetch(TMP)
        self.assertTrue(LocalFileSource(SAMPLE).fetch(TMP).is_file())
    def test_traversal(self):
        with self.assertRaises(ValueError): safe_join(TMP, "..", "etc")

if __name__ == "__main__": unittest.main()
