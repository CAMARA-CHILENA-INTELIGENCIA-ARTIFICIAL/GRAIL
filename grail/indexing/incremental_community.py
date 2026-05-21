"""
Incremental community updates.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

When documents are added / edited / deleted, we don't want to re-cluster the whole
graph from scratch. This module computes a *change ratio* (affected entities /
total) and chooses one of two strategies:

* Below the threshold — apply label propagation to new nodes by inheriting their
  most-connected neighbour's community.
* Above the threshold — run Leiden on the **affected subgraph** (changed nodes +
  their 1-hop neighbours), then merge the resulting sub-communities back into the
  global assignment by matching against existing communities.

All three methods (update, incremental_edit, incremental_delete) return the set of
**affected community IDs** so the caller can selectively regenerate only those
community reports.
"""
from __future__ import annotations

import logging
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import pandas as pd

from grail.indexing.communities import CommunityExtractor
from grail.indexing.leiden import run_leiden
from grail.reporting import NullReporter, Reporter
from grail.storage import StorageBackend

log = logging.getLogger(__name__)


@dataclass
class IncrementalCommunityExtractor:
    storage: StorageBackend
    base_extractor: CommunityExtractor
    change_threshold: float = 0.3
    output_folder: str = "output"
    reporter: Reporter = field(default_factory=NullReporter)

    def update(
        self,
        graph: nx.Graph,
        *,
        new_entity_names: list[str],
        updated_entity_names: list[str],
        deleted_entity_names: list[str] | None = None,
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame, set[str]]:
        """Decide between label propagation and subgraph Leiden, then update artefacts.

        Returns ``(graph, communities, nodes_df, comm_df, affected_community_ids)``.
        """
        deleted_entity_names = deleted_entity_names or []
        total = max(graph.number_of_nodes() + len(deleted_entity_names), 1)
        changed = len(new_entity_names) + len(updated_entity_names) + len(deleted_entity_names)
        ratio = changed / total
        self.reporter.info(
            f"Incremental update: changed={changed}, total={total}, ratio={ratio:.2f}, "
            f"threshold={self.change_threshold}"
        )

        affected_nodes = set(new_entity_names) | set(updated_entity_names)

        if ratio < self.change_threshold:
            graph, communities, nodes_df, comm_df = self._label_propagate(graph, new_entity_names)
            affected_cids = self._collect_affected_communities(graph, affected_nodes)
            return graph, communities, nodes_df, comm_df, affected_cids

        graph, communities, nodes_df, comm_df = self._subgraph_leiden(graph, affected_nodes)
        all_cids = set()
        for level_comms in communities.values():
            all_cids.update(level_comms.keys())
        return graph, communities, nodes_df, comm_df, all_cids

    # ------------------------------------------------------------------ edit

    def incremental_edit(
        self,
        graph: nx.Graph,
        *,
        new_entity_names: list[str],
        updated_entity_names: list[str],
        deleted_entity_names: list[str],
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame, set[str]]:
        """Handle edit: remove deleted nodes, re-assign affected communities.

        Returns ``(graph, communities, nodes_df, comm_df, affected_community_ids)``.
        """
        deleted_communities: set[str] = set()
        for name in deleted_entity_names:
            if name in graph.nodes:
                cid = graph.nodes[name].get("community")
                if cid is not None:
                    deleted_communities.add(str(cid))
                graph.remove_node(name)

        total = max(graph.number_of_nodes() + len(deleted_entity_names), 1)
        changed = len(new_entity_names) + len(updated_entity_names) + len(deleted_entity_names)
        ratio = changed / total
        self.reporter.info(
            f"Incremental edit: changed={changed}, total={total}, ratio={ratio:.2f}, "
            f"threshold={self.change_threshold}"
        )

        affected_nodes = set(new_entity_names) | set(updated_entity_names)

        if ratio < self.change_threshold:
            graph, communities, nodes_df, comm_df = self._label_propagate(graph, new_entity_names)
            affected_cids = self._collect_affected_communities(graph, affected_nodes)
            affected_cids |= deleted_communities
            # Track communities of updated entities too.
            for name in updated_entity_names:
                cid = graph.nodes.get(name, {}).get("community")
                if cid is not None:
                    affected_cids.add(str(cid))
            return graph, communities, nodes_df, comm_df, affected_cids

        graph, communities, nodes_df, comm_df = self._subgraph_leiden(graph, affected_nodes)
        all_cids = set()
        for level_comms in communities.values():
            all_cids.update(level_comms.keys())
        all_cids |= deleted_communities
        return graph, communities, nodes_df, comm_df, all_cids

    # ------------------------------------------------------------------ delete

    def incremental_delete(
        self,
        graph: nx.Graph,
        *,
        deleted_entity_names: list[str],
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame, set[str]]:
        """Handle delete: remove nodes, prune empty communities, rebuild artefacts.

        Returns ``(graph, communities, nodes_df, comm_df, affected_community_ids)``.
        """
        affected_cids: set[str] = set()
        for name in deleted_entity_names:
            if name in graph.nodes:
                cid = graph.nodes[name].get("community")
                if cid is not None:
                    affected_cids.add(str(cid))
                graph.remove_node(name)

        if graph.number_of_nodes() == 0:
            self.reporter.info("Graph is empty after deletion.")
            nodes_df = self.base_extractor._build_nodes_df(graph, {})
            comm_df = self.base_extractor._build_communities_df({})
            self.base_extractor._write_artifacts(nodes_df, comm_df)
            return graph, {}, nodes_df, comm_df, affected_cids

        community_attr: dict[str, str] = {}
        for node, data in graph.nodes(data=True):
            cid = data.get("community")
            if cid is not None:
                community_attr[node] = str(cid)

        communities: dict[int, dict[str, list[str]]] = {0: {}}
        for node, comm in community_attr.items():
            communities[0].setdefault(comm, []).append(node)

        self.reporter.info(
            f"After deletion: {graph.number_of_nodes()} nodes, "
            f"{len(communities[0])} communities."
        )
        nodes_df = self.base_extractor._build_nodes_df(graph, communities)
        comm_df = self.base_extractor._build_communities_df(communities)
        self.base_extractor._write_artifacts(nodes_df, comm_df)
        return graph, communities, nodes_df, comm_df, affected_cids

    # ------------------------------------------------------------------ subgraph Leiden

    def _subgraph_leiden(
        self,
        graph: nx.Graph,
        affected_nodes: set[str],
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        """Run Leiden on affected nodes + 1-hop neighbours, merge back into global assignments."""
        nodes_to_process = set(affected_nodes)
        for node in affected_nodes:
            if node in graph.nodes:
                nodes_to_process.update(graph.neighbors(node))

        self.reporter.info(
            f"Subgraph Leiden: {len(affected_nodes)} affected → "
            f"{len(nodes_to_process)} nodes to process (with 1-hop neighbours)"
        )

        subgraph = graph.subgraph(nodes_to_process)

        if subgraph.number_of_nodes() < 2:
            self.reporter.warning("Subgraph too small for Leiden; falling back to full re-cluster.")
            return self.base_extractor.extract_communities(graph)

        # Collect existing community assignments from the full graph.
        existing_communities: set[str] = set()
        for node in graph.nodes():
            comm = graph.nodes[node].get("community")
            if comm is not None:
                existing_communities.add(str(comm))

        try:
            sub_communities = run_leiden(
                subgraph,
                max_cluster_size=self.base_extractor.max_cluster_size,
                use_lcc=False,
                min_community_size=self.base_extractor.min_community_size,
                seed=self.base_extractor.seed,
                embedding_merge_eps=self.base_extractor.embedding_merge_eps,
                reporter=self.reporter,
            )
        except Exception as e:
            self.reporter.warning(f"Subgraph Leiden failed ({e}); falling back to full re-cluster.")
            return self.base_extractor.extract_communities(graph)

        if not sub_communities:
            return self.base_extractor.extract_communities(graph)

        # Use the top level from Leiden output.
        top_level = max(sub_communities.keys())
        sub_level_comms = sub_communities[top_level]

        # Match each sub-community to the best existing community.
        next_cid = max((int(c) for c in existing_communities if c.isdigit()), default=0) + 1
        community_mapping: dict[str, str] = {}

        for sub_cid, nodes in sub_level_comms.items():
            best_match = self._find_best_matching_community(nodes, existing_communities, graph)
            if best_match:
                community_mapping[sub_cid] = best_match
            else:
                community_mapping[sub_cid] = str(next_cid)
                existing_communities.add(str(next_cid))
                next_cid += 1

        # Apply new assignments to the subgraph nodes.
        for sub_cid, nodes in sub_level_comms.items():
            mapped = community_mapping[sub_cid]
            for node in nodes:
                if node in graph.nodes:
                    graph.nodes[node]["community"] = mapped

        # Rebuild the global communities dict from the full graph.
        community_attr: dict[str, str] = {}
        for node, data in graph.nodes(data=True):
            cid = data.get("community")
            if cid is not None:
                community_attr[node] = str(cid)

        communities: dict[int, dict[str, list[str]]] = {0: {}}
        for node, comm in community_attr.items():
            communities[0].setdefault(comm, []).append(node)

        nodes_df = self.base_extractor._build_nodes_df(graph, communities)
        comm_df = self.base_extractor._build_communities_df(communities)
        self.base_extractor._write_artifacts(nodes_df, comm_df)
        return graph, communities, nodes_df, comm_df

    @staticmethod
    def _find_best_matching_community(
        nodes: list[str],
        existing_communities: set[str],
        graph: nx.Graph,
    ) -> Optional[str]:
        """Score each existing community by how many neighbours of ``nodes`` belong to it."""
        scores: dict[str, int] = defaultdict(int)
        for node in nodes:
            if node not in graph.nodes:
                continue
            for nb in graph.neighbors(node):
                nb_comm = graph.nodes[nb].get("community")
                if nb_comm is not None and str(nb_comm) in existing_communities:
                    scores[str(nb_comm)] += 1
        if scores:
            return max(scores, key=scores.get)
        return None

    # ------------------------------------------------------------------ label prop

    def _label_propagate(
        self,
        graph: nx.Graph,
        new_entity_names: list[str],
        max_iterations: int = 10,
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        """Iterative label propagation with community-size awareness.

        For each new node, pick the neighbouring community with the strongest
        connection — but only if that community hasn't reached
        ``max_cluster_size``.  Iterate up to ``max_iterations`` times (with
        random shuffle each round) until assignments converge.
        """
        labels: dict[str, str] = {}
        existing_communities: set[str] = set()
        community_sizes: Counter[str] = Counter()

        for node, data in graph.nodes(data=True):
            cid = data.get("community")
            if cid is not None:
                labels[node] = str(cid)
                existing_communities.add(str(cid))
                community_sizes[str(cid)] += 1
            else:
                labels[node] = "_unlabeled"

        new_nodes = [n for n in new_entity_names if n in graph.nodes]
        max_size = self.base_extractor.max_cluster_size

        for iteration in range(max_iterations):
            changes = 0
            random.shuffle(new_nodes)

            for node in new_nodes:
                neighbour_labels = [
                    labels[nb]
                    for nb in graph.neighbors(node)
                    if nb in labels and labels[nb] != "_unlabeled"
                ]
                if not neighbour_labels:
                    continue

                label_counts = Counter(neighbour_labels)

                # Only consider communities that haven't hit the size cap.
                eligible = [
                    lbl for lbl in label_counts
                    if lbl in existing_communities and community_sizes[lbl] < max_size
                ]

                if eligible:
                    best_count = max(label_counts[lbl] for lbl in eligible)
                    candidates = [lbl for lbl in eligible if label_counts[lbl] == best_count]
                    new_label = random.choice(candidates)
                else:
                    new_label = labels[node]

                if labels[node] != new_label:
                    old = labels[node]
                    if old != "_unlabeled":
                        community_sizes[old] -= 1
                    labels[node] = new_label
                    community_sizes[new_label] += 1
                    changes += 1

            if changes == 0:
                break

        # Assign remaining unlabeled nodes to a fresh community.
        next_id = max((int(c) for c in existing_communities if c.isdigit()), default=-1) + 1
        for node, lbl in labels.items():
            if lbl == "_unlabeled":
                labels[node] = str(next_id)
                community_sizes[str(next_id)] += 1

        # Rebuild communities dict.
        communities: dict[int, dict[str, list[str]]] = {0: {}}
        for node, comm in labels.items():
            communities[0].setdefault(comm, []).append(node)
            graph.nodes[node]["community"] = comm

        nodes_df = self.base_extractor._build_nodes_df(graph, communities)
        comm_df = self.base_extractor._build_communities_df(communities)
        self.base_extractor._write_artifacts(nodes_df, comm_df)
        return graph, communities, nodes_df, comm_df

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _collect_affected_communities(graph: nx.Graph, node_names: set[str]) -> set[str]:
        """Return the community IDs of a set of nodes."""
        cids: set[str] = set()
        for name in node_names:
            cid = graph.nodes.get(name, {}).get("community")
            if cid is not None:
                cids.add(str(cid))
        return cids
