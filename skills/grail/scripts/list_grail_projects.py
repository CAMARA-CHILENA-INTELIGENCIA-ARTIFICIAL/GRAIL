"""List GRAIL projects registered in ``~/.grail/registry.json``.

Usage:
    python scripts/list_grail_projects.py [--rescan]

``--rescan`` is reserved for v2 — for now the registry is the source of
truth and is updated by every ``init_project.py`` / SDK ``MemoryProject``
call.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import Reply, run


def main() -> Reply:
    ap = argparse.ArgumentParser(description="List registered GRAIL projects.")
    ap.add_argument(
        "--rescan",
        action="store_true",
        help="(v2) Rebuild the registry by walking ``meta.json`` under known paths.",
    )
    args = ap.parse_args()

    from grail.memory.identity import list_projects

    projects = list_projects()
    # Annotate with on-disk presence (meta.json may have moved).
    for p in projects:
        path = Path(str(p.get("path", ""))).expanduser()
        p["exists"] = path.exists()
        p["meta_exists"] = (path / "meta.json").exists() if path.exists() else False

    notes: list[str] = []
    if args.rescan:
        notes.append("--rescan is not implemented yet; returning the cached registry.")

    return Reply(
        ok=True,
        data={"projects": projects, "count": len(projects)},
        warnings=notes,
        next_steps=(
            ["scripts/init_project.py — create your first project"]
            if not projects
            else ["scripts/status.py --project <ref>"]
        ),
    )


if __name__ == "__main__":
    run(main)
