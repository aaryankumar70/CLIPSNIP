"""SQLite repository for Clipper."""
import json
import sqlite3
import threading
import time
import uuid
from typing import Any
from ..config import get_settings
from ..schemas.settings import AppSettings

_lock = threading.Lock()

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY,
  name TEXT,
  status TEXT,
  stage TEXT,
  progress REAL DEFAULT 0,
  error TEXT,
  source_path TEXT,
  duration REAL,
  width INT,
  height INT,
  transcript_path TEXT,
  created_at REAL,
  started_at REAL,
  finished_at REAL,
  source_title TEXT,
  channel_name TEXT,
  channel_url TEXT,
  video_url TEXT,
  upload_date TEXT
);

CREATE TABLE IF NOT EXISTS clips(
  id TEXT PRIMARY KEY,
  project_id TEXT,
  start REAL,
  end REAL,
  title TEXT,
  hook TEXT,
  reason TEXT,
  score REAL,
  category TEXT,
  caption_style TEXT DEFAULT 'highlight',
  aspect TEXT DEFAULT '9:16',
  rendered_path TEXT,
  thumb_path TEXT,
  render_status TEXT DEFAULT 'pending',
  render_error TEXT,
  created_at REAL,
  description TEXT,
  tags TEXT,
  youtube_status TEXT DEFAULT 'ready',
  youtube_video_id TEXT,
  youtube_url TEXT,
  youtube_error TEXT,
  publish_at TEXT
);

CREATE TABLE IF NOT EXISTS uploads(
  id TEXT PRIMARY KEY,
  clip_id TEXT,
  project_id TEXT,
  status TEXT DEFAULT 'queued',
  error TEXT,
  youtube_video_id TEXT,
  youtube_url TEXT,
  scheduled_at REAL,
  created_at REAL,
  updated_at REAL
);
"""

def _migrate(c: sqlite3.Connection):
    c.executescript(BASE_SCHEMA)
    # Ensure any missing columns on existing tables are added safely
    table_columns = {
        "projects": {
            "source_title": "TEXT",
            "channel_name": "TEXT",
            "channel_url": "TEXT",
            "video_url": "TEXT",
            "upload_date": "TEXT",
        },
        "clips": {
            "description": "TEXT",
            "tags": "TEXT",
            "youtube_status": "TEXT DEFAULT 'ready'",
            "youtube_video_id": "TEXT",
            "youtube_url": "TEXT",
            "youtube_error": "TEXT",
            "publish_at": "TEXT",
        },
    }
    for table, cols in table_columns.items():
        existing = {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, col_type in cols.items():
            if col not in existing:
                try:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass
    c.commit()

def conn() -> sqlite3.Connection:
    s = get_settings()
    s.storage.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(s.storage / "clipper.db", check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    _migrate(c)
    return c

def new_id() -> str:
    return uuid.uuid4().hex[:12]

def q(sql: str, args=(), one=False) -> Any:
    with _lock:
        c = conn()
        try:
            cur = c.execute(sql, args)
            c.commit()
            rows = [dict(r) for r in cur.fetchall()]
        finally:
            c.close()
    return (rows[0] if rows else None) if one else rows

def create_project(name: str, source_path: str, **kw) -> str:
    pid = new_id()
    keys = ["id", "name", "status", "stage", "source_path", "created_at"] + list(kw.keys())
    values = [pid, name, "queued", "queued", source_path, time.time()] + list(kw.values())
    placeholders = ",".join("?" for _ in keys)
    q(f"INSERT INTO projects({','.join(keys)}) VALUES({placeholders})", tuple(values))
    return pid

def update_project(pid: str, **kw):
    if not kw:
        return
    q(f"UPDATE projects SET {','.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), pid))

def update_clip(cid: str, **kw):
    if not kw:
        return
    q(f"UPDATE clips SET {','.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), cid))

def get_db_settings() -> AppSettings:
    rows = q("SELECT key, value FROM settings")
    loaded = {}
    for r in rows:
        try:
            loaded[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            loaded[r["key"]] = r["value"]
    return AppSettings(**loaded)

def save_db_settings(updates: dict[str, Any]) -> AppSettings:
    current = get_db_settings().model_dump()
    valid_update = AppSettings(**{**current, **updates}).model_dump()
    with _lock:
        c = conn()
        try:
            for k, v in valid_update.items():
                val_str = json.dumps(v)
                c.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, val_str))
            c.commit()
        finally:
            c.close()
    return AppSettings(**valid_update)
