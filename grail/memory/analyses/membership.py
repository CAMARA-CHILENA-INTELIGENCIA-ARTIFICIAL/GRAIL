"""
Membership analysis — surface entities that "belong" to a folder they're not in.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

For each entity:
  * Count its edges that land *inside* its declared community(ies) vs edges
    that land in some other community.
  * If a single outside community dominates (and represents more edges than
    any community the entity actually belongs to), propose adding that
    community to the entity's ``community_ids``.

This is the "ALICE is filed under work/clients/acme but has 9 of her 11 edges
to entities in personal/friends" pattern. Confidence scales with the ratio
of dominant-outside edges to total edges.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from grail.config import MemoryConfig
from grail.memory.proposals import Proposal


class Membership:
    name = "membership"

    def propose(self, snapshot, config: MemoryConfig) -> list[Proposal]:
        ents = snapshot.entities
        rels = snapshot.relationships
        if ents.empty or rels.empty:
            return []

        # Entity → declared community_ids
        name_to_communities: dict[str, set[str]] = {}
        for _, row in ents.iterrows():
            name_to_communities[row["name"]] = set(_aslist(row.get("community_ids")))

        # Bucket each entity's neighbour communities.
        # For an undirected edge (A, B): A's neighbour communities include B's;
        # B's include A's.
        per_entity: dict[str, Counter] = defaultdict(Counter)
        for _, row in rels.iterrows():
            src = row["source"]
            tgt = row["target"]
            src_cids = name_to_communities.get(src, set())
            tgt_cids = name_to_communities.get(tgt, set())
            for c in tgt_cids:
                per_entity[src][c] += 1
            for c in src_cids:
                per_entity[tgt][c] += 1

        proposals: list[Proposal] = []
        for entity_name, counter in per_entity.items():
            declared = name_to_communities.get(entity_name, set())
            if not counter:
                continue
            # Drop the entity's own communities from the count to compute
            # "outside" pull, but remember in-community totals for context.
            inside_total = sum(counter[c] for c in declared)
            outside = {c: n for c, n in counter.items() if c not in declared}
            if not outside:
                continue
            dominant_cid, dominant_count = max(outside.items(), key=lambda kv: kv[1])
            total = inside_total + sum(outside.values())
            if total == 0:
                continue
            ratio = dominant_count / total
            # Two conditions: outside community dominates the total *and*
            # accounts for more edges than any declared community.
            max_inside = max((counter[c] for c in declared), default=0)
            if dominant_count <= max_inside:
                continue
            if ratio < 0.5:
                continue

            confidence = min(1.0, 0.5 + ratio / 2.0)
            rationale = (
                f"{entity_name} has {dominant_count} of {total} edges into "
                f"'{dominant_cid}'. Declared communities {sorted(declared) or '(none)'} "
                f"account for {inside_total}. Consider adding '{dominant_cid}' to "
                f"its community_ids so search surfaces it under that folder too."
            )
            proposals.append(
                Proposal.fresh(
                    kind="move_entity",
                    rationale=rationale,
                    confidence=confidence,
                    payload={
                        "entity": entity_name,
                        "add_community_ids": [dominant_cid],
                    },
                    evidence={
                        "inside_edges": int(inside_total),
                        "outside_edges": int(sum(outside.values())),
                        "dominant_community": dominant_cid,
                        "dominant_count": int(dominant_count),
                        "declared_communities": sorted(declared),
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


__all__ = ["Membership"]
