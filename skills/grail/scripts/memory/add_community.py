"""Declare a community (typically folder-as-community).

Usage:
    python scripts/memory/add_community.py --project <ref> \
        --community-id work/clients/acme \
        --title "Acme client interactions" \
        --members ALICE BOB ACME \
        --report '@meta.md'   # or inline string
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
    ap = argparse.ArgumentParser(description="Declare a community + optional report.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--community-id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--members", nargs="+", required=True)
    ap.add_argument("--kind", default="folder", help="folder | discovered | leiden.")
    ap.add_argument(
        "--report", default=None,
        help='Report markdown (or "@path/to/meta.md" to read from file).',
    )
    ap.add_argument("--rank", type=float, default=5.0)
    ap.add_argument("--level", type=int, default=0)
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    report = args.report
    if report and report.startswith("@"):
        report = Path(report[1:]).expanduser().read_text(encoding="utf-8")

    mp = open_memory_project(project)
    reply = mp.add_community(
        community_id=args.community_id,
        title=args.title,
        member_entity_names=list(args.members),
        kind=args.kind,
        report_content=report,
        rank=args.rank,
        level=args.level,
    )

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
