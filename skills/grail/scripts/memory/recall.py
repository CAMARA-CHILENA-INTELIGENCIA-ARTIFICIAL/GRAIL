"""Structural / temporal recall — no LLM, no embedding.

Usage:
    python scripts/memory/recall.py --project <ref> --since 1h
    python scripts/memory/recall.py --project <ref> \
        --category 'work/clients/**' --tag pricing
    python scripts/memory/recall.py --project <ref> \
        --query "acme pricing" --mode cascade --since 7d   # LLM-backed

This wraps the universal ``query.py`` for the common no-LLM case; pass
``--mode cascade`` (or local / global / document) plus ``--query`` for
the modifier-style composition.
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
    ap = argparse.ArgumentParser(description="Recall observations / entities.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--query", default=None)
    ap.add_argument("--mode", default="recall")
    ap.add_argument("--since", default=None)
    ap.add_argument("--before", default=None)
    ap.add_argument("--category", default=None)
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--entity-name", action="append", default=[], dest="entity_names")
    ap.add_argument("--type", action="append", default=[], dest="entity_types")
    ap.add_argument("--min-confidence", type=float, default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    mp = open_memory_project(project)
    reply = asyncio.run(
        mp.recall(
            query=args.query,
            mode=args.mode,
            since=args.since,
            before=args.before,
            category=args.category,
            tags=list(args.tag),
            entity_names=list(args.entity_names),
            entity_types=list(args.entity_types),
            min_confidence=args.min_confidence,
            limit=args.limit,
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
