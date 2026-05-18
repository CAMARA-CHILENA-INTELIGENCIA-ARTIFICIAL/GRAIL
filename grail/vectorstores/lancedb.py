"""
LanceDB-backed vector store.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Same on-disk layout and semantics as the legacy implementation: a single
PyArrow-typed table with columns ``id|text|vector|attributes(json-string)``,
Euclidean distance, and prefilter-aware ID filtering. Drop-in compatible with
data produced by the legacy code.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import lancedb
import pyarrow as pa

from grail.vectorstores.base import (
    BaseVectorStore,
    VectorStoreDocument,
    VectorStoreSearchResult,
)


_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("text", pa.string()),
    pa.field("vector", pa.list_(pa.float64())),
    pa.field("attributes", pa.string()),
])


class LanceDBVectorStore(BaseVectorStore):
    """LanceDB vector store."""

    def connect(self, **kwargs: Any) -> Any:
        db_uri = kwargs.get("db_uri", "./lancedb")
        self.db_connection = lancedb.connect(db_uri)
        return self.db_connection

    def load_documents(
        self, documents: list[VectorStoreDocument], overwrite: bool = True
    ) -> None:
        data = [
            {
                "id": str(doc.id),
                "text": doc.text or "",
                "vector": doc.vector,
                "attributes": json.dumps(doc.attributes or {}),
            }
            for doc in documents
            if doc.vector is not None
        ] or None

        if overwrite:
            if data:
                self.document_collection = self.db_connection.create_table(
                    self.collection_name, data=data, mode="overwrite"
                )
            else:
                self.document_collection = self.db_connection.create_table(
                    self.collection_name, schema=_SCHEMA, mode="overwrite"
                )
        else:
            self.document_collection = self.db_connection.open_table(self.collection_name)
            if data:
                self.document_collection.add(data)

    def filter_by_id(self, include_ids: list[str] | list[int]) -> Any:
        if not include_ids:
            self.query_filter = None
            return self.query_filter
        if isinstance(include_ids[0], str):
            id_filter = ", ".join(f"'{x}'" for x in include_ids)
        else:
            id_filter = ", ".join(str(x) for x in include_ids)
        self.query_filter = f"id in ({id_filter})"
        return self.query_filter

    def similarity_search_by_vector(
        self, query_embedding: list[float], k: int = 10, **kwargs: Any
    ) -> list[VectorStoreSearchResult]:
        query = self.document_collection.search(query=query_embedding)
        if self.query_filter:
            query = query.where(self.query_filter, prefilter=True)
        docs = query.limit(k).to_list()
        return [
            VectorStoreSearchResult(
                document=VectorStoreDocument(
                    id=doc["id"],
                    text=doc["text"],
                    vector=doc["vector"],
                    attributes=json.loads(doc["attributes"]),
                ),
                score=1 - abs(float(doc["_distance"])),
            )
            for doc in docs
        ]

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
