"""Run the full LLM-driven indexing pipeline (KB mode).

Usage:
    python scripts/index.py --project <ref> [--discover-entities]

Reads files from ``<project>/input/`` and emits parquet artefacts under
``<project>/output/runs/<run_id>/``. The CLI's ``grail index`` is the
canonical implementation — this script wraps the SDK and returns a JSON
envelope.

Costs LLM tokens. For a memory project, prefer the SDK / memory scripts
which run with no LLM.
"""
from __future__ import annotations

import asyncio

from _common import (
    Reply,
    load_grail,
    project_argparser,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = project_argparser(description="Run the LLM-driven indexing pipeline.")
    ap.add_argument(
        "--discover-entities",
        action="store_true",
        help="Let the LLM propose entity types from the corpus before extraction.",
    )
    args = ap.parse_args()
    project = resolve_project_ref(args.project)
    mode = project_mode(project)

    warnings: list[str] = []
    if mode == "memory":
        warnings.append(
            "This is a memory project. Observations are tool-managed; "
            "indexing only runs if you've also dropped files into ./input/."
        )

    grail = load_grail(project)
    if args.discover_entities:
        grail.config.indexing.discover_entity_types = True

    result = asyncio.run(grail.index())
    if not result.get("ok"):
        return Reply(
            ok=False,
            mode=mode,
            project=project_envelope(project),
            error=str(result.get("reason") or "index failed"),
            data=result,
        )

    return Reply(
        ok=True,
        mode=mode,
        project=project_envelope(project),
        data={
            "entities": int(result.get("entities", 0)),
            "relationships": int(result.get("relationships", 0)),
            "text_units": int(result.get("text_units", 0)),
            "communities": int(result.get("communities", 0)),
            "community_reports": int(result.get("reports", 0)),
            "run_id": result.get("run_id"),
            "cost": grail.cost_tracker.render_total_cost(),
        },
        warnings=warnings,
        next_steps=[
            "scripts/query.py --project <ref> --query '...'",
            "scripts/status.py --project <ref>",
        ],
    )


if __name__ == "__main__":
    run(main)
