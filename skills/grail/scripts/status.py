"""Inspect a project: mode, artefact counts, last-indexed timestamp.

Usage:
    python scripts/status.py --project <ref>
"""
from __future__ import annotations

import json
from pathlib import Path

from _common import (
    Reply,
    project_argparser,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def _count_parquet(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        import pandas as pd

        return int(len(pd.read_parquet(path)))
    except Exception:
        return -1  # parquet exists but is unreadable


def main() -> Reply:
    ap = project_argparser(description="Show status / artefact counts for a project.")
    args = ap.parse_args()
    project = resolve_project_ref(args.project)
    mode = project_mode(project)

    # Resolve the active run dir (KB projects use ``output/runs/<id>/``,
    # memory projects write straight to ``output/``).
    output = project / "output"
    active = output
    current_json = output / "current.json"
    if current_json.exists():
        try:
            raw = json.loads(current_json.read_text(encoding="utf-8"))
            active = project / raw.get("run_dir", "output")
        except Exception:
            pass

    artefacts = {
        "documents": _count_parquet(active / "final_docs.parquet"),
        "text_units": _count_parquet(active / "final_text_units.parquet"),
        "entities": _count_parquet(active / "final_entities.parquet"),
        "relationships": _count_parquet(active / "final_relationships.parquet"),
        "communities": _count_parquet(active / "final_communities.parquet"),
        "community_reports": _count_parquet(active / "final_community_reports.parquet"),
    }

    # Memory-mode extras.
    memories_dir = project / "memories"
    n_observations = (
        sum(1 for _ in memories_dir.rglob("*.md") if not _.name.startswith("."))
        if memories_dir.exists()
        else 0
    )

    proposals_dir = output / "proposals"
    n_proposal_sets = 0
    if proposals_dir.exists():
        n_proposal_sets = sum(
            1 for p in proposals_dir.glob("*.yaml") if p.name != "latest.yaml"
        )

    next_steps: list[str] = []
    if mode == "knowledge_base" and artefacts["entities"] == 0:
        next_steps.append("Drop files into ./input/ then scripts/index.py")
    if mode == "memory" and n_observations == 0:
        next_steps.append("Add an observation: scripts/memory/add_observation.py")
    if mode == "memory" and artefacts["entities"] >= 30 and n_proposal_sets == 0:
        next_steps.append("Run scripts/memory/consolidate.py to surface proposals")

    return Reply(
        ok=True,
        mode=mode,
        project=project_envelope(project),
        data={
            "artefacts": artefacts,
            "observations": n_observations,
            "proposal_sets": n_proposal_sets,
            "active_run": str(active.relative_to(project)) if active.is_relative_to(project) else str(active),
        },
        next_steps=next_steps,
    )


if __name__ == "__main__":
    run(main)
