"""ASS caption generation from word-level timings."""
from dataclasses import dataclass

@dataclass
class CaptionConfig:
    style: str = "highlight"      # classic | bold | highlight | creator | minimal
    font: str = "Arial"
    font_size: int = 64
    position: str = "bottom"      # bottom | center | top
    color: str = "#FFFFFF"
    highlight_color: str = "#FFFF00"
    background: bool = False
    words_per_line: int = 4

def _ass_color(hex_: str) -> str:
    h = hex_.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()

def _ts(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")

def build_ass(words: list[dict], clip_start: float, clip_end: float,
              width: int, height: int, cfg: CaptionConfig) -> str:
    """words: [{word,start,end}] in source-video time; output is shifted to clip time."""
    size = {"minimal": int(cfg.font_size * .6), "creator": int(cfg.font_size * 1.2)}.get(cfg.style, cfg.font_size)
    size = int(size * width / 1080)
    align = {"bottom": 2, "center": 5, "top": 8}[cfg.position]
    margin = int(height * (0.12 if cfg.position == "bottom" else 0.1))
    border = 3 if cfg.style in ("bold", "creator") else 2
    hdr = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n"
           "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
           "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
           "MarginL,MarginR,MarginV,Encoding\n"
           "Style: Default,%s,%d,%s,%s,&H00000000,%s,%d,0,0,0,100,100,0,0,%d,%d,1,%d,60,60,%d,1\n\n"
           "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
           % (width, height, cfg.font, size, _ass_color(cfg.color), _ass_color(cfg.highlight_color),
              "&H99000000" if cfg.background else "&H00000000",
              0 if cfg.style in ("classic", "minimal") else 1,
              3 if cfg.background else 1, border, align, margin))
    ws = [w for w in words if w["end"] > clip_start and w["start"] < clip_end]
    lines = []
    for i in range(0, len(ws), cfg.words_per_line):
        grp = ws[i:i + cfg.words_per_line]
        g0 = max(grp[0]["start"], clip_start) - clip_start
        g1 = min(grp[-1]["end"], clip_end) - clip_start
        if cfg.style in ("highlight", "creator"):
            hl = _ass_color(cfg.highlight_color)
            for j, w in enumerate(grp):
                s = max(w["start"], clip_start) - clip_start
                e = (min(grp[j + 1]["start"], clip_end) - clip_start) if j + 1 < len(grp) else g1
                parts = []
                for k, x in enumerate(grp):
                    t = _esc(x["word"].strip())
                    if k == j:
                        extra = "\\fscx115\\fscy115" if cfg.style == "creator" else ""
                        parts.append("{\\c%s%s}%s{\\r}" % (hl, extra, t))
                    else:
                        parts.append(t)
                lines.append(f"Dialogue: 0,{_ts(s)},{_ts(max(e, s + .05))},Default,,0,0,0,,{' '.join(parts)}")
        else:
            text = " ".join(_esc(x["word"].strip()) for x in grp)
            if cfg.style == "bold":
                text = text.upper()
            lines.append(f"Dialogue: 0,{_ts(g0)},{_ts(max(g1, g0 + .05))},Default,,0,0,0,,{text}")
    return hdr + "\n".join(lines) + "\n"
