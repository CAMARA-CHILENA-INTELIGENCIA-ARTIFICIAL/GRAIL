"""
Shared helpers for the GRAIL skill scripts.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

* ``Reply`` — JSON envelope every script emits. Mirrors ``grail.memory.Reply``.
* ``run`` — decorator that wraps ``main()`` and enforces the envelope on
  every exit path (including uncaught exceptions).
* ``resolve_project_ref`` — accepts a path, a registered name, or a ULID
  prefix and returns the absolute project path.
* ``project_envelope`` — turns a path into the ``{id, name, path}`` block
  that every reply carries.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class Reply:
    """JSON envelope returned by every skill script.

    ``ok`` is mandatory. The rest is optional — populate the fields that
    apply and the encoder drops the empty ones from the output so the
    payload stays small.
    """

    ok: bool
    data: Any = None
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    error: Optional[str] = None
    mode: Optional[str] = None
    project: Optional[dict[str, Any]] = None

    def emit(self) -> None:
        # Plain print (no rich) — JSON must be machine-parseable.
        out: dict[str, Any] = {"ok": bool(self.ok)}
        if self.mode:
            out["mode"] = self.mode
        if self.project:
            out["project"] = self.project
        if self.data is not None:
            out["data"] = self.data
        if self.warnings:
            out["warnings"] = list(self.warnings)
        if self.next_steps:
            out["next_steps"] = list(self.next_steps)
        if self.error:
            out["error"] = self.error
        print(json.dumps(out, default=str))
        sys.exit(0 if self.ok else 1)


def run(fn: Callable[[], Any]) -> None:
    """Wrap ``main()`` and always emit a JSON envelope.

    Catches every exception so the agent never gets a Python traceback on
    stdout — it gets ``{"ok": false, "error": "..."}`` and the traceback
    in ``data.traceback`` for diagnostics.
    """
    try:
        result = fn()
        if isinstance(result, Reply):
            result.emit()
        else:
            Reply(ok=True, data=result).emit()
    except SystemExit:
        # ``Reply.emit`` already called sys.exit; let it through.
        raise
    except BaseException as exc:  # noqa: BLE001 — we want to capture everything
        Reply(
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            data={"traceback": traceback.format_exc()},
        ).emit()


# ---------------------------------------------------------------- registry / ref resolution


def _looks_like_path(ref: str) -> bool:
    """Heuristic: ``ref`` is a path if it has a slash, dot, or tilde."""
    if not ref:
        return False
    return any(token in ref for token in ("/", "\\", ".", "~"))


def resolve_project_ref(ref: str) -> Path:
    """Turn a user-supplied project ref into an absolute path.

    Resolution order:
      1. ``ref`` looks like a path → expand + resolve; verify it exists.
      2. Otherwise, search the workspace registry by ``name`` (exact, case-
         insensitive), then by ``id`` (prefix, ≥8 chars to avoid collisions).
      3. None match → ``FileNotFoundError`` with the list of known projects.
    """
    if not ref:
        raise ValueError("--project is required.")
    if _looks_like_path(ref):
        p = Path(ref).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(
                f"project path does not exist: {p}"
            )
        return p

    from grail.memory.identity import list_projects

    known = list_projects()
    if not known:
        raise FileNotFoundError(
            "no projects registered. Either create one with init_project.py "
            "or pass --project as a filesystem path."
        )

    # Name lookup (exact, case-insensitive).
    ref_lower = ref.lower()
    name_hits = [e for e in known if str(e.get("name", "")).lower() == ref_lower]
    if len(name_hits) == 1:
        return Path(name_hits[0]["path"]).expanduser().resolve()
    if len(name_hits) > 1:
        raise ValueError(
            f"name {ref!r} is ambiguous — multiple registered projects. "
            "Pass the absolute path or a ULID prefix."
        )

    # ULID-prefix lookup.
    if len(ref) >= 8:
        id_hits = [e for e in known if str(e.get("id", "")).startswith(ref)]
        if len(id_hits) == 1:
            return Path(id_hits[0]["path"]).expanduser().resolve()
        if len(id_hits) > 1:
            raise ValueError(
                f"id prefix {ref!r} is ambiguous — extend it to disambiguate."
            )

    listing = ", ".join(
        f"{e.get('name', '?')} ({str(e.get('id', ''))[:8]})" for e in known
    )
    raise FileNotFoundError(
        f"no project matches {ref!r}. Known projects: {listing}"
    )


def project_envelope(project_path: Path) -> dict[str, Any]:
    """Read ``meta.json`` and return the ``{id, name, path, mode}`` block.

    Falls back gracefully when ``meta.json`` is missing — the envelope
    still has ``path`` so the agent knows what was acted on.
    """
    out: dict[str, Any] = {"path": str(project_path)}
    try:
        from grail.memory.identity import read_meta

        meta = read_meta(project_path)
        if meta is not None:
            out["id"] = meta.id
            out["name"] = meta.name
            out["mode"] = meta.mode
    except Exception:
        pass
    return out


def project_mode(project_path: Path) -> str:
    """Resolve the project's mode — meta.json first, grail.yaml fallback."""
    try:
        from grail.memory.identity import read_meta

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


# ---------------------------------------------------------------- argparse helpers


def project_argparser(*, description: str) -> argparse.ArgumentParser:
    """Argparse with ``--project`` baked in. Every script uses this."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "--project", required=True,
        help="Project ref: path, registered name, or ULID prefix.",
    )
    return p


def open_memory_project(project_path: Path):
    """Open a project as a ``MemoryProject``. Lazy import keeps argparse fast."""
    from grail.memory import MemoryProject

    return MemoryProject(project_path)


def load_grail(project_path: Path):
    """Open a project as a ``GRAIL`` instance (for KB-mode ops)."""
    from grail import GRAIL, load_config

    cfg = load_config(project_path)
    return GRAIL.from_config(cfg)


__all__ = [
    "Reply",
    "load_grail",
    "open_memory_project",
    "project_argparser",
    "project_envelope",
    "project_mode",
    "resolve_project_ref",
    "run",
]
