"""
GRAIL memory mode — agentic-memory SDK.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

``MemoryProject`` is the universal agent-facing write path. It produces the
same parquet artefacts as ``GRAIL`` (batch indexing) so every existing search
mode works on the same project — only the *write* path differs.
"""
from grail.memory.identity import (
    ProjectMeta,
    list_projects,
    new_ulid,
    read_meta,
    register_project,
    write_meta,
)
from grail.memory.observation import (
    compose_filename,
    compose_observation_markdown,
    now_iso,
    slugify_title,
)
from grail.memory.project import MemoryProject
from grail.memory.proposals import Proposal, ProposalSet
from grail.memory.types import (
    CommunityRecord,
    EntityRecord,
    Observation,
    RelationshipRecord,
    Reply,
    SimilarEntity,
)

__all__ = [
    "MemoryProject",
    "Observation",
    "EntityRecord",
    "RelationshipRecord",
    "CommunityRecord",
    "Proposal",
    "ProposalSet",
    "SimilarEntity",
    "Reply",
    "ProjectMeta",
    "new_ulid",
    "read_meta",
    "write_meta",
    "register_project",
    "list_projects",
    "compose_filename",
    "compose_observation_markdown",
    "slugify_title",
    "now_iso",
]
