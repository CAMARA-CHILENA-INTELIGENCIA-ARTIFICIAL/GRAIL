# GRAIL Benchmark Results — oncology_laws_chile_v1

## Disclaimer

> **This is an internal experimental benchmark** developed for the Cámara Chilena de Inteligencia Artificial's open-source commission. It uses a small, domain-specific corpus (Chilean oncology law) to validate GRAIL's core retrieval and agent architecture. The benchmark framework is **replicable with any corpus** — swap the documents, write domain-specific questions with gold answers, and run `benchmarks/run_benchmark.py`.
>
> Two standardized external benchmarks are planned for future validation:
> - **GraphRAG-Bench** (arXiv:2506.05690) — 4,072 questions across Medical + Novel domains, 4 difficulty levels
> - **LongMemEval** (Zep) — 500 questions testing temporal reasoning and cross-session synthesis
>
> See `docs/benchmarks.md` for evaluation stack requirements and reproducibility guidelines for these external benchmarks.

## About this benchmark

This benchmark is designed as a **worst-case scenario for graph-enhanced retrieval**: a small corpus (3 documents, 35 chunks, ~58 pages) where traditional RAG should perform at its best. With only 35 text units, every chunk is within reach of a top-10 cosine search — the exact conditions where RAG has no retrieval failures.

Despite this RAG-favorable setup, GRAIL's agent consistently outperforms:

| Metric | GRAIL Agent | RAG Agent |
|---|---|---|
| **Average score** | **4.80 / 5.00** | **4.14 / 5.00** |
| **Win-Loss-Tie** | **27-0-3** | 0-27-3 |
| **Avg response time** | ~25s | ~35s |
| **Avg LLM calls** | 2.6 | 3.1 |
| **Empty responses** | 0 | 0 |

**Why GRAIL wins on a small corpus:** The advantage comes not from retrieval coverage (both systems reach all 35 chunks) but from **context quality**. GRAIL's entity descriptions, relationships, community reports, and retrieval queries provide structured context that helps the LLM synthesize better answers. The agent's ability to pick the right search tool (local for entity concepts, cascade for text details, global for thematic overviews) further compounds the advantage.

**On a larger corpus, the gap would widen** because RAG's top-10 chunk retrieval would start missing relevant passages across hundreds of documents, while GRAIL's entity graph maintains cross-document connections at any scale.

## Corpus

3 Chilean legal documents on health rights for cancer patients:

- **Ley 19.966** (2004) — Health guarantee system (GES/AUGE), 18 pages
- **Ley 20.850** (2015) — Ricarte Soto Law, high-cost financial protection, 30 pages
- **Decreto 54** (2015) — Implementing regulation, 10 pages

Indexed into: 35 text units, 249 entities, 432 relationships, 9 communities.

## Questions

30 patient-language questions across 7 categories:

| Category | Count | Description | GRAIL advantage |
|---|---|---|---|
| Single Fact | 5 | One specific datum | +0.52 (entity descriptions answer directly) |
| Multi-Chunk | 5 | Answer spans 2+ chunks | +0.72 (entity graph connects chunks) |
| Cross-Source | 5 | Answer spans 2+ documents | +0.80 (graph links across documents) |
| Procedural | 4 | Step-by-step processes | +0.64 (relationship chains) |
| Comparative | 3 | Compare two concepts | +0.80 (two local_search calls) |
| Negation/Boundary | 3 | "Does X cover Y?" → No | +0.08 (near-tied) |
| Global Synthesis | 5 | Bird's-eye overview | +0.90 (community reports) |

All questions are written in **patient language** — how a cancer patient would actually ask, not how a legal expert would phrase it. This tests the system's ability to bridge natural language to legal concepts.

## File structure

```
results/
├── README.md                          ← this file
├── es/
│   └── reporte_final_benchmark.html   ← Spanish final report (default)
├── en/
│   ├── final_benchmark_report.html    ← English final report
│   ├── batch1_q01_q10_report.html     ← Batch 1 detail
│   ├── batch2_q11_q20_report.html     ← Batch 2 detail
│   └── batch3_q21_q30_report.html     ← Batch 3 detail
└── archive/
    ├── runs/                          ← Raw response JSONs from each run
    └── experiments/                   ← Intermediate experiment data
```

## Methodology

- **LLM:** Qwen3.6-35B-A3B (via DeepInfra)
- **Embeddings:** Qwen3-Embedding-8B (via DeepInfra)
- **Vector store:** FAISS with cosine similarity
- **Agent budget:** 3 iterations, up to 2 tool calls per question
- **Scoring:** 5-dimension rubric (Correctness 35%, Completeness 25%, Source Grounding 15%, Coherence 10%, No Hallucination 15%)
- **Judge:** Claude Opus 4.6 against expert gold answers

Both agents get the same LLM, embeddings, and source documents. The only difference is GRAIL's knowledge graph layer (entities, relationships, communities, retrieval queries).

## Key technical findings from the benchmark development process

1. **Text unit truncation bug** — chunks were silently cut to 1200 chars (fixed: full chunks)
2. **LanceDB Euclidean → FAISS cosine** — L2 distance distorted entity rankings
3. **Thinking model token budgets** — Qwen3.6 burns 50-80% of max_tokens on `<think>` blocks
4. **Mini-agent bottleneck** — the agent's tool context was being LLM-summarized from 20K to 2K tokens, destroying structured context
5. **Entity name prepend** — embedding `"NAME: description queries"` instead of just `"description"` improves entity retrieval
6. **WHO+WHAT+TERMS query formula** — crafting local_search queries as entity descriptions (not questions) triples retrieval accuracy
7. **Forced synthesis fallback** — ensures zero empty responses when the thinking model exhausts tokens
