"""
Cascade search — entity-gated retrieval with text-based rescue.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Combines the graph-aware entity similarity approach (GRAIL's strength) with
direct text matching (RAG's strength) via a cascade strategy:

1. Find top-K entity candidates by embedding similarity.
2. Collect chunks from those entities (entity-gated pool).
3. Score every candidate chunk by BM25 + cosine similarity to the query.
4. Inject top text-matched chunks that the entity gate missed.
5. Return the merged, re-ranked pool for context building.

This mode solves the "entity gate excludes the answer chunk" failure pattern
without abandoning the graph structure that gives GRAIL its edge.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
import pandas as pd

from grail.llm import EmbeddingClient, LLMClient, RerankerClient
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

if TYPE_CHECKING:
    from grail.query.recall_filter import RecallFilter
from grail.utils.tokens import tiktoken_len
from grail.vectorstores import BaseVectorStore


# ---------------------------------------------------------------------------
# BM25 scorer (lightweight, no external deps)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-záéíóúüñçàèìòùâêîôûäëïöüß\w]+", text.lower())


class _BM25:
    def __init__(self, corpus: dict[str, str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids = list(corpus.keys())
        self.doc_tokens = {did: _tokenize(text) for did, text in corpus.items()}
        self.doc_lens = {did: len(toks) for did, toks in self.doc_tokens.items()}
        self.avgdl = sum(self.doc_lens.values()) / max(len(self.doc_lens), 1)
        self.N = len(self.doc_ids)
        self.df: dict[str, int] = defaultdict(int)
        for toks in self.doc_tokens.values():
            for t in set(toks):
                self.df[t] += 1

    def score_one(self, query: str, doc_id: str) -> float:
        q_tokens = _tokenize(query)
        tf_map = Counter(self.doc_tokens.get(doc_id, []))
        dl = self.doc_lens.get(doc_id, 1)
        s = 0.0
        for qt in q_tokens:
            if qt not in tf_map:
                continue
            tf = tf_map[qt]
            df = self.df.get(qt, 0)
            idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1)
            s += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def score_all(self, query: str) -> dict[str, float]:
        return {did: self.score_one(query, did) for did in self.doc_ids}


# ---------------------------------------------------------------------------
# CascadeSearch
# ---------------------------------------------------------------------------


@dataclass
class CascadeSearch:
    storage: StorageBackend
    llm: LLMClient
    embeddings: EmbeddingClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    artifacts: Optional[SearchArtifacts] = None
    vector_store: Optional[BaseVectorStore] = None
    output_folder: str = "output"
    max_tokens: int = 32_000
    top_k_entities: int = 15
    top_k_rescue: int = 5
    text_unit_prop: float = 0.5
    community_prop: float = 0.1
    use_community_summary: bool = False
    conversation_history_max_turns: int = 5
    response_max_tokens: int = 16_384
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
        context_only: bool = False,
        filter: Optional["RecallFilter"] = None,
    ) -> SearchResult:
        started = time.perf_counter()
        self.reporter.info("Loading indexed artifacts…")
        artifacts = self.artifacts or load_artifacts_for_search(self.storage, self.output_folder)
        if filter is not None and not filter.is_empty():
            artifacts = filter.apply_to_artifacts(artifacts)
            self.reporter.info(
                f"Recall filter applied → {len(artifacts.entities)} entities, "
                f"{len(artifacts.text_units)} text units."
            )
        if artifacts.entities.empty:
            return SearchResult(
                response="No indexed data was found. Run `grail index` first.",
                context_data={}, context_text="",
                completion_time=time.perf_counter() - started, llm_calls=0,
            )
        self.reporter.success(
            f"Loaded {len(artifacts.entities)} entities, "
            f"{len(artifacts.relationships)} relationships, "
            f"{len(artifacts.community_reports)} community reports"
        )

        enriched_query = self._enrich_query(query, conversation_history)

        # Step 1: Embed query
        self.reporter.info("Embedding query…")
        query_embedding = await self.embeddings.embed_one(enriched_query, tag="query_embedding")

        # Step 2: Entity similarity — get top-K entity candidates
        self.reporter.info(f"Finding top-{self.top_k_entities} entities…")
        ranked_entities = map_query_to_entities(
            query_embedding=query_embedding,
            entities_df=artifacts.entities,
            top_k=self.top_k_entities,
            vector_store=self.vector_store,
        )

        if include_entity_names:
            forced = artifacts.entities[artifacts.entities["name"].isin(
                [n.upper() for n in include_entity_names]
            )]
            ranked_entities = pd.concat([forced, ranked_entities]).drop_duplicates(subset=["id"])
        if exclude_entity_names:
            exclude_upper = {n.upper() for n in exclude_entity_names}
            ranked_entities = ranked_entities[~ranked_entities["name"].isin(exclude_upper)]

        selected_names = ranked_entities["name"].tolist() if not ranked_entities.empty else []

        # Step 3: Collect entity-gated chunks
        name_set = set(selected_names)

        def _mentions(row) -> bool:
            ids = row.get("entity_ids")
            if ids is None or (hasattr(ids, "__len__") and len(ids) == 0):
                return False
            return any(n in name_set for n in ids)

        entity_chunks = artifacts.text_units[artifacts.text_units.apply(_mentions, axis=1)].copy()
        entity_chunk_ids = set(entity_chunks["id"].tolist())

        # Step 4: BM25 score ALL chunks
        self.reporter.info("Scoring chunks with BM25 + cosine…")
        corpus = dict(zip(artifacts.text_units["id"], artifacts.text_units["text"].fillna("")))
        bm25 = _BM25(corpus)
        bm25_scores = bm25.score_all(query)

        # Step 5: Cosine score ALL chunks against the query
        chunk_texts = artifacts.text_units["text"].fillna("").tolist()
        chunk_ids = artifacts.text_units["id"].tolist()
        chunk_embeddings = await self.embeddings.embed_safe(chunk_texts, tag="cascade_chunk_embed")

        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        cosine_scores: dict[str, float] = {}
        for cid, emb in zip(chunk_ids, chunk_embeddings):
            if emb is None:
                cosine_scores[cid] = 0.0
                continue
            e = np.array(emb, dtype=np.float32)
            n = np.linalg.norm(e)
            cosine_scores[cid] = float(np.dot(q_vec, e / n)) if n > 0 else 0.0

        # Step 6: Re-rank entity-gated chunks by text relevance
        bm25_max = max(bm25_scores.values()) if bm25_scores else 1.0
        cos_max = max(cosine_scores.values()) if cosine_scores else 1.0

        def _text_score(cid: str) -> float:
            return (bm25_scores.get(cid, 0) / max(bm25_max, 1e-9)) + \
                   (cosine_scores.get(cid, 0) / max(cos_max, 1e-9))

        # Step 7: Find rescue chunks — top text-scored chunks NOT in entity pool
        all_text_scores = [(cid, _text_score(cid)) for cid in chunk_ids]
        all_text_scores.sort(key=lambda x: -x[1])

        rescue_chunks = []
        for cid, score in all_text_scores:
            if cid not in entity_chunk_ids:
                rescue_chunks.append(cid)
                if len(rescue_chunks) >= self.top_k_rescue:
                    break

        if rescue_chunks:
            self.reporter.info(f"Rescued {len(rescue_chunks)} chunks via text matching")

        # Step 8: Build final text unit set — entity-gated + rescue, ranked by text score
        all_candidate_ids = list(entity_chunk_ids) + rescue_chunks
        candidate_scores = [(cid, _text_score(cid)) for cid in all_candidate_ids]
        candidate_scores.sort(key=lambda x: -x[1])
        final_chunk_ids = [cid for cid, _ in candidate_scores]

        reranked_text_units = artifacts.text_units[
            artifacts.text_units["id"].isin(set(final_chunk_ids))
        ].copy()
        reranked_text_units["__cascade_score__"] = reranked_text_units["id"].map(dict(candidate_scores))
        reranked_text_units = reranked_text_units.sort_values("__cascade_score__", ascending=False)
        reranked_text_units = reranked_text_units.drop(columns=["__cascade_score__"])

        # Step 9: Build context (same as local search from here)
        local_prop = max(1.0 - self.community_prop - self.text_unit_prop, 0.0)
        entity_rel_tokens = int(self.max_tokens * local_prop)
        entity_budget = entity_rel_tokens // 2
        rel_budget = entity_rel_tokens - entity_budget
        community_budget = int(self.max_tokens * self.community_prop)
        text_unit_budget = int(self.max_tokens * self.text_unit_prop)

        self.reporter.info("Building context window…")
        entity_text, entity_rows = build_entity_context(ranked_entities, max_tokens=entity_budget)
        rel_text, rel_rows = build_relationship_context(
            artifacts.relationships, selected_names, max_tokens=rel_budget
        )

        relevant_reports = self._relevant_reports(
            selected_names, artifacts.nodes, artifacts.community_reports
        )
        comm_text, comm_rows = build_community_context(
            relevant_reports, max_tokens=community_budget,
            use_community_summary=self.use_community_summary,
        )
        if isinstance(comm_text, list):
            comm_text = "\n".join(comm_text)

        source_text, source_rows = build_text_unit_context(
            reranked_text_units, selected_names,
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
            f"{f' ({len(rescue_chunks)} rescued)' if rescue_chunks else ''}"
        )

        context_blocks = [b for b in (entity_text, rel_text, comm_text, source_text) if b]
        context_data_text = "\n\n".join(context_blocks)
        context_data = {
            "entities": entity_rows,
            "relationships": rel_rows,
            "reports": comm_rows,
            "sources": source_rows,
        }

        if context_only:
            self.reporter.success("Context-only mode — skipping LLM synthesis")
            return SearchResult(
                response="",
                context_data=context_data,
                context_text=context_data_text,
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )

        # Step 10: Generate response
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
            tag="cascade_search",
        )

        return SearchResult(
            response=response or "",
            context_data=context_data,
            context_text=context_data_text,
            completion_time=time.perf_counter() - started,
            llm_calls=1,
        )

    # ------------------------------------------------------------------ helpers

    def _enrich_query(
        self, query: str, history: Optional[list[dict[str, Any]]]
    ) -> str:
        if not history:
            return query
        recent = history[-self.conversation_history_max_turns:]
        parts = []
        for turn in recent:
            content = turn.get("content", "")
            if turn.get("role") == "user" and content:
                parts.append(content)
        if parts:
            return " ".join(parts[-2:]) + " " + query
        return query

    @staticmethod
    def _relevant_reports(
        entity_names: list[str],
        nodes: pd.DataFrame,
        community_reports: pd.DataFrame,
    ) -> pd.DataFrame:
        if nodes.empty or community_reports.empty:
            return community_reports
        if "community" not in nodes.columns:
            return community_reports
        name_set = set(entity_names)
        matched = nodes[nodes["title"].isin(name_set)]
        if matched.empty:
            return community_reports
        communities = set()
        for _, row in matched.iterrows():
            c = row.get("community")
            if c is not None and str(c) != "nan":
                communities.add(str(int(float(c))) if isinstance(c, float) else str(c))
        if not communities:
            return community_reports
        col = "community" if "community" in community_reports.columns else "id"
        filtered = community_reports[community_reports[col].astype(str).isin(communities)]
        return filtered if not filtered.empty else community_reports
