"""List GRAIL projects known to this user.

Discovery order:

  1. Scan ``~/.grail/projects/*/meta.json`` directly (the default location
     for projects created via ``init_project.py`` with a bare name).
  2. Merge with ``~/.grail/registry.json`` entries (for projects created
     at custom paths via the SDK or with an explicit ``--project /abs/path``).
  3. Dedupe by ULID. Filesystem entries win on conflict (the registry can
     drift; the disk is the truth).
  4. Drop registry entries pointing at paths that no longer exist on disk
     — those are the stale-pointer footguns we used to surface.

Each returned project is annotated with ``source``:
  * ``"home"`` — found at ``~/.grail/projects/<name>/``
  * ``"custom"`` — found via registry at some other path
  * ``"stale"`` — registry entry whose path doesn't exist (returned only
    when ``--include-stale`` is passed)

Usage:
    python scripts/list_grail_projects.py
    python scripts/list_grail_projects.py --include-stale
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import Reply, discover_projects, run


_HOME_PROJECTS = Path.home() / ".grail" / "projects"


def main() -> Reply:
    ap = argparse.ArgumentParser(description="List registered GRAIL projects.")
    ap.add_argument(
        "--include-stale",
        action="store_true",
        help="Include registry entries whose path no longer exists on disk.",
    )
    ap.add_argument(
        "--rescan",
        action="store_true",
        help="(v2) Rebuild the registry by walking known paths.",
    )
    args = ap.parse_args()

    projects = discover_projects(include_stale=args.include_stale)

    warnings: list[str] = []
    stale_count = sum(1 for p in projects if p["source"] == "stale")
    if stale_count and not args.include_stale:
        warnings.append(
            f"{stale_count} registry entry(ies) point at gone paths — "
            "pass --include-stale to see them."
        )
    if args.rescan:
        warnings.append(
            "--rescan is reserved for v2; the current run already scans the "
            "filesystem before the registry."
        )

    next_steps: list[str] = []
    if not projects:
        next_steps.append(
            "scripts/init_project.py --project <name> --memory  "
            "(creates ~/.grail/projects/<name>/)"
        )
    else:
        next_steps.append("scripts/status.py --project <name-or-path>")

    return Reply(
        ok=True,
        data={
            "projects": projects,
            "count": len(projects),
            "home_dir": str(_HOME_PROJECTS),
            "by_source": {
                "home": sum(1 for p in projects if p["source"] == "home"),
                "custom": sum(1 for p in projects if p["source"] == "custom"),
                "stale": stale_count,
            },
        },
        warnings=warnings,
        next_steps=next_steps,
    )


if __name__ == "__main__":
    run(main)
