"""
Graph layout — community-aware.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

We want the viewer to *look* like the graph is organized by community: each
community renders as a visible cluster, and high-degree hubs sit at the center
of their cluster. A plain spring layout collapses everything that's strongly
connected into one ball regardless of community membership, which destroys that
story.

Two-stage algorithm:

1. **Within each community** — run NetworkX ``spring_layout`` on the community
   subgraph. This gives a tight, locally-correct embedding for that community.
2. **Across communities** — place community centers on a circle whose radius
   scales with the total node count. Larger communities get more canvas room.

Isolated nodes (no edges to their community peers) are arranged in a small
inner ring inside their community rather than spawning miles away as spring
layout would do.

The legacy ``compute_layout`` (single-stage spring) remains as a fallback for
cases without community info.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping, Optional

import networkx as nx


# ──────────────────────────────────────────────────────────────────────


def compute_layout(
    graph: nx.Graph,
    *,
    seed: int = 42,
    iterations: int = 200,
    scale: float = 1000.0,
) -> dict[Any, tuple[float, float]]:
    """Single-stage spring layout. Used as a fallback when communities are absent."""
    if graph.number_of_nodes() == 0:
        return {}
    raw = nx.spring_layout(graph, seed=seed, iterations=iterations, k=None)
    return {node: (float(x) * scale, float(y) * scale) for node, (x, y) in raw.items()}


# ──────────────────────────────────────────────────────────────────────


def compute_community_layout(
    graph: nx.Graph,
    node_communities: Mapping[Any, str],
    *,
    seed: int = 42,
    iterations: int = 120,
    canvas_scale: float = 1500.0,
    min_cluster_radius: float = 60.0,
    cluster_radius_factor: float = 22.0,
    inter_cluster_gap: float = 1.6,
) -> dict[Any, tuple[float, float]]:
    """Two-stage community-aware layout.

    Parameters
    ----------
    graph
        The full entity-relationship graph.
    node_communities
        ``node_name → community_id``. Nodes missing from this mapping are
        placed in a synthetic ``"_orphan"`` cluster.
    seed
        Reproducibility for the per-community spring layout.
    iterations
        Spring-layout iterations per community.
    canvas_scale
        Outer radius the community ring is laid out on. Scales the whole canvas.
    min_cluster_radius
        Floor for an individual community's cluster radius (so single-node
        communities still get a label-friendly footprint).
    cluster_radius_factor
        Per-node radius growth: ``cluster_radius = min + factor * sqrt(n)``.
    inter_cluster_gap
        Multiplier on the cluster ring radius to leave whitespace between
        clusters. ``1.0`` = clusters just touch; ``1.6`` = healthy gap.
    """
    if graph.number_of_nodes() == 0:
        return {}

    # ── Bucket nodes by community ──────────────────────────────────────
    buckets: dict[str, list[Any]] = defaultdict(list)
    for node in graph.nodes():
        cid = str(node_communities.get(node, "_orphan"))
        if cid in ("", "None", "nan"):
            cid = "_orphan"
        buckets[cid].append(node)

    if not buckets:
        return compute_layout(graph, seed=seed, iterations=iterations, scale=canvas_scale)

    # Sort: biggest community first so the ring placement is visually predictable.
    ordered_cids = sorted(buckets.keys(), key=lambda c: (-len(buckets[c]), c))

    # ── Pre-compute cluster radii (radius each community needs on canvas) ──
    cluster_radius: dict[str, float] = {}
    for cid in ordered_cids:
        n = len(buckets[cid])
        cluster_radius[cid] = min_cluster_radius + cluster_radius_factor * math.sqrt(n)

    # ── Place community centers on a ring ──────────────────────────────
    # The ring radius is whichever is larger:
    #   - canvas_scale (so small graphs still spread out nicely), or
    #   - enough to keep adjacent clusters from overlapping.
    n_cids = len(ordered_cids)
    if n_cids == 1:
        centers = {ordered_cids[0]: (0.0, 0.0)}
    else:
        max_cluster = max(cluster_radius.values())
        # Circumference per cluster needs to be ≥ 2 * cluster_radius * inter_cluster_gap.
        needed_radius = max_cluster * inter_cluster_gap * n_cids / (2 * math.pi)
        ring_radius = max(canvas_scale, needed_radius)
        centers = {}
        for i, cid in enumerate(ordered_cids):
            angle = 2 * math.pi * i / n_cids
            centers[cid] = (
                ring_radius * math.cos(angle),
                ring_radius * math.sin(angle),
            )

    # ── Compute positions per community ────────────────────────────────
    positions: dict[Any, tuple[float, float]] = {}
    for cid in ordered_cids:
        members = buckets[cid]
        cx, cy = centers[cid]
        r = cluster_radius[cid]

        if len(members) == 1:
            positions[members[0]] = (cx, cy)
            continue

        sub = graph.subgraph(members).copy()
        sub_edges = sub.number_of_edges()

        if sub_edges == 0:
            # Pure isolates — arrange in a small concentric ring.
            n = len(members)
            inner_r = r * 0.55
            for j, node in enumerate(members):
                angle = 2 * math.pi * j / n
                positions[node] = (cx + inner_r * math.cos(angle), cy + inner_r * math.sin(angle))
            continue

        # Spring layout on the subgraph. Use a small k so neighbours pack tight.
        try:
            sub_pos = nx.spring_layout(
                sub,
                seed=seed,
                iterations=iterations,
                k=1.0 / max(math.sqrt(sub.number_of_nodes()), 1),
            )
        except Exception:  # pragma: no cover — defensive
            sub_pos = nx.circular_layout(sub)

        # spring_layout output is in roughly [-1, 1]^2. Scale to cluster radius,
        # then translate to community center.
        for node, (x, y) in sub_pos.items():
            positions[node] = (cx + x * r, cy + y * r)

    return positions


# ──────────────────────────────────────────────────────────────────────


def compute_hierarchical_layout(
    *,
    entity_graph: nx.Graph,
    node_communities: Mapping[str, str],
    document_ids: Iterable[str],
    chunk_ids: Iterable[str],
    chunk_to_entities: Mapping[str, list[str]],
    chunk_to_documents: Mapping[str, list[str]],
    community_ids: Iterable[str],
    members_by_community: Mapping[str, list[str]],
    report_by_cid: Mapping[str, Mapping[str, Any]],
    seed: int = 42,
    iterations: int = 120,
) -> dict[tuple[str, str], tuple[float, float]]:
    """Compute positions for every node kind in one pass.

    The returned dict is keyed by ``(kind, id)`` so the exporter can look up
    positions for the right kind without name collisions (an entity name and a
    document id could otherwise collide).

    Layout strategy
    ---------------
    * **Entities** — community-aware spring layout (existing algorithm). Entity
      positions are keyed by ``entity_id`` *and* ``entity_name`` so callers can
      query by either.
    * **Communities** — each community node sits at the centroid of its member
      entities. If a community has no members it sits at the origin.
    * **Documents** — placed on a wide outer ring around the entity galaxy.
    * **Chunks** — each chunk is positioned at the midpoint between its
      document(s) and the entities it mentions. Falls back to its document's
      neighbourhood if the chunk has no entity references.
    * **Findings** — small inner ring inside their parent community.
    """
    positions: dict[tuple[str, str], tuple[float, float]] = {}

    # ── 1. Entities ────────────────────────────────────────────────────
    name_to_pos = compute_community_layout(
        entity_graph, node_communities, seed=seed, iterations=iterations,
    )
    for name, xy in name_to_pos.items():
        positions[("entity", name)] = xy

    if not name_to_pos:
        # No entities → nothing else needs layout. Return empty.
        return positions

    # Compute canvas bounds from the entity layout.
    xs = [p[0] for p in name_to_pos.values()]
    ys = [p[1] for p in name_to_pos.values()]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    cx, cy = (x_min + x_max) / 2, (y_min + y_max) / 2
    span = max(x_max - x_min, y_max - y_min, 1.0)

    # ── 2. Communities — at centroid of members ────────────────────────
    for cid in community_ids:
        if not cid:
            continue
        members = members_by_community.get(cid, [])
        if not members:
            positions[("community", cid)] = (cx, cy)
            continue
        mx = sum(name_to_pos.get(m, (cx, cy))[0] for m in members) / len(members)
        my = sum(name_to_pos.get(m, (cx, cy))[1] for m in members) / len(members)
        positions[("community", cid)] = (mx, my)

    # ── 3. Documents — outer ring ──────────────────────────────────────
    doc_ids_list = [d for d in document_ids if d]
    n_docs = len(doc_ids_list)
    if n_docs:
        outer_radius = span * 0.85
        for i, doc_id in enumerate(doc_ids_list):
            angle = 2 * math.pi * i / n_docs - math.pi / 2  # start at the top
            positions[("document", doc_id)] = (
                cx + outer_radius * math.cos(angle),
                cy + outer_radius * math.sin(angle),
            )

    # ── 4. Chunks — midpoint between their doc(s) and their entities ───
    for chunk_id in chunk_ids:
        doc_ids_for_chunk = [d for d in chunk_to_documents.get(chunk_id, []) if d]
        entity_names_for_chunk = chunk_to_entities.get(chunk_id, [])

        doc_positions = [positions.get(("document", d)) for d in doc_ids_for_chunk]
        doc_positions = [p for p in doc_positions if p is not None]
        ent_positions = [name_to_pos.get(n) for n in entity_names_for_chunk]
        ent_positions = [p for p in ent_positions if p is not None]

        if doc_positions and ent_positions:
            avg_doc = (
                sum(p[0] for p in doc_positions) / len(doc_positions),
                sum(p[1] for p in doc_positions) / len(doc_positions),
            )
            avg_ent = (
                sum(p[0] for p in ent_positions) / len(ent_positions),
                sum(p[1] for p in ent_positions) / len(ent_positions),
            )
            # 60% of the way from the doc toward the entities — keeps chunks
            # readable as a "bridge" layer.
            positions[("chunk", chunk_id)] = (
                avg_doc[0] + 0.6 * (avg_ent[0] - avg_doc[0]),
                avg_doc[1] + 0.6 * (avg_ent[1] - avg_doc[1]),
            )
        elif ent_positions:
            positions[("chunk", chunk_id)] = (
                sum(p[0] for p in ent_positions) / len(ent_positions),
                sum(p[1] for p in ent_positions) / len(ent_positions),
            )
        elif doc_positions:
            positions[("chunk", chunk_id)] = doc_positions[0]
        else:
            positions[("chunk", chunk_id)] = (cx, cy)

    # ── 5. Findings — small inner ring inside their community ──────────
    finding_radius = span * 0.04
    for cid, report in report_by_cid.items():
        comm_pos = positions.get(("community", cid))
        if not comm_pos:
            continue
        findings = report.get("findings") if isinstance(report, Mapping) else None
        if findings is None:
            continue
        try:
            findings_list = list(findings)
        except TypeError:
            continue
        n = len(findings_list)
        if n == 0:
            continue
        for idx in range(n):
            angle = 2 * math.pi * idx / n
            key = f"find:{cid}:{idx}"
            positions[("finding", key)] = (
                comm_pos[0] + finding_radius * math.cos(angle),
                comm_pos[1] + finding_radius * math.sin(angle),
            )

    return positions
