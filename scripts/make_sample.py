"""Generate a small 20s test video (tone + test pattern) for pipeline/FFmpeg tests: python scripts/make_sample.py"""
import subprocess, sys
from pathlib import Path
out = Path(sys.argv[1] if len(sys.argv) > 1 else "storage/sample.mp4"); out.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi",
                "-i", "sine=frequency=440", "-t", "20", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out)], check=True)
print("Wrote", out)
