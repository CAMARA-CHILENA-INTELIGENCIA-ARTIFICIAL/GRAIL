"""
FAISS-backed in-memory vector store.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Pure in-memory FAISS index (IndexFlatL2 by default). Suitable for projects
that want zero external services and can fit the entity embeddings in RAM.
Persistence is handled via faiss.write_index / faiss.read_index on the
project's root_dir.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

import faiss
import numpy as np

from grail.vectorstores.base import (
    BaseVectorStore,
    VectorStoreDocument,
    VectorStoreSearchResult,
)


class FAISSVectorStore(BaseVectorStore):
    """FAISS vector store using L2 (Euclidean) distance."""

    def __init__(self, collection_name: str, **kwargs: Any) -> None:
        super().__init__(collection_name, **kwargs)
        self.index: faiss.Index | None = None
        self._documents: list[VectorStoreDocument] = []
        self._id_to_pos: dict[str, int] = {}
        self._persist_dir: str | None = None

    def connect(self, **kwargs: Any) -> None:
        self._persist_dir = kwargs.get("db_uri", None)
        if self._persist_dir:
            index_path = os.path.join(self._persist_dir, f"{self.collection_name}.faiss")
            meta_path = os.path.join(self._persist_dir, f"{self.collection_name}.json")
            if os.path.exists(index_path) and os.path.exists(meta_path):
                self.index = faiss.read_index(index_path)
                with open(meta_path) as f:
                    docs_raw = json.load(f)
                self._documents = [
                    VectorStoreDocument(
                        id=d["id"],
                        text=d.get("text"),
                        vector=d.get("vector"),
                        attributes=d.get("attributes", {}),
                    )
                    for d in docs_raw
                ]
                self._id_to_pos = {str(doc.id): i for i, doc in enumerate(self._documents)}

    def load_documents(
        self, documents: list[VectorStoreDocument], overwrite: bool = True
    ) -> None:
        docs_with_vectors = [d for d in documents if d.vector is not None]
        if not docs_with_vectors:
            if overwrite:
                self.index = None
                self._documents = []
                self._id_to_pos = {}
            return

        dim = len(docs_with_vectors[0].vector)  # type: ignore[arg-type]

        if overwrite:
            self.index = faiss.IndexFlatL2(dim)
            self._documents = []
            self._id_to_pos = {}

        if self.index is None:
            self.index = faiss.IndexFlatL2(dim)

        vectors = np.array(
            [d.vector for d in docs_with_vectors], dtype=np.float32
        )
        start = len(self._documents)
        self.index.add(vectors)
        for i, doc in enumerate(docs_with_vectors):
            pos = start + i
            self._documents.append(doc)
            self._id_to_pos[str(doc.id)] = pos

        self._persist()

    def filter_by_id(self, include_ids: list[str] | list[int]) -> Any:
        if not include_ids:
            self.query_filter = None
            return self.query_filter
        self.query_filter = set(str(x) for x in include_ids)
        return self.query_filter

    def similarity_search_by_vector(
        self, query_embedding: list[float], k: int = 10, **kwargs: Any
    ) -> list[VectorStoreSearchResult]:
        if self.index is None or self.index.ntotal == 0:
            return []

        query = np.array([query_embedding], dtype=np.float32)
        search_k = min(k * 3, self.index.ntotal) if self.query_filter else min(k, self.index.ntotal)
        distances, indices = self.index.search(query, search_k)

        results: list[VectorStoreSearchResult] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            doc = self._documents[idx]
            if self.query_filter and str(doc.id) not in self.query_filter:
                continue
            score = 1.0 / (1.0 + float(dist))
            results.append(VectorStoreSearchResult(document=doc, score=score))
            if len(results) >= k:
                break

        return results

    def similarity_search_by_text(
        self,
        text: str,
        text_embedder: Callable[[str], list[float] | None],
        k: int = 10,
        **kwargs: Any,
    ) -> list[VectorStoreSearchResult]:
        query_embedding = text_embedder(text)
        if query_embedding:
            return self.similarity_search_by_vector(query_embedding, k)
        return []

    def _persist(self) -> None:
        if not self._persist_dir or self.index is None:
            return
        os.makedirs(self._persist_dir, exist_ok=True)
        index_path = os.path.join(self._persist_dir, f"{self.collection_name}.faiss")
        meta_path = os.path.join(self._persist_dir, f"{self.collection_name}.json")
        faiss.write_index(self.index, index_path)
        docs_raw = [
            {
                "id": str(d.id),
                "text": d.text,
                "vector": d.vector,
                "attributes": d.attributes,
            }
            for d in self._documents
        ]
        with open(meta_path, "w") as f:
            json.dump(docs_raw, f)
