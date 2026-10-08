from pathlib import Path

def safe_join(base: Path, *parts: str) -> Path:
    """Join parts under base; refuse anything that escapes base (path traversal)."""
    base = base.resolve()
    p = base.joinpath(*parts).resolve()
    if base != p and base not in p.parents:
        raise ValueError("Path escapes storage directory")
    return p
