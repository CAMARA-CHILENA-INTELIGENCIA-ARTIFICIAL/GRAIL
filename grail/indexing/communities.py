"""
Community extraction orchestrator.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Reads the graph + entities/relationships parquets, runs Leiden, writes
``final_nodes.parquet`` and ``final_communities.parquet`` describing per-level
community membership. Delegates LLM-driven report generation to
:class:`CommunityReportGenerator`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import pandas as pd

from grail.indexing.leiden import run_leiden
from grail.reporting import NullReporter, Reporter
from grail.storage import StorageBackend

log = logging.getLogger(__name__)


@dataclass
class CommunityExtractor:
    storage: StorageBackend
    output_folder: str = "output"
    max_cluster_size: int = 50
    use_lcc: bool = False
    min_community_size: int = 10
    seed: Optional[int] = 0xDEADBEEF
    embedding_merge_eps: float = 0.5
    reporter: Reporter = field(default_factory=NullReporter)

    # ------------------------------------------------------------------ run

    def extract_communities(
        self, graph: Optional[nx.Graph] = None
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        if graph is None:
            graph = self._read_graph()
        if graph is None or graph.number_of_nodes() == 0:
            self.reporter.warning("No graph available; skipping community extraction.")
            return nx.Graph(), {}, pd.DataFrame(), pd.DataFrame()

        communities = run_leiden(
            graph,
            max_cluster_size=self.max_cluster_size,
            use_lcc=self.use_lcc,
            min_community_size=self.min_community_size,
            seed=self.seed,
            embedding_merge_eps=self.embedding_merge_eps,
            reporter=self.reporter,
        )
        nodes_df = self._build_nodes_df(graph, communities)
        comm_df = self._build_communities_df(communities)
        self._write_artifacts(nodes_df, comm_df)
        # Tag the graph with community ids (top level wins for the per-node attribute).
        if communities:
            top_level = max(communities.keys())
            node_to_comm = {n: cid for cid, nodes in communities[top_level].items() for n in nodes}
            for node, comm_id in node_to_comm.items():
                if node in graph.nodes:
                    graph.nodes[node]["community"] = comm_id
        return graph, communities, nodes_df, comm_df

    # ------------------------------------------------------------------ persistence

    def _read_graph(self) -> Optional[nx.Graph]:
        key = f"{self.output_folder}/entity_relationship_graph.graphml"
        if not self.storage.exists(key):
            return None
        with self.storage.open_for_read(key) as path:
            return nx.read_graphml(path)

    def _build_nodes_df(
        self, graph: nx.Graph, communities: dict[int, dict[str, list[str]]]
    ) -> pd.DataFrame:
        rows = []
        for level, level_communities in communities.items():
            for community_id, nodes in level_communities.items():
                for node in nodes:
                    data = graph.nodes.get(node, {})
                    rows.append(
                        {
                            "level": int(level),
                            "community": str(community_id),
                            "title": node,
                            "id": data.get("id", node),
                            "type": data.get("type"),
                            "description": data.get("description", ""),
                            "degree": int(data.get("degree", 0) or 0),
                        }
                    )
        return pd.DataFrame(rows)

    def _build_communities_df(
        self, communities: dict[int, dict[str, list[str]]]
    ) -> pd.DataFrame:
        rows = []
        for level, level_communities in communities.items():
            for community_id, nodes in level_communities.items():
                rows.append(
                    {
                        "id": f"{level}-{community_id}",
                        "level": int(level),
                        "community": str(community_id),
                        "title": f"Community {community_id} (level {level})",
                        "entity_ids": sorted(nodes),
                        "size": len(nodes),
                    }
                )
        return pd.DataFrame(rows)

    def _write_artifacts(self, nodes_df: pd.DataFrame, communities_df: pd.DataFrame) -> None:
        with self.storage.open_for_write(f"{self.output_folder}/final_nodes.parquet") as path:
            nodes_df.to_parquet(path, index=False)
        with self.storage.open_for_write(f"{self.output_folder}/final_communities.parquet") as path:
            communities_df.to_parquet(path, index=False)
