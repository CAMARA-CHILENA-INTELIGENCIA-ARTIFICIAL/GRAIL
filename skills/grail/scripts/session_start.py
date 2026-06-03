"""Session-start probe — call this ONCE per session and cache the result.

Usage:
    python scripts/session_start.py

Returns one JSON envelope with everything the agent needs to route for the
rest of the session:

  * ``setup`` — is ``graphgrail`` installed, what version, in a venv?
  * ``projects`` — registered GRAIL projects with quick stats
    (entities, observations, mode) per project, so the agent can pitch
    save/consolidate/recall without re-reading parquets later
  * ``next_steps`` — directive recommendations the agent should act on
    (or remember) for the rest of the session.

CACHE THE RESULT. Do not re-run setup.sh or list_grail_projects.py within
the same session. Only re-run ``session_start.py`` when the agent creates
or deletes a project mid-session.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from _common import Reply, run


def _grail_state() -> dict[str, Any]:
    """Probe whether ``graphgrail`` is importable + venv state."""
    try:
        from grail import __version__ as grail_version
    except ImportError:
        return {
            "ok": False,
            "status": "not-installed",
            "grail_version": None,
            "in_venv": _in_venv(),
            "python": sys.executable,
        }
    return {
        "ok": True,
        "status": "already-installed",
        "grail_version": grail_version,
        "in_venv": _in_venv(),
        "python": sys.executable,
    }


def _in_venv() -> bool:
    return (
        sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        or "VIRTUAL_ENV" in os.environ
    )


def _project_quick_stats(project_path: Path) -> dict[str, Any]:
    """Cheap per-project read: artefact counts + observation count."""
    import pandas as pd  # lazy — only when needed

    output = project_path / "output"
    active = output
    # KB projects write under output/runs/<run_id>/.
    current = output / "current.json"
    if current.exists():
        try:
            raw = json.loads(current.read_text(encoding="utf-8"))
            active = project_path / raw.get("run_dir", "output")
        except Exception:
            pass

    def _count(parquet_name: str) -> int:
        p = active / parquet_name
        if not p.exists():
            return 0
        try:
            return int(len(pd.read_parquet(p)))
        except Exception:
            return -1

    stats = {
        "entities": _count("final_entities.parquet"),
        "relationships": _count("final_relationships.parquet"),
        "communities": _count("final_communities.parquet"),
        "documents": _count("final_docs.parquet"),
    }

    # Memory-mode observation count: walk memories/ on disk.
    memories = project_path / "memories"
    if memories.exists():
        stats["observations"] = sum(
            1
            for p in memories.rglob("*.md")
            if not p.name.startswith(".")
        )
    else:
        stats["observations"] = 0

    # Pending proposals (memory mode).
    proposals_dir = output / "proposals"
    if proposals_dir.exists():
        pending = []
        for y in proposals_dir.glob("*.yaml"):
            if y.name == "latest.yaml":
                continue
            try:
                import yaml as _yaml

                ps = _yaml.safe_load(y.read_text(encoding="utf-8")) or {}
                pending.extend(
                    p for p in (ps.get("proposals") or [])
                    if p.get("status") == "pending"
                )
            except Exception:
                continue
        stats["pending_proposals"] = len(pending)
    else:
        stats["pending_proposals"] = 0

    return stats


def _build_next_steps(
    setup: dict[str, Any],
    projects: list[dict[str, Any]],
) -> list[str]:
    out: list[str] = []
    if not setup["ok"]:
        out.append("graphgrail is not installed — run `bash scripts/setup.sh`")
        return out
    if not projects:
        out.append(
            "User has no GRAIL projects yet. If this is a real conversation "
            "(not a one-shot lookup), propose creating one: "
            "`scripts/init_project.py --project ./my-memory --memory --name my-memory`"
        )
        return out

    # Active projects exist — push the agent toward using them.
    out.append(
        f"User has {len(projects)} project(s). Before answering a question that "
        "could plausibly live in them, run `scripts/query.py --project <ref> "
        "--query \"...\"` — do not answer from training data first."
    )
    for proj in projects:
        name = proj.get("name", "?")
        mode = proj.get("mode", "?")
        ents = proj.get("entities", 0) or 0
        obs = proj.get("observations", 0) or 0
        pending = proj.get("pending_proposals", 0) or 0
        if mode == "memory" and ents >= 30:
            out.append(
                f"Project '{name}' has {ents} entities — eligible for "
                f"`scripts/memory/consolidate.py --project {name}` to surface communities."
            )
        if pending:
            out.append(
                f"Project '{name}' has {pending} pending proposal(s) — review with "
                f"`scripts/memory/list_proposals.py --project {name}`."
            )
        if obs == 0 and mode == "memory":
            out.append(
                f"Project '{name}' (memory) has no observations yet. "
                "Propose adding the first one when the user shares save-worthy content."
            )
    return out


def _summary(setup: dict[str, Any], projects: list[dict[str, Any]]) -> str:
    if not setup["ok"]:
        return "graphgrail not installed"
    if not projects:
        return f"graphgrail {setup['grail_version']} installed; no projects yet"
    by_mode: dict[str, int] = {}
    for p in projects:
        by_mode[p.get("mode", "?")] = by_mode.get(p.get("mode", "?"), 0) + 1
    counts = ", ".join(f"{n} {m}" for m, n in sorted(by_mode.items()))
    return f"graphgrail {setup['grail_version']} installed; projects: {counts}"


def main() -> Reply:
    setup = _grail_state()

    projects: list[dict[str, Any]] = []
    if setup["ok"]:
        # graphgrail is importable — list projects + per-project stats.
        try:
            from grail.memory.identity import list_projects

            for entry in list_projects():
                proj_path = Path(str(entry.get("path", ""))).expanduser()
                stats: dict[str, Any] = {}
                if proj_path.exists():
                    try:
                        stats = _project_quick_stats(proj_path)
                    except Exception as exc:  # pragma: no cover - defensive
                        stats = {"error": f"{type(exc).__name__}: {exc}"}
                projects.append(
                    {
                        "id": entry.get("id"),
                        "name": entry.get("name"),
                        "mode": entry.get("mode"),
                        "path": entry.get("path"),
                        "exists": proj_path.exists(),
                        **stats,
                    }
                )
        except Exception as exc:  # pragma: no cover - defensive
            return Reply(
                ok=False,
                error=f"failed to list projects: {type(exc).__name__}: {exc}",
                data={"setup": setup, "projects": []},
            )

    return Reply(
        ok=True,
        data={
            "setup": setup,
            "projects": projects,
            "summary": _summary(setup, projects),
        },
        next_steps=_build_next_steps(setup, projects),
    )


if __name__ == "__main__":
    run(main)
