"""SQLite storage; short-lived connections and WAL support web + SMTP threads."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator


class Database:
    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 15000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def init(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_part TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias_id INTEGER NOT NULL REFERENCES aliases(id) ON DELETE CASCADE,
                    sender TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    preview TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    received_at INTEGER NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS messages_received ON messages(received_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS messages_alias ON messages(alias_id, received_at DESC);
                CREATE INDEX IF NOT EXISTS aliases_active ON aliases(active, local_part);
            """)

    def list_aliases(self, domain: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""
                SELECT a.id, a.local_part, a.active, a.created_at,
                COUNT(m.id) AS message_count,
                COALESCE(SUM(CASE WHEN m.is_read=0 THEN 1 ELSE 0 END),0) AS unread_count
                FROM aliases a LEFT JOIN messages m ON m.alias_id=a.id
                GROUP BY a.id ORDER BY a.created_at DESC, a.id DESC
            """).fetchall()
            return [dict(id=r["id"], local_part=r["local_part"], address=f'{r["local_part"]}@{domain}',
                         active=bool(r["active"]), created_at=r["created_at"],
                         message_count=r["message_count"], unread_count=r["unread_count"]) for r in rows]

    def create_alias(self, local_part: str, max_aliases: int) -> tuple[int | None, str]:
        """Atomic cap and hourly cap, including concurrent web requests."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            if count >= max_aliases:
                return None, "limit"
            recent = db.execute("SELECT COUNT(*) FROM aliases WHERE created_at >= ?", (int(time.time()) - 3600,)).fetchone()[0]
            if recent >= 10:
                return None, "rate"
            try:
                cursor = db.execute("INSERT INTO aliases(local_part,created_at) VALUES(?,?)", (local_part, int(time.time())))
            except sqlite3.IntegrityError:
                return None, "exists"
            return int(cursor.lastrowid), "ok"

    def get_alias(self, alias_id: int) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute("SELECT * FROM aliases WHERE id=?", (alias_id,)).fetchone()

    def set_alias_active(self, alias_id: int, active: bool) -> bool:
        with self.connect() as db:
            cursor = db.execute("UPDATE aliases SET active=? WHERE id=?", (int(active), alias_id))
            return cursor.rowcount > 0

    def delete_alias(self, alias_id: int) -> bool:
        with self.connect() as db:
            cursor = db.execute("DELETE FROM aliases WHERE id=?", (alias_id,))
            return cursor.rowcount > 0

    def recipient_alias_id(self, local_part: str) -> int | None:
        with self.connect() as db:
            row = db.execute("SELECT id FROM aliases WHERE local_part=? COLLATE NOCASE AND active=1", (local_part,)).fetchone()
            return int(row["id"]) if row else None

    def save_messages(self, alias_ids: list[int], sender: str, subject: str, body: str,
                      message_id: str, *, retention_days: int, max_stored_messages: int) -> int:
        now = int(time.time())
        saved = 0
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for alias_id in set(alias_ids):
                # Re-check status after acceptance: deleted/disabled recipients are not delivered.
                row = db.execute("SELECT 1 FROM aliases WHERE id=? AND active=1", (alias_id,)).fetchone()
                if not row:
                    continue
                db.execute("""INSERT INTO messages
                    (alias_id,sender,subject,body,preview,message_id,received_at)
                    VALUES (?,?,?,?,?,?,?)""",
                    (alias_id, sender, subject, body, " ".join(body.split())[:180], message_id, now))
                saved += 1
            db.execute("DELETE FROM messages WHERE received_at < ?", (now - retention_days * 86400,))
            db.execute("""DELETE FROM messages WHERE id IN (
                SELECT id FROM messages ORDER BY received_at DESC, id DESC LIMIT -1 OFFSET ?
            )""", (max_stored_messages,))
        return saved

    def cleanup(self, retention_days: int, max_stored_messages: int) -> None:
        now = int(time.time())
        with self.connect() as db:
            db.execute("DELETE FROM messages WHERE received_at < ?", (now - retention_days * 86400,))
            db.execute("""DELETE FROM messages WHERE id IN (
                SELECT id FROM messages ORDER BY received_at DESC, id DESC LIMIT -1 OFFSET ?
            )""", (max_stored_messages,))

    def list_messages(self, alias_id: int | None, q: str, unread_only: bool = False,
                      before_id: int | None = None, limit: int = 51) -> list[dict]:
        where = []
        params: list = []
        if alias_id is not None:
            where.append("m.alias_id=?")
            params.append(alias_id)
        if unread_only:
            where.append("m.is_read=0")
        if before_id is not None:
            where.append("m.id < ?")
            params.append(before_id)
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(m.sender LIKE ? ESCAPE '\\' OR m.subject LIKE ? ESCAPE '\\' OR m.preview LIKE ? ESCAPE '\\')")
            params += [f"%{escaped}%"] * 3
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self.connect() as db:
            rows = db.execute("""SELECT m.id, m.alias_id, a.local_part, m.sender, m.subject,
                m.preview, m.received_at, m.is_read FROM messages m
                JOIN aliases a ON a.id=m.alias_id""" + clause +
                " ORDER BY m.id DESC LIMIT ?", (*params, limit)).fetchall()
            return [{**dict(r), "is_read": bool(r["is_read"])} for r in rows]

    def get_message(self, message_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("""SELECT m.*, a.local_part FROM messages m
                JOIN aliases a ON a.id=m.alias_id WHERE m.id=?""", (message_id,)).fetchone()
            return {**dict(row), "is_read": bool(row["is_read"])} if row else None

    def set_read(self, message_id: int, value: bool) -> bool:
        with self.connect() as db:
            c = db.execute("UPDATE messages SET is_read=? WHERE id=?", (int(value), message_id))
            return c.rowcount > 0

    def delete_message(self, message_id: int) -> bool:
        with self.connect() as db:
            c = db.execute("DELETE FROM messages WHERE id=?", (message_id,))
            return c.rowcount > 0

    def stats(self) -> dict:
        with self.connect() as db:
            active = db.execute("SELECT COUNT(*) FROM aliases WHERE active=1").fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            unread = db.execute("SELECT COUNT(*) FROM messages WHERE is_read=0").fetchone()[0]
            return dict(active_aliases=active, message_count=count, unread_count=unread)

    def create_session(self, token_hash: str, csrf: str, expires_at: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
            db.execute("INSERT INTO sessions(token_hash, csrf, expires_at) VALUES(?,?,?)",
                       (token_hash, csrf, expires_at))

    def get_session(self, token_hash: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT csrf, expires_at FROM sessions WHERE token_hash=? AND expires_at>?",
                             (token_hash, int(time.time()))).fetchone()
            return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
