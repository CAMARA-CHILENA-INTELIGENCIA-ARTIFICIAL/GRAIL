"""
Project identity: ULID generation, meta.json, workspace registry.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

* ``meta.json`` lives at the project root and carries the immutable id, the
  display name, the project mode, and a few timestamps. It's machine-managed:
  agents and humans should not edit it by hand.
* ``~/.grail/registry.json`` is a cache of known projects across the user's
  machine so ``list_grail_projects`` doesn't have to crawl the filesystem.
  ``meta.json`` is authoritative — the registry can be rebuilt from it.
* ULIDs are hand-rolled (Crockford Base32, 26 chars, sortable by timestamp).
  Avoids a new package dependency.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# Crockford Base32 — excludes I, L, O, U to dodge visual ambiguity.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(now_ms: Optional[int] = None) -> str:
    """Return a 26-char Crockford Base32 ULID.

    Layout: 10 chars timestamp (ms since epoch) + 16 chars randomness.
    Sortable by creation time when compared lexically — useful for
    timestamp-prefixed filenames.
    """
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    # 48-bit timestamp → 10 chars (each char = 5 bits, 50 bits available).
    ts_chars = []
    for _ in range(10):
        ts_chars.append(_CROCKFORD[ts & 0x1F])
        ts >>= 5
    ts_part = "".join(reversed(ts_chars))
    # 80 bits of randomness → 16 chars.
    rand = secrets.randbits(80)
    rand_chars = []
    for _ in range(16):
        rand_chars.append(_CROCKFORD[rand & 0x1F])
        rand >>= 5
    rand_part = "".join(reversed(rand_chars))
    return ts_part + rand_part


def _now_iso() -> str:
    """Current time as ISO-8601 UTC, second-precision (compact for meta.json)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- meta.json


@dataclass
class ProjectMeta:
    """Per-project identity record, persisted at ``<project>/meta.json``."""

    schema_version: int = 1
    id: str = ""
    name: str = ""
    mode: str = "knowledge_base"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    last_indexed_at: Optional[str] = None
    grail_version: str = ""

    @classmethod
    def fresh(
        cls,
        *,
        name: str,
        mode: str,
        description: str = "",
        tags: Optional[list[str]] = None,
        grail_version: str = "",
    ) -> "ProjectMeta":
        return cls(
            schema_version=1,
            id=new_ulid(),
            name=name,
            mode=mode,
            description=description,
            tags=list(tags or []),
            created_at=_now_iso(),
            grail_version=grail_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "description": self.description,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "last_indexed_at": self.last_indexed_at,
            "grail_version": self.grail_version,
        }


def meta_path(project_path: str | os.PathLike) -> Path:
    return Path(project_path) / "meta.json"


def read_meta(project_path: str | os.PathLike) -> Optional[ProjectMeta]:
    p = meta_path(project_path)
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    return ProjectMeta(
        schema_version=int(raw.get("schema_version", 1)),
        id=str(raw.get("id", "")),
        name=str(raw.get("name", "")),
        mode=str(raw.get("mode", "knowledge_base")),
        description=str(raw.get("description", "")),
        tags=list(raw.get("tags", []) or []),
        created_at=str(raw.get("created_at", "")),
        last_indexed_at=raw.get("last_indexed_at"),
        grail_version=str(raw.get("grail_version", "")),
    )


def write_meta(project_path: str | os.PathLike, meta: ProjectMeta) -> Path:
    p = meta_path(project_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta.to_dict(), indent=2) + "\n", encoding="utf-8")
    return p


def touch_indexed(project_path: str | os.PathLike) -> None:
    """Update ``last_indexed_at`` to now. Silent no-op if meta.json missing."""
    m = read_meta(project_path)
    if m is None:
        return
    m.last_indexed_at = _now_iso()
    write_meta(project_path, m)


# ---------------------------------------------------------------- registry


def registry_path(home: Optional[str | os.PathLike] = None) -> Path:
    """``~/.grail/registry.json`` by default; override for tests."""
    base = Path(home).expanduser() if home else Path.home()
    return base / ".grail" / "registry.json"


def _load_registry(reg_path: Path) -> dict[str, Any]:
    if not reg_path.exists():
        return {"schema_version": 1, "projects": []}
    try:
        return json.loads(reg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "projects": []}


def _save_registry(reg_path: Path, data: dict[str, Any]) -> None:
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def register_project(
    project_path: str | os.PathLike,
    meta: ProjectMeta,
    *,
    home: Optional[str | os.PathLike] = None,
) -> None:
    """Add or update a project entry in the workspace registry.

    Idempotent — same ``id`` overwrites the existing row; new ``id`` appends.
    """
    reg = _load_registry(registry_path(home))
    entries: list[dict[str, Any]] = reg.setdefault("projects", [])
    abspath = str(Path(project_path).expanduser().resolve())
    new_entry = {
        "id": meta.id,
        "name": meta.name,
        "mode": meta.mode,
        "path": abspath,
        "last_seen": _now_iso(),
    }
    for i, entry in enumerate(entries):
        if entry.get("id") == meta.id:
            entries[i] = new_entry
            break
    else:
        entries.append(new_entry)
    _save_registry(registry_path(home), reg)


def list_projects(home: Optional[str | os.PathLike] = None) -> list[dict[str, Any]]:
    return list(_load_registry(registry_path(home)).get("projects", []))


def unregister_project(
    project_id: str, *, home: Optional[str | os.PathLike] = None
) -> bool:
    """Remove a project from the registry. Returns True if a row was dropped."""
    reg = _load_registry(registry_path(home))
    entries: list[dict[str, Any]] = reg.get("projects", [])
    before = len(entries)
    reg["projects"] = [e for e in entries if e.get("id") != project_id]
    if len(reg["projects"]) == before:
        return False
    _save_registry(registry_path(home), reg)
    return True


__all__ = [
    "ProjectMeta",
    "new_ulid",
    "meta_path",
    "read_meta",
    "write_meta",
    "touch_indexed",
    "registry_path",
    "register_project",
    "list_projects",
    "unregister_project",
]
