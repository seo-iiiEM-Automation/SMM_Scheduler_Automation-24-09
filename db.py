"""SQLite storage for scheduled posts (shared by app.py and scheduler.py)."""
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "scheduler.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def to_utc_iso(dt: datetime) -> str:
    """Store every time as a UTC ISO string so string comparison == time comparison."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def init_db():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                media_path   TEXT NOT NULL,
                media_type   TEXT NOT NULL CHECK (media_type IN ('image','video')),
                caption      TEXT DEFAULT '',
                hashtags     TEXT DEFAULT '',
                platforms    TEXT NOT NULL,          -- 'facebook,instagram'
                scheduled_at TEXT NOT NULL,          -- UTC ISO
                status       TEXT NOT NULL DEFAULT 'scheduled',
                results      TEXT DEFAULT '{}',      -- per-platform JSON
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )"""
        )


def add_post(media_path, media_type, caption, hashtags, platforms, scheduled_dt):
    now = to_utc_iso(datetime.now(timezone.utc))
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO posts (media_path, media_type, caption, hashtags, platforms,
                                  scheduled_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (media_path, media_type, caption, hashtags, ",".join(platforms),
             to_utc_iso(scheduled_dt), now, now),
        )
        return cur.lastrowid


def list_posts(statuses):
    q = ",".join("?" * len(statuses))
    with _conn() as c:
        return [dict(r) for r in c.execute(
            f"SELECT * FROM posts WHERE status IN ({q}) ORDER BY scheduled_at", statuses)]


def claim_due_posts():
    """Atomically move due posts to 'publishing' so a post is never published twice."""
    now = to_utc_iso(datetime.now(timezone.utc))
    c = _conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM posts WHERE status='scheduled' AND scheduled_at <= ?", (now,))]
        for r in rows:
            c.execute("UPDATE posts SET status='publishing', updated_at=? WHERE id=?", (now, r["id"]))
        c.commit()
        return rows
    finally:
        c.close()


def set_result(post_id, status, results: dict):
    with _conn() as c:
        c.execute("UPDATE posts SET status=?, results=?, updated_at=? WHERE id=?",
                  (status, json.dumps(results), to_utc_iso(datetime.now(timezone.utc)), post_id))


def fail_stuck_posts():
    """If the worker died mid-publish, mark those posts failed (safer than re-posting blindly)."""
    with _conn() as c:
        rows = list(c.execute("SELECT id, results FROM posts WHERE status='publishing'"))
        for r in rows:
            res = json.loads(r["results"] or "{}")
            res["_note"] = "Worker stopped while publishing. Check your pages, then retry if needed."
            c.execute("UPDATE posts SET status='failed', results=? WHERE id=?", (json.dumps(res), r["id"]))
        return len(rows)


def reschedule(post_id, new_dt):
    with _conn() as c:
        c.execute("UPDATE posts SET status='scheduled', scheduled_at=?, updated_at=? WHERE id=?",
                  (to_utc_iso(new_dt), to_utc_iso(datetime.now(timezone.utc)), post_id))


def delete_post(post_id):
    with _conn() as c:
        row = c.execute("SELECT media_path FROM posts WHERE id=?", (post_id,)).fetchone()
        c.execute("DELETE FROM posts WHERE id=?", (post_id,))
        return row["media_path"] if row else None
