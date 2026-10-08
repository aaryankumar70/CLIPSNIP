"""SQLite repository. Project row also carries video + job state (single-user MVP); swap for SQLAlchemy later."""
import sqlite3, threading, time, uuid
from ..config import get_settings

_lock = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT, status TEXT, stage TEXT, progress REAL DEFAULT 0,
  error TEXT, source_path TEXT, duration REAL, width INT, height INT, transcript_path TEXT, created_at REAL, started_at REAL, finished_at REAL);
CREATE TABLE IF NOT EXISTS clips(id TEXT PRIMARY KEY, project_id TEXT, start REAL, end REAL, title TEXT, hook TEXT, reason TEXT,
  score REAL, category TEXT, caption_style TEXT DEFAULT 'highlight', aspect TEXT DEFAULT '9:16',
  rendered_path TEXT, thumb_path TEXT, render_status TEXT DEFAULT 'pending', render_error TEXT, created_at REAL);
"""

def conn():
    s = get_settings(); s.storage.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(s.storage / "clipper.db", check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row; c.executescript(SCHEMA); return c

def new_id() -> str: return uuid.uuid4().hex[:12]

def q(sql: str, args=(), one=False):
    with _lock:
        c = conn()
        try:
            cur = c.execute(sql, args); c.commit()
            rows = [dict(r) for r in cur.fetchall()]
        finally: c.close()
    return (rows[0] if rows else None) if one else rows

def create_project(name: str, source_path: str) -> str:
    pid = new_id()
    q("INSERT INTO projects(id,name,status,stage,source_path,created_at) VALUES(?,?,?,?,?,?)",
      (pid, name, "queued", "queued", source_path, time.time()))
    return pid

def update_project(pid: str, **kw):
    q(f"UPDATE projects SET {','.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), pid))

def update_clip(cid: str, **kw):
    q(f"UPDATE clips SET {','.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), cid))
