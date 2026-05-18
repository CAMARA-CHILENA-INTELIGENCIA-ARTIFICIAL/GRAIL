"""
Disk-backed cache for LLM responses.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Cache key derives from ``(model, messages, temperature, max_tokens, response_format,
top_p, stop)``. Hits return immediately. Misses block on the LLM call and write the
result to disk. Entries are grouped by ``session_id`` so users can inspect what one
logical operation consumed.

The cache is intentionally simple JSON-on-disk — robust enough for the kinds of
re-runs that happen during iterative indexing / debugging, while being easy to
inspect, copy, and version. Swap for SQLite later if it becomes a hot spot.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional


def _hash_key(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LLMCache:
    """Filesystem cache. One JSON file per (session, key) pair.

    Enable with ``LLMCache(directory=..., enabled=True)``. When ``enabled=False`` all
    operations no-op so callers can leave the cache hooked up in production.
    """

    def __init__(
        self,
        directory: str | Path | None = None,
        *,
        enabled: bool = False,
    ) -> None:
        self.enabled = enabled
        self.directory = Path(directory) if directory else None
        if self.enabled and self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _path_for(self, session_id: str, key: str) -> Path:
        assert self.directory is not None
        return self.directory / session_id / f"{key}.json"

    def make_key(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[dict[str, Any]] = None,
        top_p: Optional[float] = None,
        stop: Optional[list[str]] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "top_p": top_p,
            "stop": stop,
            "extra": extra or {},
        }
        return _hash_key(payload)

    async def get(self, session_id: str, key: str) -> Optional[str]:
        if not self.enabled or self.directory is None:
            return None
        path = self._path_for(session_id, key)
        if not path.exists():
            return None
        try:
            return await asyncio.to_thread(self._read_text, path)
        except OSError:
            return None

    async def set(self, session_id: str, key: str, value: str) -> None:
        if not self.enabled or self.directory is None:
            return
        path = self._path_for(session_id, key)
        async with self._lock:
            await asyncio.to_thread(self._write_text, path, value)

    def clear(self, session_id: str | None = None) -> int:
        """Delete cache entries. Returns count removed. Useful for tests / iteration."""
        if self.directory is None:
            return 0
        root = self.directory / session_id if session_id else self.directory
        if not root.exists():
            return 0
        count = 0
        for path in root.rglob("*.json"):
            try:
                path.unlink()
                count += 1
            except OSError:
                pass
        return count

    @staticmethod
    def _read_text(path: Path) -> str:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)["value"]

    @staticmethod
    def _write_text(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump({"value": value}, fh, ensure_ascii=False)
        os.replace(tmp, path)
