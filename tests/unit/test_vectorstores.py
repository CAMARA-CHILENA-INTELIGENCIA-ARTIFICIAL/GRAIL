"""
Tests for FAISS and ChromaDB vector store backends.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from grail.vectorstores.base import VectorStoreDocument, VectorStoreSearchResult


def _make_docs(n: int = 5, dim: int = 8) -> list[VectorStoreDocument]:
    import numpy as np

    rng = np.random.default_rng(42)
    return [
        VectorStoreDocument(
            id=f"doc-{i}",
            text=f"Document number {i}",
            vector=rng.random(dim).tolist(),
            attributes={"index": i},
        )
        for i in range(n)
    ]


# ─── FAISS ────────────────────────────────────────────────────────────────────

faiss = pytest.importorskip("faiss")


class TestFAISSVectorStore:
    def _make_store(self, tmp_path: Path):
        from grail.vectorstores.faiss import FAISSVectorStore

        store = FAISSVectorStore(collection_name="test_collection")
        store.connect(db_uri=str(tmp_path))
        return store

    def test_load_and_search(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        results = store.similarity_search_by_vector(docs[0].vector, k=3)
        assert len(results) == 3
        assert results[0].document.id == "doc-0"
        assert results[0].score > 0

    def test_filter_by_id(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        store.filter_by_id(["doc-2", "doc-4"])
        results = store.similarity_search_by_vector(docs[0].vector, k=5)
        assert all(r.document.id in ("doc-2", "doc-4") for r in results)

    def test_clear_filter(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        store.filter_by_id(["doc-0"])
        store.filter_by_id([])
        results = store.similarity_search_by_vector(docs[0].vector, k=5)
        assert len(results) == 5

    def test_persistence(self, tmp_path: Path):
        from grail.vectorstores.faiss import FAISSVectorStore

        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        store2 = FAISSVectorStore(collection_name="test_collection")
        store2.connect(db_uri=str(tmp_path))
        results = store2.similarity_search_by_vector(docs[1].vector, k=2)
        assert len(results) == 2
        assert results[0].document.id == "doc-1"

    def test_append_documents(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs(3)
        store.load_documents(docs, overwrite=True)

        extra = _make_docs(2)
        for i, d in enumerate(extra):
            d.id = f"doc-extra-{i}"
        store.load_documents(extra, overwrite=False)

        results = store.similarity_search_by_vector(docs[0].vector, k=10)
        assert len(results) == 5

    def test_empty_store(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        results = store.similarity_search_by_vector([0.0] * 8, k=3)
        assert results == []

    def test_similarity_search_by_text(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        def embedder(text: str) -> list[float] | None:
            return docs[2].vector

        results = store.similarity_search_by_text("query", embedder, k=2)
        assert len(results) == 2
        assert results[0].document.id == "doc-2"


# ─── ChromaDB ─────────────────────────────────────────────────────────────────

chromadb = pytest.importorskip("chromadb")


class TestChromaDBVectorStore:
    def _make_store(self, tmp_path: Path):
        from grail.vectorstores.chroma import ChromaDBVectorStore

        store = ChromaDBVectorStore(collection_name="test_collection")
        store.connect(db_uri=str(tmp_path / "chroma"))
        return store

    def test_load_and_search(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        results = store.similarity_search_by_vector(docs[0].vector, k=3)
        assert len(results) == 3
        assert results[0].document.id == "doc-0"
        assert results[0].score > 0

    def test_filter_by_id(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        store.filter_by_id(["doc-2", "doc-4"])
        results = store.similarity_search_by_vector(docs[0].vector, k=5)
        returned_ids = {r.document.id for r in results}
        assert returned_ids <= {"doc-2", "doc-4"}

    def test_overwrite(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs(5)
        store.load_documents(docs, overwrite=True)

        new_docs = _make_docs(2)
        store.load_documents(new_docs, overwrite=True)

        store.filter_by_id([])
        results = store.similarity_search_by_vector(new_docs[0].vector, k=10)
        assert len(results) == 2

    def test_similarity_search_by_text(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        def embedder(text: str) -> list[float] | None:
            return docs[3].vector

        results = store.similarity_search_by_text("query", embedder, k=2)
        assert len(results) == 2
        assert results[0].document.id == "doc-3"

    def test_empty_embedder_returns_empty(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        docs = _make_docs()
        store.load_documents(docs, overwrite=True)

        results = store.similarity_search_by_text("x", lambda t: None, k=2)
        assert results == []
