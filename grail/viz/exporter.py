"""
Convert GRAIL parquet artefacts into a D3 force-graph payload.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This module mirrors the Neo4j data model used by the legacy notebook:
``Document → Chunk → Entity ↔ Entity → Community → Finding``. Every node
carries a ``_kind`` attribute the viewer reads to pick shape, size, default
visibility, and which fields to show in the side panel.

Edge kinds (one of ``PART_OF, HAS_ENTITY, RELATED, IN_COMMUNITY, HAS_FINDING,
MENTIONS``) live on the edge's ``_kind`` attribute and drive the same
visibility logic on the edge reducer.

Layout is computed **client-side** by D3's force simulation — this module no
longer emits ``x, y`` for nodes. The ``meta.force_settings`` block ships the
tuning knobs the renderer reads on first start.

Node attributes shared by every kind
------------------------------------
* ``label``         — display name.
* ``size``          — radius in renderer units; per-kind scaling.
* ``color``         — current color (depends on color-mode toggle).
* ``_kind``         — ``document | chunk | entity | community | finding``.

Kind-specific attributes
------------------------
* document:    ``_title, _path, _n_text_units, _doc_id``
* chunk:       ``_text, _n_tokens, _document_ids, _chunk_id``
* entity:      ``_type, _community, _degree, _description, _documents``,
                 ``typeColor, communityColor``
* community:   ``_community_id, _level, _size, _rank, _title, _summary, _n_findings``
* finding:     ``_summary, _explanation, _community_id``
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import networkx as nx
import pandas as pd

from grail.viz.colors import (
    KIND_PALETTE,
    build_community_palette,
    build_type_palette,
    hash_color,
)

log = logging.getLogger(__name__)


# ── Visual tuning ─────────────────────────────────────────────────────────
NODE_MIN_SIZE = 3.0
NODE_MAX_SIZE = 22.0

# Per-kind size profile. Entities are the star of the show; the others stay
# visually quiet so that, when toggled on, they don't dominate the canvas.
KIND_SIZE = {
    "document":  12.0,
    "chunk":     5.0,
    "entity":    None,           # scaled by degree (see _make_log_scaler)
    "community": 14.0,           # tiny scaling by member count later
    "finding":   4.0,
}

EDGE_MIN_SIZE = 0.6
EDGE_MAX_SIZE = 3.5
EDGE_COLOR = "#5b6478"
EDGE_LABEL_MAX_CHARS = 80

# Default-visible kinds. We start with ENTITIES ONLY so the viewer looks like
# a clean community-coloured social-graph (the GoT/Sigma demo aesthetic). All
# the other Neo4j-style layers (documents, chunks, communities-as-nodes,
# findings) are one toggle away in the sidebar.
DEFAULT_VISIBLE_KINDS = ["entity"]
DEFAULT_VISIBLE_EDGE_KINDS = ["RELATED"]

# Default force-simulation tunables piped through to the client renderer.
# CLI flags override these per-run via the ``force_settings`` keyword.
DEFAULT_FORCE_SETTINGS: dict[str, float | int] = {
    "seed": 42,
    "linkDistance": 200,
    "linkStrength": 0.2,
    "chargeStrength": -3000,
    "collideRadius": 50,
    "centerStrength": 0.05,
    "isolatedRadius": 100,
    "isolatedStrength": 0.15,
    "alphaDecay": 0.05,
}


# ──────────────────────────────────────────────────────────────────────────


@dataclass
class SigmaGraph:
    """The full payload embedded in the HTML page."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges, "meta": self.meta}


# ──────────────────────────────────────────────────────────────────────────


