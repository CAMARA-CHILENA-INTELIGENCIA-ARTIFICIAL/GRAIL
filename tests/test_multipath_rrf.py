"""
Multi-path retrieval with Reciprocal Rank Fusion — experiment script.

Tests 5 parallel retrieval paths fused via RRF against the benchmark_laws
corpus to evaluate whether multi-path retrieval can solve known GRAIL
failure patterns.

Paths:
  A: Entity similarity (FAISS on entity description embeddings)
  B: Direct chunk cosine (embed query → cosine against chunk text embeddings)
  C: Graph walk from matched entities (NetworkX traversal)
  D: Keyword/BM25 on chunk text
  E: Community-scoped retrieval

Fusion: Reciprocal Rank Fusion (RRF) with k=60

Usage:
    uv run python tests/test_multipath_rrf.py
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import networkx as nx
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT = Path(__file__).parent.parent / "benchmark_laws"
RRF_K = 60
TOP_K = 10

# ---------------------------------------------------------------------------
# Load artifacts
# ---------------------------------------------------------------------------


def load_artifacts():
    current = json.loads((PROJECT / "output" / "current.json").read_text())
    run_dir = PROJECT / current["run_dir"]

    entities = pd.read_parquet(run_dir / "final_entities.parquet")
    relationships = pd.read_parquet(run_dir / "final_relationships.parquet")
    text_units = pd.read_parquet(run_dir / "final_text_units.parquet")
    communities = pd.read_parquet(run_dir / "final_communities.parquet")
    community_reports = pd.read_parquet(run_dir / "final_community_reports.parquet")
    nodes = pd.read_parquet(run_dir / "final_nodes.parquet")
    graph = nx.read_graphml(run_dir / "entity_relationship_graph.graphml")

    return {
        "entities": entities,
        "relationships": relationships,
        "text_units": text_units,
        "communities": communities,
        "community_reports": community_reports,
        "nodes": nodes,
        "graph": graph,
        "run_dir": run_dir,
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
# Index builders
# ---------------------------------------------------------------------------


def build_entity_chunk_index(text_units: pd.DataFrame) -> dict[str, set[str]]:
    idx: dict[str, set[str]] = {}
    for _, row in text_units.iterrows():
        for ent in _ensure_list(row.get("entity_ids")):
            idx.setdefault(ent, set()).add(row["id"])
    return idx


def build_chunk_entity_index(text_units: pd.DataFrame) -> dict[str, set[str]]:
    idx: dict[str, set[str]] = {}
    for _, row in text_units.iterrows():
        idx[row["id"]] = set(_ensure_list(row.get("entity_ids")))
    return idx


def build_entity_community_index(nodes: pd.DataFrame) -> dict[str, str]:
    """Map entity name → community id."""
    idx: dict[str, str] = {}
    if "community" in nodes.columns and "title" in nodes.columns:
        for _, row in nodes.iterrows():
            comm = row.get("community")
            if comm is not None and str(comm) != "nan":
                idx[row["title"]] = str(int(float(comm))) if isinstance(comm, (float, int)) else str(comm)
    return idx


# ---------------------------------------------------------------------------
# PATH A: Entity similarity → chunks
# ---------------------------------------------------------------------------


def path_a_entity_similarity(
    query_embedding: list[float],
    entities: pd.DataFrame,
    entity_chunk_idx: dict[str, set[str]],
    top_k_entities: int = 15,
) -> list[tuple[str, float]]:
    """Find top entities by vector similarity, then collect their chunks
    ranked by how many top entities mention them."""
    embs = []
    valid_indices = []
    for i, (idx, row) in enumerate(entities.iterrows()):
        emb = row.get("description_embedding")
        if emb is not None and not (isinstance(emb, float) and math.isnan(emb)):
            embs.append(np.array(emb, dtype=np.float32))
            valid_indices.append(i)

    if not embs:
        return []

    emb_matrix = np.stack(embs)
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    emb_matrix = emb_matrix / norms

    q = np.array(query_embedding, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1)

    scores = emb_matrix @ q
    top_idx = np.argsort(-scores)[:top_k_entities]

    top_entity_names = []
    for i in top_idx:
        orig_idx = valid_indices[i]
        name = entities.iloc[orig_idx]["name"]
        top_entity_names.append(name)

    chunk_scores: dict[str, float] = {}
    for rank, ent_name in enumerate(top_entity_names):
        ent_score = float(scores[top_idx[rank]])
        for cid in entity_chunk_idx.get(ent_name, set()):
            chunk_scores[cid] = chunk_scores.get(cid, 0) + ent_score

    return sorted(chunk_scores.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# PATH B: Direct chunk cosine
# ---------------------------------------------------------------------------


def path_b_chunk_cosine(
    query_embedding: list[float],
    text_units: pd.DataFrame,
    chunk_embeddings: dict[str, np.ndarray],
) -> list[tuple[str, float]]:
    """Direct cosine similarity between query and each chunk's text embedding."""
    if not chunk_embeddings:
        return []

    q = np.array(query_embedding, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1)

    results = []
    for cid, emb in chunk_embeddings.items():
        norm = np.linalg.norm(emb)
        if norm == 0:
            continue
        score = float(np.dot(q, emb / norm))
        results.append((cid, score))
    return sorted(results, key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# PATH C: Graph walk from matched entities
# ---------------------------------------------------------------------------


def path_c_graph_walk(
    query_embedding: list[float],
    entities: pd.DataFrame,
    graph: nx.Graph,
    entity_chunk_idx: dict[str, set[str]],
    top_k_seeds: int = 5,
    hops: int = 1,
) -> list[tuple[str, float]]:
    """Find seed entities by similarity, expand through graph, score chunks."""
    embs = []
    names = []
    for _, row in entities.iterrows():
        emb = row.get("description_embedding")
        if emb is not None and not (isinstance(emb, float) and math.isnan(emb)):
            embs.append(np.array(emb, dtype=np.float32))
            names.append(row["name"])

    if not embs:
        return []

    emb_matrix = np.stack(embs)
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    emb_matrix = emb_matrix / norms

    q = np.array(query_embedding, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1)

    scores = emb_matrix @ q
    top_idx = np.argsort(-scores)[:top_k_seeds]
    seed_entities = [names[i] for i in top_idx]
    seed_scores = {names[i]: float(scores[i]) for i in top_idx}

    # Expand through graph
    expanded = set(seed_entities)
    for _ in range(hops):
        neighbors = set()
        for n in list(expanded):
            if n in graph:
                neighbors.update(graph.neighbors(n))
        expanded.update(neighbors)

    # Score chunks: seed entities contribute more than neighbors
    chunk_scores: dict[str, float] = {}
    for ent in expanded:
        weight = seed_scores.get(ent, 0.3)
        for cid in entity_chunk_idx.get(ent, set()):
            chunk_scores[cid] = chunk_scores.get(cid, 0) + weight

    return sorted(chunk_scores.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# PATH D: Keyword / BM25 on chunks
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-záéíóúüñ]+", text.lower())


class BM25:
    """Minimal BM25 implementation."""

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

    def score(self, query: str) -> list[tuple[str, float]]:
        q_tokens = _tokenize(query)
        results = []
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
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                s += idf * numerator / denominator
            results.append((did, s))
        return sorted(results, key=lambda x: -x[1])


def path_d_bm25(query: str, text_units: pd.DataFrame) -> list[tuple[str, float]]:
    corpus = dict(zip(text_units["id"], text_units["text"].fillna("")))
    bm25 = BM25(corpus)
    return bm25.score(query)


# ---------------------------------------------------------------------------
# PATH E: Community-scoped retrieval
# ---------------------------------------------------------------------------


def path_e_community_scoped(
    query_embedding: list[float],
    entities: pd.DataFrame,
    entity_chunk_idx: dict[str, set[str]],
    entity_community_idx: dict[str, str],
    top_k_seeds: int = 5,
) -> list[tuple[str, float]]:
    """Find seed entities, identify their communities, retrieve all chunks
    from entities in those communities."""
    embs = []
    names = []
    for _, row in entities.iterrows():
        emb = row.get("description_embedding")
        if emb is not None and not (isinstance(emb, float) and math.isnan(emb)):
            embs.append(np.array(emb, dtype=np.float32))
            names.append(row["name"])

    if not embs:
        return []

    emb_matrix = np.stack(embs)
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    emb_matrix = emb_matrix / norms

    q = np.array(query_embedding, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1)

    scores = emb_matrix @ q
    top_idx = np.argsort(-scores)[:top_k_seeds]
    seed_entities = [names[i] for i in top_idx]

    # Find communities of seed entities
    target_communities = set()
    for ent in seed_entities:
        comm = entity_community_idx.get(ent)
        if comm:
            target_communities.add(comm)

    if not target_communities:
        return []

    # Get ALL entities in those communities
    community_entities = set()
    for ent, comm in entity_community_idx.items():
        if comm in target_communities:
            community_entities.add(ent)

    # Collect chunks, score by overlap with seed entities
    chunk_scores: dict[str, float] = {}
    seed_set = set(seed_entities)
    for ent in community_entities:
        weight = 2.0 if ent in seed_set else 0.5
        for cid in entity_chunk_idx.get(ent, set()):
            chunk_scores[cid] = chunk_scores.get(cid, 0) + weight

    return sorted(chunk_scores.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[tuple[str, float]]],
    k: int = 60,
    top_n: int = 10,
    weights: dict[str, float] | None = None,
) -> list[tuple[str, float, dict[str, int]]]:
    """Fuse multiple ranked lists using RRF with optional per-path weights.

    Returns [(chunk_id, rrf_score, {path: rank}), ...] sorted by rrf_score desc.
    """
    scores: dict[str, float] = defaultdict(float)
    ranks: dict[str, dict[str, int]] = defaultdict(dict)

    for path_name, ranked in ranked_lists.items():
        w = (weights or {}).get(path_name, 1.0)
        for rank_0, (cid, _score) in enumerate(ranked):
            rrf_contribution = w / (k + rank_0 + 1)
            scores[cid] += rrf_contribution
            ranks[cid][path_name] = rank_0 + 1

    fused = sorted(scores.items(), key=lambda x: -x[1])
    return [(cid, sc, ranks[cid]) for cid, sc in fused[:top_n]]


