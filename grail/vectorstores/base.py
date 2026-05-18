"""
Vector store base classes.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The schema is intentionally small: a vector store holds documents with an id,
optional text, optional vector, and a free-form attributes dict. Similarity
search returns a list of (document, score) pairs where the score is in [0, 1].

To swap in a new backend (faiss, chroma, qdrant, ...), subclass and implement
``connect``, ``load_documents``, ``similarity_search_by_vector``,
``similarity_search_by_text``, and ``filter_by_id``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class VectorStoreDocument:
    """One indexed item."""

    id: str | int
    text: str | None
    vector: list[float] | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorStoreSearchResult:
    """One similarity-search hit."""

    document: VectorStoreDocument
    score: float


class BaseVectorStore(ABC):
    """Abstract vector store. Concrete backends subclass this."""

    def __init__(
        self,
        collection_name: str,
        db_connection: Any | None = None,
        document_collection: Any | None = None,
        query_filter: Any | None = None,
        **kwargs: Any,
    ) -> None:
        self.collection_name = collection_name
        self.db_connection = db_connection
        self.document_collection = document_collection
        self.query_filter = query_filter
        self.kwargs = kwargs

    @abstractmethod
    def connect(self, **kwargs: Any) -> None: ...

    @abstractmethod
    def load_documents(
        self, documents: list[VectorStoreDocument], overwrite: bool = True
    ) -> None: ...

    @abstractmethod
    def similarity_search_by_vector(
        self, query_embedding: list[float], k: int = 10, **kwargs: Any
    ) -> list[VectorStoreSearchResult]: ...

    @abstractmethod
    def similarity_search_by_text(
        self, text: str, text_embedder: Callable[[str], list[float] | None], k: int = 10, **kwargs: Any
    ) -> list[VectorStoreSearchResult]: ...

    @abstractmethod
    def filter_by_id(self, include_ids: list[str] | list[int]) -> Any: ...
