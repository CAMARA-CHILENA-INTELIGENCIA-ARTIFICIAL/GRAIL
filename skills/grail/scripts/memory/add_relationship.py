"""Declare a typed relationship between two existing entities.

Usage:
    python scripts/memory/add_relationship.py --project <ref> \
        --source ALICE --target ACME \
        --type WORKS_AT --description "Alice is the rep for Acme."
"""
from __future__ import annotations

import argparse
import asyncio
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
    ap = argparse.ArgumentParser(description="Declare a relationship.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--type", default="RELATED", dest="relationship_type")
    ap.add_argument("--description", required=True)
    ap.add_argument("--weight", type=float, default=1.0)
    ap.add_argument("--confidence", type=float, default=1.0)
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    mp = open_memory_project(project)
    reply = asyncio.run(
        mp.add_relationship(
            source=args.source,
            target=args.target,
            relationship_type=args.relationship_type,
            description=args.description,
            weight=args.weight,
            confidence=args.confidence,
        )
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
