"""Look up entities whose names look like ``--name``.

Usage:
    python scripts/memory/find_similar_entity.py --project <ref> --name "dr smith"

Call this BEFORE ``add_entity`` so the agent can decide whether the new
entity is actually a duplicate. Uses exact match + Jaro-Winkler edit
distance; when embeddings are configured, also cosine similarity.
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
    ap = argparse.ArgumentParser(description="Find similar entity names.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    mp = open_memory_project(project)
    reply = asyncio.run(mp.find_similar_entity(args.name, top_k=args.top_k))

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
