"""Quick graph-shape report (KB or memory).

Usage:
    python scripts/explore.py --project <ref> [--top-k 10]

Returns top entities by degree, community sizes, and overall counts.
Pure pandas — no LLM, no embedding.
"""
from __future__ import annotations

import argparse

import pandas as pd

from _common import (
    Reply,
    project_argparser,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = project_argparser(description="Inspect a GRAIL project's graph shape.")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()
    project = resolve_project_ref(args.project)

    from grail.query.retrieval import load_artifacts_for_search
    from grail.storage import LocalStorage

    storage = LocalStorage(root=project)
    # KB projects write under output/runs/<id>/. Resolve the active run via
    # output/current.json so we read the latest artefacts.
    import json as _json
    output_folder = "output"
    current = project / "output" / "current.json"
    if current.exists():
        try:
            raw = _json.loads(current.read_text(encoding="utf-8"))
            output_folder = raw.get("run_dir") or "output"
        except Exception:
            pass
    arts = load_artifacts_for_search(storage, output_folder=output_folder)
    if arts.entities.empty:
        return Reply(
            ok=True,
            mode=project_mode(project),
            project=project_envelope(project),
            data={"empty": True},
            next_steps=["scripts/index.py or scripts/memory/add_observation.py"],
        )

    ents = arts.entities.copy()
    if "degree" not in ents.columns:
        ents["degree"] = 0
    top_entities = (
        ents.sort_values("degree", ascending=False)
        .head(args.top_k)[["name", "type", "degree"]]
        .to_dict(orient="records")
    )

    type_counts = ents["type"].value_counts().to_dict() if "type" in ents.columns else {}
    community_sizes: dict[str, int] = {}
    if not arts.communities.empty and "community" in arts.communities.columns:
        community_sizes = {
            str(row["community"]): int(row.get("size", 0) or 0)
            for _, row in arts.communities.iterrows()
        }

    return Reply(
        ok=True,
        mode=project_mode(project),
        project=project_envelope(project),
        data={
            "counts": {
                "entities": int(len(arts.entities)),
                "relationships": int(len(arts.relationships)),
                "text_units": int(len(arts.text_units)),
                "documents": int(len(arts.documents)),
                "communities": int(len(arts.communities)),
                "community_reports": int(len(arts.community_reports)),
            },
            "top_entities_by_degree": top_entities,
            "type_counts": {str(k): int(v) for k, v in type_counts.items()},
            "community_sizes": community_sizes,
        },
    )


if __name__ == "__main__":
    run(main)
