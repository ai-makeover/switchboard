"""SQLite on the service volume: drafts and the send ledger used for pacing.

A draft holds the exact recipient and text. Once it's sent, discarded or expired its text is wiped,
so the database never becomes an archive of message content.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    token_hash TEXT UNIQUE NOT NULL,
    channel TEXT NOT NULL,
    chat_raw TEXT NOT NULL,
    recipient_name TEXT,
    recipient_number TEXT,
    is_group INTEGER NOT NULL DEFAULT 0,
    text TEXT,
    links TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    decided_at REAL
);
CREATE TABLE IF NOT EXISTS sends (
    channel TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sends_channel_at ON sends(channel, at);
CREATE INDEX IF NOT EXISTS drafts_created ON drafts(created_at);
"""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    # ---- drafts ---------------------------------------------------------------------------------

    def drafts_in_last_hour(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM drafts WHERE created_at > ?", (time.time() - 3600,)).fetchone()[0]

    def create_draft(self, *, channel, chat_raw, recipient_name, recipient_number, is_group, text, links,
                     created_by, ttl_s) -> tuple[str, str]:
        draft_id = "d_" + secrets.token_hex(6)
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.db.execute(
            "INSERT INTO drafts (id, token_hash, channel, chat_raw, recipient_name, recipient_number, is_group,"
            " text, links, created_by, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (draft_id, token_hash(token), channel, chat_raw, recipient_name, recipient_number, int(is_group),
             text, json.dumps(links), created_by, now, now + ttl_s),
        )
        return draft_id, token

    def by_token(self, token: str):
        self.expire()
        return self.db.execute("SELECT * FROM drafts WHERE token_hash = ?", (token_hash(token),)).fetchone()

    def claim(self, draft_id: str) -> bool:
        """pending -> sending, exactly once. A second tap, a replayed POST or a race all get False."""
        cur = self.db.execute(
            "UPDATE drafts SET status='sending' WHERE id=? AND status='pending' AND expires_at > ?",
            (draft_id, time.time()),
        )
        return cur.rowcount == 1

    def finish(self, draft_id: str, status: str) -> None:
        assert status in ("sent", "discarded", "failed")
        self.db.execute("UPDATE drafts SET status=?, text=NULL, decided_at=? WHERE id=?", (status, time.time(), draft_id))

    def discard(self, draft_id: str) -> bool:
        cur = self.db.execute(
            "UPDATE drafts SET status='discarded', text=NULL, decided_at=? WHERE id=? AND status='pending'",
            (time.time(), draft_id),
        )
        return cur.rowcount == 1

    def expire(self) -> None:
        self.db.execute(
            "UPDATE drafts SET status='expired', text=NULL WHERE status='pending' AND expires_at <= ?", (time.time(),)
        )

    # ---- pacing ---------------------------------------------------------------------------------

    def record_send(self, channel: str, at: float | None = None) -> None:
        self.db.execute("INSERT INTO sends (channel, at) VALUES (?, ?)", (channel, at or time.time()))

    def pacing(self, channel: str, limits: dict) -> int:
        """Seconds to wait before this channel may send again (0 = go)."""
        now = time.time()
        q = self.db.execute
        last = q("SELECT MAX(at) FROM sends WHERE channel=?", (channel,)).fetchone()[0]
        waits = [0.0]
        if last:
            waits.append(last + limits["min_gap_s"] - now)
        hour = q("SELECT at FROM sends WHERE channel=? AND at > ? ORDER BY at", (channel, now - 3600)).fetchall()
        if len(hour) >= limits["per_hour"]:
            waits.append(hour[len(hour) - limits["per_hour"]][0] + 3600 - now)
        day = q("SELECT at FROM sends WHERE channel=? AND at > ? ORDER BY at", (channel, now - 86400)).fetchall()
        if len(day) >= limits["per_day"]:
            waits.append(day[len(day) - limits["per_day"]][0] + 86400 - now)
        return max(0, int(max(waits) + 0.999))
