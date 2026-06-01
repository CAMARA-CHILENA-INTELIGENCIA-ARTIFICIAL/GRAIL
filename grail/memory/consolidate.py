"""
``consolidate()`` orchestrator — runs the enabled analyses, persists the result.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This module never mutates the parquets. It builds a :class:`GraphSnapshot`
from the project, calls every analysis registered in
``analyses.default_analyses(...)``, applies the per-kind confidence floors,
and writes a yaml file the agent can review.

Apply semantics (turning ``status: accepted`` into actual mutations) live in
``MemoryProject``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from grail.config import MemoryConfig
from grail.memory.analyses import (
    AnalysisProtocol,
    GraphSnapshot,
    default_analyses,
)
from grail.memory.proposals import (
    Proposal,
    ProposalSet,
    proposals_root,
)


def filter_by_confidence(proposals: list[Proposal], config: MemoryConfig) -> list[Proposal]:
    """Drop proposals below their per-kind confidence floor."""
    floors = {
        "discover_community": config.confidence_threshold_discover_community,
        "merge_aliases": config.confidence_threshold_merge_aliases,
        "move_entity": config.confidence_threshold_move_entity,
        "split_folder": config.confidence_threshold_split_folder,
    }
    return [p for p in proposals if p.confidence >= floors.get(p.kind, 0.0)]


def build_snapshot(
    *,
    entities: pd.DataFrame,
    relationships: pd.DataFrame,
    text_units: pd.DataFrame,
    documents: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
) -> GraphSnapshot:
    return GraphSnapshot(
        entities=entities,
        relationships=relationships,
        text_units=text_units,
        documents=documents,
        communities=communities,
        community_reports=community_reports,
    )


def run_consolidate(
    snapshot: GraphSnapshot,
    config: MemoryConfig,
    *,
    extra_analyses: Optional[list[AnalysisProtocol]] = None,
) -> ProposalSet:
    """Run analyses against ``snapshot`` and return a fresh ``ProposalSet``.

    The set is *not* persisted — callers (typically ``MemoryProject``) save
    it under ``output/proposals/`` after deciding on a filename.
    """
    analyses = list(default_analyses(config))
    if extra_analyses:
        analyses.extend(extra_analyses)

    proposals: list[Proposal] = []
    for analysis in analyses:
        try:
            new_proposals = analysis.propose(snapshot, config)
        except Exception as exc:  # pragma: no cover - defensive
            proposals.append(
                Proposal.fresh(
                    kind="discover_community",  # placeholder; tagged via rationale
                    rationale=(
                        f"[error] analysis {analysis.name!r} raised "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    confidence=0.0,
                    payload={"analysis": analysis.name},
                    evidence={"error": str(exc)},
                )
            )
            continue
        proposals.extend(new_proposals)

    proposals = filter_by_confidence(proposals, config)
    proposals = _dedup_by_payload(proposals)
    proposals.sort(key=lambda p: -p.confidence)

    ps = ProposalSet(
        graph_snapshot={
            "entities": int(len(snapshot.entities)),
            "relationships": int(len(snapshot.relationships)),
            "communities": int(len(snapshot.communities)),
            "documents": int(len(snapshot.documents)),
        },
        proposals=proposals,
    )
    return ps


def proposal_set_path(project_path: str | Path, *, output_folder: str = "output") -> Path:
    """Compute a fresh, timestamp-sortable path under ``output/proposals/``."""
    from grail.memory.identity import new_ulid

    return proposals_root(project_path, output_folder) / f"{new_ulid()}.yaml"


def _dedup_by_payload(proposals: list[Proposal]) -> list[Proposal]:
    """Drop proposals that duplicate another's payload (same kind + canonical key).

    For ``merge_aliases``: the pair ``frozenset({canonical, *aliases})``.
    For ``discover_community``: the frozenset of members.
    For ``move_entity``: ``(entity, frozenset(add_community_ids))``.
    For ``split_folder``: ``folder``.
    """
    seen: set[tuple] = set()
    out: list[Proposal] = []
    for p in proposals:
        key: tuple
        if p.kind == "merge_aliases":
            members = [p.payload.get("canonical", "")] + list(
                p.payload.get("aliases") or []
            )
            key = ("merge_aliases", frozenset(m.upper() for m in members if m))
        elif p.kind == "discover_community":
            members = list(p.payload.get("members") or [])
            key = ("discover_community", frozenset(m.upper() for m in members))
        elif p.kind == "move_entity":
            key = (
                "move_entity",
                str(p.payload.get("entity", "")).upper(),
                frozenset(p.payload.get("add_community_ids") or []),
            )
        elif p.kind == "split_folder":
            key = ("split_folder", str(p.payload.get("folder", "")))
        else:
            key = (p.kind, p.id)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


__all__ = [
    "build_snapshot",
    "filter_by_confidence",
    "proposal_set_path",
    "run_consolidate",
]
