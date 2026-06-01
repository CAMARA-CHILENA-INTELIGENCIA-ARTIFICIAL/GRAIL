"""
Memory-mode merge helpers.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The agent supplies entities/relationships directly (no LLM extraction). The
merge with existing parquets is therefore much simpler than the KB-mode
``EntityRelationshipExtractor._merge_with_existing`` — no summarizer, no
re-embed unless an embeddings client is configured.

Schema additions from Phase A (community_ids, observed_at, confidence, source,
relationship_type) are populated here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from grail.utils.ids import generate_guid


def _aslist(value: Any) -> list:
    """Normalise possibly-numpy / possibly-None list values to a plain list.

    Parquet round-trips lists as numpy arrays — and ``array or []`` raises
    "truth value is ambiguous". This helper centralises the dance.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        return list(value)
    return [value]


@dataclass
class _MergeEntity:
    """Agent-supplied entity input. ``text_unit_ids`` are attached at merge time."""

    name: str
    type: str
    description: str
    retrieval_queries: list[str] = field(default_factory=list)
    text_unit_ids: set[str] = field(default_factory=set)
    document_ids: set[str] = field(default_factory=set)
    community_ids: list[str] = field(default_factory=list)
    observed_at: Optional[str] = None
    confidence: float = 1.0
    source: Optional[str] = None


@dataclass
class _MergeRelationship:
    source: str
    target: str
    relationship_type: str
    description: str
    weight: float = 1.0
    text_unit_ids: set[str] = field(default_factory=set)
    document_ids: set[str] = field(default_factory=set)
    observed_at: Optional[str] = None
    confidence: float = 1.0
    source_attribution: Optional[str] = None


