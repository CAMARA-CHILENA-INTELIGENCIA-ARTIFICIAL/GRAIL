"""
Consolidate analyses — pluggable strategies that turn a graph snapshot into proposals.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Each analysis takes a :class:`GraphSnapshot` (a thin wrapper around the
parquet DataFrames) and returns a list of :class:`Proposal` objects. The
orchestrator in ``grail.memory.consolidate`` calls every enabled analysis in
turn, dedups by id, and writes the result to a yaml file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from grail.config import MemoryConfig
from grail.memory.proposals import Proposal


@dataclass
class GraphSnapshot:
    """Immutable view of the parquet artefacts at consolidate time."""

    entities: pd.DataFrame
    relationships: pd.DataFrame
    text_units: pd.DataFrame
    documents: pd.DataFrame
    communities: pd.DataFrame
    community_reports: pd.DataFrame


class AnalysisProtocol(Protocol):
    """An analysis takes a snapshot + config and returns proposals."""

    name: str

    def propose(self, snapshot: GraphSnapshot, config: MemoryConfig) -> list[Proposal]: ...


from grail.memory.analyses.alias_detect import AliasDetect  # noqa: E402
from grail.memory.analyses.edge_density import EdgeDensity  # noqa: E402
from grail.memory.analyses.folder_split import FolderSplit  # noqa: E402
from grail.memory.analyses.membership import Membership  # noqa: E402


def default_analyses(config: MemoryConfig) -> list[AnalysisProtocol]:
    """Return the list of enabled analyses per the user's config."""
    out: list[AnalysisProtocol] = []
    if config.enable_edge_density:
        out.append(EdgeDensity())
    if config.enable_alias_detect:
        out.append(AliasDetect())
    if config.enable_membership:
        out.append(Membership())
    if config.enable_folder_split:
        out.append(FolderSplit())
    return out


__all__ = [
    "AliasDetect",
    "AnalysisProtocol",
    "EdgeDensity",
    "FolderSplit",
    "GraphSnapshot",
    "Membership",
    "default_analyses",
]
