"""Filesystem-backed storage.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from grail.storage.base import StorageBackend, normalize_key


class LocalStorage(StorageBackend):
    """Plain filesystem storage rooted at a single directory.

    All keys are interpreted as paths relative to :attr:`root`. The root is created
    on first use if it does not exist.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers

    def _path(self, key: str) -> Path:
        key = normalize_key(key)
        target = (self.root / key).resolve()
        # Refuse traversal outside the root.
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError(f"Key {key!r} escapes the storage root.") from exc
        return target

    def join(self, *parts: str) -> str:
        return normalize_key("/".join(parts))

    # ------------------------------------------------------------------ metadata

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list(self, prefix: str = "") -> list[str]:
        base = self._path(prefix) if prefix else self.root
        if not base.exists():
            return []
        out: list[str] = []
        if base.is_file():
            out.append(str(base.relative_to(self.root)).replace(os.sep, "/"))
            return out
        for path in base.rglob("*"):
            if path.is_file():
                out.append(str(path.relative_to(self.root)).replace(os.sep, "/"))
        return sorted(out)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def ensure_prefix(self, prefix: str) -> None:
        self._path(prefix).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ bytes

    def read_bytes(self, key: str) -> bytes:
        with self._path(key).open("rb") as fh:
            return fh.read()

    def write_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("wb") as fh:
            fh.write(data)
        os.replace(tmp, path)

    # ------------------------------------------------------------------ paths

    @contextmanager
    def open_for_read(self, key: str) -> Iterator[Path]:
        yield self._path(key)

    @contextmanager
    def open_for_write(self, key: str) -> Iterator[Path]:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        yield path

    # ------------------------------------------------------------------ bulk overrides

    def copy_in(self, local_path: str | Path, key: str) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)

    def copy_out(self, key: str, local_path: str | Path) -> None:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._path(key), local_path)

    def path_for(self, key: str) -> Path:
        """Escape hatch: return the filesystem :class:`Path` for callers (e.g. lancedb)
        that need a real on-disk location.
        """
        return self._path(key)

    def __repr__(self) -> str:
        return f"LocalStorage(root={self.root!s})"