def merge_entities(
    existing_df: pd.DataFrame,
    incoming: list[_MergeEntity],
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Merge ``incoming`` entities into ``existing_df``.

    Returns ``(merged_df, new_entity_names, updated_entity_names)``. New
    descriptions overwrite (memory mode does not summarise — the agent owns
    the description). ``community_ids`` are *appended* with dedup so an
    entity can accumulate folder + discovered memberships.
    """
    existing_by_name: dict[str, dict] = {}
    if not existing_df.empty:
        for _, row in existing_df.iterrows():
            existing_by_name[row["name"]] = row.to_dict()

    max_hrid = 0
    if not existing_df.empty and "human_readable_id" in existing_df.columns:
        try:
            max_hrid = int(existing_df["human_readable_id"].max())
        except (ValueError, TypeError):
            max_hrid = 0

    new_names: list[str] = []
    updated_names: list[str] = []

    for ent in incoming:
        if ent.name in existing_by_name:
            existing = existing_by_name[ent.name]
            if ent.description and ent.description != existing.get("description", ""):
                existing["description"] = ent.description
                # Embedding becomes stale when description changes.
                existing["description_embedding"] = None
                updated_names.append(ent.name)
            old_tus = set(_aslist(existing.get("text_unit_ids")))
            old_docs = set(_aslist(existing.get("document_ids")))
            existing["text_unit_ids"] = sorted(old_tus | ent.text_unit_ids)
            existing["document_ids"] = sorted(old_docs | ent.document_ids)
            old_rq = existing.get("retrieval_queries")
            if isinstance(old_rq, str):
                old_rq = [q.strip() for q in old_rq.split(";") if q.strip()]
            else:
                old_rq = _aslist(old_rq)
            existing["retrieval_queries"] = list(
                dict.fromkeys(list(old_rq) + ent.retrieval_queries)
            )
            old_cids = _aslist(existing.get("community_ids"))
            for cid in ent.community_ids:
                if cid not in old_cids:
                    old_cids.append(cid)
            existing["community_ids"] = old_cids
            # Provenance: keep the freshest observation, the lowest confidence.
            if ent.observed_at:
                old_obs = existing.get("observed_at")
                existing["observed_at"] = max(old_obs, ent.observed_at) if old_obs else ent.observed_at
            old_conf = existing.get("confidence")
            if old_conf is None:
                existing["confidence"] = ent.confidence
            else:
                existing["confidence"] = min(float(old_conf), ent.confidence)
            if ent.source and not existing.get("source"):
                existing["source"] = ent.source
        else:
            max_hrid += 1
            existing_by_name[ent.name] = {
                "id": generate_guid(),
                "name": ent.name,
                "title": ent.name,
                "type": ent.type,
                "description": ent.description,
                "retrieval_queries": list(ent.retrieval_queries),
                "human_readable_id": max_hrid,
                "graph_embedding": None,
                "text_unit_ids": sorted(ent.text_unit_ids),
                "document_ids": sorted(ent.document_ids),
                "description_embedding": None,
                "degree": 0,
                "community_ids": list(ent.community_ids),
                "observed_at": ent.observed_at,
                "confidence": ent.confidence,
                "source": ent.source,
            }
            new_names.append(ent.name)

    merged_df = pd.DataFrame(list(existing_by_name.values()))
    return merged_df, new_names, updated_names


def merge_relationships(
    existing_df: pd.DataFrame,
    incoming: list[_MergeRelationship],
    valid_entity_names: set[str],
) -> tuple[pd.DataFrame, list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Merge ``incoming`` relationships into ``existing_df``.

    Key is ``(src, tgt, relationship_type)`` — typed edges between the same
    pair are distinct. Endpoints not in ``valid_entity_names`` are dropped.
    Returns ``(merged_df, new_keys, updated_keys)``.
    """
    by_key: dict[tuple[str, str, str], dict] = {}
    if not existing_df.empty:
        for _, row in existing_df.iterrows():
            pair = tuple(sorted((row["source"], row["target"])))
            rel_type = row.get("relationship_type") or row.get("type") or "RELATED"
            by_key[(pair[0], pair[1], str(rel_type))] = row.to_dict()

    max_hrid = 0
    if not existing_df.empty and "human_readable_id" in existing_df.columns:
        try:
            max_hrid = int(existing_df["human_readable_id"].max())
        except (ValueError, TypeError):
            max_hrid = 0

    new_keys: list[tuple[str, str, str]] = []
    updated_keys: list[tuple[str, str, str]] = []

    for rel in incoming:
        if rel.source not in valid_entity_names or rel.target not in valid_entity_names:
            continue
        if rel.source == rel.target:
            continue
        pair = tuple(sorted((rel.source, rel.target)))
        key = (pair[0], pair[1], rel.relationship_type)
        if key in by_key:
            existing = by_key[key]
            if rel.description and rel.description != existing.get("description", ""):
                existing["description"] = rel.description
                updated_keys.append(key)
            old_w = float(existing.get("weight", 1.0))
            existing["weight"] = (old_w + rel.weight) / 2.0
            old_tus = set(_aslist(existing.get("text_unit_ids")))
            old_docs = set(_aslist(existing.get("document_ids")))
            existing["text_unit_ids"] = sorted(old_tus | rel.text_unit_ids)
            existing["document_ids"] = sorted(old_docs | rel.document_ids)
            if rel.observed_at:
                old_obs = existing.get("observed_at")
                existing["observed_at"] = max(old_obs, rel.observed_at) if old_obs else rel.observed_at
            old_conf = existing.get("confidence")
            if old_conf is None:
                existing["confidence"] = rel.confidence
            else:
                existing["confidence"] = min(float(old_conf), rel.confidence)
            if rel.source_attribution and not existing.get("source_attribution"):
                existing["source_attribution"] = rel.source_attribution
        else:
            max_hrid += 1
            by_key[key] = {
                "id": generate_guid(),
                "source": pair[0],
                "target": pair[1],
                "source_id": None,  # populated after entity ids are known
                "target_id": None,
                "relationship_type": rel.relationship_type,
                "description": rel.description,
                "weight": rel.weight,
                "text_unit_ids": sorted(rel.text_unit_ids),
                "document_ids": sorted(rel.document_ids),
                "human_readable_id": max_hrid,
                "source_degree": 0,
                "target_degree": 0,
                "rank": 0,
                "observed_at": rel.observed_at,
                "confidence": rel.confidence,
                # Provenance: separate from the ``source`` endpoint name —
                # this is the actor / pipeline that produced the relationship
                # ("agent-claude", "llm", ...). KB-mode legacy parquets used a
                # colliding ``source`` key; we renamed to avoid that.
                "source_attribution": rel.source_attribution,
            }
            new_keys.append(key)

    merged_df = pd.DataFrame(list(by_key.values()))
    return merged_df, new_keys, updated_keys


def recompute_degrees(
    entities_df: pd.DataFrame, rels_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recompute degrees on entities and rank on relationships from scratch."""
    if entities_df.empty:
        return entities_df, rels_df
    if rels_df.empty:
        entities_df = entities_df.copy()
        entities_df["degree"] = 0
        return entities_df, rels_df
    entities_df = entities_df.copy()
    rels_df = rels_df.copy()
    degree = (
        pd.concat([rels_df["source"], rels_df["target"]])
        .value_counts()
        .to_dict()
    )
    entities_df["degree"] = entities_df["name"].map(degree).fillna(0).astype(int)
    rels_df["source_degree"] = rels_df["source"].map(degree).fillna(0).astype(int)
    rels_df["target_degree"] = rels_df["target"].map(degree).fillna(0).astype(int)
    rels_df["rank"] = rels_df["source_degree"] + rels_df["target_degree"]
    # Backfill source_id / target_id from the entity table for rows that
    # don't have them yet (newly-added rels in memory mode).
    name_to_id = dict(zip(entities_df["name"], entities_df["id"]))
    rels_df["source_id"] = rels_df.apply(
        lambda r: r["source_id"] if r.get("source_id") else name_to_id.get(r["source"]),
        axis=1,
    )
    rels_df["target_id"] = rels_df.apply(
        lambda r: r["target_id"] if r.get("target_id") else name_to_id.get(r["target"]),
        axis=1,
    )
    return entities_df, rels_df


__all__ = [
    "_MergeEntity",
    "_MergeRelationship",
    "merge_entities",
    "merge_relationships",
    "recompute_degrees",
]
