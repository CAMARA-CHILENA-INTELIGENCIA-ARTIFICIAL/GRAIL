"""Search a GRAIL project. Works for both KB and memory mode.

Usage:
    python scripts/query.py --project <ref> --query "what did acme say"
    python scripts/query.py --project <ref> --mode recall --since 1h \
        --category 'work/clients/**' --tag pricing

Modes:
  * ``local``   — entity-anchored search (default for KB).
  * ``cascade`` — entity-gate + text rescue (most robust factual queries).
  * ``global``  — community-report synthesis (broad / thematic).
  * ``document``— scoped to one source file (requires --document).
  * ``agent``   — LLM picks tools across the above.
  * ``recall``  — zero-LLM structural filter (default for memory).

Filter flags (compose with any mode):
  --since / --before (ISO-8601 or relative: 1h, 7d, "2 weeks ago")
  --category 'work/clients/**'  (folder glob)
  --tag pricing  (repeatable)
  --entity-name ALICE  (repeatable)
  --type PERSON  (repeatable)
  --min-confidence 0.7
"""
from __future__ import annotations

import argparse
import asyncio

from _common import (
    Reply,
    load_grail,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = argparse.ArgumentParser(description="Search a GRAIL project.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--query", default="", help="The question to ask.")
    ap.add_argument(
        "--mode",
        default=None,
        help="local | cascade | global | document | agent | recall.",
    )
    ap.add_argument("--document", default=None, help="Filename for --mode document.")
    ap.add_argument("--since", default=None)
    ap.add_argument("--before", default=None)
    ap.add_argument("--category", default=None)
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--entity-name", action="append", default=[])
    ap.add_argument("--type", action="append", default=[])
    ap.add_argument("--min-confidence", type=float, default=None)
    ap.add_argument(
        "--rerank", dest="rerank", action="store_true", default=None,
        help="Override the reranker config to ON for this query.",
    )
    ap.add_argument(
        "--no-rerank", dest="rerank", action="store_false",
        help="Override the reranker config to OFF for this query.",
    )
    args = ap.parse_args()

    project = resolve_project_ref(args.project)
    mode = project_mode(project)

    # Default search mode = best for the project type.
    search_mode = args.mode or ("recall" if mode == "memory" else "cascade")
    if search_mode != "recall" and not args.query:
        return Reply(
            ok=False,
            mode=mode,
            project=project_envelope(project),
            error="--query is required for every mode except --mode recall.",
        )
    if search_mode == "document" and not args.document:
        return Reply(
            ok=False,
            mode=mode,
            project=project_envelope(project),
            error="--mode document requires --document <filename>.",
        )

    from grail.query.recall_filter import RecallFilter

    rfilter = RecallFilter(
        since=args.since,
        before=args.before,
        category=args.category,
        tags=list(args.tag),
        entity_names=list(args.entity_name),
        entity_types=list(args.type),
        min_confidence=args.min_confidence,
    )

    grail = load_grail(project)
    try:
        if search_mode == "agent":
            result = asyncio.run(grail.agent_search(args.query))
        else:
            result = asyncio.run(
                grail.search(
                    args.query,
                    mode=search_mode,
                    document=args.document,
                    use_reranker=args.rerank,
                    filter=rfilter if not rfilter.is_empty() else None,
                )
            )
    except ValueError as exc:
        return Reply(
            ok=False,
            mode=mode,
            project=project_envelope(project),
            error=f"search failed: {exc}",
        )

    # Render context_data DataFrames as counts; the agent can call
    # ``explore.py`` if it needs the raw rows.
    context_stats: dict[str, int] = {}
    if isinstance(result.context_data, dict):
        for k, v in result.context_data.items():
            if hasattr(v, "__len__"):
                context_stats[k] = int(len(v))

    response = (
        result.response
        if isinstance(result.response, str)
        else result.response
    )

    return Reply(
        ok=True,
        mode=mode,
        project=project_envelope(project),
        data={
            "search_mode": search_mode,
            "response": response,
            "context_stats": context_stats,
            "completion_time": float(result.completion_time),
            "llm_calls": int(result.llm_calls),
            "cost": grail.cost_tracker.render_total_cost(),
            "filter_active": not rfilter.is_empty(),
        },
    )


if __name__ == "__main__":
    run(main)
