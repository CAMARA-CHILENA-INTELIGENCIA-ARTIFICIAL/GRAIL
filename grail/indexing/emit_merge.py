"""
Emit-handler merge math.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

An *emit* handler (see :mod:`grail.indexing.handlers`) turns one source file into
deterministic entities + relationships, skipping LLM extraction. To keep the rest
of the pipeline (communities, reports, vector store, citations) working, each
emit file needs a synthetic :class:`Document` + :class:`TextUnit` for provenance,
and its entities/relationships must match the exact column layout the
:class:`~grail.indexing.entities_relationships.EntityRelationshipExtractor`
produces.

These are pure builders — no I/O, no LLM — so they're easy to unit-test. The
caller (``GRAIL.index`` / ``GRAIL.append``) supplies pre-computed description
embeddings and persists the merged frames.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from grail.indexing.handlers import EmitResult
from grail.utils.ids import generate_guid


@dataclass
class EmitFrames:
    """The synthetic rows produced for a batch of emit files."""

    docs: pd.DataFrame
    text_units: pd.DataFrame
    entities: pd.DataFrame
    relationships: pd.DataFrame
    mapping: dict[str, Any]


def entity_embedding_text(name: str, description: str, retrieval_queries: list[str]) -> str:
    """Match the extractor's embedding text format (entities_relationships.py:170)."""
    return f"{name}: {description} {' '.join(retrieval_queries)}".strip()


def build_emit_frames(
    *,
    results: list[tuple[str, EmitResult]],
    embeddings_by_name: dict[str, Optional[list[float]]],
    n_tokens: Optional[Any] = None,
) -> EmitFrames:
    """Build synthetic doc/TU/entity/relationship rows for emit files.

    Parameters
    ----------
    results:
        ``(input_key, EmitResult)`` pairs — one per emit file.
    embeddings_by_name:
        ``entity name -> description embedding`` (required for the vector store;
        an entity with ``None`` here is dropped from search).
    n_tokens:
        Optional callable ``str -> int`` for the synthetic TU token count.
    """
    doc_rows: list[dict[str, Any]] = []
    tu_rows: list[dict[str, Any]] = []
    entity_rows: list[dict[str, Any]] = []
    rel_rows: list[dict[str, Any]] = []
    mapping: dict[str, Any] = {}

    # Collapse to one entity row per (file, name); relationships carry endpoint
    # names that map to the per-file entity ids.
    for key, result in results:
        doc_id = generate_guid()
        tu_id = generate_guid()
        title = Path(key).name
        body = result.text or (
            f"Structured data emitted from {title} "
            f"({len(result.entities)} entities, {len(result.relationships)} relationships)."
        )

        doc_rows.append(
            {
                "id": doc_id,
                "title": title,
                "raw_content": body,
                "path": key,
                "text_unit_ids": [tu_id],
                "mapping": key,
                "category": None,
                "tags": ["emitted"],
                "attributes": None,
                "observed_at": None,
                "confidence": 1.0,
                "source": None,
            }
        )
        mapping[doc_id] = {
            "original_path": key,
            "processed_path": None,
            "title": title,
            "extension": Path(key).suffix.lower(),
            "data_type": "emitted",
            "size_chars": len(body),
        }

        name_to_id: dict[str, str] = {}
        for ent in result.entities:
            ent_id = generate_guid()
            name_to_id[ent.name] = ent_id
            entity_rows.append(
                {
                    "id": ent_id,
                    "name": ent.name,
                    "title": ent.name,
                    "type": ent.type,
                    "description": ent.description,
                    "retrieval_queries": list(ent.retrieval_queries),
                    "human_readable_id": 0,  # renumbered at merge time
                    "graph_embedding": None,
                    "text_unit_ids": [tu_id],
                    "document_ids": [doc_id],
                    "description_embedding": embeddings_by_name.get(ent.name),
                    "degree": 0,
                    "community_ids": [],
                    "observed_at": None,
                    "confidence": 1.0,
                    "source": None,
                }
            )

        for rel in result.relationships:
            rel_rows.append(
                {
                    "id": generate_guid(),
                    "source": rel.source,
                    "target": rel.target,
                    "source_id": name_to_id.get(rel.source),
                    "target_id": name_to_id.get(rel.target),
                    "relationship_type": rel.type,
                    "description": rel.description,
                    "weight": float(rel.weight),
                    "text_unit_ids": [tu_id],
                    "document_ids": [doc_id],
                    "human_readable_id": 0,
                    "rank": 0,
                    "observed_at": None,
                    "confidence": 1.0,
                    "source_attribution": None,
                    "source_degree": 0,
                    "target_degree": 0,
                }
            )

        ent_names = [e.name for e in result.entities]
        rel_ids = [f"{r.source}|{r.target}" for r in result.relationships]
        tu_rows.append(
            {
                "id": tu_id,
                "text": body,
                "n_tokens": int(n_tokens(body)) if callable(n_tokens) else len(body.split()),
                "document_id": doc_id,
                "document_ids": [doc_id],
                "observed_at": None,
                "confidence": 1.0,
                "source": None,
                "entity_ids": ent_names,
                "relationship_ids": rel_ids,
            }
        )

    return EmitFrames(
        docs=pd.DataFrame(doc_rows),
        text_units=pd.DataFrame(tu_rows),
        entities=pd.DataFrame(entity_rows),
        relationships=pd.DataFrame(rel_rows),
        mapping=mapping,
    )


def recompute_degrees(
    entities_df: pd.DataFrame, relationships_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recompute entity degree and relationship rank over the merged frames.

    Mirrors ``_build_relationships_df`` (entities_relationships.py:437-442) so a
    merged graph is internally consistent.
    """
    entities_df = entities_df.copy()
    relationships_df = relationships_df.copy()
    if relationships_df.empty:
        entities_df["degree"] = 0
        return entities_df, relationships_df
    degree = (
        pd.concat([relationships_df["source"], relationships_df["target"]])
        .value_counts()
        .to_dict()
    )
    entities_df["degree"] = entities_df["name"].map(degree).fillna(0).astype(int)
    relationships_df["source_degree"] = (
        relationships_df["source"].map(degree).fillna(0).astype(int)
    )
    relationships_df["target_degree"] = (
        relationships_df["target"].map(degree).fillna(0).astype(int)
    )
    relationships_df["rank"] = (
        relationships_df["source_degree"] + relationships_df["target_degree"]
    )
    return entities_df, relationships_df


def renumber_human_readable_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Assign contiguous ``human_readable_id`` values after a concat."""
    if df.empty:
        return df
    df = df.copy()
    df["human_readable_id"] = range(len(df))
    return df
