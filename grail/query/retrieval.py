"""
Retrieval primitives shared by local and global search.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Functions here read parquet artefacts off storage and assemble them into the
DataFrame tables that the context builders pack into the LLM prompt.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from grail.storage import StorageBackend
from grail.utils.tokens import tiktoken_len
from grail.vectorstores import LanceDBVectorStore, VectorStoreSearchResult

log = logging.getLogger(__name__)


@dataclass
class SearchArtifacts:
    """All parquet tables + mapping.json needed for search."""

    entities: pd.DataFrame
    relationships: pd.DataFrame
    text_units: pd.DataFrame
    nodes: pd.DataFrame
    communities: pd.DataFrame
    community_reports: pd.DataFrame
    documents: pd.DataFrame
    mapping: dict[str, Any]


def _read_or_empty(storage: StorageBackend, key: str) -> pd.DataFrame:
    if not storage.exists(key):
        return pd.DataFrame()
    with storage.open_for_read(key) as path:
        return pd.read_parquet(path)


def load_artifacts_for_search(
    storage: StorageBackend, output_folder: str = "output"
) -> SearchArtifacts:
    """Load every parquet GRAIL wrote during indexing."""
    return SearchArtifacts(
        entities=_read_or_empty(storage, f"{output_folder}/final_entities.parquet"),
        relationships=_read_or_empty(storage, f"{output_folder}/final_relationships.parquet"),
        text_units=_read_or_empty(storage, f"{output_folder}/final_text_units.parquet"),
        nodes=_read_or_empty(storage, f"{output_folder}/final_nodes.parquet"),
        communities=_read_or_empty(storage, f"{output_folder}/final_communities.parquet"),
        community_reports=_read_or_empty(
            storage, f"{output_folder}/final_community_reports.parquet"
        ),
        documents=_read_or_empty(storage, f"{output_folder}/final_docs.parquet"),
        mapping=(
            json.loads(storage.read_text("mapping.json"))
            if storage.exists("mapping.json")
            else {}
        ),
    )


# ----------------------------------------------------------------------- entity mapping


def _cosine(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


def map_query_to_entities(
    query_embedding: list[float],
    entities_df: pd.DataFrame,
    *,
    top_k: int = 10,
    vector_store: Optional[LanceDBVectorStore] = None,
) -> pd.DataFrame:
    """Return the top-k entities most similar to the query vector.

    If a vector store is provided we use it (fast ANN). Otherwise we fall back to
    a pandas cosine scan over the description embeddings — fine for small graphs.
    """
    if entities_df.empty:
        return entities_df.copy()

    if vector_store is not None:
        results: list[VectorStoreSearchResult] = vector_store.similarity_search_by_vector(
            query_embedding=query_embedding, k=top_k
        )
        matched_ids = [r.document.id for r in results]
        scores = {r.document.id: r.score for r in results}
        out = entities_df[entities_df["id"].isin(matched_ids)].copy()
        out["__score__"] = out["id"].map(scores)
        return out.sort_values("__score__", ascending=False).head(top_k)

    embeddings = entities_df["description_embedding"]
    scores = []
    for emb in embeddings:
        if emb is None or (isinstance(emb, float) and np.isnan(emb)):
            scores.append(-1.0)
            continue
        scores.append(_cosine(query_embedding, emb))
    out = entities_df.copy()
    out["__score__"] = scores
    return out.sort_values("__score__", ascending=False).head(top_k)


# ----------------------------------------------------------------------- contexts


def build_entity_context(
    entities: pd.DataFrame, *, max_tokens: int = 2000
) -> tuple[str, pd.DataFrame]:
    """Render a CSV-like entity table that fits in ``max_tokens``."""
    if entities.empty:
        return "", entities
    header = "Entities\nid,entity,type,description"
    rows = []
    selected_idx = []
    used = tiktoken_len(header)
    for idx, row in entities.iterrows():
        line = f"{row.get('human_readable_id', idx)},{row['name']},{row.get('type','')},{(row.get('description') or '').replace(chr(10), ' ')[:300]}"
        tok = tiktoken_len(line)
        if used + tok > max_tokens:
            break
        rows.append(line)
        selected_idx.append(idx)
        used += tok
    text = "\n".join([header, *rows])
    return text, entities.loc[selected_idx]


def build_relationship_context(
    relationships: pd.DataFrame,
    entity_names: list[str],
    *,
    max_tokens: int = 2000,
) -> tuple[str, pd.DataFrame]:
    """Render a CSV-like relationship table prioritising edges between selected entities."""
    if relationships.empty:
        return "", relationships
    name_set = set(entity_names)
    in_network = relationships[
        relationships["source"].isin(name_set) & relationships["target"].isin(name_set)
    ]
    out_network = relationships[
        relationships["source"].isin(name_set) ^ relationships["target"].isin(name_set)
    ]
    ordered = pd.concat([in_network, out_network])
    header = "Relationships\nid,source,target,description,weight"
    rows = []
    selected_idx = []
    used = tiktoken_len(header)
    for idx, row in ordered.iterrows():
        line = (
            f"{row.get('human_readable_id', idx)},{row['source']},{row['target']},"
            f"{(row.get('description') or '').replace(chr(10),' ')[:300]},{row.get('weight', 1.0):.2f}"
        )
        tok = tiktoken_len(line)
        if used + tok > max_tokens:
            break
        rows.append(line)
        selected_idx.append(idx)
        used += tok
    text = "\n".join([header, *rows])
    return text, ordered.loc[selected_idx]


def build_community_context(
    community_reports: pd.DataFrame,
    *,
    max_tokens: int = 4000,
) -> tuple[str | list[str], pd.DataFrame]:
    """Render community-report headers + summaries until ``max_tokens`` is exhausted.

    Returns the joined string if everything fits, or a list of chunked strings when
    the report set exceeds the budget (the map-reduce path slices on this).
    """
    if community_reports.empty:
        return "", community_reports

    sorted_reports = community_reports.sort_values("rank", ascending=False)
    header = "Reports\nid,title,summary,rank"
    chunks: list[str] = []
    selected_idx = []
    rows: list[str] = []
    used = tiktoken_len(header)
    for idx, row in sorted_reports.iterrows():
        summary = (row.get("summary") or "").replace("\n", " ")
        line = f"{row.get('id', idx)},{row.get('title','')},{summary},{row.get('rank', 1.0)}"
        tok = tiktoken_len(line)
        if used + tok > max_tokens and rows:
            chunks.append("\n".join([header, *rows]))
            rows = []
            used = tiktoken_len(header)
        rows.append(line)
        selected_idx.append(idx)
        used += tok
    if rows:
        chunks.append("\n".join([header, *rows]))

    if len(chunks) <= 1:
        return chunks[0] if chunks else "", sorted_reports.loc[selected_idx]
    return chunks, sorted_reports.loc[selected_idx]


def build_text_unit_context(
    text_units: pd.DataFrame,
    entity_names: list[str],
    *,
    max_tokens: int = 3000,
    documents: Optional[pd.DataFrame] = None,
    mapping: Optional[dict[str, Any]] = None,
) -> tuple[str, pd.DataFrame]:
    """Pick the text units that mention any selected entity and pack them as Sources."""
    if text_units.empty:
        return "", text_units
    name_set = set(entity_names)

    def _mentions(row) -> bool:
        ids = row.get("entity_ids")
        if ids is None or (hasattr(ids, "__len__") and len(ids) == 0):
            return False
        return any(n in name_set for n in ids)

    relevant = text_units[text_units.apply(_mentions, axis=1)] if entity_names else text_units
    if relevant.empty:
        return "", relevant

    doc_titles: dict[str, str] = {}
    if documents is not None and not documents.empty:
        doc_titles = dict(zip(documents["id"], documents["title"]))
    if mapping:
        for doc_id, info in mapping.items():
            doc_titles.setdefault(doc_id, info.get("title", doc_id))

    header = "Sources\nid,document,text"
    rows = []
    selected_idx = []
    used = tiktoken_len(header)
    for idx, row in relevant.iterrows():
        raw_doc_ids = row.get("document_ids")
        if raw_doc_ids is None or (hasattr(raw_doc_ids, "__len__") and len(raw_doc_ids) == 0):
            doc_ids = [row.get("document_id")]
        else:
            doc_ids = list(raw_doc_ids)
        doc_label = "; ".join(doc_titles.get(d, str(d)) for d in doc_ids if d)
        line = f"{row['id']},{doc_label},{(row['text'] or '').replace(chr(10), ' ')[:1200]}"
        tok = tiktoken_len(line)
        if used + tok > max_tokens:
            break
        rows.append(line)
        selected_idx.append(idx)
        used += tok
    text = "\n".join([header, *rows])
    return text, relevant.loc[selected_idx]
