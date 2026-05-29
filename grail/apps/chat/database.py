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
    source TEXT NOT NULL DEFAULT 'web',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    tool_calls TEXT,
    tool_call_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""

_MIGRATIONS = [
    "ALTER TABLE messages ADD COLUMN tool_calls TEXT",
    "ALTER TABLE messages ADD COLUMN tool_call_id TEXT",
    "ALTER TABLE sessions ADD COLUMN source TEXT NOT NULL DEFAULT 'web'",
]


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
        for migration in _MIGRATIONS:
            try:
                await db.execute(migration)
            except Exception:
                pass
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


async def list_sessions(user_id: str, source: Optional[str] = None) -> list[dict[str, Any]]:
    """List sessions for a user. If *source* is given, filter by source (e.g. 'web' or 'cli')."""
    async with get_db() as db:
        if source is None:
            cursor = await db.execute(
                """
                SELECT s.id, s.title, s.mode, s.source, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM messages WHERE session_id = s.id AND role IN ('user', 'assistant') AND tool_calls IS NULL) AS message_count
                FROM sessions s
                WHERE s.user_id = ?
                ORDER BY s.updated_at DESC
                """,
                (user_id,),
            )
        else:
            cursor = await db.execute(
                """
                SELECT s.id, s.title, s.mode, s.source, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM messages WHERE session_id = s.id AND role IN ('user', 'assistant') AND tool_calls IS NULL) AS message_count
                FROM sessions s
                WHERE s.user_id = ? AND s.source = ?
                ORDER BY s.updated_at DESC
                """,
                (user_id, source),
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "title": r[1], "mode": r[2], "source": r[3],
                "created_at": r[4], "updated_at": r[5], "message_count": r[6],
            }
            for r in rows
        ]


async def create_session(
    user_id: str, title: str = "New Chat", mode: str = "local", source: str = "web",
) -> dict[str, Any]:
    session_id = _uuid()
    now = _now()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO sessions (id, user_id, title, mode, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, title, mode, source, now, now),
        )
        await db.commit()
    return {
        "id": session_id, "title": title, "mode": mode, "source": source,
        "created_at": now, "updated_at": now,
    }


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


def _row_to_message(r: tuple) -> dict[str, Any]:
    """Convert a DB row to a message dict."""
    msg: dict[str, Any] = {
        "id": r[0], "role": r[1], "content": r[2],
        "metadata": json.loads(r[3]), "created_at": r[4],
    }
    if r[5]:
        msg["tool_calls"] = json.loads(r[5])
    if r[6]:
        msg["tool_call_id"] = r[6]
    return msg


async def get_messages(session_id: str, *, include_tool_messages: bool = False) -> list[dict[str, Any]]:
    """Get messages for display. By default excludes tool-call machinery."""
    async with get_db() as db:
        if include_tool_messages:
            cursor = await db.execute(
                "SELECT id, role, content, metadata, created_at, tool_calls, tool_call_id "
                "FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT id, role, content, metadata, created_at, tool_calls, tool_call_id "
                "FROM messages WHERE session_id = ? "
                "AND role IN ('user', 'assistant') AND tool_calls IS NULL "
                "ORDER BY created_at ASC",
                (session_id,),
            )
        rows = await cursor.fetchall()
        return [_row_to_message(r) for r in rows]


async def create_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict[str, Any]] = None,
    tool_calls: Optional[list[dict[str, Any]]] = None,
    tool_call_id: Optional[str] = None,
) -> dict[str, Any]:
    msg_id = _uuid()
    now = _now()
    meta_json = json.dumps(metadata or {})
    tc_json = json.dumps(tool_calls) if tool_calls else None
    async with get_db() as db:
        await db.execute(
            "INSERT INTO messages (id, session_id, role, content, metadata, tool_calls, tool_call_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, meta_json, tc_json, tool_call_id, now),
        )
        await db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()
    msg: dict[str, Any] = {
        "id": msg_id, "role": role, "content": content,
        "metadata": metadata or {}, "created_at": now,
    }
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if tool_call_id:
        msg["tool_call_id"] = tool_call_id
    return msg


async def create_messages_batch(
    session_id: str, messages: list[dict[str, Any]],
) -> None:
    """Insert a batch of messages preserving order (for agent tool-call sequences)."""
    base = datetime.now(timezone.utc)
    async with get_db() as db:
        for i, msg in enumerate(messages):
            msg_id = _uuid()
            ts = (base + __import__("datetime").timedelta(microseconds=i)).isoformat()
            meta_json = json.dumps(msg.get("metadata") or {})
            tc = msg.get("tool_calls")
            tc_json = json.dumps(tc) if tc else None
            await db.execute(
                "INSERT INTO messages (id, session_id, role, content, metadata, tool_calls, tool_call_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (msg_id, session_id, msg["role"], msg.get("content", ""),
                 meta_json, tc_json, msg.get("tool_call_id"), ts),
            )
        await db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (base.isoformat(), session_id),
        )
        await db.commit()


async def get_recent_messages(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent messages including tool-call messages for history building."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, role, content, metadata, created_at, tool_calls, tool_call_id
            FROM messages WHERE session_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        rows = list(reversed(rows))
        return [_row_to_message(r) for r in rows]
