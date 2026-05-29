"""
Test graph-based retrieval strategies against known GRAIL failure cases.

Uses NetworkX on the local graphml + parquet artifacts — no Neo4j needed.
Validates whether graph traversal can find answer chunks that GRAIL's
entity-gated vector search misses.

Usage:
    uv run python tests/test_graph_search.py
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd

PROJECT = Path(__file__).parent.parent / "benchmark_laws"
OUTPUT = PROJECT / "output"


def load_artifacts():
    """Load the latest run artifacts."""
    current = json.loads((OUTPUT / "current.json").read_text())
    run_dir = PROJECT / current["run_dir"]

    entities = pd.read_parquet(run_dir / "final_entities.parquet")
    relationships = pd.read_parquet(run_dir / "final_relationships.parquet")
    text_units = pd.read_parquet(run_dir / "final_text_units.parquet")
    graph = nx.read_graphml(run_dir / "entity_relationship_graph.graphml")

    return entities, relationships, text_units, graph


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


def build_chunk_entity_index(text_units: pd.DataFrame) -> dict[str, set[str]]:
    """Map chunk_id → set of entity names mentioned in it."""
    index: dict[str, set[str]] = {}
    for _, row in text_units.iterrows():
        entity_ids = _ensure_list(row.get("entity_ids"))
        index[row["id"]] = set(entity_ids)
    return index


def build_entity_chunk_index(text_units: pd.DataFrame) -> dict[str, set[str]]:
    """Map entity_name → set of chunk_ids that mention it."""
    index: dict[str, set[str]] = {}
    for _, row in text_units.iterrows():
        for ent in _ensure_list(row.get("entity_ids")):
            index.setdefault(ent, set()).add(row["id"])
    return index


# ---- Strategy 1: Graph neighborhood expansion ----

def graph_neighborhood_search(
    graph: nx.Graph,
    seed_entities: list[str],
    entity_chunk_idx: dict[str, set[str]],
    hops: int = 1,
) -> list[str]:
    """Expand seed entities through the graph, collect all reachable chunks."""
    expanded = set()
    for seed in seed_entities:
        if seed not in graph:
            # Try case-insensitive match
            for node in graph.nodes:
                if node.upper() == seed.upper():
                    seed = node
                    break
        if seed in graph:
            expanded.add(seed)
            for hop in range(1, hops + 1):
                neighbors = set()
                for n in list(expanded):
                    neighbors.update(graph.neighbors(n))
                expanded.update(neighbors)

    chunks: set[str] = set()
    for ent in expanded:
        chunks.update(entity_chunk_idx.get(ent, set()))
    return list(chunks)


# ---- Strategy 2: Graph + keyword hybrid ----

def graph_keyword_search(
    graph: nx.Graph,
    seed_entities: list[str],
    entity_chunk_idx: dict[str, set[str]],
    text_units: pd.DataFrame,
    keywords: list[str],
    hops: int = 1,
) -> list[str]:
    """Expand entities via graph, then filter chunks by keyword match."""
    candidate_chunks = graph_neighborhood_search(
        graph, seed_entities, entity_chunk_idx, hops=hops
    )

    tu_text = dict(zip(text_units["id"], text_units["text"].str.lower()))

    filtered = []
    for cid in candidate_chunks:
        text = tu_text.get(cid, "")
        if any(kw.lower() in text for kw in keywords):
            filtered.append(cid)
    return filtered


# ---- Strategy 3: Direct keyword search on chunks (RAG-like baseline) ----

def keyword_search(
    text_units: pd.DataFrame,
    keywords: list[str],
) -> list[str]:
    """Simple keyword search on chunk text."""
    results = []
    for _, row in text_units.iterrows():
        text = (row["text"] or "").lower()
        if any(kw.lower() in text for kw in keywords):
            results.append(row["id"])
    return results


# ---- Strategy 4: Entity-gated search (current GRAIL approach) ----

def entity_gated_search(
    seed_entities: list[str],
    entity_chunk_idx: dict[str, set[str]],
    chunk_entity_idx: dict[str, set[str]],
) -> list[tuple[str, int]]:
    """Current GRAIL approach: find chunks that mention seed entities, rank by overlap."""
    seed_set = set(e.upper() for e in seed_entities)
    chunk_scores: dict[str, int] = {}
    for ent in seed_entities:
        for cid in entity_chunk_idx.get(ent, set()):
            chunk_entities = chunk_entity_idx.get(cid, set())
            overlap = len(chunk_entities & seed_set)
            chunk_scores[cid] = max(chunk_scores.get(cid, 0), overlap)
    return sorted(chunk_scores.items(), key=lambda x: -x[1])


def find_answer_chunk(text_units: pd.DataFrame, needle: str) -> str | None:
    """Find the chunk ID that contains the answer text."""
    for _, row in text_units.iterrows():
        if needle.lower() in (row["text"] or "").lower():
            return row["id"]
    return None


def run_test(
    label: str,
    question: str,
    answer_needle: str,
    seed_entities: list[str],
    keywords: list[str],
    graph: nx.Graph,
    entities: pd.DataFrame,
    text_units: pd.DataFrame,
    entity_chunk_idx: dict[str, set[str]],
    chunk_entity_idx: dict[str, set[str]],
):
    print(f"\n{'='*80}")
    print(f"  {label}: {question[:70]}")
    print(f"{'='*80}")

    answer_cid = find_answer_chunk(text_units, answer_needle)
    if not answer_cid:
        print(f"  ⚠ Could not find answer chunk with needle: '{answer_needle}'")
        return
    print(f"  Answer chunk: {answer_cid[:12]}…")
    answer_text = text_units[text_units["id"] == answer_cid].iloc[0]["text"]
    print(f"  Preview: {answer_text[:100].replace(chr(10), ' ')}…")
    print()

    # Test 1: Current GRAIL entity-gated search
    print("  ── Current GRAIL (entity-gated) ──")
    gated = entity_gated_search(seed_entities, entity_chunk_idx, chunk_entity_idx)
    gated_ids = [cid for cid, _ in gated]
    found = answer_cid in gated_ids
    rank = gated_ids.index(answer_cid) + 1 if found else -1
    print(f"  Chunks found: {len(gated_ids)}")
    print(f"  Answer found: {'YES at rank ' + str(rank) if found else 'NO ✗'}")

    # Test 2: 1-hop graph expansion
    print("\n  ── Graph neighborhood (1-hop) ──")
    expanded_1 = graph_neighborhood_search(graph, seed_entities, entity_chunk_idx, hops=1)
    found = answer_cid in expanded_1
    print(f"  Chunks found: {len(expanded_1)}")
    print(f"  Answer found: {'YES ✓' if found else 'NO ✗'}")

    # Test 3: 2-hop graph expansion
    print("\n  ── Graph neighborhood (2-hop) ──")
    expanded_2 = graph_neighborhood_search(graph, seed_entities, entity_chunk_idx, hops=2)
    found = answer_cid in expanded_2
    print(f"  Chunks found: {len(expanded_2)}")
    print(f"  Answer found: {'YES ✓' if found else 'NO ✗'}")

    # Test 4: Graph + keyword hybrid (1-hop)
    print("\n  ── Graph + keyword hybrid (1-hop) ──")
    hybrid_1 = graph_keyword_search(
        graph, seed_entities, entity_chunk_idx, text_units, keywords, hops=1
    )
    found = answer_cid in hybrid_1
    print(f"  Chunks found: {len(hybrid_1)}")
    print(f"  Answer found: {'YES ✓' if found else 'NO ✗'}")

    # Test 5: Graph + keyword hybrid (2-hop)
    print("\n  ── Graph + keyword hybrid (2-hop) ──")
    hybrid_2 = graph_keyword_search(
        graph, seed_entities, entity_chunk_idx, text_units, keywords, hops=2
    )
    found = answer_cid in hybrid_2
    print(f"  Chunks found: {len(hybrid_2)}")
    print(f"  Answer found: {'YES ✓' if found else 'NO ✗'}")

    # Test 6: Pure keyword search (RAG-like)
    print("\n  ── Pure keyword search (baseline) ──")
    kw_results = keyword_search(text_units, keywords)
    found = answer_cid in kw_results
    print(f"  Chunks found: {len(kw_results)}")
    print(f"  Answer found: {'YES ✓' if found else 'NO ✗'}")

    # Test 7: Graph ranked search (the proposed new strategy)
    print("\n  ── Graph ranked search (1-hop + keyword boost) ──")
    ranked_graph = graph_ranked_search(
        graph, seed_entities, entity_chunk_idx, chunk_entity_idx,
        text_units, keywords, hops=1
    )
    ranked_ids = [cid for cid, _ in ranked_graph]
    found = answer_cid in ranked_ids
    rank_g = ranked_ids.index(answer_cid) + 1 if found else -1
    print(f"  Chunks found: {len(ranked_ids)}")
    print(f"  Answer found: {'YES at rank ' + str(rank_g) if found else 'NO ✗'}")
    if found:
        score = dict(ranked_graph)[answer_cid]
        print(f"  Answer score: {score:.1f}")
        print(f"  Top 5 ranked:")
        for i, (cid, sc) in enumerate(ranked_graph[:5]):
            marker = " ◄ ANSWER" if cid == answer_cid else ""
            preview = text_units[text_units["id"] == cid].iloc[0]["text"][:60].replace("\n", " ")
            print(f"    #{i+1} [{sc:.1f}] {cid[:10]}… {preview}…{marker}")

    # Summary
    print(f"\n  ── Summary ──")
    print(f"  {'Method':<35} {'Chunks':>6}  {'Rank':>6}  Precision")
    print(f"  {'-'*65}")
    for name, n, cid_list in [
        ("GRAIL entity-gated", len(gated_ids), gated_ids),
        ("Graph 1-hop", len(expanded_1), expanded_1),
        ("Graph+keyword 1-hop", len(hybrid_1), hybrid_1),
        ("Graph ranked (proposed)", len(ranked_ids), ranked_ids),
        ("Keyword only", len(kw_results), kw_results),
    ]:
        found = answer_cid in cid_list
        r = cid_list.index(answer_cid) + 1 if found else -1
        rank_str = str(r) if found else "—"
        precision = f"1/{n}" if found and n > 0 else "—"
        marker = "✓" if found else "✗"
        print(f"  {name:<35} {n:>6}  {rank_str:>6}  {precision}")


def graph_ranked_search(
    graph: nx.Graph,
    seed_entities: list[str],
    entity_chunk_idx: dict[str, set[str]],
    chunk_entity_idx: dict[str, set[str]],
    text_units: pd.DataFrame,
    keywords: list[str],
    hops: int = 1,
) -> list[tuple[str, float]]:
    """Graph expansion + keyword boost ranking.

    Score = (entity_overlap from expanded set) + (keyword_matches * 2)
    This combines graph structure with text relevance.
    """
    expanded = set()
    seed_set = set()
    for seed in seed_entities:
        matched = None
        if seed in graph:
            matched = seed
        else:
            for node in graph.nodes:
                if node.upper() == seed.upper():
                    matched = node
                    break
        if matched:
            seed_set.add(matched)
            expanded.add(matched)
            for _ in range(hops):
                neighbors = set()
                for n in list(expanded):
                    neighbors.update(graph.neighbors(n))
                expanded.update(neighbors)

    tu_text = dict(zip(text_units["id"], text_units["text"].str.lower()))

    chunk_scores: dict[str, float] = {}
    for ent in expanded:
        for cid in entity_chunk_idx.get(ent, set()):
            # Base score: entity is in expanded set
            chunk_scores.setdefault(cid, 0)
            # Bonus for seed entities (not just neighbors)
            if ent in seed_set:
                chunk_scores[cid] += 2.0
            else:
                chunk_scores[cid] += 0.5

    # Keyword boost
    for cid in chunk_scores:
        text = tu_text.get(cid, "")
        kw_hits = sum(1 for kw in keywords if kw.lower() in text)
        chunk_scores[cid] += kw_hits * 3.0

    return sorted(chunk_scores.items(), key=lambda x: -x[1])


def main():
    print("Loading benchmark_laws artifacts…")
    entities, relationships, text_units, graph = load_artifacts()
    print(f"  Entities: {len(entities)}, Relationships: {len(relationships)}")
    print(f"  Text units: {len(text_units)}, Graph nodes: {graph.number_of_nodes()}")

    entity_chunk_idx = build_entity_chunk_index(text_units)
    chunk_entity_idx = build_chunk_entity_index(text_units)
    print(f"  Entity→chunk index: {len(entity_chunk_idx)} entities")
    print(f"  Chunk→entity index: {len(chunk_entity_idx)} chunks")

    # ========================================================
    # Q06: Entity gate excludes the answer chunk
    # ========================================================
    run_test(
        label="Q06 (Failure 1: entity gate excludes answer)",
        question="¿Cuáles son las condiciones copulativas para incorporar un tratamiento al decreto de alto costo?",
        answer_needle="condiciones copulativas",
        seed_entities=[
            "TRATAMIENTO DE ALTO COSTO",
            "DECRETO SUPREMO",
            "LEY 20850",
            "SISTEMA DE PROTECCIÓN FINANCIERA PARA DIAGNÓSTICOS Y TRATAMIENTOS DE ALTO COSTO",
        ],
        keywords=["condiciones copulativas", "incorporar", "artículo 5"],
        graph=graph,
        entities=entities,
        text_units=text_units,
        entity_chunk_idx=entity_chunk_idx,
        chunk_entity_idx=chunk_entity_idx,
    )

    # ========================================================
    # Q04: Noisy entity matching, no selectivity
    # ========================================================
    run_test(
        label="Q04 (Failure 2: noisy matching, no selectivity)",
        question="¿Cuál es el plazo de prescripción de las infracciones y sanciones del Título IV?",
        answer_needle="prescripción",
        seed_entities=[
            "TÉRMINO DE PRESCRIPCIÓN",
            "LEY 19966",
            "LEY 20850",
        ],
        keywords=["prescripción", "plazo", "infracciones"],
        graph=graph,
        entities=entities,
        text_units=text_units,
        entity_chunk_idx=entity_chunk_idx,
        chunk_entity_idx=chunk_entity_idx,
    )

    # ========================================================
    # Q21: Sanctions comparison — too broad entity matching
    # ========================================================
    run_test(
        label="Q21 (Failure 2b: comparative, broad matching)",
        question="¿En qué se diferencian las sanciones por incumplimiento del Título IV vs Título V?",
        answer_needle="sanciones",
        seed_entities=[
            "LEY 20850",
            "SUPERINTENDENCIA DE SALUD",
        ],
        keywords=["sanciones", "multa", "título iv", "título v"],
        graph=graph,
        entities=entities,
        text_units=text_units,
        entity_chunk_idx=entity_chunk_idx,
        chunk_entity_idx=chunk_entity_idx,
    )


if __name__ == "__main__":
    main()
