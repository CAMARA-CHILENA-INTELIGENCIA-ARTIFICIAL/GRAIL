"""
Edge-density analysis — discover communities the agent didn't declare.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Looks for clusters of entities that:
  1. are densely connected to each other (internal edge density above threshold),
  2. **span multiple declared folder communities** (so they're a cross-cutting group
     the agent might not have noticed),
  3. have at least ``edge_density_min_members`` entities.

Each such cluster becomes one ``discover_community`` proposal. The clustering
itself is a simple connected-components scan on a filtered graph — we keep
only the *strong* edges (top quartile by weight, or weight >= 1) and look at
the resulting components. Cheap, deterministic, no external clustering deps.

For richer outputs the orchestrator can layer Leiden or HDBSCAN on top later.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import networkx as nx
import numpy as np
import pandas as pd

from grail.config import MemoryConfig
from grail.memory.proposals import Proposal


class EdgeDensity:
    name = "edge_density"

    def propose(self, snapshot, config: MemoryConfig) -> list[Proposal]:
        ents = snapshot.entities
        rels = snapshot.relationships
        if ents.empty or rels.empty:
            return []

        # Build a weighted graph from the relationships.
        g = nx.Graph()
        for _, row in ents.iterrows():
            g.add_node(row["name"])
        for _, row in rels.iterrows():
            src = row["source"]
            tgt = row["target"]
            if src in g.nodes and tgt in g.nodes:
                w = float(row.get("weight", 1.0))
                if g.has_edge(src, tgt):
                    g[src][tgt]["weight"] += w
                else:
                    g.add_edge(src, tgt, weight=w)

        # Strong-edge subgraph: keep edges whose weight is at or above the
        # median of all weights. Cheap heuristic — surfaces the densest
        # neighbourhoods without an external library.
        weights = [d["weight"] for _, _, d in g.edges(data=True)]
        if not weights:
            return []
        threshold = float(np.median(weights))
        strong = nx.Graph()
        for u, v, d in g.edges(data=True):
            if d["weight"] >= threshold:
                strong.add_edge(u, v, weight=d["weight"])

        # Entity → declared folder communities map.
        name_to_communities: dict[str, list[str]] = {}
        for _, row in ents.iterrows():
            name_to_communities[row["name"]] = _aslist(row.get("community_ids"))

        proposals: list[Proposal] = []
        already_seen: set[frozenset[str]] = set()

        # Walk connected components of the strong-edge graph. Each component
        # is a candidate cluster.
        for component in nx.connected_components(strong):
            members = sorted(component)
            if len(members) < config.edge_density_min_members:
                continue
            if frozenset(members) in already_seen:
                continue
            already_seen.add(frozenset(members))

            # Internal edge density inside the strong subgraph: edges / max_edges.
            n = len(members)
            max_edges = n * (n - 1) / 2
            internal_edges = strong.subgraph(members).number_of_edges()
            density = internal_edges / max_edges if max_edges > 0 else 0.0
            if density < config.edge_density_min_internal:
                continue

            # Cross-folder check: do the members span 2+ declared communities?
            shared: set[str] = set()
            distinct_per_member: list[set[str]] = []
            for m in members:
                cids = set(name_to_communities.get(m, []) or [])
                distinct_per_member.append(cids)
                shared |= cids
            # Subtract the trivial case where all members share exactly the
            # same single folder.
            if len(shared) < 2:
                continue
            cross_folder_count = sum(
                1
                for s in distinct_per_member
                if s and not all(c in s for c in shared)
            )
            if cross_folder_count < config.edge_density_min_cross_folder:
                continue

            # Confidence: density (up to 1.0) lightly boosted by cross-folder span.
            confidence = min(
                1.0,
                density + 0.05 * (len(shared) - 1) + 0.05 * (cross_folder_count - 1),
            )

            suggested_id = "discovered/" + "-".join(
                m.lower().replace("_", "-")[:20] for m in members[:3]
            )
            shared_folders = sorted(shared)

            rationale = (
                f"{', '.join(members[:5])}"
                f"{' …' if len(members) > 5 else ''} co-occur with internal "
                f"density {density:.2f} (threshold {config.edge_density_min_internal:.2f}) "
                f"across folders [{', '.join(shared_folders)}]. "
                "Consider declaring a discovered community to capture the link."
            )

            proposals.append(
                Proposal.fresh(
                    kind="discover_community",
                    rationale=rationale,
                    confidence=confidence,
                    payload={
                        "members": members,
                        "suggested_id": suggested_id,
                    },
                    evidence={
                        "internal_density": float(density),
                        "internal_edges": int(internal_edges),
                        "member_count": int(n),
                        "shared_folders": shared_folders,
                    },
                )
            )

        return proposals


def _aslist(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "tolist"):
        return list(value.tolist())
    return [value]


__all__ = ["EdgeDensity"]
