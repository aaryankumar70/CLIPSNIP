"""ASS caption generation from word-level timings with Shorts/Reels safe zones and hook title overlays."""
from dataclasses import dataclass
from typing import Any

@dataclass
class CaptionConfig:
    style: str = "highlight"  # classic | bold | highlight | creator | viral | minimal | off
    font: str = "Arial"
    font_size: int = 64
    position: str = "bottom"  # bottom | center | top
    color: str = "#FFFFFF"
    highlight_color: str = "#FFFF00"
    background: bool = False
    words_per_line: int = 3
    hook_title: str | None = None  # Optional overlay for the first 3 seconds

def _ass_color(hex_: str) -> str:
    h = hex_.lstrip("#")
    if len(h) == 6:
        return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
    return "&H00FFFFFF"

def _ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()

def build_ass(
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    width: int,
    height: int,
    cfg: CaptionConfig,
) -> str:
    """Generate ASS subtitle script with captions placed ~28% above the bottom on 9:16

    to safely clear TikTok, Instagram Reels, and YouTube Shorts UI overlays.
    """
    size = {"minimal": int(cfg.font_size * 0.6), "creator": int(cfg.font_size * 1.2), "viral": int(cfg.font_size * 1.25)}.get(cfg.style, cfg.font_size)
    size = int(size * width / 1080)
    size = max(24, size)

    align = {"bottom": 2, "center": 5, "top": 8}[cfg.position]
    # 28% vertical margin on 9:16 videos to avoid Shorts overlay (likes, comments, description)
    is_vertical = height > width
    bottom_ratio = 0.28 if is_vertical else 0.12
    margin_v = int(height * (bottom_ratio if cfg.position == "bottom" else 0.10))
    border = 4 if cfg.style in ("bold", "creator", "viral") else 2

    styles_block = [
        "Style: Default,%s,%d,%s,%s,&H00000000,%s,%d,0,0,0,100,100,0,0,%d,%d,1,%d,40,40,%d,1"
        % (
            cfg.font,
            size,
            _ass_color(cfg.color),
            _ass_color(cfg.highlight_color),
            "&H99000000" if cfg.background else "&H00000000",
            0 if cfg.style in ("classic", "minimal") else 1,
            3 if cfg.background else 1,
            border,
            align,
            margin_v,
        )
    ]

    # Hook title style for top-center display in first 3 seconds
    if cfg.hook_title:
        title_size = max(28, int(size * 1.15))
        title_margin_top = int(height * 0.10)
        styles_block.append(
            f"Style: HookTitle,{cfg.font},{title_size},&H00FFFFFF,&H0000FFFF,&H00000000,&HAA000000,1,0,0,0,100,100,0,0,3,3,1,8,40,40,{title_margin_top},1"
        )

    hdr = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
        "MarginL,MarginR,MarginV,Encoding\n"
        "%s\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        % (width, height, "\n".join(styles_block))
    )

    lines = []

    # Optional 3-second hook overlay
    if cfg.hook_title:
        clean_title = _esc(cfg.hook_title)[:80]
        lines.append(f"Dialogue: 1,0:00:00.00,0:00:03.00,HookTitle,,0,0,0,,{clean_title}")

    # Captions
    if cfg.style != "off":
        ws = [w for w in words if w["end"] > clip_start and w["start"] < clip_end]
        for i in range(0, len(ws), cfg.words_per_line):
            grp = ws[i : i + cfg.words_per_line]
            g0 = max(grp[0]["start"], clip_start) - clip_start
            g1 = min(grp[-1]["end"], clip_end) - clip_start

            if cfg.style in ("highlight", "creator", "viral"):
                hl = _ass_color(cfg.highlight_color)
                for j, w in enumerate(grp):
                    s = max(w["start"], clip_start) - clip_start
                    e = (min(grp[j + 1]["start"], clip_end) - clip_start) if j + 1 < len(grp) else g1
                    parts = []
                    for k, x in enumerate(grp):
                        t = _esc(x["word"])
                        if k == j:
                            extra = "\\fscx120\\fscy120" if cfg.style in ("creator", "viral") else ""
                            parts.append("{\\c%s%s}%s{\\r}" % (hl, extra, t))
                        else:
                            parts.append(t)
                    lines.append(f"Dialogue: 0,{_ts(s)},{_ts(max(e, s + 0.05))},Default,,0,0,0,,{' '.join(parts)}")
            else:
                text = " ".join(_esc(x["word"]) for x in grp)
                if cfg.style == "bold":
                    text = text.upper()
                lines.append(f"Dialogue: 0,{_ts(g0)},{_ts(max(g1, g0 + 0.05))},Default,,0,0,0,,{text}")

    return hdr + "\n".join(lines) + "\n"
