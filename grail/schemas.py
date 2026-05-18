"""
Core dataclasses for the GRAIL knowledge graph and search layer.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

These types are the lingua franca between indexing, vectorstores, and query. Every
parquet row, every LLM extraction, every retrieval result flows through one of these
shapes. The ``from_dict`` constructors map parquet column names → object fields,
so renaming a column means updating the corresponding key argument here only.
"""
from __future__ import annotations

import tiktoken
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


@dataclass
class Identified:
    """An item with an id and an optional human-readable short id."""

    id: str
    short_id: str | None


@dataclass
class Named(Identified):
    """An :class:`Identified` item with a title (entity name, community name, etc.)."""

    title: str


@dataclass
class SearchResult:
    """A structured search result returned by ``LocalSearch`` / ``GlobalSearch``."""

    response: str | dict[str, Any] | list[dict[str, Any]]
    context_data: str | list[pd.DataFrame] | dict[str, pd.DataFrame]
    context_text: str | list[str] | dict[str, str]
    completion_time: float
    llm_calls: int


class GlobalContextBuilder(ABC):
    """Base class for global-search context builders."""

    @abstractmethod
    def build_context(
        self, conversation_history: list | None = None, **kwargs
    ) -> tuple[str | list[str], dict[str, pd.DataFrame]]:
        """Build the context for the global search mode."""


class LocalContextBuilder(ABC):
    """Base class for local-search context builders."""

    @abstractmethod
    def build_context(
        self,
        query: str,
        conversation_history: list | None = None,
        **kwargs,
    ) -> tuple[str | list[str], dict[str, pd.DataFrame]]:
        """Build the context for the local search mode."""


class BaseSearch(ABC):
    """Base class shared by ``LocalSearch`` and ``GlobalSearch``."""

    def __init__(
        self,
        context_builder: GlobalContextBuilder | LocalContextBuilder,
        token_encoder: tiktoken.Encoding | None = None,
        llm_params: dict[str, Any] | None = None,
        context_builder_params: dict[str, Any] | None = None,
        llm: Optional[Any] = None,
    ) -> None:
        self.llm = llm
        self.context_builder = context_builder
        self.token_encoder = token_encoder
        self.llm_params = llm_params or {}
        self.context_builder_params = context_builder_params or {}

    @abstractmethod
    async def asearch(
        self,
        query: str,
        conversation_history: list | None = None,
        **kwargs,
    ) -> SearchResult:
        """Asynchronously answer ``query``."""


@dataclass
class Entity(Named):
    """A node in the knowledge graph."""

    type: str | None = None
    description: str | None = None
    description_embedding: list[float] | None = None
    name_embedding: list[float] | None = None
    graph_embedding: list[float] | None = None
    community_ids: list[str] | None = None
    text_unit_ids: list[str] | None = None
    document_ids: list[str] | None = None
    rank: int | None = 1
    attributes: dict[str, Any] | None = None

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        id_key: str = "id",
        short_id_key: str = "short_id",
        title_key: str = "title",
        type_key: str = "type",
        description_key: str = "description",
        description_embedding_key: str = "description_embedding",
        name_embedding_key: str = "name_embedding",
        graph_embedding_key: str = "graph_embedding",
        community_key: str = "community",
        text_unit_ids_key: str = "text_unit_ids",
        document_ids_key: str = "document_ids",
        rank_key: str = "degree",
        attributes_key: str = "attributes",
    ) -> "Entity":
        return Entity(
            id=d[id_key],
            title=d[title_key],
            short_id=d.get(short_id_key),
            type=d.get(type_key),
            description=d.get(description_key),
            name_embedding=d.get(name_embedding_key),
            description_embedding=d.get(description_embedding_key),
            graph_embedding=d.get(graph_embedding_key),
            community_ids=d.get(community_key),
            rank=d.get(rank_key, 1),
            text_unit_ids=d.get(text_unit_ids_key),
            document_ids=d.get(document_ids_key),
            attributes=d.get(attributes_key),
        )


@dataclass
class Relationship(Identified):
    """An edge between two entities."""

    source: str
    target: str
    weight: float | None = 1.0
    description: str | None = None
    description_embedding: list[float] | None = None
    text_unit_ids: list[str] | None = None
    document_ids: list[str] | None = None
    attributes: dict[str, Any] | None = None

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        id_key: str = "id",
        short_id_key: str = "short_id",
        source_key: str = "source",
        target_key: str = "target",
        description_key: str = "description",
        weight_key: str = "weight",
        text_unit_ids_key: str = "text_unit_ids",
        document_ids_key: str = "document_ids",
        attributes_key: str = "attributes",
    ) -> "Relationship":
        return Relationship(
            id=d[id_key],
            short_id=d.get(short_id_key),
            source=d[source_key],
            target=d[target_key],
            description=d.get(description_key),
            weight=d.get(weight_key, 1.0),
            text_unit_ids=d.get(text_unit_ids_key),
            document_ids=d.get(document_ids_key),
            attributes=d.get(attributes_key),
        )


