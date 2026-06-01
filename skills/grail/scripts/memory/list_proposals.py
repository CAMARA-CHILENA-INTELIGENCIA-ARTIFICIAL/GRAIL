"""List proposals from the most-recent consolidate run.

Usage:
    python scripts/memory/list_proposals.py --project <ref>
    python scripts/memory/list_proposals.py --project <ref> --status pending
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import (  # noqa: E402
    Reply,
    open_memory_project,
    project_envelope,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = argparse.ArgumentParser(description="List proposals.")
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--status", default=None,
        help="pending | accepted | rejected | accepted-pending-manual",
    )
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    mp = open_memory_project(project)
    reply = mp.list_proposals(status=args.status)

    return Reply(
        ok=reply.ok,
        mode="memory",
        project=project_envelope(project),
        data=reply.data,
        warnings=list(reply.warnings or []),
        next_steps=list(reply.next_steps or []),
        error=reply.error,
    )


if __name__ == "__main__":
    run(main)
