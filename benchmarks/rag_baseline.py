"""
Naive RAG baseline for GRAIL benchmarks.

Embeds raw text chunks (not entity descriptions) and retrieves by cosine
similarity.  Uses the same chunker, embedding model, and LLM as GRAIL so
the only variable is the graph layer.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from grail.llm import EmbeddingClient, LLMClient
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import StorageBackend

log = logging.getLogger("grail.benchmarks.rag_baseline")

RAG_SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions based ONLY on the provided
context excerpts.  If the context does not contain enough information to answer
the question, say so honestly.  Do not fabricate information.

Cite the source document and section when possible.
"""

RAG_USER_TEMPLATE = """\
## Context

{context}

---

## Question

{question}
"""


@dataclass
class RAGBaseline:
    """Naive chunk-retrieval RAG for benchmark comparison.

    Loads ``partial_text_units.parquet`` (raw chunks before entity extraction),
    embeds them, and at query time retrieves top-k by cosine similarity.
    """

    storage: StorageBackend
    llm: LLMClient
    embeddings: EmbeddingClient
    output_folder: str = "output"
    top_k: int = 10
    response_max_tokens: int = 16_384
    response_temperature: float = 0.0
    endpoint: Optional[str] = None
    model: Optional[str] = None
    reporter: Reporter = field(default_factory=NullReporter)

    # populated by prepare()
    _chunks: Optional[pd.DataFrame] = field(default=None, init=False, repr=False)
    _embeddings: Optional[np.ndarray] = field(default=None, init=False, repr=False)

    async def prepare(self) -> int:
        """Load chunks and compute embeddings. Returns number of chunks."""
        self._chunks = self._load_chunks()
        if self._chunks.empty:
            raise RuntimeError("No text chunks found. Run `grail index` first.")

        texts = self._chunks["text"].tolist()
        self.reporter.info(f"RAG baseline: embedding {len(texts)} chunks")

        raw = await self.embeddings.embed(texts, tag="rag_baseline_embed")
        self._embeddings = np.array(raw, dtype=np.float32)
        self.reporter.info("RAG baseline: embeddings ready")
        return len(texts)

    def _load_chunks(self) -> pd.DataFrame:
        key = f"{self.output_folder}/partial_text_units.parquet"
        if not self.storage.exists(key):
            return pd.DataFrame()
        with self.storage.open_for_read(key) as path:
            return pd.read_parquet(path)

    async def query(self, question: str) -> SearchResult:
        """Embed query, retrieve top-k chunks, call LLM."""
        if self._chunks is None or self._embeddings is None:
            await self.prepare()

        t0 = time.perf_counter()

        q_emb = await self.embeddings.embed_one(question, tag="rag_baseline_query")
        q_vec = np.array(q_emb, dtype=np.float32)

        scores = self._cosine_scores(q_vec, self._embeddings)
        top_indices = np.argsort(scores)[::-1][: self.top_k]

        context_parts = []
        for idx in top_indices:
            row = self._chunks.iloc[idx]
            doc_ids = row.get("document_ids", row.get("document_id", "unknown"))
            context_parts.append(
                f"[Source: {doc_ids} | Score: {scores[idx]:.3f}]\n{row['text']}"
            )
        context_text = "\n\n---\n\n".join(context_parts)

        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": RAG_USER_TEMPLATE.format(
                    context=context_text, question=question
                ),
            },
        ]

        response = await self.llm.execute(
            messages,
            endpoint=self.endpoint,
            model=self.model,
            max_tokens=self.response_max_tokens,
            temperature=self.response_temperature,
            tag="rag_baseline_answer",
        )

        elapsed = time.perf_counter() - t0
        return SearchResult(
            response=response,
            context_data=context_text,
            context_text=context_text,
            completion_time=elapsed,
            llm_calls=1,
        )

    @staticmethod
    def _cosine_scores(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1)
        q_norm = np.linalg.norm(query)
        denom = norms * q_norm
        denom[denom == 0] = 1e-10
        return matrix @ query / denom
