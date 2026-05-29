"""
Document-scoped search.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Restricts the search to a single source document. Given a document path or ID,
finds only the text units, entities, and relationships that belong to it, then
runs entity ranking + context building within that restricted scope.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from grail.llm import EmbeddingClient, LLMClient, RerankerClient
from grail.prompts import PromptRegistry
from grail.query.retrieval import (
    SearchArtifacts,
    build_entity_context,
    build_relationship_context,
    build_text_unit_context,
    load_artifacts_for_search,
    map_query_to_entities,
)
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import StorageBackend
from grail.vectorstores import BaseVectorStore


@dataclass
class DocumentSearch:
    """Search within a single source document."""

    storage: StorageBackend
    llm: LLMClient
    embeddings: EmbeddingClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    artifacts: Optional[SearchArtifacts] = None
    output_folder: str = "output"
    max_tokens: int = 8192
    top_k_entities: int = 10
    response_max_tokens: int = 16_384
    response_temperature: float = 0.0
    endpoint: Optional[str] = None
    model: Optional[str] = None
    assistant_name: str = "GRAIL"
    reporter: Reporter = field(default_factory=NullReporter)
    reranker: Optional[RerankerClient] = None
    reranker_overfetch_factor: int = 3
    rerank_entities: bool = False

    async def asearch(
        self,
        query: str,
        *,
        document: str,
        conversation_history: Optional[list[dict[str, Any]]] = None,
        artifact_instructions: str = "",
        use_reranker: Optional[bool] = None,
        context_only: bool = False,
    ) -> SearchResult:
        """Search within a single document.

        ``document`` can be a filename (e.g. ``"report.txt"``), a path fragment,
        or a document ID. The method tries to match it flexibly.
        """
        started = time.perf_counter()
        self.reporter.info("Loading indexed artifacts…")
        artifacts = self.artifacts or load_artifacts_for_search(self.storage, self.output_folder)
        if artifacts.entities.empty or artifacts.documents.empty:
            return SearchResult(
                response="No indexed data was found. Run `grail index` first.",
                context_data={},
                context_text="",
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )

        self.reporter.info(f"Resolving document '{document}'…")
        doc_ids = self._resolve_document(document, artifacts)
        if not doc_ids:
            return SearchResult(
                response=f"Document '{document}' not found in the index.",
                context_data={},
                context_text="",
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )

        self.reporter.info(f"Scoping to {len(doc_ids)} document(s)…")
        scoped_tu, scoped_entities, scoped_rels = self._scope_to_document(
            doc_ids, artifacts
        )

        if scoped_entities.empty:
            return SearchResult(
                response=f"No entities found in document '{document}'.",
                context_data={},
                context_text="",
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )
        self.reporter.success(
            f"Scoped: {len(scoped_entities)} entities, "
            f"{len(scoped_rels)} relationships, {len(scoped_tu)} text units"
        )

        do_rerank = (
            use_reranker is True
            or (use_reranker is None and self.rerank_entities)
        ) and self.reranker is not None

        self.reporter.info("Embedding query…")
        query_embedding = await self.embeddings.embed_one(query, tag="query_embedding")

        fetch_k = (
            self.top_k_entities * self.reranker_overfetch_factor
            if do_rerank
            else self.top_k_entities
        )
        self.reporter.info(f"Ranking top-{fetch_k} entities…")
        ranked = map_query_to_entities(
            query_embedding=query_embedding,
            entities_df=scoped_entities,
            top_k=fetch_k,
        )

        if do_rerank and not ranked.empty:
            assert self.reranker is not None
            descriptions = []
            for _, row in ranked.iterrows():
                desc = row.get("description") or row.get("name", "")
                name = row.get("name", "")
                etype = row.get("type", "")
                descriptions.append(f"{name} ({etype}): {desc}")
            self.reporter.info(
                f"Re-ranking {len(descriptions)} entities with cross-encoder…"
            )
            results = await self.reranker.rerank(
                query, descriptions, tag="rerank_entities"
            )
            score_map = {r.index: r.score for r in results}
            ranked = ranked.copy()
            ranked["__rerank_score__"] = [
                score_map.get(i, -float("inf")) for i in range(len(ranked))
            ]
            ranked = ranked.sort_values("__rerank_score__", ascending=False)
            ranked = ranked.head(self.top_k_entities)
            ranked = ranked.drop(columns=["__rerank_score__"])
            self.reporter.success(
                f"Re-ranked → top-{self.top_k_entities} entities selected"
            )

        entity_budget = self.max_tokens // 3
        rel_budget = self.max_tokens // 4
        source_budget = self.max_tokens - entity_budget - rel_budget

        self.reporter.info("Building context window…")
        entity_text, entity_rows = build_entity_context(ranked, max_tokens=entity_budget)
        selected_names = entity_rows["name"].tolist() if not entity_rows.empty else []
        rel_text, rel_rows = build_relationship_context(
            scoped_rels, selected_names, max_tokens=rel_budget
        )
        source_text, source_rows = build_text_unit_context(
            scoped_tu,
            selected_names,
            max_tokens=source_budget,
            documents=artifacts.documents,
            mapping=artifacts.mapping,
        )

        context_blocks = [b for b in (entity_text, rel_text, source_text) if b]
        context_data_text = "\n\n".join(context_blocks)
        context_data = {
            "entities": entity_rows,
            "relationships": rel_rows,
            "sources": source_rows,
        }

        if context_only:
            return SearchResult(
                response="",
                context_data=context_data,
                context_text=context_data_text,
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )

        self.reporter.info("Generating response…")
        messages = self.prompts.build(
            "local_search",
            context_data=context_data_text,
            user_query=query,
            assistant_name=self.assistant_name,
            artifact_instructions=artifact_instructions
            or f"Only answer based on information from document '{document}'.",
            conversation_history=conversation_history or [],
        )
        response = await self.llm.execute_safe(
            messages=messages,
            endpoint=self.endpoint,
            model=self.model,
            max_tokens=self.response_max_tokens,
            temperature=self.response_temperature,
            tag="document_search",
        )

        return SearchResult(
            response=response or "",
            context_data=context_data,
            context_text=context_data_text,
            completion_time=time.perf_counter() - started,
            llm_calls=1,
        )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _resolve_document(
        document: str, artifacts: SearchArtifacts
    ) -> list[str]:
        """Match ``document`` to doc IDs. Tries exact ID, then path contains, then title."""
        docs = artifacts.documents
        if docs.empty:
            return []
        if document in docs["id"].values:
            return [document]
        path_match = docs[docs["path"].str.contains(document, case=False, na=False)]
        if not path_match.empty:
            return path_match["id"].tolist()
        title_match = docs[docs["title"].str.contains(document, case=False, na=False)]
        if not title_match.empty:
            return title_match["id"].tolist()
        for doc_id, info in artifacts.mapping.items():
            if document.lower() in info.get("original_path", "").lower():
                return [doc_id]
        return []

    @staticmethod
    def _scope_to_document(
        doc_ids: list[str],
        artifacts: SearchArtifacts,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Filter text units, entities, and relationships to only those referencing ``doc_ids``."""
        doc_set = set(doc_ids)

        # Text units belonging to these documents.
        tu = artifacts.text_units
        if tu.empty:
            return tu, pd.DataFrame(), pd.DataFrame()
        if "document_ids" in tu.columns:
            mask = tu["document_ids"].apply(
                lambda x: bool(doc_set & set(list(x) if hasattr(x, 'tolist') else (x if isinstance(x, list) else [x])))
            )
        else:
            mask = tu["document_id"].isin(doc_set)
        scoped_tu = tu[mask].copy()
        scoped_tu_ids = set(scoped_tu["id"])

        # Entities whose text_unit_ids overlap with the scoped text units.
        ents = artifacts.entities
        if ents.empty or not scoped_tu_ids:
            return scoped_tu, pd.DataFrame(), pd.DataFrame()
        scoped_entities = ents[
            ents["text_unit_ids"].apply(
                lambda x: bool(scoped_tu_ids & set(list(x) if hasattr(x, 'tolist') else (x if isinstance(x, list) else [])))
            )
        ].copy()
        entity_names = set(scoped_entities["name"])

        # Relationships between scoped entities.
        rels = artifacts.relationships
        if rels.empty:
            scoped_rels = pd.DataFrame()
        else:
            scoped_rels = rels[
                rels["source"].isin(entity_names) & rels["target"].isin(entity_names)
            ].copy()

        return scoped_tu, scoped_entities, scoped_rels