def build_sigma_graph(
    entities_df: pd.DataFrame,
    relationships_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    documents_df: Optional[pd.DataFrame] = None,
    text_units_df: Optional[pd.DataFrame] = None,
    communities_df: Optional[pd.DataFrame] = None,
    reports_df: Optional[pd.DataFrame] = None,
    *,
    force_settings: Optional[dict[str, float | int]] = None,
    truncation: Optional[dict[str, Any]] = None,
    # Legacy kwargs kept for back-compat with older callers; ignored.
    layout_seed: int = 42,
    layout_iterations: int = 120,
) -> SigmaGraph:
    """Build the multi-kind force-graph payload from the indexed parquet tables.

    ``force_settings`` overrides individual entries of
    :data:`DEFAULT_FORCE_SETTINGS` for this run. The renderer reads them on
    first start; passing ``{"seed": 7}`` is enough to change the seed without
    rewriting the other knobs.
    """
    if entities_df.empty:
        return SigmaGraph(nodes=[], edges=[], meta=_empty_meta(force_settings))

    # Reconcile force settings — the legacy seed is honoured if a CLI caller
    # passed `layout_seed=N` but didn't pass `force_settings`.
    resolved_force = dict(DEFAULT_FORCE_SETTINGS)
    if layout_seed != 42 and (force_settings is None or "seed" not in force_settings):
        resolved_force["seed"] = layout_seed
    if force_settings:
        resolved_force.update(force_settings)
    del layout_iterations  # only kept for signature compatibility

    # ── Identifiers + indexes ─────────────────────────────────────────────
    # Entity-name → entity-id and community-id → entity-name set.
    name_to_id: dict[str, str] = dict(
        zip(entities_df["name"].astype(str), entities_df["id"].astype(str))
    )
    name_to_community = _resolve_communities(nodes_df)
    members_by_community: dict[str, list[str]] = {}
    for ent_name, cid in name_to_community.items():
        members_by_community.setdefault(cid, []).append(ent_name)

    # Document id → row mapping for label / metadata lookups.
    doc_rows: dict[str, dict[str, Any]] = {}
    if documents_df is not None and not documents_df.empty:
        for _, row in documents_df.iterrows():
            doc_rows[str(row["id"])] = row.to_dict()

    # Community id → report row (the LLM-narrated summary).
    report_by_cid: dict[str, dict[str, Any]] = {}
    if reports_df is not None and not reports_df.empty:
        for _, row in reports_df.iterrows():
            report_by_cid[str(row["community"])] = row.to_dict()

    # Community id → structural row (size, entity_ids).
    struct_by_cid: dict[str, dict[str, Any]] = {}
    if communities_df is not None and not communities_df.empty:
        for _, row in communities_df.iterrows():
            struct_by_cid[str(row["community"])] = row.to_dict()

    # Inverse map: chunk_id → list of entity names mentioned in that chunk.
    chunk_to_entities: dict[str, list[str]] = {}
    for _, row in entities_df.iterrows():
        for tu_id in _as_list(row.get("text_unit_ids")):
            chunk_to_entities.setdefault(str(tu_id), []).append(str(row["name"]))

    # ── Palettes ──────────────────────────────────────────────────────────
    type_palette = build_type_palette(entities_df["type"].dropna().astype(str).unique())
    all_cids = set(name_to_community.values()) | set(struct_by_cid.keys()) | set(report_by_cid.keys())
    community_palette = build_community_palette(all_cids)

    # ── Build nodes ───────────────────────────────────────────────────────
    nodes: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {k: 0 for k in KIND_PALETTE}

    # Entities ----------
    degrees = entities_df["degree"].astype(float).fillna(0)
    ent_size_fn = _make_log_scaler(degrees, NODE_MIN_SIZE, NODE_MAX_SIZE)
    for _, row in entities_df.iterrows():
        name = str(row["name"])
        node_id = name_to_id[name]
        ent_type = str(row.get("type") or "").upper() or "UNKNOWN"
        type_counts[ent_type] = type_counts.get(ent_type, 0) + 1
        type_color = type_palette.get(ent_type) or hash_color(ent_type)
        community = name_to_community.get(name, "")
        community_color = community_palette.get(community, "#666c79") if community else "#666c79"
        degree = float(row.get("degree") or 0)
        docs = _resolve_documents(row.get("document_ids"), doc_rows)
        nodes.append({
            "key": node_id,
            "attributes": {
                "label": name,
                "size": ent_size_fn(degree),
                "color": community_color,         # community is the default color
                "typeColor": type_color,
                "communityColor": community_color,
                "_kind": "entity",
                "_type": ent_type,
                "_community": community,
                "_degree": int(degree),
                "_description": str(row.get("description") or ""),
                "_documents": docs,
            },
        })
        kind_counts["entity"] += 1

    # Documents ----------
    for doc_id, row in doc_rows.items():
        node_key = f"doc:{doc_id}"
        n_tus = len(_as_list(row.get("text_unit_ids")))
        title = str(row.get("title") or doc_id)
        nodes.append({
            "key": node_key,
            "attributes": {
                "label": title,
                "size": KIND_SIZE["document"],
                "color": KIND_PALETTE["document"],
                "typeColor": KIND_PALETTE["document"],
                "communityColor": KIND_PALETTE["document"],
                "_kind": "document",
                "_title": title,
                "_path": str(row.get("path") or ""),
                "_n_text_units": n_tus,
                "_doc_id": doc_id,
            },
        })
        kind_counts["document"] += 1

    # Chunks (text units) ----------
    if text_units_df is not None and not text_units_df.empty:
        for _, row in text_units_df.iterrows():
            chunk_id = str(row["id"])
            node_key = f"chunk:{chunk_id}"
            text = str(row.get("text") or "")
            preview = text[:140] + ("…" if len(text) > 140 else "")
            nodes.append({
                "key": node_key,
                "attributes": {
                    "label": f"Chunk {chunk_id[:8]}",
                    "size": KIND_SIZE["chunk"],
                    "color": KIND_PALETTE["chunk"],
                    "typeColor": KIND_PALETTE["chunk"],
                    "communityColor": KIND_PALETTE["chunk"],
                    "_kind": "chunk",
                    "_text": preview,
                    "_n_tokens": int(row.get("n_tokens") or 0),
                    "_document_ids": [str(d) for d in _as_list(row.get("document_ids"))],
                    "_chunk_id": chunk_id,
                },
            })
            kind_counts["chunk"] += 1

    # Communities ----------
    community_node_keys: dict[str, str] = {}
    for cid in sorted(all_cids, key=lambda c: (len(c), c)):
        if not cid:
            continue
        node_key = f"comm:{cid}"
        community_node_keys[cid] = node_key
        report = report_by_cid.get(cid, {})
        struct = struct_by_cid.get(cid, {})
        n_members = int(struct.get("size") or len(members_by_community.get(cid, [])))
        n_findings = len(_as_list(report.get("findings")))
        title = str(report.get("title") or struct.get("title") or f"Community {cid}")
        community_color = community_palette.get(cid, "#666c79")
        # Communities scale up *gently* with member count — they're meant as a
        # labelled landmark when the user toggles them on, not a giant halo
        # that swallows its members.
        size = KIND_SIZE["community"] + min(8.0, n_members * 0.08)
        nodes.append({
            "key": node_key,
            "attributes": {
                "label": title,
                "size": size,
                "color": community_color,
                "typeColor": community_color,
                "communityColor": community_color,
                "_kind": "community",
                "_community_id": cid,
                "_level": int(report.get("level") or struct.get("level") or 0),
                "_size": n_members,
                "_rank": float(report.get("rank") or 0.0),
                "_title": title,
                "_summary": str(report.get("summary") or ""),
                "_n_findings": n_findings,
            },
        })
        kind_counts["community"] += 1

    # Findings ----------
    finding_keys: list[tuple[str, str]] = []  # [(cid, finding_node_key), ...]
    if reports_df is not None and not reports_df.empty:
        for _, row in reports_df.iterrows():
            cid = str(row["community"])
            findings = _as_list(row.get("findings"))
            community_color = community_palette.get(cid, "#666c79")
            for idx, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    continue
                node_key = f"find:{cid}:{idx}"
                summary = str(finding.get("summary") or "")
                nodes.append({
                    "key": node_key,
                    "attributes": {
                        "label": summary[:60] + ("…" if len(summary) > 60 else ""),
                        "size": KIND_SIZE["finding"],
                        "color": community_color,
                        "typeColor": KIND_PALETTE["finding"],
                        "communityColor": community_color,
                        "_kind": "finding",
                        "_summary": summary,
                        "_explanation": str(finding.get("explanation") or ""),
                        "_community_id": cid,
                    },
                })
                kind_counts["finding"] += 1
                finding_keys.append((cid, node_key))

    # ── Build edges ───────────────────────────────────────────────────────
    edges: list[dict[str, Any]] = []
    edge_kind_counts: dict[str, int] = {}

    def _add_edge(key: str, src: str, tgt: str, kind: str, **attrs: Any) -> None:
        if src == tgt:
            return
        edges.append({
            "key": key,
            "source": src,
            "target": tgt,
            "attributes": {
                "size": attrs.pop("size", EDGE_MIN_SIZE),
                "color": attrs.pop("color", EDGE_COLOR),
                "_kind": kind,
                **attrs,
            },
        })
        edge_kind_counts[kind] = edge_kind_counts.get(kind, 0) + 1

    # RELATED — entity↔entity edges.
    if not relationships_df.empty:
        weights = relationships_df["weight"].astype(float).fillna(1.0)
        edge_size_fn = _make_log_scaler(weights, EDGE_MIN_SIZE, EDGE_MAX_SIZE)
        for _, row in relationships_df.iterrows():
            src = name_to_id.get(str(row["source"]))
            tgt = name_to_id.get(str(row["target"]))
            if not src or not tgt:
                continue
            description = str(row.get("description") or "")
            label = description if len(description) <= EDGE_LABEL_MAX_CHARS else description[: EDGE_LABEL_MAX_CHARS - 1] + "…"
            _add_edge(
                str(row["id"]), src, tgt, "RELATED",
                label=label,
                size=edge_size_fn(float(row.get("weight") or 1.0)),
                _description=description,
                _weight=float(row.get("weight") or 1.0),
                _rank=float(row.get("rank") or 0.0),
            )

    # PART_OF — chunk → document.
    if text_units_df is not None and not text_units_df.empty:
        for _, row in text_units_df.iterrows():
            chunk_node = f"chunk:{row['id']}"
            for doc_id in _as_list(row.get("document_ids")):
                if str(doc_id) in doc_rows:
                    _add_edge(
                        f"partof:{row['id']}:{doc_id}",
                        chunk_node, f"doc:{doc_id}", "PART_OF",
                    )

    # HAS_ENTITY — chunk → entity. Derived from entities.text_unit_ids inverted.
    if text_units_df is not None and not text_units_df.empty:
        for chunk_id, entity_names in chunk_to_entities.items():
            chunk_node = f"chunk:{chunk_id}"
            for name in entity_names:
                ent_id = name_to_id.get(name)
                if ent_id:
                    _add_edge(
                        f"hasent:{chunk_id}:{ent_id}",
                        chunk_node, ent_id, "HAS_ENTITY",
                    )

    # IN_COMMUNITY — entity → community.
    for ent_name, cid in name_to_community.items():
        ent_id = name_to_id.get(ent_name)
        comm_key = community_node_keys.get(cid)
        if ent_id and comm_key:
            _add_edge(
                f"incomm:{ent_id}:{cid}",
                ent_id, comm_key, "IN_COMMUNITY",
                color=community_palette.get(cid, EDGE_COLOR) + "55",
            )

    # HAS_FINDING — community → finding.
    for cid, finding_key in finding_keys:
        comm_key = community_node_keys.get(cid)
        if comm_key:
            _add_edge(
                f"hasfind:{finding_key}",
                comm_key, finding_key, "HAS_FINDING",
                color=community_palette.get(cid, EDGE_COLOR) + "77",
            )

    # MENTIONS — synthetic document ↔ entity, used when chunks are hidden so
    # the chain Doc—Chunk—Entity collapses into a direct Doc—Entity edge.
    for _, row in entities_df.iterrows():
        ent_id = str(row["id"])
        seen: set[str] = set()
        for doc_id in _as_list(row.get("document_ids")):
            doc_key = f"doc:{doc_id}"
            if str(doc_id) in doc_rows and doc_id not in seen:
                seen.add(doc_id)
                _add_edge(
                    f"mentions:{doc_id}:{ent_id}",
                    doc_key, ent_id, "MENTIONS",
                    color=KIND_PALETTE["document"] + "44",
                )

    # ── Meta ──────────────────────────────────────────────────────────────
    community_counts: dict[str, int] = {}
    for c in name_to_community.values():
        if c:
            community_counts[c] = community_counts.get(c, 0) + 1

    meta = {
        "n_entities": kind_counts["entity"],
        "n_relationships": edge_kind_counts.get("RELATED", 0),
        "n_communities": kind_counts["community"],
        "n_documents": kind_counts["document"],
        "n_chunks": kind_counts["chunk"],
        "n_findings": kind_counts["finding"],
        "kind_counts": kind_counts,
        "edge_kind_counts": edge_kind_counts,
        "kind_palette": KIND_PALETTE,
        "type_palette": type_palette,
        "type_counts": type_counts,
        "community_palette": community_palette,
        "community_counts": community_counts,
        "default_visible_kinds": list(DEFAULT_VISIBLE_KINDS),
        "default_visible_edge_kinds": list(DEFAULT_VISIBLE_EDGE_KINDS),
        "force_settings": resolved_force,
    }
    if truncation is not None:
        meta["truncation"] = truncation
    return SigmaGraph(nodes=nodes, edges=edges, meta=meta)


