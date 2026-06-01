"""
Memory mode data types.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The ``Reply`` envelope is the unified return shape for every ``MemoryProject``
method. It mirrors the JSON envelope the skill scripts emit so the SDK and
skill share one contract — the agent always reads the same keys whether it's
calling Python directly or invoking a script.

Typed records (``Observation``, ``EntityRecord``, ...) are conveniences for
callers that want structured access without dipping into the parquet rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Reply:
    """Unified return envelope for every ``MemoryProject`` method.

    ``ok`` is the only field guaranteed to be present. The rest are optional
    so callers can pattern-match cheaply (``if reply.ok: ...``) and inspect
    the structured payload when they care.
    """

    ok: bool
    data: Any = None
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok}
        if self.data is not None:
            out["data"] = self.data
        if self.warnings:
            out["warnings"] = list(self.warnings)
        if self.next_steps:
            out["next_steps"] = list(self.next_steps)
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class Observation:
    """One memory observation — corresponds to a markdown file on disk."""

    id: str  # document_id assigned by FileLoader
    title: str
    slug: str  # filename stem under memories/<category>/
    category: Optional[str]
    tags: list[str]
    content: str
    observed_at: Optional[str]
    confidence: float
    source: Optional[str]
    file_path: str  # absolute path to the markdown file on disk


@dataclass
class EntityRecord:
    """A row from ``final_entities.parquet`` exposed as a typed object."""

    id: str
    name: str
    type: str
    description: str
    community_ids: list[str] = field(default_factory=list)
    text_unit_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    observed_at: Optional[str] = None
    confidence: float = 1.0
    source: Optional[str] = None
    degree: int = 0


@dataclass
class RelationshipRecord:
    id: str
    source: str
    target: str
    relationship_type: str
    description: str
    weight: float = 1.0
    text_unit_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    observed_at: Optional[str] = None
    confidence: float = 1.0
    source_attribution: Optional[str] = None


@dataclass
class CommunityRecord:
    """A row from ``final_communities.parquet`` (declared or discovered)."""

    id: str
    community: str
    title: str
    level: int
    size: int
    kind: str  # "folder" | "discovered" | "leiden"
    entity_ids: list[str] = field(default_factory=list)


@dataclass
class SimilarEntity:
    """One hit from ``find_similar_entity``."""

    name: str
    similarity: float
    method: str  # "embedding" | "edit_distance" | "exact"
    description: Optional[str] = None
    type: Optional[str] = None


__all__ = [
    "Reply",
    "Observation",
    "EntityRecord",
    "RelationshipRecord",
    "CommunityRecord",
    "SimilarEntity",
]
