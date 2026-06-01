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
from grail.indexing.schema_migration import migrate_dataframe
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
        self,
        graph: Optional[nx.Graph] = None,
        entities_df: Optional[pd.DataFrame] = None,
    ) -> tuple[nx.Graph, dict[int, dict[str, list[str]]], pd.DataFrame, pd.DataFrame]:
        if graph is None:
            graph = self._read_graph()
        if graph is None or graph.number_of_nodes() == 0:
            self.reporter.warning("No graph available; skipping community extraction.")
            return nx.Graph(), {}, pd.DataFrame(), pd.DataFrame()

        if entities_df is None:
            entities_df = self._read_entities()

        communities = run_leiden(
            graph,
            max_cluster_size=self.max_cluster_size,
            use_lcc=self.use_lcc,
            min_community_size=self.min_community_size,
            seed=self.seed,
            embedding_merge_eps=self.embedding_merge_eps,
            reporter=self.reporter,
        )
        nodes_df = self._build_nodes_df(graph, communities, entities_df)
        comm_df = self._build_communities_df(communities)
        self._write_artifacts(nodes_df, comm_df)
        # Tag the graph with community ids (top level wins for the per-node attribute).
        if communities:
            top_level = max(communities.keys())
            node_to_comm = {n: cid for cid, nodes in communities[top_level].items() for n in nodes}
            for node, comm_id in node_to_comm.items():
                if node in graph.nodes:
                    graph.nodes[node]["community"] = comm_id
        # Backfill ``community_ids`` on final_entities so the column is
        # populated for cascade/local search and memory-mode tools alike.
        # KB mode produces single-element lists (Leiden's hard partition);
        # memory mode extends the list when the agent declares folder
        # membership or consolidate accepts a discovered community.
        self._update_entity_community_ids(comm_df)
        return graph, communities, nodes_df, comm_df

    def _update_entity_community_ids(self, comm_df: pd.DataFrame) -> None:
        """Write ``community_ids`` back to ``final_entities.parquet``.

        For each entity, collect every community it belongs to (across all
        levels). KB-mode entities typically end up with one entry per level
        they exist at (Leiden is a hard partition within a level).
        """
        if comm_df is None or comm_df.empty:
            return
        entities_key = f"{self.output_folder}/final_entities.parquet"
        if not self.storage.exists(entities_key):
            return
        with self.storage.open_for_read(entities_key) as path:
            entities_df = pd.read_parquet(path)
        if entities_df.empty:
            return
        name_to_cids: dict[str, list[str]] = {}
        for _, row in comm_df.iterrows():
            cid = str(row["community"])
            members = row.get("entity_ids") or []
            for name in members:
                name_to_cids.setdefault(name, [])
                if cid not in name_to_cids[name]:
                    name_to_cids[name].append(cid)
        entities_df = entities_df.copy()
        entities_df["community_ids"] = entities_df["name"].map(
            lambda n: name_to_cids.get(n, [])
        )
        with self.storage.open_for_write(entities_key) as path:
            entities_df.to_parquet(path, index=False)

    # ------------------------------------------------------------------ persistence

    def _read_graph(self) -> Optional[nx.Graph]:
        key = f"{self.output_folder}/entity_relationship_graph.graphml"
        if not self.storage.exists(key):
            return None
        with self.storage.open_for_read(key) as path:
            return nx.read_graphml(path)

    def _read_entities(self) -> Optional[pd.DataFrame]:
        key = f"{self.output_folder}/final_entities.parquet"
        if not self.storage.exists(key):
            return None
        with self.storage.open_for_read(key) as path:
            df = pd.read_parquet(path)
        return migrate_dataframe(df, "final_entities")

    def _build_nodes_df(
        self,
        graph: nx.Graph,
        communities: dict[int, dict[str, list[str]]],
        entities_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        if entities_df is None:
            entities_df = self._read_entities()
        entity_lookup: dict[str, dict] = {}
        if entities_df is not None and not entities_df.empty:
            for _, e in entities_df.iterrows():
                tids = e.get("text_unit_ids")
                if tids is not None and hasattr(tids, "__iter__") and not isinstance(tids, str):
                    source_id = ",".join(str(t) for t in tids)
                else:
                    source_id = ""
                entity_lookup[e["name"]] = {
                    "human_readable_id": int(e.get("human_readable_id", 0) or 0),
                    "source_id": source_id,
                    "graph_embedding": e.get("graph_embedding"),
                }

        top_level = max(communities.keys()) if communities else 0
        top_level_map: dict[str, str] = {}
        if communities and top_level in communities:
            for cid, nodes in communities[top_level].items():
                for n in nodes:
                    top_level_map[n] = str(cid)

        rows = []
        for level, level_communities in communities.items():
            for community_id, nodes in level_communities.items():
                for node in nodes:
                    data = graph.nodes.get(node, {})
                    extra = entity_lookup.get(node, {})
                    degree = int(data.get("degree", 0) or 0)
                    rows.append(
                        {
                            "level": int(level),
                            "community": str(community_id),
                            "title": node,
                            "id": data.get("id", node),
                            "type": data.get("type"),
                            "description": data.get("description", ""),
                            "degree": degree,
                            "human_readable_id": extra.get("human_readable_id", 0),
                            "source_id": extra.get("source_id", ""),
                            "size": degree,
                            "graph_embedding": extra.get("graph_embedding"),
                            "top_level_node_id": top_level_map.get(node, ""),
                            "x": 0,
                            "y": 0,
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
                        # ``kind`` differentiates how this community came to
                        # exist: ``leiden`` is the default KB-mode output,
                        # ``folder`` is declared via the agent's memory tree,
                        # ``discovered`` is added by ``consolidate()`` after
                        # the agent accepts a proposal.
                        "kind": "leiden",
                    }
                )
        return pd.DataFrame(rows)

    def _write_artifacts(self, nodes_df: pd.DataFrame, communities_df: pd.DataFrame) -> None:
        with self.storage.open_for_write(f"{self.output_folder}/final_nodes.parquet") as path:
            nodes_df.to_parquet(path, index=False)
        with self.storage.open_for_write(f"{self.output_folder}/final_communities.parquet") as path:
            communities_df.to_parquet(path, index=False)
