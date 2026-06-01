# GRAIL — Project Context

> Single source of truth for Claude Code sessions. For detailed documentation see `docs/`.

---

## 1. What GRAIL Is

**GRAIL** (Graph RAG with Advanced Integration and Learning) is an open-source Python library for building queryable knowledge graphs from document collections. It is a hardened fork of Microsoft GraphRAG with substantial architectural improvements.

**Author:** Benjamin Gonzalez Guerrero  
**Org:** Nirvai (Nirvana) — CAMARA CHILENA DE INTELIGENCIA ARTIFICIAL  
**Repo:** `git@github.com:CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL.git` (branch: `master`, not yet pushed)  
**License:** Apache-2.0 (recommended, not yet added)

**Attribution.** Every module header carries:
```python
"""Provided by Nirvai (Nirvana). Author: Benjamin Gonzalez Guerrero."""
```

---

## 2. Key Innovations Over MS-GraphRAG

1. **Incremental graph updates** — Custom Leiden + change-ratio scheduler (threshold 0.3) updates communities without full rebuild. See `docs/incremental_pipeline.md`.
2. **Cascade search** — Hybrid entity-gated + BM25/cosine text rescue. Solves GraphRAG's classic "fact retrieval" weakness where key details exist in text but no entity captured them. See `grail/query/cascade_search.py`.
3. **Agent search** — LLM-driven tool-calling loop that picks between local/cascade/global/document search per question. See `grail/query/agent.py`.
4. **Single-pass extraction** — Entities + relationships + descriptions + retrieval queries in one LLM call per chunk (vs Zep's 5 sequential calls per message). 11x fewer LLM calls for the same quality.
5. **Retrieval queries on entities** — Each entity stores 2-3 anticipated user questions in its embedding text. Format: `"ENTITY_NAME: description query_1; query_2; query_3"`. Dramatically improves cross-lingual and intent-based matching.
6. **Optional typed relationships** — LLM classifies edges with UPPER_SNAKE_CASE labels (REGULATES, FUNDS, etc.). Three modes: disabled (default "RELATED"), free (LLM picks), constrained (user vocabulary). See `grail/config.py:IndexingConfig.extract_relationship_types`.
7. **File-level provenance** — Every text unit retains back-pointers to source files. Citations reference real documents.
8. **Mixed-content local search** — Proportional token budgeting across entities, relationships, community reports, and text units in a single context window.
9. **Community-level selection** — `community_level: "coarsest"|"finest"|"all"|int` replaces implicit `max(level)`. Plus `min_report_size` to filter trivial communities.
10. **Honest cost tracking** — Distinguishes "complete" / "partial" / "undefined" pricing. Never reports $0.00 when pricing is unknown.

---

## 3. Architecture

```
INPUT FILES (.txt, .md, .pdf, .docx, code, ...)
    ↓  preprocess.py (PDF/DOCX → markdown, cached by mtime)
FILELOADER (chunk with provenance, document_boundary markers)
    ↓  entities_relationships.py (concurrent LLM extraction)
ENTITIES + RELATIONSHIPS (parquet + GraphML)
    ↓  leiden.py (hierarchical Leiden, DBSCAN merge)
COMMUNITIES (parquet, level-based)
    ↓  community_reports.py (LLM narrative reports, JSON correction)
COMMUNITY REPORTS (parquet + optional markdown)
    ↓  vectorstores/ (FAISS cosine default)
VECTOR INDEX (entity description embeddings)
    ↓
SEARCH (5 modes):
  local_search    → entity similarity → context → LLM
  cascade_search  → entity gate + BM25 text rescue → context → LLM
  global_search   → community reports → map-reduce → LLM
  document_search → scoped to single file → context → LLM
  agent_search    → LLM picks tools iteratively → synthesize
```

**Incremental ops:** `append`, `edit`, `delete` drive the same pipeline incrementally via `_merge_with_existing` (entities), `_prune_orphan_entities`, and `IncrementalCommunityExtractor` (change-ratio threshold → label propagation OR local Leiden re-run).

---

## 4. Current State (as of 2026-05-31)

### What Works

- **CLI:** `grail init|index|append|edit|delete|query|create-entities|config show|status`
- **Search modes:** local, cascade, global, document, agent (all with optional reranker)
- **Query tracing:** `--trace <dir>` captures full prompts/responses/context to JSON
- **Chat apps:** CLI (Textual TUI) and Web (FastAPI + React) at `grail/apps/`
- **Templates:** `configs/templates/low_cost_setup/` (10 YAML files)
- **Tests:** 160 unit tests passing
- **Benchmark framework:** `benchmarks/run_benchmark.py` (30 questions, GRAIL agent vs RAG agent)

### Default Stack

- **LLM:** `deepinfra | Qwen/Qwen3.6-35B-A3B` (thinking model)
- **Embeddings:** `deepinfra | Qwen/Qwen3-Embedding-0.6B`
- **Vector store:** FAISS (`IndexFlatIP` on L2-normalized vectors = cosine)
- **Reranker:** `deepinfra | Qwen/Qwen3-Reranker-0.6B` (optional, off by default)

### Verified on Quickstart Corpus

Project: `examples/quickstart/` (3 Chilean oncology law PDFs, SEOM benchmark)  
Indexing cost: $0.36 (Qwen3.6) or $0.04 (Gemma-4-26B)  
Benchmark result: GRAIL agent 4.80/5 vs RAG agent 4.14/5 (27 wins, 0 losses, 3 ties)

---

## 5. Search Modes Reference

| Mode | Best For | How It Works |
|------|----------|-------------|
| `local` | Named concepts, entities | Embed query → find similar entities → retrieve linked text units |
| `cascade` | Factual questions, specific details | Entity-gate + BM25/cosine text rescue → combined ranking |
| `global` | Broad/thematic questions | Community report synthesis → map-reduce if >100K tokens |
| `document` | Single-file questions | Scope retrieval to one source document |
| `agent` | Complex questions needing multiple tools | LLM picks tools (1-3 iterations), forced synthesis fallback |

**Query optimization formula (for local/cascade):** Craft queries as `[WHO does it] + [WHAT is the process] + [SPECIFIC TERMS from entity descriptions]` — matches entity embeddings 3x better than keyword-only queries.

Full details: `docs/search_modes.md`

---

## 6. Project Layout

```
GRAIL/
├── CLAUDE.md                       # this file
├── grail/                          # the package
│   ├── core.py                     # GRAIL class (index/append/edit/delete/search)
│   ├── config.py                   # Pydantic config models
│   ├── schemas.py                  # Entity, Relationship, TextUnit, SearchResult
│   ├── llm/                        # wrapper.py, embeddings.py, reranker.py, cost.py, cache.py, providers.py
│   ├── indexing/                   # loader.py, entities_relationships.py, communities.py, leiden.py, incremental_community.py, community_reports.py, summarize_descriptions.py, entity_dedup.py, preprocess.py, run_manifest.py
│   ├── query/                      # local_search.py, cascade_search.py, global_search.py, document_search.py, agent.py, retrieval.py, trace.py
│   ├── prompts/                    # loader.py + builtin/ (11 prompt modules)
│   ├── vectorstores/               # base.py, faiss.py, lancedb.py, chroma.py
│   ├── storage/                    # local.py, s3.py
│   ├── apps/                       # chat/ (FastAPI+React), cli_chat/ (Textual TUI)
│   ├── cli/                        # main.py + command modules
│   └── reporting/                  # rich_reporter.py
├── configs/templates/              # low_cost_setup/ (10 YAMLs)
├── benchmarks/                     # run_benchmark.py, rag_baseline.py, judge_prompt.py, results/
├── docs/                           # 21 documentation files
├── dev_prompts/                    # session context for future work
├── examples/quickstart/            # SEOM corpus + grail.yaml
└── tests/unit/                     # 160 tests
```

---

## 7. Configuration

Single `grail.yaml` or directory with per-module YAMLs. Key config classes in `grail/config.py`:

- `LLMConfig` — endpoint, model, concurrency (8), timeout (180s), retries (3), extra_pricing
- `EmbeddingsConfig` — endpoint, model, batch_size (1024)
- `IndexingConfig` — chunk_size (2000), entity_types, extract_relationship_types, relationship_types, max_gleanings, extraction_max_tokens (8192)
- `CommunityConfig` — community_level ("coarsest"), min_report_size (3), incremental_change_threshold (0.3)
- `SearchConfig` — local_max_tokens (32000), response_max_tokens (16384), agent_max_iterations (5)
- `RerankerConfig` — enabled (false), overfetch_factor (3.0)
- `VectorStoreConfig` — backend ("faiss"), distance_fn ("cosine")
- `PromptsConfig` — custom_paths, strict mode

Full glossary: `docs/glossary.md`

---

## 8. Prompt System

Every prompt is a Python module with `NAME`, `REQUIRED_PARAMS`, `build_messages(**params)`. Override via `prompts.custom_paths` in config.

| Prompt | Stage | Purpose |
|--------|-------|---------|
| `entity_relation` | Indexing | Entity + relationship extraction (single-pass) |
| `summarize_description` | Indexing | Consolidate duplicate entity descriptions |
| `community_report` | Indexing | Generate narrative JSON reports per community |
| `entity_dedup` | Indexing | Judge duplicate entities for merging |
| `json_correction` | Indexing | Repair malformed JSON (fallback) |
| `create_custom_entities` | Indexing | Propose entity types from corpus samples |
| `claim_extraction` | Indexing | Extract claims/covariates (optional) |
| `local_search` | Inference | Local search answer synthesis |
| `global_map` | Inference | Global search relevance scoring |
| `global_reduce` | Inference | Global search final synthesis |
| `AGENT_SYSTEM_PROMPT` | Inference | Agent tool selection (inlined, gap: should be in registry) |

Customization guide: `docs/prompt_customization.md`  
Technical reference: `docs/prompts.md`

---

## 9. Parquet Artifacts

Produced under `output/runs/<run_id>/`:

| File | Key Columns |
|------|-------------|
| `final_entities.parquet` | id, name, type, description, description_embedding, text_unit_ids, document_ids, degree |
| `final_relationships.parquet` | id, source, target, description, weight, type, text_unit_ids, document_ids, rank |
| `final_text_units.parquet` | id, text, n_tokens, document_id, entity_ids, relationship_ids, document_ids |
| `final_communities.parquet` | id, title, level, entity_ids, relationship_ids, text_unit_ids |
| `final_community_reports.parquet` | community, title, summary, findings, full_content, full_content_json, rank, level |
| `final_docs.parquet` | id, title, path, text_unit_ids, raw_content |
| `entity_relationship_graph.graphml` | NetworkX graph |
| `mapping.json` | Source-file metadata for citation |

Active run pointer: `output/current.json`  
Each run includes: `manifest.json`, `llm_calls.jsonl`, `summary.json`

---

## 10. External Benchmarks

### GraphRAG-Bench (KB mode, runnable now)

- **Paper:** arXiv:2506.05690 (ICLR 2026)
- **Dataset:** 4,072 questions (Novel + Medical), 4 difficulty levels
- **Target:** Beat MS-GraphRAG's 36.92% (global) / 47% (local) on Novel Fact Retrieval
- **Cost:** $12 testing / $58 full (Qwen3.6) / $212 official (gpt-4-turbo judge)
- **Dev prompt:** `dev_prompts/prompt_graphrag_bench.md`

### LongMemEval v1 (Memory mode, blocked on implementation)

- **Paper:** arXiv:2410.10813 (ICLR 2025)
- **Dataset:** 500 questions, chat-session memory (S tier: 40 sessions/question)
- **Target:** Beat Zep's 71.2% accuracy while being 11x cheaper on indexing
- **Cost:** $54 (gpt-4o-mini, fair comparison) / $87 (gpt-4o reader, official)
- **Blocked on:** Memory mode Phases 2-3 (`dev_prompts/prompt_grail_agentic_memory_design.md`)
- **Dev prompt:** `dev_prompts/prompt_graphrag_bench.md` (second section)

### Internal Benchmark (Chilean Oncology Laws)

- **Location:** `benchmarks/simple_benchmark/benchmark.json` (30 questions, 7 categories)
- **Result:** GRAIL agent 4.80/5 vs RAG agent 4.14/5
- **Dev prompt:** `dev_prompts/prompt_grail_benchmark.md`

---

## 11. Known Gaps

1. **`AGENT_SYSTEM_PROMPT` inlined** — Extract to `grail/prompts/builtin/agent.py` for override via PromptRegistry.
2. **DocumentSearch reuses `local_search` prompt** — Needs dedicated prompt.
3. **No tests for incremental ops or AgentSearch/DocumentSearch** — Cover `append_extract`, `edit_extract`, `delete_extract` and the agent tool-call loop.
4. **Relationship ranking signals unused** — `rank` field (source_degree + target_degree) exists in parquet but local search doesn't leverage it.
5. **`grail propose-entities` not built** — Design exists (clusterer + proposal YAML); needs implementation.
6. **Benchmark CLI command pending** — Runner exists at `benchmarks/run_benchmark.py`; needs `grail benchmark` integration.
7. **Memory mode not started** — Full design at `dev_prompts/prompt_grail_agentic_memory_design.md`.

---

## 12. Conventions

- **Naming:** snake_case modules, PascalCase classes, no `Nirvana` prefix
- **Async by default:** All I/O paths are `async`; sync facades wrap `asyncio.run`
- **Optional deps:** S3, vision, reranking behind `pyproject.toml` extras
- **Endpoint|model split:** Config uses `endpoint:` and `model:` separately; pipe shorthand valid in code but not config/docs
- **Comments:** Only when the WHY is non-obvious
- **Entity types:** Always UPPER_SNAKE_CASE; PERSON + ORGANIZATION mandatory
- **Testing:** `uv venv` + `uv pip install -e .` + `uv run pytest`
- **Do not push without explicit user confirmation**

---

## 13. Dev Prompts (Context for Future Sessions)

| File | Topic |
|------|-------|
| `dev_prompts/prompt_grail_benchmark.md` | Agent logic, WHO+WHAT formula, benchmark methodology, results |
| `dev_prompts/prompt_graphrag_bench.md` | GraphRAG-Bench + LongMemEval integration plans, cost estimates, model requirements |
| `dev_prompts/prompt_grail_agentic_memory_design.md` | Memory mode architecture, SDK design, implementation phases |
| `dev_prompts/prompt_grail_ui_dev.md` | Chat UI development context |

---

## 14. Quick Reference

| What | Where |
|------|-------|
| Main class | `grail/core.py:GRAIL` |
| Config | `grail/config.py` + `docs/glossary.md` |
| All prompts | `grail/prompts/builtin/` |
| Search modes | `docs/search_modes.md` |
| Incremental pipeline | `docs/incremental_pipeline.md` |
| Prompt customization | `docs/prompt_customization.md` |
| Cost tracking | `grail/llm/cost.py` |
| Quickstart corpus | `examples/quickstart/` |
| Benchmark runner | `benchmarks/run_benchmark.py` |
| CLI chat | `grail/apps/cli_chat/app.py` |
| Web chat | `grail/apps/chat/server.py` |
