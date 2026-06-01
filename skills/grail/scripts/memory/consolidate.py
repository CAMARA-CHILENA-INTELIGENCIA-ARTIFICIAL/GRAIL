"""Run the proposal analyses on a memory project.

Usage:
    python scripts/memory/consolidate.py --project <ref>

Pure read pass — never mutates parquets. Writes a yaml file under
``<project>/output/proposals/<ULID>.yaml`` and returns its path + a
summary of proposals by kind. Use ``list_proposals.py`` to inspect them
and ``apply_proposal.py`` to act on each one.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import (  # noqa: E402
    Reply,
    open_memory_project,
    project_argparser,
    project_envelope,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = project_argparser(description="Generate proposals for a memory project.")
    args = ap.parse_args()
    project = resolve_project_ref(args.project)
    mp = open_memory_project(project)
    reply = mp.consolidate()

    next_steps: list[str] = []
    if reply.ok and (reply.data or {}).get("total"):
        next_steps = [
            "scripts/memory/list_proposals.py --project <ref>",
            "scripts/memory/apply_proposal.py --project <ref> --id <prefix> --accept",
        ]

    return Reply(
        ok=reply.ok,
        mode="memory",
        project=project_envelope(project),
        data=reply.data,
        warnings=list(reply.warnings or []),
        next_steps=next_steps + list(reply.next_steps or []),
        error=reply.error,
    )


if __name__ == "__main__":
    run(main)
