"""Stable largest-connected-component utilities.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Same graph → same LCC, every time. Node names are uppercased and HTML-unescaped to
match the legacy normalization, so existing parquet artefacts remain queryable.
"""
from __future__ import annotations

import html
from typing import cast

import networkx as nx
from graspologic.utils import largest_connected_component


def normalize_node_names(graph: nx.Graph | nx.DiGraph) -> nx.Graph | nx.DiGraph:
    """Uppercase + HTML-unescape every node name and strip whitespace."""
    mapping = {node: html.unescape(str(node).upper().strip()) for node in graph.nodes()}
    return nx.relabel_nodes(graph, mapping)


def stable_largest_connected_component(graph: nx.Graph) -> nx.Graph:
    """Return the LCC of ``graph`` with nodes and edges sorted deterministically."""
    graph = graph.copy()
    graph = cast(nx.Graph, largest_connected_component(graph))
    graph = normalize_node_names(graph)
    return _stabilize_graph(graph)


def _stabilize_graph(graph: nx.Graph) -> nx.Graph:
    fixed: nx.Graph = nx.DiGraph() if graph.is_directed() else nx.Graph()
    sorted_nodes = sorted(graph.nodes(data=True), key=lambda x: x[0])
    fixed.add_nodes_from(sorted_nodes)
    edges = list(graph.edges(data=True))
    if not graph.is_directed():
        edges = [
            (min(s, t), max(s, t), data) for s, t, data in edges
        ]
    edges.sort(key=lambda x: f"{x[0]} -> {x[1]}")
    fixed.add_edges_from(edges)
    return fixed
