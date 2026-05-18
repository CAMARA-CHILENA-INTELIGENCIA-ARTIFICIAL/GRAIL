"""
StorageBackend — the abstract interface every backend implements.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

GRAIL writes a lot of small artefacts (parquet tables, JSON manifests, GraphML files,
zipped bundles) and reads them back during search. Decoupling that from the
filesystem lets us run the same pipeline against S3, a temp dir, or an in-memory
fake without rewriting the indexing modules.

The interface is intentionally narrow:

* ``exists(key)`` / ``delete(key)``
* ``list(prefix)`` → list of keys
* ``read_bytes(key)`` / ``write_bytes(key, data)`` — primitives
* ``read_text(key)`` / ``write_text(key, content)`` — convenience text views
* ``open_for_read(key)`` / ``open_for_write(key)`` — context managers that yield a path
  on disk for libraries (lancedb, pyarrow.parquet, networkx) that insist on a real file.

Async support is bolted on for the operations that show up on the hot path (mostly
metadata + parquet I/O). Anything else uses the sync surface plus ``asyncio.to_thread``
internally.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


class StorageBackend(ABC):
    """Abstract base for GRAIL storage backends.

    Keys are forward-slash separated paths relative to the project root. The local
    backend treats them as plain paths; cloud backends treat them as object keys.
    """

    # ------------------------------------------------------------------ metadata

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def list(self, prefix: str = "") -> list[str]: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    # ------------------------------------------------------------------ bytes

    @abstractmethod
    def read_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def write_bytes(self, key: str, data: bytes) -> None: ...

    # ------------------------------------------------------------------ text helpers

    def read_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(key).decode(encoding)

    def write_text(self, key: str, content: str, encoding: str = "utf-8") -> None:
        self.write_bytes(key, content.encode(encoding))

    # ------------------------------------------------------------------ path views

    @abstractmethod
    @contextmanager
    def open_for_read(self, key: str) -> Iterator[Path]:
        """Yield a local path containing ``key``. Cloud backends download into a temp dir."""

    @abstractmethod
    @contextmanager
    def open_for_write(self, key: str) -> Iterator[Path]:
        """Yield a local path; on exit, the contents are uploaded to ``key``."""

    @abstractmethod
    def join(self, *parts: str) -> str:
        """Return a backend-native key by joining ``parts`` with forward slashes."""

    # ------------------------------------------------------------------ bulk helpers

    def copy_in(self, local_path: str | Path, key: str) -> None:
        """Copy a local file into storage at ``key``. Default impl uses read_bytes/write_bytes."""
        with open(local_path, "rb") as fh:
            self.write_bytes(key, fh.read())

    def copy_out(self, key: str, local_path: str | Path) -> None:
        """Copy a stored object out to ``local_path``."""
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as fh:
            fh.write(self.read_bytes(key))

    def ensure_prefix(self, prefix: str) -> None:
        """Backends may use this to create directories; default is no-op."""
        return None

    # ------------------------------------------------------------------ optional async

    async def aread_bytes(self, key: str) -> bytes:
        import asyncio

        return await asyncio.to_thread(self.read_bytes, key)

    async def awrite_bytes(self, key: str, data: bytes) -> None:
        import asyncio

        await asyncio.to_thread(self.write_bytes, key, data)


def normalize_key(key: str) -> str:
    """Strip leading/trailing slashes and collapse repeated slashes."""
    parts = [p for p in key.replace("\\", "/").split("/") if p]
    return "/".join(parts)


def split_key(key: str) -> tuple[str, str]:
    """Split a key into (prefix, basename)."""
    key = normalize_key(key)
    if "/" not in key:
        return "", key
    prefix, _, base = key.rpartition("/")
    return prefix, base


__all__ = ["StorageBackend", "normalize_key", "split_key"]