@dataclass
class Covariate(Identified):
    """Metadata attached to a subject entity (e.g. a claim)."""

    subject_id: str
    subject_type: str = "entity"
    covariate_type: str = "claim"
    text_unit_ids: list[str] | None = None
    document_ids: list[str] | None = None
    attributes: dict[str, Any] | None = None

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        id_key: str = "id",
        subject_id_key: str = "subject_id",
        subject_type_key: str = "subject_type",
        covariate_type_key: str = "covariate_type",
        short_id_key: str = "short_id",
        text_unit_ids_key: str = "text_unit_ids",
        document_ids_key: str = "document_ids",
        attributes_key: str = "attributes",
    ) -> "Covariate":
        return Covariate(
            id=d[id_key],
            short_id=d.get(short_id_key),
            subject_id=d[subject_id_key],
            subject_type=d.get(subject_type_key, "entity"),
            covariate_type=d.get(covariate_type_key, "claim"),
            text_unit_ids=d.get(text_unit_ids_key),
            document_ids=d.get(document_ids_key),
            attributes=d.get(attributes_key),
        )


@dataclass
class TextUnit(Identified):
    """A chunk of source text. May span multiple documents (mixed-document chunks)."""

    text: str
    text_embedding: list[float] | None = None
    entity_ids: list[str] | None = None
    relationship_ids: list[str] | None = None
    covariate_ids: dict[str, list[str]] | None = None
    n_tokens: int | None = None
    document_ids: list[str] | None = None
    attributes: dict[str, Any] | None = None

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        id_key: str = "id",
        short_id_key: str = "short_id",
        text_key: str = "text",
        text_embedding_key: str = "text_embedding",
        entities_key: str = "entity_ids",
        relationships_key: str = "relationship_ids",
        covariates_key: str = "covariate_ids",
        n_tokens_key: str = "n_tokens",
        document_ids_key: str = "document_ids",
        attributes_key: str = "attributes",
    ) -> "TextUnit":
        return TextUnit(
            id=d[id_key],
            short_id=d.get(short_id_key),
            text=d[text_key],
            text_embedding=d.get(text_embedding_key),
            entity_ids=d.get(entities_key),
            relationship_ids=d.get(relationships_key),
            covariate_ids=d.get(covariates_key),
            n_tokens=d.get(n_tokens_key),
            document_ids=d.get(document_ids_key),
            attributes=d.get(attributes_key),
        )


@dataclass
class CommunityReport(Named):
    """LLM-generated narrative summary of a community."""

    community_id: str
    summary: str = ""
    full_content: str = ""
    rank: float | None = 1.0
    summary_embedding: list[float] | None = None
    full_content_embedding: list[float] | None = None
    attributes: dict[str, Any] | None = None

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        id_key: str = "id",
        title_key: str = "title",
        community_id_key: str = "community_id",
        short_id_key: str = "short_id",
        summary_key: str = "summary",
        full_content_key: str = "full_content",
        rank_key: str = "rank",
        summary_embedding_key: str = "summary_embedding",
        full_content_embedding_key: str = "full_content_embedding",
        attributes_key: str = "attributes",
    ) -> "CommunityReport":
        return CommunityReport(
            id=d[id_key],
            title=d[title_key],
            community_id=d[community_id_key],
            short_id=d.get(short_id_key),
            summary=d[summary_key],
            full_content=d[full_content_key],
            rank=d[rank_key],
            summary_embedding=d.get(summary_embedding_key),
            full_content_embedding=d.get(full_content_embedding_key),
            attributes=d.get(attributes_key),
        )


@dataclass
class Community(Named):
    """A community of related entities at a given hierarchical level."""

    level: str = ""
    entity_ids: list[str] | None = None
    relationship_ids: list[str] | None = None
    covariate_ids: dict[str, list[str]] | None = None
    attributes: dict[str, Any] | None = None

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        id_key: str = "id",
        title_key: str = "title",
        short_id_key: str = "short_id",
        level_key: str = "level",
        entities_key: str = "entity_ids",
        relationships_key: str = "relationship_ids",
        covariates_key: str = "covariate_ids",
        attributes_key: str = "attributes",
    ) -> "Community":
        return Community(
            id=d[id_key],
            title=d[title_key],
            short_id=d.get(short_id_key),
            level=d[level_key],
            entity_ids=d.get(entities_key),
            relationship_ids=d.get(relationships_key),
            covariate_ids=d.get(covariates_key),
            attributes=d.get(attributes_key),
        )


@dataclass
class Document(Named):
    """A source document. ``text_unit_ids`` are the chunks generated from this file."""

    type: str = "text"
    text_unit_ids: list[str] = field(default_factory=list)
    raw_content: str = ""
    summary: str | None = None
    summary_embedding: list[float] | None = None
    raw_content_embedding: list[float] | None = None
    attributes: dict[str, Any] | None = None

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        id_key: str = "id",
        short_id_key: str = "short_id",
        title_key: str = "title",
        type_key: str = "type",
        raw_content_key: str = "raw_content",
        summary_key: str = "summary",
        summary_embedding_key: str = "summary_embedding",
        raw_content_embedding_key: str = "raw_content_embedding",
        text_units_key: str = "text_units",
        attributes_key: str = "attributes",
    ) -> "Document":
        return Document(
            id=d[id_key],
            short_id=d.get(short_id_key),
            title=d[title_key],
            type=d.get(type_key, "text"),
            raw_content=d[raw_content_key],
            summary=d.get(summary_key),
            summary_embedding=d.get(summary_embedding_key),
            raw_content_embedding=d.get(raw_content_embedding_key),
            text_unit_ids=d.get(text_units_key, []),
            attributes=d.get(attributes_key),
        )


DEFAULT_VECTOR_SIZE: int = 1536
