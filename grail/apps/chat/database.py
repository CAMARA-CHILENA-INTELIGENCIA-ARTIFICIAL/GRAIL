"""
SQLite database layer for the GRAIL chat API.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import aiosqlite

_db_path: Path = Path.home() / ".grail" / "chat.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    mode TEXT NOT NULL DEFAULT 'local',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""


def configure_db_path(path: Path) -> None:
    global _db_path
    _db_path = path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


async def init_db() -> None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(_db_path)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(_SCHEMA)
        await db.commit()


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    db = await aiosqlite.connect(str(_db_path))
    await db.execute("PRAGMA foreign_keys=ON")
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


# ------------------------------------------------------------------ Users


async def get_user_count() -> int:
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0]


async def create_user(username: str, password_hash: str) -> dict[str, Any]:
    user_id = _uuid()
    now = _now()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, password_hash, now),
        )
        await db.commit()
    return {"id": user_id, "username": username, "created_at": now}


async def get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (username,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "password_hash": row[2], "created_at": row[3]}


async def get_user_by_id(user_id: str) -> Optional[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "created_at": row[2]}


# ------------------------------------------------------------------ Sessions


async def list_sessions(user_id: str) -> list[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT s.id, s.title, s.mode, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM messages WHERE session_id = s.id) AS message_count
            FROM sessions s
            WHERE s.user_id = ?
            ORDER BY s.updated_at DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "title": r[1], "mode": r[2],
                "created_at": r[3], "updated_at": r[4], "message_count": r[5],
            }
            for r in rows
        ]


async def create_session(user_id: str, title: str = "New Chat", mode: str = "local") -> dict[str, Any]:
    session_id = _uuid()
    now = _now()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO sessions (id, user_id, title, mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_id, title, mode, now, now),
        )
        await db.commit()
    return {"id": session_id, "title": title, "mode": mode, "created_at": now, "updated_at": now}


async def get_session(session_id: str, user_id: str) -> Optional[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, user_id, title, mode, created_at, updated_at FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "user_id": row[1], "title": row[2],
            "mode": row[3], "created_at": row[4], "updated_at": row[5],
        }


async def update_session(session_id: str, user_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    allowed = {"title", "mode"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_session(session_id, user_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [session_id, user_id]
    async with get_db() as db:
        await db.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ? AND user_id = ?",
            values,
        )
        await db.commit()
    return await get_session(session_id, user_id)


async def delete_session(session_id: str, user_id: str) -> bool:
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ------------------------------------------------------------------ Messages


async def get_messages(session_id: str) -> list[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, role, content, metadata, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "role": r[1], "content": r[2],
                "metadata": json.loads(r[3]), "created_at": r[4],
            }
            for r in rows
        ]


async def create_message(
    session_id: str, role: str, content: str, metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    msg_id = _uuid()
    now = _now()
    meta_json = json.dumps(metadata or {})
    async with get_db() as db:
        await db.execute(
            "INSERT INTO messages (id, session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, meta_json, now),
        )
        await db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()
    return {"id": msg_id, "role": role, "content": content, "metadata": metadata or {}, "created_at": now}


async def get_recent_messages(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, role, content, metadata, created_at
            FROM messages WHERE session_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        rows = list(reversed(rows))
        return [
            {
                "id": r[0], "role": r[1], "content": r[2],
                "metadata": json.loads(r[3]), "created_at": r[4],
            }
            for r in rows
        ]
