"""
Hierarchical Leiden community detection with embedding-based small-cluster merging.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Ports the legacy `leiden.py` with quieter logging and a slimmer signature. Returns
``{level: {community_id: [node_names]}}``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import networkx as nx
import numpy as np
from graspologic.partition import hierarchical_leiden
from sklearn.cluster import DBSCAN

from grail.indexing.stable_lcc import stable_largest_connected_component
from grail.reporting import NullReporter, Reporter

log = logging.getLogger(__name__)


def run_leiden(
    graph: nx.Graph,
    *,
    max_cluster_size: int = 50,
    use_lcc: bool = False,
    min_community_size: int = 10,
    seed: Optional[int] = 0xDEADBEEF,
    embedding_merge_eps: float = 0.5,
    levels: Optional[list[int]] = None,
    reporter: Reporter | None = None,
) -> dict[int, dict[str, list[str]]]:
    """Cluster ``graph`` with hierarchical Leiden and merge small communities by embedding."""
    rep = reporter or NullReporter()
    if graph.number_of_nodes() == 0:
        return {}

    rep.info(
        f"Leiden: nodes={graph.number_of_nodes()} edges={graph.number_of_edges()} "
        f"max_cluster_size={max_cluster_size} use_lcc={use_lcc}"
    )

    raw = _compute_leiden_communities(graph, max_cluster_size, use_lcc, seed=seed)
    if not raw:
        return {}

    levels = levels if levels is not None else sorted(raw.keys())
    results_by_level: dict[int, dict[str, list[str]]] = {}
    for level in levels:
        bucket: dict[str, list[str]] = {}
        for node_id, raw_community_id in raw[level].items():
            community_id = str(raw_community_id)
            bucket.setdefault(community_id, []).append(node_id)
        results_by_level[level] = bucket

    merged: dict[int, dict[str, list[str]]] = {}
    for level, communities in results_by_level.items():
        merged[level] = merge_communities_by_embedding(
            graph,
            communities,
            min_community_size=min_community_size,
            eps=embedding_merge_eps,
            reporter=rep,
        )
    return merged


def _compute_leiden_communities(
    graph: nx.Graph | nx.DiGraph,
    max_cluster_size: int,
    use_lcc: bool,
    *,
    seed: Optional[int] = 0xDEADBEEF,
) -> dict[int, dict[str, int]]:
    target = stable_largest_connected_component(graph) if use_lcc else graph
    if target.number_of_nodes() == 0:
        return {}

    partitions = hierarchical_leiden(target, max_cluster_size=max_cluster_size, random_seed=seed)

    results: dict[int, dict[str, int]] = {}
    for partition in partitions:
        results.setdefault(partition.level, {})[partition.node] = partition.cluster

    if not results:
        return {}

    # Any nodes that fell out (LCC trimming or graphrag isolates) go into a SINGLE
    # shared bucket per level, not per-node singletons. Promoting each isolate to
    # its own community used to produce dozens of one-entity "reports" that are
    # useless: by definition isolates have no relationships, so the "community"
    # has no graph structure to summarise. Filing them under one ID makes the
    # downstream report generator skip them via min_report_size.
    max_level = max(results.keys())
    max_id = max((max(v.values()) for v in results.values()), default=0)
    missing = set(graph.nodes()) - set(results[max_level].keys())
    if missing:
        isolate_id = max_id + 1
        for lvl in results:
            for node in missing:
                results[lvl][node] = isolate_id
    return results


def merge_communities_by_embedding(
    graph: nx.Graph,
    communities: dict[str, list[str]],
    *,
    min_community_size: int,
    eps: float = 0.5,
    reporter: Reporter | None = None,
) -> dict[str, list[str]]:
    """Merge small communities by DBSCAN-clustering their entity-embedding centroids."""
    rep = reporter or NullReporter()

    def _embedding(node: str) -> Optional[np.ndarray]:
        raw = graph.nodes[node].get("embedding")
        if raw is None:
            return None
        try:
            return np.array(json.loads(raw)) if isinstance(raw, str) else np.array(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    small = {cid: nodes for cid, nodes in communities.items() if len(nodes) < min_community_size}
    large = {cid: nodes for cid, nodes in communities.items() if len(nodes) >= min_community_size}

    centroids: dict[str, np.ndarray] = {}
    for cid, nodes in small.items():
        embeddings = [emb for n in nodes if (emb := _embedding(n)) is not None]
        if embeddings:
            try:
                centroids[cid] = np.mean(embeddings, axis=0)
            except Exception:  # pragma: no cover - defensive
                rep.warning(f"Failed to compute centroid for community {cid}")

    if centroids:
        labels = DBSCAN(eps=eps, min_samples=2).fit_predict(np.array(list(centroids.values())))
    else:
        labels = []

    merged = dict(large)
    next_id = max((int(k) for k in merged.keys() if k.isdigit()), default=0) + 1
    cluster_to_id: dict[int, str] = {}
    # Single "miscellaneous" bucket for noise. Previously each noise community
    # got a fresh id, which is what produced the long tail of singleton "reports"
    # we'd see at indexing time.
    misc_bucket_id: Optional[str] = None

    for i, (cid, _centroid) in enumerate(centroids.items()):
        label = labels[i] if i < len(labels) else -1
        if label == -1:
            if misc_bucket_id is None:
                misc_bucket_id = str(next_id)
                next_id += 1
            merged.setdefault(misc_bucket_id, []).extend(small[cid])
        else:
            if label not in cluster_to_id:
                cluster_to_id[label] = str(next_id)
                next_id += 1
            new_id = cluster_to_id[label]
            merged.setdefault(new_id, []).extend(small[cid])

    # Small communities whose nodes had no embeddings at all: lump them with the
    # noise bucket as well — same reasoning, no signal to cluster on.
    for cid, nodes in small.items():
        if cid in centroids:
            continue
        if misc_bucket_id is None:
            misc_bucket_id = str(next_id)
            next_id += 1
        merged.setdefault(misc_bucket_id, []).extend(nodes)
    return merged
