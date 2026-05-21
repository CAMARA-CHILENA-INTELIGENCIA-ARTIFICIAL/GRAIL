"""
Local search.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

1. Embed the query (enriched with conversation history for context continuity).
2. Pick the top-k entities by description similarity.
3. Collect related relationships and the text units that mention any selected entity.
4. Pull in community reports the entities belong to.
5. Pack everything into a single context block with proportional token budgeting.
6. Send to the LLM with the local-search prompt.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from grail.llm import EmbeddingClient, LLMClient
from grail.prompts import PromptRegistry
from grail.query.retrieval import (
    SearchArtifacts,
    build_community_context,
    build_entity_context,
    build_relationship_context,
    build_text_unit_context,
    load_artifacts_for_search,
    map_query_to_entities,
)
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import StorageBackend
from grail.vectorstores import LanceDBVectorStore


@dataclass
class LocalSearch:
    storage: StorageBackend
    llm: LLMClient
    embeddings: EmbeddingClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    artifacts: Optional[SearchArtifacts] = None
    vector_store: Optional[LanceDBVectorStore] = None
    output_folder: str = "output"
    max_tokens: int = 8192
    top_k_entities: int = 10
    top_k_relationships: int = 10
    text_unit_prop: float = 0.5
    community_prop: float = 0.1
    conversation_history_max_turns: int = 5
    response_max_tokens: int = 2048
    response_temperature: float = 0.0
    endpoint: Optional[str] = None
    model: Optional[str] = None
    assistant_name: str = "GRAIL"
    reporter: Reporter = field(default_factory=NullReporter)

    async def asearch(
        self,
        query: str,
        *,
        conversation_history: Optional[list[dict[str, Any]]] = None,
        artifact_instructions: str = "",
        include_entity_names: Optional[list[str]] = None,
        exclude_entity_names: Optional[list[str]] = None,
    ) -> SearchResult:
        started = time.perf_counter()
        self.reporter.info("Loading indexed artifacts…")
        artifacts = self.artifacts or load_artifacts_for_search(self.storage, self.output_folder)
        if artifacts.entities.empty:
            return SearchResult(
                response="No indexed data was found. Run `grail index` first.",
                context_data={},
                context_text="",
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )
        self.reporter.success(
            f"Loaded {len(artifacts.entities)} entities, "
            f"{len(artifacts.relationships)} relationships, "
            f"{len(artifacts.community_reports)} community reports"
        )

        enriched_query = self._enrich_query_with_history(query, conversation_history)

        self.reporter.info("Embedding query…")
        query_embedding = await self.embeddings.embed_one(enriched_query, tag="query_embedding")

        self.reporter.info(f"Ranking top-{self.top_k_entities} entities by similarity…")
        ranked = map_query_to_entities(
            query_embedding=query_embedding,
            entities_df=artifacts.entities,
            top_k=self.top_k_entities,
            vector_store=self.vector_store,
        )

        if include_entity_names:
            forced = artifacts.entities[artifacts.entities["name"].isin(
                [n.upper() for n in include_entity_names]
            )]
            ranked = pd.concat([forced, ranked]).drop_duplicates(subset=["id"])
        if exclude_entity_names:
            exclude_upper = {n.upper() for n in exclude_entity_names}
            ranked = ranked[~ranked["name"].isin(exclude_upper)]

        local_prop = max(1.0 - self.community_prop - self.text_unit_prop, 0.0)
        entity_rel_tokens = int(self.max_tokens * local_prop)
        entity_budget = entity_rel_tokens // 2
        rel_budget = entity_rel_tokens - entity_budget
        community_budget = int(self.max_tokens * self.community_prop)
        text_unit_budget = int(self.max_tokens * self.text_unit_prop)

        self.reporter.info("Building context window…")
        entity_text, entity_rows = build_entity_context(ranked, max_tokens=entity_budget)
        selected_names = entity_rows["name"].tolist() if not entity_rows.empty else []
        rel_text, rel_rows = build_relationship_context(
            artifacts.relationships, selected_names, max_tokens=rel_budget
        )

        relevant_reports = self._relevant_reports(
            selected_names, artifacts.nodes, artifacts.community_reports
        )
        comm_text, comm_rows = build_community_context(
            relevant_reports, max_tokens=community_budget
        )
        if isinstance(comm_text, list):
            comm_text = "\n".join(comm_text)

        source_text, source_rows = build_text_unit_context(
            artifacts.text_units,
            selected_names,
            max_tokens=text_unit_budget,
            documents=artifacts.documents,
            mapping=artifacts.mapping,
        )

        n_ents = len(entity_rows) if not entity_rows.empty else 0
        n_rels = len(rel_rows) if not rel_rows.empty else 0
        n_comm = len(comm_rows) if not comm_rows.empty else 0
        n_src = len(source_rows) if not source_rows.empty else 0
        self.reporter.success(
            f"Context: {n_ents} entities, {n_rels} relationships, "
            f"{n_comm} communities, {n_src} source chunks"
        )

        context_blocks = [block for block in (entity_text, rel_text, comm_text, source_text) if block]
        context_data_text = "\n\n".join(context_blocks)
        context_data = {
            "entities": entity_rows,
            "relationships": rel_rows,
            "reports": comm_rows,
            "sources": source_rows,
        }

        self.reporter.info("Generating response…")
        messages = self.prompts.build(
            "local_search",
            context_data=context_data_text,
            user_query=query,
            assistant_name=self.assistant_name,
            artifact_instructions=artifact_instructions,
            conversation_history=conversation_history or [],
        )
        response = await self.llm.execute_safe(
            messages=messages,
            endpoint=self.endpoint,
            model=self.model,
            max_tokens=self.response_max_tokens,
            temperature=self.response_temperature,
            tag="local_search",
        )

        return SearchResult(
            response=response or "",
            context_data=context_data,
            context_text=context_data_text,
            completion_time=time.perf_counter() - started,
            llm_calls=1,
        )

    # ------------------------------------------------------------------ helpers

    def _enrich_query_with_history(
        self,
        query: str,
        conversation_history: Optional[list[dict[str, Any]]],
    ) -> str:
        """Prepend recent user turns to the query for richer entity matching."""
        if not conversation_history:
            return query
        user_turns: list[str] = []
        for msg in conversation_history:
            if msg.get("role") == "user":
                user_turns.append(msg["content"])
        recent = user_turns[-(self.conversation_history_max_turns):]
        if not recent:
            return query
        return query + "\n" + "\n".join(recent)

    def _relevant_reports(
        self,
        entity_names: list[str],
        nodes_df: pd.DataFrame,
        reports_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if reports_df.empty or nodes_df.empty or not entity_names:
            return reports_df.head(0)
        node_subset = nodes_df[nodes_df["title"].isin(entity_names)]
        community_ids = node_subset["community"].astype(str).unique().tolist()
        return reports_df[reports_df["community"].astype(str).isin(community_ids)]
