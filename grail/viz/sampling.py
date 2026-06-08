"""
Subgraph sampling helpers for the visualisation pipeline.

Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero.

When a project's entity count grows past a few thousand the browser-side
renderer starts to struggle on memory and frame rate. The functions in this
module produce *induced subgraphs* over a chosen subset of entities so the
rest of the pipeline (exporter, template, chat UI) can stay the same.

The selection policy this module implements right now is **top-N by degree**.
This preserves the densest, structurally most central entities — what users
typically want to see first on a large graph.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class SamplingResult:
    """The dataframes after sampling plus diagnostic metadata."""

    entities: pd.DataFrame
    relationships: pd.DataFrame
    text_units: pd.DataFrame
    nodes: pd.DataFrame
    communities: pd.DataFrame
    community_reports: pd.DataFrame
    documents: pd.DataFrame

    truncated: bool
    total_entities: int
    total_relationships: int
    kept_entities: int
    kept_relationships: int
    policy: str


def top_n_by_degree(
    entities: pd.DataFrame,
    relationships: pd.DataFrame,
    text_units: pd.DataFrame,
    nodes: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
    documents: pd.DataFrame,
    *,
    max_entities: Optional[int],
) -> SamplingResult:
    """Restrict the graph to the ``max_entities`` highest-degree entities.

    ``max_entities = None`` or any non-positive value is treated as "no cap"
    and returns the inputs untouched (with ``truncated=False``).

    The induced subgraph keeps:
      * the top-N entities
      * relationships whose both endpoints survive
      * text units linked to surviving entities (used by HAS_ENTITY edges)
      * nodes rows for surviving entity names
      * communities + reports that still have at least one member entity
      * documents that still have at least one surviving entity linked to them
    """
    total_entities = int(len(entities))
    total_relationships = int(len(relationships))
    policy = "top_n_by_degree"

    if max_entities is None or max_entities <= 0 or total_entities <= max_entities:
        return SamplingResult(
            entities=entities,
            relationships=relationships,
            text_units=text_units,
            nodes=nodes,
            communities=communities,
            community_reports=community_reports,
            documents=documents,
            truncated=False,
            total_entities=total_entities,
            total_relationships=total_relationships,
            kept_entities=total_entities,
            kept_relationships=total_relationships,
            policy=policy,
        )

    # Sort by degree desc, then by name for deterministic tie-breaks.
    sort_cols = ["degree", "name"] if "degree" in entities.columns else ["name"]
    ascending = [False, True] if "degree" in entities.columns else [True]
    top = (
        entities.sort_values(by=sort_cols, ascending=ascending, kind="mergesort")
        .head(max_entities)
        .copy()
    )
    kept_names = set(top["name"].astype(str))
    kept_ids = set(top["id"].astype(str))

    # Relationships: both endpoints must survive.
    if not relationships.empty:
        rel_mask = relationships["source"].astype(str).isin(kept_names) & relationships[
            "target"
        ].astype(str).isin(kept_names)
        rels = relationships[rel_mask].copy()
    else:
        rels = relationships

    # Text units: keep those referenced by surviving entities, drop the rest.
    # This shrinks the HAS_ENTITY / PART_OF edge count too.
    if text_units is not None and not text_units.empty:
        kept_chunk_ids: set[str] = set()
        for _, row in top.iterrows():
            tu_ids = row.get("text_unit_ids")
            if tu_ids is None:
                continue
            try:
                for tu in tu_ids:
                    if tu is None:
                        continue
                    kept_chunk_ids.add(str(tu))
            except TypeError:
                pass
        tus = text_units[text_units["id"].astype(str).isin(kept_chunk_ids)].copy()
    else:
        tus = text_units

    # Nodes table: keep only rows whose entity title survived.
    if nodes is not None and not nodes.empty and "title" in nodes.columns:
        nds = nodes[nodes["title"].astype(str).isin(kept_names)].copy()
    else:
        nds = nodes

    # Communities + reports: keep those that still have members in `kept_names`.
    surviving_communities: set[str] = set()
    if nds is not None and not nds.empty and "community" in nds.columns:
        surviving_communities = set(nds["community"].astype(str).unique())

    if communities is not None and not communities.empty and "community" in communities.columns:
        coms = communities[
            communities["community"].astype(str).isin(surviving_communities)
        ].copy()
    else:
        coms = communities

    if (
        community_reports is not None
        and not community_reports.empty
        and "community" in community_reports.columns
    ):
        reps = community_reports[
            community_reports["community"].astype(str).isin(surviving_communities)
        ].copy()
    else:
        reps = community_reports

    # Documents: keep those linked to any surviving entity. Falls back to the
    # full table if the entities table doesn't carry document_ids.
    if documents is not None and not documents.empty and "id" in documents.columns:
        kept_doc_ids: set[str] = set()
        for _, row in top.iterrows():
            doc_ids = row.get("document_ids")
            if doc_ids is None:
                continue
            try:
                for did in doc_ids:
                    if did is None:
                        continue
                    kept_doc_ids.add(str(did))
            except TypeError:
                pass
        if kept_doc_ids:
            docs = documents[documents["id"].astype(str).isin(kept_doc_ids)].copy()
        else:
            docs = documents
    else:
        docs = documents

    # Help the type checker — entities slice is guaranteed indexed by id.
    del kept_ids  # currently unused; kept for future filters

    return SamplingResult(
        entities=top,
        relationships=rels,
        text_units=tus,
        nodes=nds,
        communities=coms,
        community_reports=reps,
        documents=docs,
        truncated=True,
        total_entities=total_entities,
        total_relationships=total_relationships,
        kept_entities=int(len(top)),
        kept_relationships=int(len(rels)),
        policy=policy,
    )
