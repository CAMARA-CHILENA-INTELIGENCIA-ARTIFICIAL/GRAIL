"""Indexing pipeline.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Public surface:

* :class:`FileLoader` — chunk source files into text units.
* :class:`EntityRelationshipExtractor` — extract entities + relationships via LLM.
* :class:`SummarizeExtractor` — summarize per-entity descriptions.
* :class:`CommunityExtractor` — cluster the graph with Leiden.
* :class:`CommunityReportGenerator` — produce JSON community reports.
* :class:`IncrementalCommunityExtractor` — apply incremental updates after edits.
"""
from grail.indexing.communities import CommunityExtractor
from grail.indexing.community_reports import CommunityReportGenerator
from grail.indexing.entities_relationships import EntityRelationshipExtractor
from grail.indexing.incremental_community import IncrementalCommunityExtractor
from grail.indexing.leiden import run_leiden
from grail.indexing.loader import FileLoader
from grail.indexing.stable_lcc import (
    normalize_node_names,
    stable_largest_connected_component,
)
from grail.indexing.summarize_descriptions import SummarizeExtractor

__all__ = [
    "CommunityExtractor",
    "CommunityReportGenerator",
    "EntityRelationshipExtractor",
    "FileLoader",
    "IncrementalCommunityExtractor",
    "SummarizeExtractor",
    "normalize_node_names",
    "run_leiden",
    "stable_largest_connected_component",
]
