"""Append new source files to an existing KB index incrementally.

Usage:
    python scripts/append.py --project <ref> --files path/a.pdf path/b.md

Each file is copied into ``<project>/input/`` (if it isn't already there)
and incrementally processed: chunk → extract → merge → update communities.
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from _common import (
    Reply,
    load_grail,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = argparse.ArgumentParser(description="Append new files to a KB index.")
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--files",
        nargs="+",
        required=True,
        help="Files to append. Copied into <project>/input/ if not there.",
    )
    args = ap.parse_args()
    project = resolve_project_ref(args.project)
    mode = project_mode(project)

    warnings: list[str] = []
    if mode == "memory":
        warnings.append(
            "This is a memory project. ``append`` operates on the LLM-driven "
            "indexing path; for agent-supplied observations use "
            "memory/add_observation.py instead."
        )

    input_dir = project / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for f in args.files:
        src = Path(f).expanduser().resolve()
        if not src.exists():
            return Reply(ok=False, error=f"file not found: {src}")
        dest = input_dir / src.name
        if dest.resolve() != src:
            shutil.copy2(src, dest)
        copied.append(dest.name)

    grail = load_grail(project)
    # GRAIL.append's parameter is ``new_files`` (snake_case, plural). Earlier
    # versions of this script passed ``files=`` which TypeErrored on the
    # underlying SDK call.
    result = asyncio.run(grail.append(new_files=copied))
    if not result.get("ok"):
        return Reply(
            ok=False,
            mode=mode,
            project=project_envelope(project),
            error=str(result.get("reason") or "append failed"),
            data=result,
        )

    return Reply(
        ok=True,
        mode=mode,
        project=project_envelope(project),
        data={
            "appended_files": copied,
            "new_entities": int(result.get("new_entities", 0)),
            "new_relationships": int(result.get("new_relationships", 0)),
            "cost": grail.cost_tracker.render_total_cost(),
        },
        warnings=warnings,
        next_steps=["scripts/query.py --project <ref> --query '...'"],
    )


if __name__ == "__main__":
    run(main)
