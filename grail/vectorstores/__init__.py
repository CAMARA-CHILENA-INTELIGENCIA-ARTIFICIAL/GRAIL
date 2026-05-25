"""Vector store backends.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from grail.vectorstores.base import (
    BaseVectorStore,
    VectorStoreDocument,
    VectorStoreSearchResult,
)
from grail.vectorstores.lancedb import LanceDBVectorStore

__all__ = [
    "BaseVectorStore",
    "ChromaDBVectorStore",
    "FAISSVectorStore",
    "LanceDBVectorStore",
    "VectorStoreDocument",
    "VectorStoreSearchResult",
]


def __getattr__(name: str):
    if name == "FAISSVectorStore":
        from grail.vectorstores.faiss import FAISSVectorStore
        return FAISSVectorStore
    if name == "ChromaDBVectorStore":
        from grail.vectorstores.chroma import ChromaDBVectorStore
        return ChromaDBVectorStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
