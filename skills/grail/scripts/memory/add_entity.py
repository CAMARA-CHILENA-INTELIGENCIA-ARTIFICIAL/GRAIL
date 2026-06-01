"""Declare a stand-alone entity without an underlying observation file.

Usage:
    python scripts/memory/add_entity.py --project <ref> \
        --name ALICE_SMITH --type PERSON --description "..."

Warning: the entity has no source provenance (empty ``text_unit_ids`` and
``document_ids``). Prefer ``add_observation`` so the fact is grounded in
a memory file.
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
    ap = argparse.ArgumentParser(description="Declare a stand-alone entity.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--type", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--retrieval-queries", nargs="*", default=[])
    ap.add_argument("--community", action="append", default=[])
    ap.add_argument("--confidence", type=float, default=1.0)
    ap.add_argument("--source", default=None)
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    mp = open_memory_project(project)
    reply = asyncio.run(
        mp.add_entity(
            name=args.name,
            type=args.type,
            description=args.description,
            retrieval_queries=list(args.retrieval_queries),
            community_ids=list(args.community),
            confidence=args.confidence,
            source=args.source,
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
