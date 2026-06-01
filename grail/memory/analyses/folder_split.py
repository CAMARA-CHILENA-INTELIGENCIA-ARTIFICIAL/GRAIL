"""
Folder-split analysis — suggest dividing a large folder into sub-folders.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

For each declared folder community with at least ``folder_split_min_entities``
members, look at the induced subgraph and check whether it bimodally splits
into two dense sub-clusters with few cross-cluster edges.

The clustering itself is a one-shot greedy modularity partition: deterministic,
no external clustering deps, good enough to flag bimodality. When it produces
two sub-clusters both above a minimum size and the inter-cluster edge count
is at most half the intra-cluster total, fire a ``split_folder`` proposal.

Applying a split is destructive (files have to move on disk), so the
applier generates a shell script and marks the proposal
``accepted-pending-manual`` — the agent reviews + runs it explicitly.
"""
from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from grail.config import MemoryConfig
from grail.memory.proposals import Proposal


class FolderSplit:
    name = "folder_split"

    def propose(self, snapshot, config: MemoryConfig) -> list[Proposal]:
        ents = snapshot.entities
        rels = snapshot.relationships
        if ents.empty:
            return []

        # Folder → entity names that belong to it.
        folder_members: dict[str, list[str]] = {}
        for _, row in ents.iterrows():
            for cid in _aslist(row.get("community_ids")):
                folder_members.setdefault(str(cid), []).append(row["name"])

        # Build the global graph once.
        g = nx.Graph()
        for _, row in ents.iterrows():
            g.add_node(row["name"])
        if not rels.empty:
            for _, row in rels.iterrows():
                if row["source"] in g.nodes and row["target"] in g.nodes:
                    g.add_edge(row["source"], row["target"])

        proposals: list[Proposal] = []
        for folder, members in folder_members.items():
            if len(members) < config.folder_split_min_entities:
                continue
            sub = g.subgraph(members).copy()
            if sub.number_of_edges() < 4:
                continue
            # Greedy modularity gives at least one split if one exists. It
            # returns a list of frozensets; we keep the two largest.
            try:
                parts = list(
                    nx.algorithms.community.greedy_modularity_communities(sub)
                )
            except Exception:
                continue
            if len(parts) < 2:
                continue
            largest = sorted((list(p) for p in parts), key=len, reverse=True)[:2]
            if any(len(p) < 3 for p in largest):
                continue
            a, b = largest
            # Edges between vs within.
            within_a = sub.subgraph(a).number_of_edges()
            within_b = sub.subgraph(b).number_of_edges()
            between = sum(
                1 for u, v in sub.edges if (u in a and v in b) or (u in b and v in a)
            )
            inside_total = within_a + within_b
            if inside_total == 0:
                continue
            between_ratio = between / max(inside_total + between, 1)
            # We only suggest a split if the two sides are clearly cohesive.
            if between_ratio > 0.5:
                continue
            confidence = min(
                1.0,
                0.5 + (1.0 - between_ratio) / 2.0 + 0.05 * (min(len(a), len(b)) - 3),
            )

            suggested_a = f"{folder}/cluster-a"
            suggested_b = f"{folder}/cluster-b"
            rationale = (
                f"Folder '{folder}' has {len(members)} entities; greedy modularity finds "
                f"two cohesive sub-clusters of sizes {len(a)} and {len(b)} with only "
                f"{between} inter-cluster edges ({between_ratio:.0%} of total). "
                "Consider splitting into sub-folders. Accept generates a shell script "
                "you can review and run to move the underlying observation files."
            )
            proposals.append(
                Proposal.fresh(
                    kind="split_folder",
                    rationale=rationale,
                    confidence=confidence,
                    payload={
                        "folder": folder,
                        "suggested_split": [
                            {"id": suggested_a, "members": sorted(a)},
                            {"id": suggested_b, "members": sorted(b)},
                        ],
                    },
                    evidence={
                        "within_a": int(within_a),
                        "within_b": int(within_b),
                        "between": int(between),
                        "between_ratio": float(between_ratio),
                    },
                )
            )
        return proposals


def _aslist(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if hasattr(value, "tolist"):
        return list(value.tolist())
    return [value]


__all__ = ["FolderSplit"]