# ──────────────────────────────────────────────────────────────── helpers


def _build_entity_networkx(entities_df: pd.DataFrame, relationships_df: pd.DataFrame) -> nx.Graph:
    g = nx.Graph()
    for name in entities_df["name"].astype(str):
        g.add_node(name)
    if not relationships_df.empty:
        for _, row in relationships_df.iterrows():
            src, tgt = str(row["source"]), str(row["target"])
            if src == tgt:
                continue
            g.add_edge(src, tgt, weight=float(row.get("weight") or 1.0))
    return g


def _resolve_communities(nodes_df: pd.DataFrame) -> dict[str, str]:
    if nodes_df is None or nodes_df.empty:
        return {}
    if "title" not in nodes_df.columns or "community" not in nodes_df.columns:
        return {}
    df = nodes_df.copy()
    if "level" in df.columns:
        df["level"] = df["level"].astype(int)
        df = df.sort_values("level").drop_duplicates("title", keep="last")
    return {str(row["title"]): str(row["community"]) for _, row in df.iterrows()}


def _resolve_documents(doc_ids: Any, doc_rows: dict[str, dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for did in _as_list(doc_ids):
        info = doc_rows.get(str(did))
        title = str(info.get("title")) if info else None
        if title and title not in titles:
            titles.append(title)
    return titles


def _as_list(value: Any) -> list[Any]:
    """Normalise ``None``, numpy arrays, pandas series, and python iterables to a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(value)
    except TypeError:
        return [value]


def _make_log_scaler(values: pd.Series, lo: float, hi: float):
    import math

    vmin = float(values.min()) if not values.empty else 0.0
    vmax = float(values.max()) if not values.empty else 1.0
    if vmax <= vmin:
        return lambda _v: (lo + hi) / 2
    log_min = math.log1p(max(vmin, 0))
    log_max = math.log1p(max(vmax, 0))
    span = log_max - log_min or 1.0

    def scale(v: float) -> float:
        t = (math.log1p(max(v, 0)) - log_min) / span
        t = max(0.0, min(1.0, t))
        return lo + t * (hi - lo)

    return scale


def _empty_meta(
    force_settings: Optional[dict[str, float | int]] = None,
) -> dict[str, Any]:
    resolved = dict(DEFAULT_FORCE_SETTINGS)
    if force_settings:
        resolved.update(force_settings)
    return {
        "n_entities": 0,
        "n_relationships": 0,
        "n_communities": 0,
        "n_documents": 0,
        "n_chunks": 0,
        "n_findings": 0,
        "kind_counts": {k: 0 for k in KIND_PALETTE},
        "edge_kind_counts": {},
        "kind_palette": KIND_PALETTE,
        "type_palette": {},
        "type_counts": {},
        "community_palette": {},
        "community_counts": {},
        "default_visible_kinds": list(DEFAULT_VISIBLE_KINDS),
        "default_visible_edge_kinds": list(DEFAULT_VISIBLE_EDGE_KINDS),
        "force_settings": resolved,
    }
