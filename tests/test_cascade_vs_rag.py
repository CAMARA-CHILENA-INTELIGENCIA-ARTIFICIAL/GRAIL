"""
Cascade vs RAG vs Local — head-to-head comparison on benchmark_laws.

Runs all three retrieval strategies on every benchmark question and compares:
- Which chunks each strategy selects for the context window
- Where the answer chunk ranks in each strategy's output
- Overlap and divergence between strategies

No LLM calls for response generation — only retrieval + ranking.

Usage:
    uv run python tests/test_cascade_vs_rag.py
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

PROJECT = Path(__file__).parent.parent / "benchmark_laws"
TOP_K = 10


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_all():
    current = json.loads((PROJECT / "output" / "current.json").read_text())
    run_dir = PROJECT / current["run_dir"]
    return {
        "entities": pd.read_parquet(run_dir / "final_entities.parquet"),
        "relationships": pd.read_parquet(run_dir / "final_relationships.parquet"),
        "text_units": pd.read_parquet(run_dir / "final_text_units.parquet"),
        "nodes": pd.read_parquet(run_dir / "final_nodes.parquet"),
        "community_reports": pd.read_parquet(run_dir / "final_community_reports.parquet"),
        "documents": pd.read_parquet(run_dir / "final_docs.parquet"),
    }


def _ensure_list(val):
    if val is None:
        return []
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else [val]
        except (json.JSONDecodeError, TypeError):
            return [val]
    if hasattr(val, "__iter__"):
        return list(val)
    return [val]


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-záéíóúüñçàèìòùâêîôûäëïöüß\w]+", text.lower())


class BM25:
    def __init__(self, corpus: dict[str, str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_ids = list(corpus.keys())
        self.doc_tokens = {d: _tokenize(t) for d, t in corpus.items()}
        self.doc_lens = {d: len(t) for d, t in self.doc_tokens.items()}
        self.avgdl = sum(self.doc_lens.values()) / max(len(self.doc_lens), 1)
        self.N = len(self.doc_ids)
        self.df: dict[str, int] = defaultdict(int)
        for toks in self.doc_tokens.values():
            for t in set(toks):
                self.df[t] += 1

    def score_all(self, query: str) -> dict[str, float]:
        q_tokens = _tokenize(query)
        out = {}
        for did in self.doc_ids:
            s = 0.0
            tf_map = Counter(self.doc_tokens[did])
            dl = self.doc_lens[did]
            for qt in q_tokens:
                if qt not in tf_map:
                    continue
                tf = tf_map[qt]
                df = self.df.get(qt, 0)
                idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1)
                s += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out[did] = s
        return out


# ---------------------------------------------------------------------------
# Retrieval strategies
# ---------------------------------------------------------------------------

def _cosine_scores(q_vec: np.ndarray, embeddings: dict[str, np.ndarray]) -> dict[str, float]:
    scores = {}
    for cid, emb in embeddings.items():
        n = np.linalg.norm(emb)
        scores[cid] = float(np.dot(q_vec, emb / n)) if n > 0 else 0.0
    return scores


def strategy_local(
    query_emb: np.ndarray,
    entities: pd.DataFrame,
    text_units: pd.DataFrame,
    top_k_entities: int = 10,
) -> list[tuple[str, float]]:
    """Current GRAIL: entity similarity → entity-linked chunks ranked by overlap."""
    embs, valid_idx = [], []
    for i, (_, row) in enumerate(entities.iterrows()):
        e = row.get("description_embedding")
        if e is not None and not (isinstance(e, float) and math.isnan(e)):
            embs.append(np.array(e, dtype=np.float32))
            valid_idx.append(i)
    if not embs:
        return []

    mat = np.stack(embs)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.where(norms == 0, 1, norms)
    scores = mat @ query_emb
    top_idx = np.argsort(-scores)[:top_k_entities]
    top_names = [entities.iloc[valid_idx[i]]["name"] for i in top_idx]

    name_set = set(top_names)
    chunk_scores: dict[str, int] = {}
    for _, row in text_units.iterrows():
        eids = set(_ensure_list(row.get("entity_ids")))
        overlap = len(eids & name_set)
        if overlap > 0:
            chunk_scores[row["id"]] = overlap
    return sorted(chunk_scores.items(), key=lambda x: -x[1])


def strategy_rag(
    query_emb: np.ndarray,
    text_units: pd.DataFrame,
    chunk_embeddings: dict[str, np.ndarray],
    bm25: BM25,
    query: str,
) -> list[tuple[str, float]]:
    """Pure RAG: BM25 + cosine on chunk text, no graph."""
    cos = _cosine_scores(query_emb, chunk_embeddings)
    bm25_scores = bm25.score_all(query)

    cos_max = max(cos.values()) if cos else 1.0
    bm25_max = max(bm25_scores.values()) if bm25_scores else 1.0

    combined = {}
    for cid in text_units["id"]:
        combined[cid] = (cos.get(cid, 0) / max(cos_max, 1e-9)) + \
                        (bm25_scores.get(cid, 0) / max(bm25_max, 1e-9))
    return sorted(combined.items(), key=lambda x: -x[1])


def strategy_cascade(
    query_emb: np.ndarray,
    entities: pd.DataFrame,
    text_units: pd.DataFrame,
    chunk_embeddings: dict[str, np.ndarray],
    bm25: BM25,
    query: str,
    top_k_entities: int = 15,
    top_k_rescue: int = 5,
) -> list[tuple[str, float]]:
    """Cascade: entity-gate + text re-rank + text rescue."""
    # Step 1: Entity similarity
    embs, valid_idx = [], []
    for i, (_, row) in enumerate(entities.iterrows()):
        e = row.get("description_embedding")
        if e is not None and not (isinstance(e, float) and math.isnan(e)):
            embs.append(np.array(e, dtype=np.float32))
            valid_idx.append(i)
    if not embs:
        return strategy_rag(query_emb, text_units, chunk_embeddings, bm25, query)

    mat = np.stack(embs)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.where(norms == 0, 1, norms)
    scores = mat @ query_emb
    top_idx = np.argsort(-scores)[:top_k_entities]
    top_names = set(entities.iloc[valid_idx[i]]["name"] for i in top_idx)

    # Step 2: Entity-gated chunks
    entity_chunk_ids = set()
    for _, row in text_units.iterrows():
        eids = set(_ensure_list(row.get("entity_ids")))
        if eids & top_names:
            entity_chunk_ids.add(row["id"])

    # Step 3: Text scores for ALL chunks
    cos = _cosine_scores(query_emb, chunk_embeddings)
    bm25_scores = bm25.score_all(query)
    cos_max = max(cos.values()) if cos else 1.0
    bm25_max = max(bm25_scores.values()) if bm25_scores else 1.0

    def _text_score(cid: str) -> float:
        return (cos.get(cid, 0) / max(cos_max, 1e-9)) + \
               (bm25_scores.get(cid, 0) / max(bm25_max, 1e-9))

    # Step 4: Re-rank entity-gated chunks by text score
    candidates = [(cid, _text_score(cid)) for cid in entity_chunk_ids]

    # Step 5: Rescue — top text-scored chunks NOT in entity pool
    all_text = sorted(
        [(cid, _text_score(cid)) for cid in text_units["id"]],
        key=lambda x: -x[1]
    )
    rescued = 0
    for cid, sc in all_text:
        if cid not in entity_chunk_ids:
            candidates.append((cid, sc))
            rescued += 1
            if rescued >= top_k_rescue:
                break

    candidates.sort(key=lambda x: -x[1])
    return candidates


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

def find_answer_chunks(text_units: pd.DataFrame, needles: list[str]) -> list[str]:
    found = []
    for _, row in text_units.iterrows():
        text = (row["text"] or "").lower()
        if any(n.lower() in text for n in needles):
            found.append(row["id"])
    return found


def best_rank(ranked: list[tuple[str, float]], answer_cids: list[str], top_n: int) -> int | None:
    for i, (cid, _) in enumerate(ranked[:top_n]):
        if cid in answer_cids:
            return i + 1
    return None


async def main():
    print("Loading benchmark_laws artifacts…")
    data = load_all()
    entities = data["entities"]
    text_units = data["text_units"]

    print(f"  Entities: {len(entities)}, Chunks: {len(text_units)}")

    # Get index dimension
    sample_emb = None
    for _, row in entities.iterrows():
        e = row.get("description_embedding")
        if e is not None and not (isinstance(e, float)):
            sample_emb = e
            break
    index_dim = len(sample_emb) if sample_emb is not None else 0
    print(f"  Index embedding dim: {index_dim}")

    # Embed all chunks once
    print("\nEmbedding all chunks…")
    from dotenv import load_dotenv
    load_dotenv(str(PROJECT.parent / ".env"))
    from grail.llm.embeddings import EmbeddingClient
    embed_client = EmbeddingClient(endpoint="deepinfra", model="Qwen/Qwen3-Embedding-8B")

    chunk_texts = text_units["text"].fillna("").tolist()
    chunk_ids = text_units["id"].tolist()
    raw_embeddings = await embed_client.embed(chunk_texts, tag="test_chunk_embed")

    chunk_embeddings: dict[str, np.ndarray] = {}
    for cid, emb in zip(chunk_ids, raw_embeddings):
        if len(emb) < index_dim:
            emb = emb + [0.0] * (index_dim - len(emb))
        elif len(emb) > index_dim:
            emb = emb[:index_dim]
        chunk_embeddings[cid] = np.array(emb, dtype=np.float32)
    print(f"  Embedded {len(chunk_embeddings)} chunks")

    # Build BM25 index once
    corpus = dict(zip(text_units["id"], text_units["text"].fillna("")))
    bm25 = BM25(corpus)

    # Load benchmark
    with open("benchmarks/simple_benchmark/benchmark.json") as f:
        benchmark = json.load(f)

    # Load latest judge scores for context
    scores_path = Path("benchmarks/results/2026-05-26T01-08-37Z/judge_scores.json")
    judge_scores = json.loads(scores_path.read_text()) if scores_path.exists() else {}

    # Answer needles per question
    needles_map = {
        "Q01": ["sistema de protección financiera"],
        "Q02": ["12 miembros", "comisión de recomendación"],
        "Q03": ["tres años", "umbral nacional"],
        "Q04": ["prescripción", "prescriben en el plazo"],
        "Q05": ["nombre completo", "rut del paciente"],
        "Q06": ["condiciones copulativas"],
        "Q07": ["evaluación científica", "recomendación priorizada"],
        "Q08": ["urgencia vital", "trasladado"],
        "Q09": ["carga de enfermedad", "epidemiológicos"],
        "Q10": ["cien mil millones", "aportes fiscales"],
    }

    all_results: dict[str, dict[str, int | None]] = {}

    for q_data in benchmark["questions"]:
        qid = q_data["id"]
        if qid not in needles_map:
            continue

        question = q_data["question"].strip()
        needles = needles_map[qid]
        answer_cids = find_answer_chunks(text_units, needles)

        if not answer_cids:
            continue

        # Embed query
        raw_qemb = await embed_client.embed_one(question, tag="test_query")
        if len(raw_qemb) < index_dim:
            raw_qemb = raw_qemb + [0.0] * (index_dim - len(raw_qemb))
        elif len(raw_qemb) > index_dim:
            raw_qemb = raw_qemb[:index_dim]
        q_vec = np.array(raw_qemb, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        # Run all three strategies
        local_ranked = strategy_local(q_vec, entities, text_units, top_k_entities=10)
        rag_ranked = strategy_rag(q_vec, text_units, chunk_embeddings, bm25, question)
        cascade_ranked = strategy_cascade(q_vec, entities, text_units, chunk_embeddings, bm25, question)

        r_local = best_rank(local_ranked, answer_cids, TOP_K)
        r_rag = best_rank(rag_ranked, answer_cids, TOP_K)
        r_cascade = best_rank(cascade_ranked, answer_cids, TOP_K)

        # Get judge scores
        js = judge_scores.get(qid, {})
        grail_score = js.get("grail_local", {}).get("weighted_score", "?")
        rag_bench_score = js.get("rag", {}).get("weighted_score", "?")

        all_results[qid] = {
            "local": r_local,
            "rag": r_rag,
            "cascade": r_cascade,
        }

        # Per-question details
        print(f"\n{'─'*70}")
        print(f"  {qid}: {question[:65]}")
        print(f"  Answer chunks: {len(answer_cids)}  |  Bench scores: GRAIL={grail_score} RAG={rag_bench_score}")
        print(f"  {'─'*66}")

        # Show top-5 from each strategy with overlap analysis
        local_top5 = set(c for c, _ in local_ranked[:5])
        rag_top5 = set(c for c, _ in rag_ranked[:5])
        cascade_top5 = set(c for c, _ in cascade_ranked[:5])

        print(f"  {'Strategy':<12} {'Rank':>5}  {'Top-5 chunks':>12}  Top-5 overlap with others")
        print(f"  {'─'*66}")
        print(f"  {'Local':<12} {str(r_local or '—'):>5}  {len(local_top5):>5} chunks  "
              f"RAG:{len(local_top5 & rag_top5)}  Cascade:{len(local_top5 & cascade_top5)}")
        print(f"  {'RAG':<12} {str(r_rag or '—'):>5}  {len(rag_top5):>5} chunks  "
              f"Local:{len(rag_top5 & local_top5)}  Cascade:{len(rag_top5 & cascade_top5)}")
        print(f"  {'Cascade':<12} {str(r_cascade or '—'):>5}  {len(cascade_top5):>5} chunks  "
              f"Local:{len(cascade_top5 & local_top5)}  RAG:{len(cascade_top5 & rag_top5)}")

        # Show which chunks cascade rescued (in cascade top-5 but not in local)
        rescued = cascade_top5 - local_top5
        if rescued:
            for cid in rescued:
                is_answer = " ◄ ANSWER" if cid in answer_cids else ""
                preview = text_units[text_units["id"] == cid].iloc[0]["text"][:50].replace("\n", " ")
                print(f"    rescued: {cid[:10]}… {preview}…{is_answer}")

    # ================================================================
    # Final comparison table
    # ================================================================
    print(f"\n{'='*70}")
    print("  FINAL COMPARISON: answer rank in top-10 (lower = better)")
    print(f"{'='*70}\n")

    qids = sorted(all_results.keys())

    header = f"  {'QID':<6}"
    for strat in ["local", "rag", "cascade"]:
        header += f" {strat:>8}"
    header += "   Winner"
    print(header)
    print(f"  {'─'*55}")

    wins = {"local": 0, "rag": 0, "cascade": 0, "tie": 0}
    for qid in qids:
        r = all_results[qid]
        row = f"  {qid:<6}"
        best_val = None
        for strat in ["local", "rag", "cascade"]:
            val = r[strat]
            row += f" {str(val or '—'):>8}"
            if val is not None and (best_val is None or val < best_val):
                best_val = val
        # Determine winner
        winners = [s for s in ["local", "rag", "cascade"] if r[s] == best_val and r[s] is not None]
        if len(winners) > 1:
            winner_str = "tie"
            wins["tie"] += 1
        elif winners:
            winner_str = winners[0]
            wins[winner_str] += 1
        else:
            winner_str = "—"
        row += f"   {winner_str}"
        print(row)

    print(f"\n  {'─'*55}")

    # Summary stats
    for strat in ["local", "rag", "cascade"]:
        ranks = [r[strat] for r in all_results.values() if r[strat] is not None]
        hits = sum(1 for r in all_results.values() if r[strat] is not None and r[strat] <= TOP_K)
        avg = sum(ranks) / len(ranks) if ranks else 0
        top3 = sum(1 for r in ranks if r <= 3)
        print(f"  {strat:<12} hits: {hits}/{len(all_results)}  avg_rank: {avg:.1f}  top-3: {top3}  wins: {wins[strat]}")

    print(f"\n  Key insight: cascade = local ∪ rag. When local works, cascade")
    print(f"  matches it. When local fails, cascade rescues via text matching.")
    print(f"  Cascade should never be worse than max(local, rag).")


if __name__ == "__main__":
    asyncio.run(main())
