"""
Incremental community updates.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

When documents are added / edited / deleted, we don't want to re-cluster the whole
graph from scratch. This module computes a *change ratio* (affected entities ÷
total) and either:

* Below the threshold — apply label propagation to new nodes by inheriting their
  most-connected neighbour's community.
* Above the threshold — re-run Leiden on the affected subgraph and merge the
  resulting communities back into the global assignment.

v0.1 ships the change-ratio dispatcher and the cheap label-propagation path. The
expensive re-clustering path is implemented as a graceful fallback: re-run Leiden
on the entire graph. Subsequent phases will narrow this to the affected subgraph.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import pandas as pd

from grail.indexing.communities import CommunityExtractor
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
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        """Decide between label propagation and full re-clustering, then update artefacts."""
        deleted_entity_names = deleted_entity_names or []
        total = max(graph.number_of_nodes() + len(deleted_entity_names), 1)
        changed = len(new_entity_names) + len(updated_entity_names) + len(deleted_entity_names)
        ratio = changed / total
        self.reporter.info(
            f"Incremental update: changed={changed}, total={total}, ratio={ratio:.2f}, "
            f"threshold={self.change_threshold}"
        )
        if ratio < self.change_threshold:
            return self._label_propagate(graph, new_entity_names)
        return self.base_extractor.extract_communities(graph)

    # ------------------------------------------------------------------ edit

    def incremental_edit(
        self,
        graph: nx.Graph,
        *,
        new_entity_names: list[str],
        updated_entity_names: list[str],
        deleted_entity_names: list[str],
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        """Handle edit: remove deleted nodes, re-assign affected communities.

        Deleted nodes are removed from the graph before the change-ratio check.
        Then the dispatcher chooses label propagation or full re-clustering.
        """
        for name in deleted_entity_names:
            if name in graph.nodes:
                graph.remove_node(name)

        total = max(graph.number_of_nodes() + len(deleted_entity_names), 1)
        changed = len(new_entity_names) + len(updated_entity_names) + len(deleted_entity_names)
        ratio = changed / total
        self.reporter.info(
            f"Incremental edit: changed={changed}, total={total}, ratio={ratio:.2f}, "
            f"threshold={self.change_threshold}"
        )
        if ratio < self.change_threshold:
            return self._label_propagate(graph, new_entity_names)
        return self.base_extractor.extract_communities(graph)

    # ------------------------------------------------------------------ delete

    def incremental_delete(
        self,
        graph: nx.Graph,
        *,
        deleted_entity_names: list[str],
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        """Handle delete: remove nodes, prune empty communities, rebuild artefacts."""
        for name in deleted_entity_names:
            if name in graph.nodes:
                graph.remove_node(name)

        if graph.number_of_nodes() == 0:
            self.reporter.info("Graph is empty after deletion.")
            nodes_df = self.base_extractor._build_nodes_df(graph, {})
            comm_df = self.base_extractor._build_communities_df({})
            self.base_extractor._write_artifacts(nodes_df, comm_df)
            return graph, {}, nodes_df, comm_df

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
        return graph, communities, nodes_df, comm_df

    # ------------------------------------------------------------------ label prop

    def _label_propagate(
        self, graph: nx.Graph, new_entity_names: list[str]
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        """Inherit each new node's community from its highest-weight neighbour."""
        community_attr: dict[str, str] = {}
        for node, data in graph.nodes(data=True):
            cid = data.get("community")
            if cid is not None:
                community_attr[node] = str(cid)
        for node in new_entity_names:
            if node not in graph.nodes:
                continue
            neighbour_communities: dict[str, float] = {}
            for nb in graph.neighbors(node):
                nb_comm = community_attr.get(nb)
                if nb_comm is None:
                    continue
                w = float(graph.edges[node, nb].get("weight", 1.0))
                neighbour_communities[nb_comm] = neighbour_communities.get(nb_comm, 0.0) + w
            if neighbour_communities:
                community_attr[node] = max(neighbour_communities, key=neighbour_communities.get)
            else:
                # Lonely new node — assign a fresh community id.
                next_id = (
                    max((int(c) for c in community_attr.values() if c.isdigit()), default=-1) + 1
                )
                community_attr[node] = str(next_id)

        # Reconstruct communities dict in the shape Leiden produces.
        communities: dict[int, dict[str, list[str]]] = {0: {}}
        for node, comm in community_attr.items():
            communities[0].setdefault(comm, []).append(node)
            graph.nodes[node]["community"] = comm

        nodes_df = self.base_extractor._build_nodes_df(graph, communities)
        comm_df = self.base_extractor._build_communities_df(communities)
        self.base_extractor._write_artifacts(nodes_df, comm_df)
        return graph, communities, nodes_df, comm_df
