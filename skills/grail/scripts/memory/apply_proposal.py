"""Accept or reject a single proposal.

Usage:
    python scripts/memory/apply_proposal.py --project <ref> --id 01HFZP3J --accept
    python scripts/memory/apply_proposal.py --project <ref> --id 01HFZP3J --reject \
        --reason "not worth the noise"

``--id`` accepts an unambiguous prefix of the ULID.
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
    ap = argparse.ArgumentParser(description="Accept or reject a proposal.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--id", required=True, help="Proposal id or prefix.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--accept", action="store_true")
    group.add_argument("--reject", action="store_true")
    ap.add_argument("--reason", default=None, help="Optional rejection reason.")
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    mp = open_memory_project(project)
    if args.accept:
        reply = mp.accept_proposal(args.id)
    else:
        reply = mp.reject_proposal(args.id, reason=args.reason)

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