# ---------------------------------------------------------------------------
# Adaptive fusion strategies
# ---------------------------------------------------------------------------


def strategy_uniform_rrf(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Baseline: equal-weight RRF across all 5 paths."""
    return reciprocal_rank_fusion(paths, k=60, top_n=top_n)


def strategy_weighted_rrf(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Static weights: upweight text-based paths (B, D) which are more reliable
    for lexical/factual queries."""
    weights = {
        "A:entity_sim": 1.0,
        "B:chunk_cos":  2.0,
        "C:graph_walk": 1.0,
        "D:bm25":       2.0,
        "E:community":  0.5,
    }
    return reciprocal_rank_fusion(paths, k=60, top_n=top_n, weights=weights)


def strategy_confidence_gated(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Only include a path if its top-1 score shows confidence (score gap
    between #1 and #3 is significant). Paths with flat score distributions
    aren't discriminating — they add noise."""
    selected: dict[str, list[tuple[str, float]]] = {}
    for name, ranked in paths.items():
        if len(ranked) < 3:
            selected[name] = ranked
            continue
        top1_score = ranked[0][1]
        top3_score = ranked[2][1]
        if top1_score == 0:
            continue
        gap_ratio = (top1_score - top3_score) / top1_score if top1_score > 0 else 0
        if gap_ratio > 0.05:
            selected[name] = ranked
    if not selected:
        selected = paths
    return reciprocal_rank_fusion(selected, k=60, top_n=top_n)


def strategy_top_k_gated(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Only take top-5 from each path before fusing. Prevents long-tail noise
    from entity-gated paths from diluting text-based signals."""
    truncated = {name: ranked[:5] for name, ranked in paths.items()}
    return reciprocal_rank_fusion(truncated, k=60, top_n=top_n)


def strategy_score_weighted_rrf(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Weight each path's contribution by the raw score of its top-1 result.
    Paths whose top result has a strong score get more influence."""
    weights: dict[str, float] = {}
    for name, ranked in paths.items():
        if ranked:
            weights[name] = max(ranked[0][1], 0.01)
        else:
            weights[name] = 0.01
    max_w = max(weights.values())
    weights = {k: v / max_w for k, v in weights.items()}
    return reciprocal_rank_fusion(paths, k=60, top_n=top_n, weights=weights)


def strategy_text_only(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Fuse only text-based paths (B: chunk cosine + D: BM25). Ignores
    entity-gated paths entirely."""
    text_paths = {k: v for k, v in paths.items() if k in ("B:chunk_cos", "D:bm25")}
    return reciprocal_rank_fusion(text_paths, k=60, top_n=top_n)


def strategy_adaptive_quorum(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Boost chunks that appear in the top-5 of at least 2 different paths.
    Chunks found by only 1 path get halved RRF. Rewards agreement across
    different retrieval paradigms."""
    top5_sets: dict[str, set[str]] = {}
    for name, ranked in paths.items():
        top5_sets[name] = {cid for cid, _ in ranked[:5]}

    chunk_appearances: dict[str, int] = defaultdict(int)
    for s in top5_sets.values():
        for cid in s:
            chunk_appearances[cid] += 1

    scores: dict[str, float] = defaultdict(float)
    ranks: dict[str, dict[str, int]] = defaultdict(dict)

    for path_name, ranked in paths.items():
        for rank_0, (cid, _score) in enumerate(ranked):
            quorum_boost = 1.5 if chunk_appearances.get(cid, 0) >= 2 else 0.5
            rrf_contribution = quorum_boost / (60 + rank_0 + 1)
            scores[cid] += rrf_contribution
            ranks[cid][path_name] = rank_0 + 1

    fused = sorted(scores.items(), key=lambda x: -x[1])
    return [(cid, sc, ranks[cid]) for cid, sc in fused[:top_n]]


def strategy_cascade(
    paths: dict[str, list[tuple[str, float]]], top_n: int = 10,
) -> list[tuple[str, float, dict[str, int]]]:
    """Cascade: start with entity similarity (A) top-10 candidates, then
    re-rank using BM25 (D) and chunk cosine (B) scores. Falls back to
    text-only fusion if entity path returns fewer than 3 candidates."""
    a_ranked = paths.get("A:entity_sim", [])
    b_ranked = paths.get("B:chunk_cos", [])
    d_ranked = paths.get("D:bm25", [])

    b_scores = {cid: sc for cid, sc in b_ranked}
    d_scores = {cid: sc for cid, sc in d_ranked}

    if len(a_ranked) < 3:
        return strategy_text_only(paths, top_n=top_n)

    candidates = [cid for cid, _ in a_ranked[:15]]
    b_max = max(b_scores.values()) if b_scores else 1.0
    d_max = max(d_scores.values()) if d_scores else 1.0

    reranked: list[tuple[str, float]] = []
    for cid in candidates:
        score = (b_scores.get(cid, 0) / b_max) + (d_scores.get(cid, 0) / d_max)
        reranked.append((cid, score))

    # Add top B and D results not in entity candidates
    seen = set(candidates)
    for cid, _ in b_ranked[:5]:
        if cid not in seen:
            score = (b_scores.get(cid, 0) / b_max) + (d_scores.get(cid, 0) / d_max)
            reranked.append((cid, score))
            seen.add(cid)
    for cid, _ in d_ranked[:5]:
        if cid not in seen:
            score = (b_scores.get(cid, 0) / b_max) + (d_scores.get(cid, 0) / d_max)
            reranked.append((cid, score))
            seen.add(cid)

    reranked.sort(key=lambda x: -x[1])

    ranks: dict[str, dict[str, int]] = defaultdict(dict)
    for i, (cid, _) in enumerate(reranked):
        for pname, pranked in paths.items():
            pids = [c for c, _ in pranked]
            if cid in pids:
                ranks[cid][pname] = pids.index(cid) + 1

    return [(cid, sc, dict(ranks[cid])) for cid, sc in reranked[:top_n]]


ALL_STRATEGIES = {
    "1_uniform_rrf":       strategy_uniform_rrf,
    "2_weighted_rrf":      strategy_weighted_rrf,
    "3_confidence_gated":  strategy_confidence_gated,
    "4_top_k_gated":       strategy_top_k_gated,
    "5_score_weighted":    strategy_score_weighted_rrf,
    "6_text_only":         strategy_text_only,
    "7_quorum":            strategy_adaptive_quorum,
    "8_cascade":           strategy_cascade,
}


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------


def find_answer_chunks(text_units: pd.DataFrame, needles: list[str]) -> list[str]:
    """Find chunk IDs containing any of the needle strings."""
    found = []
    for _, row in text_units.iterrows():
        text = (row["text"] or "").lower()
        if any(n.lower() in text for n in needles):
            found.append(row["id"])
    return found


def _best_answer_rank(ranked_ids: list[str], answer_cids: list[str]) -> int | None:
    for acid in answer_cids:
        if acid in ranked_ids:
            r = ranked_ids.index(acid) + 1
            return r
    return None


def run_test(
    qid: str,
    question: str,
    answer_needles: list[str],
    query_embedding: list[float],
    artifacts: dict[str, Any],
    chunk_embeddings: dict[str, np.ndarray],
    entity_chunk_idx: dict[str, set[str]],
    chunk_entity_idx: dict[str, set[str]],
    entity_community_idx: dict[str, str],
) -> dict[str, int | None]:
    """Run all paths and all fusion strategies. Returns {strategy: best_rank}."""
    text_units = artifacts["text_units"]
    entities = artifacts["entities"]
    graph = artifacts["graph"]

    answer_cids = find_answer_chunks(text_units, answer_needles)

    print(f"\n{'='*80}")
    print(f"  {qid}: {question[:70]}")
    print(f"{'='*80}")
    if not answer_cids:
        print(f"  ⚠ No answer chunks found with needles: {answer_needles}")
        return {}
    print(f"  Answer chunks: {len(answer_cids)} — {[c[:10] for c in answer_cids]}")

    # Run all paths
    paths: dict[str, list[tuple[str, float]]] = {}
    paths["A:entity_sim"] = path_a_entity_similarity(
        query_embedding, entities, entity_chunk_idx, top_k_entities=15
    )
    paths["B:chunk_cos"] = path_b_chunk_cosine(
        query_embedding, text_units, chunk_embeddings
    )
    paths["C:graph_walk"] = path_c_graph_walk(
        query_embedding, entities, graph, entity_chunk_idx, top_k_seeds=5, hops=1
    )
    paths["D:bm25"] = path_d_bm25(question, text_units)
    paths["E:community"] = path_e_community_scoped(
        query_embedding, entities, entity_chunk_idx, entity_community_idx, top_k_seeds=5
    )

    # Per-path results
    print()
    print(f"  {'Path':<20} {'Total':>5}  Best answer rank")
    print(f"  {'-'*50}")
    for name, ranked in paths.items():
        ranked_ids = [cid for cid, _ in ranked]
        best = _best_answer_rank(ranked_ids, answer_cids)
        print(f"  {name:<20} {len(ranked_ids):>5}  {best or 'NOT FOUND'}")

    # Run all strategies
    results: dict[str, int | None] = {}

    # Individual paths as baselines
    results["path_A_only"] = _best_answer_rank([c for c, _ in paths["A:entity_sim"]], answer_cids)
    results["path_B_only"] = _best_answer_rank([c for c, _ in paths["B:chunk_cos"]], answer_cids)
    results["path_D_only"] = _best_answer_rank([c for c, _ in paths["D:bm25"]], answer_cids)

    for strat_name, strat_fn in ALL_STRATEGIES.items():
        fused = strat_fn(paths, top_n=TOP_K)
        fused_ids = [cid for cid, _, _ in fused]
        results[strat_name] = _best_answer_rank(fused_ids, answer_cids)

    # Print strategy comparison
    print()
    print(f"  ── Strategy comparison (top-{TOP_K}) ──")
    print(f"  {'Strategy':<30} {'Rank':>6}")
    print(f"  {'-'*38}")
    for name, rank in results.items():
        marker = ""
        if rank is not None and rank <= 3:
            marker = " ★"
        elif rank is None:
            marker = " ✗"
        print(f"  {name:<30} {str(rank or '—'):>6}{marker}")

    return results


def _get_index_dim(entities: pd.DataFrame) -> int:
    """Get the embedding dimension from the stored entity embeddings."""
    for _, row in entities.iterrows():
        emb = row.get("description_embedding")
        if emb is not None and not (isinstance(emb, float) and math.isnan(emb)):
            return len(emb)
    return 0


async def _get_embed_client(dim: int):
    """Get an embedding client that matches the index dimension."""
    from dotenv import load_dotenv
    load_dotenv(str(PROJECT.parent / ".env"))
    from grail.llm.embeddings import EmbeddingClient

    kwargs: dict[str, Any] = {}
    return EmbeddingClient(
        endpoint="deepinfra",
        model="Qwen/Qwen3-Embedding-8B",
        **kwargs,
    ), dim


async def embed_query(question: str, target_dim: int) -> list[float]:
    """Embed a query, padding/truncating to match the index dimension."""
    client, _ = await _get_embed_client(target_dim)
    emb = await client.embed_one(question, tag="test_query")
    if len(emb) < target_dim:
        emb = emb + [0.0] * (target_dim - len(emb))
    elif len(emb) > target_dim:
        emb = emb[:target_dim]
    return emb


async def embed_chunks(text_units: pd.DataFrame, target_dim: int) -> dict[str, np.ndarray]:
    """Embed all chunk texts for Path B."""
    client, _ = await _get_embed_client(target_dim)
    texts = text_units["text"].fillna("").tolist()
    ids = text_units["id"].tolist()
    embeddings = await client.embed(texts, tag="test_chunk_embed")
    result = {}
    for cid, emb in zip(ids, embeddings):
        if len(emb) < target_dim:
            emb = emb + [0.0] * (target_dim - len(emb))
        elif len(emb) > target_dim:
            emb = emb[:target_dim]
        result[cid] = np.array(emb, dtype=np.float32)
    return result


async def main():
    print("Loading benchmark_laws artifacts…")
    artifacts = load_artifacts()
    entities = artifacts["entities"]
    text_units = artifacts["text_units"]
    nodes = artifacts["nodes"]

    entity_chunk_idx = build_entity_chunk_index(text_units)
    chunk_entity_idx = build_chunk_entity_index(text_units)
    entity_community_idx = build_entity_community_index(nodes)

    print(f"  Entities: {len(entities)}, Text units: {len(text_units)}")
    print(f"  Graph nodes: {artifacts['graph'].number_of_nodes()}")
    print(f"  Entity→community index: {len(entity_community_idx)} entries")

    # Detect index embedding dimension
    index_dim = _get_index_dim(entities)
    print(f"  Index embedding dim: {index_dim}")

    # Load benchmark questions
    benchmark_path = Path("benchmarks/simple_benchmark/benchmark.json")
    with open(benchmark_path) as f:
        benchmark = json.load(f)

    # Focus on the known failure questions + a few that work well for comparison
    test_questions = {
        "Q04": {
            "needles": ["prescripción", "prescriben en el plazo"],
        },
        "Q06": {
            "needles": ["condiciones copulativas"],
        },
        "Q21": {
            "needles": ["sanciones", "multa"],
        },
        # Control questions where GRAIL already scores 5.0
        "Q01": {
            "needles": ["sistema de protección financiera"],
        },
        "Q02": {
            "needles": ["12 miembros", "comisión de recomendación"],
        },
        "Q10": {
            "needles": ["cien mil millones", "aportes fiscales"],
        },
    }

    # Embed all chunks once (Path B needs this)
    print("\nEmbedding chunks for Path B (direct cosine)…")
    chunk_embeddings = await embed_chunks(text_units, target_dim=index_dim)
    print(f"  Embedded {len(chunk_embeddings)} chunks (dim={index_dim})")

    # Run each test question
    all_results: dict[str, dict[str, int | None]] = {}
    for q_data in benchmark["questions"]:
        qid = q_data["id"]
        if qid not in test_questions:
            continue

        question = q_data["question"].strip()
        needles = test_questions[qid]["needles"]

        print(f"\nEmbedding query: {qid}…")
        query_embedding = await embed_query(question, target_dim=index_dim)

        qresults = run_test(
            qid=qid,
            question=question,
            answer_needles=needles,
            query_embedding=query_embedding,
            artifacts=artifacts,
            chunk_embeddings=chunk_embeddings,
            entity_chunk_idx=entity_chunk_idx,
            chunk_entity_idx=chunk_entity_idx,
            entity_community_idx=entity_community_idx,
        )
        all_results[qid] = qresults

    # ================================================================
    # Final comparison matrix
    # ================================================================
    print(f"\n{'='*80}")
    print("  FINAL COMPARISON MATRIX")
    print(f"{'='*80}")
    print()

    qids = sorted(all_results.keys())
    strategies = list(next(iter(all_results.values())).keys()) if all_results else []

    # Header
    header = f"  {'Strategy':<30}"
    for qid in qids:
        header += f" {qid:>5}"
    header += "   AVG    IN-TOP-10"
    print(header)
    print(f"  {'-' * (32 + 6 * len(qids) + 16)}")

    for strat in strategies:
        row = f"  {strat:<30}"
        ranks = []
        hits = 0
        for qid in qids:
            r = all_results[qid].get(strat)
            if r is not None:
                row += f" {r:>5}"
                ranks.append(r)
                if r <= TOP_K:
                    hits += 1
            else:
                row += f"   {'—':>2}"
        avg = sum(ranks) / len(ranks) if ranks else 0
        row += f"   {avg:>4.1f}    {hits}/{len(qids)}"
        print(row)

    print()
    print("  Legend: number = best answer rank in top-10, — = not in top-10")
    print("  ★ = rank ≤ 3 (excellent), lower is better")
    print()
    print("  Strategies:")
    print("    path_A_only         Current GRAIL (entity similarity → chunks)")
    print("    path_B_only         Direct chunk cosine (RAG-like)")
    print("    path_D_only         BM25 keyword match")
    print("    1_uniform_rrf       Equal-weight RRF across all 5 paths")
    print("    2_weighted_rrf      2x weight for B (cosine) and D (BM25)")
    print("    3_confidence_gated  Drop paths with flat score distributions")
    print("    4_top_k_gated       Only top-5 per path before fusing")
    print("    5_score_weighted    Weight paths by their top-1 raw score")
    print("    6_text_only         Fuse only B + D (ignore entity-gated paths)")
    print("    7_quorum            Boost chunks in top-5 of ≥2 paths")
    print("    8_cascade           Entity candidates re-ranked by B+D scores")


if __name__ == "__main__":
    asyncio.run(main())
