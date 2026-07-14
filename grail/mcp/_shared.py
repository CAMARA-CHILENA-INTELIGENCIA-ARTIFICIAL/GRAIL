"""
Shared helpers for the GRAIL MCP server.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Mirrors the project-resolution and JSON-envelope logic the skill scripts use
(``skills/grail/scripts/_common.py``), but lives in the package so the MCP
server is self-contained and shippable in the wheel. The MCP server only runs
when ``grail`` is installed, so — unlike the skill ``_common`` — these helpers
import ``grail`` eagerly.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from grail.memory.identity import list_projects, read_meta

_HOME_PROJECTS = Path.home() / ".grail" / "projects"


# ---------------------------------------------------------------- project resolution


def _looks_like_path(ref: str) -> bool:
    return bool(ref) and any(t in ref for t in ("/", "\\", ".", "~"))


def resolve_project_ref(ref: str) -> Path:
    """Turn a project ref (path, registered name, or ULID prefix) into a path.

    Resolution order matches the skill: explicit path → ``~/.grail/projects/<name>``
    → registry name (exact, case-insensitive) → registry id prefix (≥8 chars).
    """
    if not ref:
        raise ValueError("project is required (path, registered name, or ULID prefix).")
    if _looks_like_path(ref):
        p = Path(ref).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"project path does not exist: {p}")
        return p

    home_candidate = (_HOME_PROJECTS / ref).expanduser().resolve()
    if (home_candidate / "meta.json").exists():
        return home_candidate

    known = [e for e in list_projects() if Path(str(e.get("path", ""))).expanduser().exists()]
    if not known:
        raise FileNotFoundError(
            "no projects found. Create one (memory_create_project / kb_create_project) "
            "or pass project as a filesystem path."
        )

    ref_lower = ref.lower()
    name_hits = [e for e in known if str(e.get("name", "")).lower() == ref_lower]
    if len(name_hits) == 1:
        return Path(name_hits[0]["path"]).expanduser().resolve()
    if len(name_hits) > 1:
        raise ValueError(f"name {ref!r} is ambiguous — pass the path or a ULID prefix.")

    if len(ref) >= 8:
        id_hits = [e for e in known if str(e.get("id", "")).startswith(ref)]
        if len(id_hits) == 1:
            return Path(id_hits[0]["path"]).expanduser().resolve()
        if len(id_hits) > 1:
            raise ValueError(f"id prefix {ref!r} is ambiguous — extend it.")

    listing = ", ".join(f"{e.get('name', '?')} ({str(e.get('id', ''))[:8]})" for e in known)
    raise FileNotFoundError(f"no project matches {ref!r}. Known projects: {listing}")


def discover_projects(*, include_stale: bool = False) -> list[dict[str, Any]]:
    """All GRAIL projects for this user — home-dir scan first, then registry."""
    import json as _json

    out: list[dict[str, Any]] = []
    home_ids: set[str] = set()
    if _HOME_PROJECTS.exists():
        for child in sorted(_HOME_PROJECTS.iterdir()):
            meta_path = child / "meta.json"
            if not child.is_dir() or not meta_path.exists():
                continue
            try:
                meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            except (_json.JSONDecodeError, OSError):
                continue
            entry_id = str(meta.get("id", ""))
            home_ids.add(entry_id)
            out.append(
                {
                    "id": entry_id,
                    "name": str(meta.get("name", child.name)),
                    "mode": str(meta.get("mode", "knowledge_base")),
                    "path": str(child),
                    "source": "home",
                    "exists": True,
                }
            )
    for entry in list_projects():
        entry_id = str(entry.get("id", ""))
        if entry_id and entry_id in home_ids:
            continue
        path = Path(str(entry.get("path", ""))).expanduser()
        exists = path.exists()
        if not exists and not include_stale:
            continue
        out.append(
            {
                "id": entry_id,
                "name": str(entry.get("name", "")),
                "mode": str(entry.get("mode", "knowledge_base")),
                "path": str(path),
                "source": "custom" if exists else "stale",
                "exists": exists,
            }
        )
    return out


def project_envelope(project_path: Path) -> dict[str, Any]:
    """The ``{id, name, path, mode}`` block every reply carries."""
    out: dict[str, Any] = {"path": str(project_path)}
    try:
        meta = read_meta(project_path)
        if meta is not None:
            out["id"] = meta.id
            out["name"] = meta.name
            out["mode"] = meta.mode
    except Exception:
        pass
    return out


def project_mode(project_path: Path) -> str:
    """Resolve a project's mode — meta.json first, grail.yaml fallback."""
    try:
        meta = read_meta(project_path)
        if meta is not None and meta.mode:
            return str(meta.mode)
    except Exception:
        pass
    try:
        from grail import load_config

        return str(load_config(project_path).mode or "knowledge_base")
    except Exception:
        return "knowledge_base"


# ---------------------------------------------------------------- core openers


def open_memory_project(project_path: Path):
    from grail.memory import MemoryProject

    return MemoryProject(project_path)


def load_grail(project_path: Path):
    from grail import GRAIL, load_config

    return GRAIL.from_config(load_config(project_path))


# ---------------------------------------------------------------- serialization


def _jsonable(value: Any) -> Any:
    """Best-effort conversion of core return values to JSON-safe structures."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def reply(
    ok: bool,
    *,
    data: Any = None,
    mode: str | None = None,
    project: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    next_steps: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the JSON envelope MCP tools return — same shape as the skill."""
    out: dict[str, Any] = {"ok": bool(ok)}
    if mode:
        out["mode"] = mode
    if project:
        out["project"] = project
    if data is not None:
        out["data"] = _jsonable(data)
    if warnings:
        out["warnings"] = list(warnings)
    if next_steps:
        out["next_steps"] = list(next_steps)
    if error:
        out["error"] = error
    return out


def reply_from_core(core_reply: Any, project_path: Path) -> dict[str, Any]:
    """Wrap a ``grail.memory.Reply`` (or its ``.to_dict()``) with the project block."""
    base = core_reply.to_dict() if hasattr(core_reply, "to_dict") else dict(core_reply)
    return reply(
        bool(base.get("ok")),
        data=base.get("data"),
        mode=project_mode(project_path),
        project=project_envelope(project_path),
        warnings=base.get("warnings"),
        next_steps=base.get("next_steps"),
        error=base.get("error"),
    )


def search_result_data(result: Any, *, search_mode: str, cost: str, filter_active: bool) -> dict[str, Any]:
    """Compact a ``SearchResult`` into the same dict the skill's query.py emits."""
    context_stats: dict[str, int] = {}
    if isinstance(result.context_data, dict):
        for k, v in result.context_data.items():
            if hasattr(v, "__len__"):
                context_stats[k] = int(len(v))
    return {
        "search_mode": search_mode,
        "response": result.response,
        "context_stats": context_stats,
        "completion_time": float(result.completion_time),
        "llm_calls": int(result.llm_calls),
        "cost": cost,
        "filter_active": filter_active,
    }
