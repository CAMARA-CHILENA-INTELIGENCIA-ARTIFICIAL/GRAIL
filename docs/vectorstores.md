# Vector stores

> **Scope.** Where entity description embeddings live for the local-search recall step. Configures: ``configs/vectorstore.yaml``. Code: ``grail/vectorstores/``.

## v0.1 — LanceDB only

GRAIL ships one backend (``lancedb``). The schema is portable across backends, so
swapping later is a matter of implementing the :class:`BaseVectorStore` interface.

PyArrow schema:

```
id (string) | text (string) | vector (list<float64>) | attributes (string, JSON)
```

* ``id`` — the entity id from ``final_entities.parquet``.
* ``text`` — the entity description.
* ``vector`` — the embedding produced by :class:`EmbeddingClient`.
* ``attributes`` — JSON dump of ``{name, type, human_readable_id}``.

LanceDB stores this as ``{root}/lancedb/<collection_name>.lance``. Default collection
name is ``entity_descriptions`` (configurable).

## Config

```yaml
vectorstore:
  backend: lancedb
  collection_name: entity_descriptions
  uri: null               # null → {root_dir}/lancedb
```

## Interface

```python
class BaseVectorStore:
    def connect(**kwargs)
    def load_documents(documents: list[VectorStoreDocument], overwrite: bool = True)
    def filter_by_id(include_ids: list[str | int]) -> filter
    def similarity_search_by_vector(query_embedding: list[float], k: int = 10) -> list[VectorStoreSearchResult]
    def similarity_search_by_text(text: str, text_embedder: Callable, k: int = 10)
```

Distance metric is Euclidean; scores returned by GRAIL are ``1 - abs(_distance)``
(higher = closer). When ``filter_by_id`` is called first, the next search applies
the filter via LanceDB's ``where(prefilter=True)``.

## Adding a new backend

1. Subclass :class:`BaseVectorStore`.
2. Implement the five abstract methods. Keep the same id/vector/attributes shape
   so the rest of the pipeline doesn't need changes.
3. Register in ``grail/vectorstores/__init__.py`` (or instantiate directly).

A typical FAISS or ChromaDB adapter is ~80 lines. Roadmap entries in CLAUDE.md
will land in Phase 7.

## Why store *entity description* embeddings, not text-unit embeddings?

Local search starts by mapping the query to the most relevant *entities*. We
already do all the heavy lifting (description summarization, deduping) on
entities during indexing, so a single embedding per entity is enough to anchor
the search. Text units come along for the ride once entities are picked, and
their relevance is determined by which entities they mention — no extra vector
math needed.

If you want text-unit-level retrieval too, embed the ``text`` column of
``final_text_units.parquet`` and stand up a second collection in the same vector
store. The current ``LocalSearch`` doesn't read it, but the abstraction supports
it.
