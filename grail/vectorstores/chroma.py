"""
ChromaDB-backed vector store.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Uses ChromaDB's persistent client for on-disk storage. Supports both L2 and
cosine distance (configurable at connect time). Good choice when you want a
lightweight server-optional store with built-in metadata filtering.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import chromadb
from chromadb.config import Settings

from grail.vectorstores.base import (
    BaseVectorStore,
    VectorStoreDocument,
    VectorStoreSearchResult,
)


class ChromaDBVectorStore(BaseVectorStore):
    """ChromaDB vector store."""

    def __init__(self, collection_name: str, **kwargs: Any) -> None:
        super().__init__(collection_name, **kwargs)
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    def connect(self, **kwargs: Any) -> None:
        db_uri = kwargs.get("db_uri", "./chromadb")
        distance_fn = kwargs.get("distance_fn", "l2")

        self._client = chromadb.PersistentClient(
            path=db_uri,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": distance_fn},
        )

    def load_documents(
        self, documents: list[VectorStoreDocument], overwrite: bool = True
    ) -> None:
        if self._client is None or self._collection is None:
            raise RuntimeError("Call connect() before load_documents()")

        docs_with_vectors = [d for d in documents if d.vector is not None]
        if not docs_with_vectors:
            return

        if overwrite:
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata=self._collection.metadata,
            )

        batch_size = 5000
        for i in range(0, len(docs_with_vectors), batch_size):
            batch = docs_with_vectors[i : i + batch_size]
            ids = [str(d.id) for d in batch]
            embeddings = [d.vector for d in batch]  # type: ignore[misc]
            documents_text = [d.text or "" for d in batch]
            metadatas = [
                {"attributes": json.dumps(d.attributes or {})} for d in batch
            ]
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,  # type: ignore[arg-type]
                documents=documents_text,
                metadatas=metadatas,  # type: ignore[arg-type]
            )

    def filter_by_id(self, include_ids: list[str] | list[int]) -> Any:
        if not include_ids:
            self.query_filter = None
            return self.query_filter
        self.query_filter = [str(x) for x in include_ids]
        return self.query_filter

    def similarity_search_by_vector(
        self, query_embedding: list[float], k: int = 10, **kwargs: Any
    ) -> list[VectorStoreSearchResult]:
        if self._collection is None:
            return []

        query_params: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["documents", "embeddings", "metadatas", "distances"],
        }
        if self.query_filter:
            query_params["where"] = {"$or": [{"id": fid} for fid in self.query_filter]} if len(self.query_filter) > 1 else None
            query_params["ids"] = self.query_filter

        # ChromaDB ids filter via the ids param directly
        if self.query_filter:
            query_params.pop("where", None)
            query_params["ids"] = self.query_filter

        results = self._collection.query(**query_params)

        if not results["ids"] or not results["ids"][0]:
            return []

        output: list[VectorStoreSearchResult] = []
        ids = results["ids"][0]
        distances = results["distances"][0] if results["distances"] else [0.0] * len(ids)
        documents_text = results["documents"][0] if results["documents"] else [""] * len(ids)
        embeddings = results["embeddings"][0] if results["embeddings"] else [None] * len(ids)
        metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)

        for doc_id, dist, text, emb, meta in zip(ids, distances, documents_text, embeddings, metadatas):
            attrs = json.loads(meta.get("attributes", "{}")) if meta else {}
            score = 1.0 / (1.0 + float(dist))
            output.append(
                VectorStoreSearchResult(
                    document=VectorStoreDocument(
                        id=doc_id,
                        text=text,
                        vector=emb,
                        attributes=attrs,
                    ),
                    score=score,
                )
            )

        return output

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
