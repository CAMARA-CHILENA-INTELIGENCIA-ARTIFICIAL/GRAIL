"""Write a memory observation: markdown file + parquet rows.

Usage:
    python scripts/memory/add_observation.py --project <ref> \
        --title "Meeting with Acme" \
        --content "John said pricing should drop 15%..." \
        --category work/clients/acme \
        --tag meeting --tag pricing \
        --observed-at 2026-05-27T15:30:00Z \
        --entities '[{"name":"JOHN_SMITH","type":"PERSON","description":"Acme negotiator"}]' \
        --relationships '[{"source":"JOHN_SMITH","target":"ACME","relationship_type":"WORKS_AT","description":"..."}]'

Atomic: writes the file, parses frontmatter, merges into parquets, updates
the audit log — single SDK call so the agent never has to chain. Returns
the observation id, slug, file path, and what changed in the graph.
"""
from __future__ import annotations

import argparse
import asyncio
import json
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


def _parse_json_arg(raw: str | None, label: str) -> list[dict]:
    if raw is None:
        return []
    s = raw.strip()
    if not s:
        return []
    # Allow ``@file.json`` for large payloads.
    if s.startswith("@"):
        s = Path(s[1:]).expanduser().read_text(encoding="utf-8")
    try:
        out = json.loads(s)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--{label} is not valid JSON: {exc}")
    if not isinstance(out, list):
        raise ValueError(f"--{label} must be a JSON array of objects.")
    return out


def main() -> Reply:
    ap = argparse.ArgumentParser(description="Write a memory observation.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--content", required=True, help="Markdown body. Prefix ``@`` to read from a file.")
    ap.add_argument("--category", default=None, help="Folder community, e.g. work/clients/acme.")
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--observed-at", default=None, help="ISO-8601 timestamp.")
    ap.add_argument("--confidence", type=float, default=1.0)
    ap.add_argument("--source", default=None, help="Provenance attribution e.g. agent-claude.")
    ap.add_argument(
        "--entities", default=None,
        help='JSON array. Each entry: {"name", "type", "description", optional "retrieval_queries"}.',
    )
    ap.add_argument(
        "--relationships", default=None,
        help='JSON array. Each entry: {"source", "target", optional "relationship_type", "description"}.',
    )
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    content = args.content
    if content.startswith("@"):
        content = Path(content[1:]).expanduser().read_text(encoding="utf-8")

    entities = _parse_json_arg(args.entities, "entities")
    relationships = _parse_json_arg(args.relationships, "relationships")

    mp = open_memory_project(project)
    reply = asyncio.run(
        mp.add_observation(
            title=args.title,
            content=content,
            category=args.category,
            tags=list(args.tag),
            observed_at=args.observed_at,
            confidence=args.confidence,
            source=args.source,
            entities=entities,
            relationships=relationships,
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
