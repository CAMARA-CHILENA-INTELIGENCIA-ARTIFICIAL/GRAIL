# GRAIL — Project Brief & Migration Roadmap

> **Read this file first.** It is the single source of truth for what GRAIL is, where it came from, how its pipeline works, what must be stripped before open-sourcing, and the phased plan to get there. Code documentation lives next to the code; this file documents *intent*, *boundaries*, and *roadmap*.

---

## 1. What GRAIL is

**GRAIL** (Graph RAG with Advanced Integration and Learning) is an open-source Python library for building queryable knowledge graphs from heterogeneous source files (text, PDF, code, Excel, images via vision models, etc.). It is a hardened, production-tested fork of Microsoft GraphRAG with several substantial improvements:

1. **Incremental graph updates.** A custom Leiden + change-ratio scheduler updates community structure when documents are added / edited / deleted, without rebuilding the entire graph.
2. **File-level provenance.** Every text unit retains a back-pointer to the originating file, so answers cite real sources rather than opaque chunk IDs.
3. **Document-aware edit/delete.** The dataframe layer tracks original files instead of raw chunks, so users can edit or remove specific source files without losing the rest of the graph.
4. **Multi-modal extraction.** Excel, vision, and structured-format sources are extracted into entities/relationships rather than embedded multimodally — making the graph fully searchable with standard text-similarity machinery.
5. **Robust prompting + AI-driven recovery.** JSON repair, custom entity-type discovery, and structured-output prompts are designed to work across a wide model family (GPT-4o-mini, Llama-3.x, Qwen3, etc.) — not just one vendor.
6. **Mixed-content local search.** Local search composes entity tables, relationship tables, community summaries, and raw text units into a single ranked context window with proportional token budgeting.
7. **Hierarchical configuration.** Per-module config files (planned) instead of code-embedded defaults, each accompanied by a markdown explainer.

GRAIL is the open-source release of an "expert agent" framework built inside **Nirvai (Nirvana)** — a closed-source platform that creates personalized agents with knowledge bases, tool integrations, and channel connectors (Telegram, WhatsApp, Slack, Teams, Discord, web, API). The GraphRAG component proved too powerful for Nirvai's typical use case, so it is being released for the broader community.

**Author / attribution.** Files originally authored inside Nirvai should carry, in the module header:

```python
"""
Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
```

Do not rename the author or remove the attribution — only the "nirvana" identifiers in code paths and string defaults should change. Branding (class names, default titles, prompt placeholders) becomes **GRAIL**.

---

## 2. Provenance & repository layout

The library originates here (proprietary monorepo, do not commit references to this path in public-facing docs):

```
/Users/bgg/Documents/repos/nirvana/nirvanav0/backend_ml_cpu/agents/nirvana_agents/utilities/graphrag/
```

A verbatim, **gitignored** snapshot of that tree is mirrored into `_legacy_source/graphrag/` so future Claude Code sessions are self-contained. Delete `_legacy_source/` once the migration is complete and verified.

Public-facing target layout (proposed; subject to refinement in subsequent sessions):

```
GRAIL/
├── CLAUDE.md                     # this file
├── README.md                     # user-facing, written late
├── LICENSE                       # to be decided (Apache-2.0 recommended)
├── pyproject.toml                # packaging, deps, entry points
├── .gitignore
├── .env.example
├── grail/                        # the package
│   ├── __init__.py
│   ├── core.py                   # the GRAIL class (formerly GRAIL.py)
│   ├── config/                   # YAML configs + .md explainers per module
│   ├── schemas.py                # Entity, Relationship, ...
│   ├── llm/
│   │   ├── wrapper.py            # OpenAI-compat async LLM wrapper (replaces achain_nirvana)
│   │   ├── embeddings.py
│   │   └── reranker.py           # optional, future
│   ├── indexing/
│   │   ├── loader.py
│   │   ├── entities_relationships.py
│   │   ├── communities.py
│   │   ├── incremental_community.py
│   │   ├── community_reports.py
│   │   ├── summarize_descriptions.py
│   │   ├── leiden.py
│   │   ├── stable_lcc.py
│   │   ├── prompts.py
│   │   └── defaults.py
│   ├── query/
│   │   ├── retrieval.py
│   │   ├── local_search.py
│   │   ├── local_search_mixed_content.py
│   │   ├── global_search.py
│   │   ├── local_context.py
│   │   ├── global_community_context.py
│   │   ├── prompts/
│   │   ├── indexer_adapters.py
│   │   └── dfs.py
│   ├── vectorstores/
│   │   ├── base.py               # ABC moved out of schemas.py
│   │   ├── lancedb.py
│   │   ├── chroma.py             # alternative backend
│   │   └── faiss.py              # in-memory backend
│   ├── storage/
│   │   ├── local.py              # default backend
│   │   └── s3.py                 # optional
│   ├── reporting/
│   │   └── rich_reporter.py
│   └── cli/
│       ├── __main__.py
│       ├── init.py               # `grail init`
│       ├── index.py              # `grail index`
│       ├── append.py             # `grail append`
│       ├── edit.py               # `grail edit`
│       ├── delete.py             # `grail delete`
│       ├── query.py              # `grail query`
│       └── benchmark.py          # `grail benchmark`  (last to land)
├── examples/
│   ├── quickstart/
│   ├── incremental/
│   └── multimodal/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/                 # small sample corpora
├── docs/                         # local code-companion docs; docusaurus lives in a separate repo
└── _legacy_source/               # gitignored snapshot, delete when migration is done
    └── graphrag/                 # the original Nirvai tree
```

**Git status.** Repo is initialized on branch `master`, remote `origin = git@github.com:CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL.git`. Nothing has been pushed. Do **not** push without explicit user confirmation; once the first migration milestone lands, ask the user before running `git push -u origin master`. The init_context.md instructed `master`; if you want `main`, run `git branch -M main` first.

---

## 3. Pipeline mental model

```
┌─────────────┐    chunk + provenance     ┌──────────────────────┐
│  Source     │  ───────────────────────► │ partial_text_units   │
│  files / S3 │                            │ final_docs           │
└─────────────┘                            └──────────────────────┘
                                                       │
                                                       ▼  LLM extracts
                                           ┌──────────────────────┐
                                           │  ENTITY_RELATION     │
                                           │  prompt (concurrent) │
                                           └──────────────────────┘
                                                       │
                                                       ▼
                                           ┌──────────────────────┐
                                           │ final_entities       │
                                           │ final_relationships  │
                                           │ final_text_units     │
                                           │ entity_relationship  │
                                           │   _graph.graphml     │
                                           └──────────────────────┘
                                                       │
                                                       ▼  hierarchical Leiden
                                           ┌──────────────────────┐
                                           │ final_communities    │
                                           │ final_nodes (lvl)    │
                                           └──────────────────────┘
                                                       │
                                                       ▼  LLM summarizes
                                           ┌──────────────────────┐
                                           │ final_community_     │
                                           │   reports (JSON)     │
                                           └──────────────────────┘
                                                       │
                                                       ▼
                                       ┌──────────────────────────────┐
                                       │ LanceDB: entity description  │
                                       │   embeddings, indexed by ID  │
                                       └──────────────────────────────┘

QUERY paths:
  • local_search   →  map query → entities (vector sim) → candidate rels/units → context → LLM
  • global_search  →  map query → community reports → map-reduce (if >100k tok) → LLM
```

Incremental updates (`append`, `edit`, `delete`) operate on the same artifacts, with `IncrementalCommunityExtractor` deciding label propagation vs. local Leiden re-run based on change ratio (default threshold 0.3).

---

## 4. Per-module reference (verified against legacy snapshot)

Risk legend: **L** = drop-in / standalone, **M** = needs targeted edits, **H** = heavy coupling to proprietary infra. All paths below are relative to `_legacy_source/graphrag/`.

### 4.1 Top-level

| File | Size | Role | Risk | Notes |
|---|---|---|---|---|
| `GRAIL.py` | 55 KB | Main orchestrator class with `acreate / aappend / aedit / adelete / asearch / anirvana_edit / acreate_entites / package_grail`; modes `INDEX / CHANGE / QUERY` | **H** | S3 mandatory; `/tmp/test_grail` hardcoded; `custom_ai_path` S3 prefix; calls `achain_nirvana` for custom-entity generation; uses `vendor|model` strings (e.g. `"together|meta-llama/Llama-3.3-70B-Instruct-Turbo"`). Becomes `grail/core.py`. |
| `GraphRag.py` | 34 KB | Legacy entry that **shells out** to the Microsoft `graphrag` CLI via subprocess; predates GRAIL | **H** | Drop entirely from the open-source release — preserved in `_legacy_source/` for reference only. |
| `AdvancedRAG.py` | 14 KB | Lightweight source-mapping RAG (no graph); CallAgent HTTP dependency for summary/keyword extraction | **M** | Could become an `AdvancedRAG` lite mode later; not in the first migration milestone. |
| `advancedrag_schema.py` | 4.7 KB | `AdvancedRAGSource`, `AdvancedRAGMapping` pydantic models | **L** | Portable. |
| `advancedrag_extraction.py` | 8.6 KB | Batch summary/keyword extraction via internal HTTP service | **M** | Replace HTTP with direct local LLM calls. |
| `create_entities.py` | 5.5 KB | Standalone `PROMPT_CREATE_CUSTOM_ENTITIES` template | **M** | Duplicated in `indexing/prompts.py` as `CREATE_CUSTOM_ENTITIES`; pick one. |
| `schemas.py` | 18 KB | Core dataclasses: `Identified`, `Named`, `Entity`, `Relationship`, `Covariate`, `TextUnit`; ABCs: `BaseSearch`, `GlobalContextBuilder`, `LocalContextBuilder`, `SearchResult` | **L** | Move `BaseVectorStore` and `VectorStoreDocument` out into `vectorstores/base.py`. |
| `tools.py` | 32 KB | `NirvanaAgileGraphSearch`, `NirvanaGraphSearch` BaseTool wrappers for Nirvai agents | **H** | **Drop** — Nirvai-specific agent glue. Reimagine as generic LangChain/LlamaIndex adapters in a future module. |
| `rich_reporter.py` | 6 KB | `RichProgressReporter` (rich-library wrapper) | **L** | Rename string `"Nirvana BGG GraphRag"` → `"GRAIL"`. |
| `default_settings_graphrag.yaml` | 4.7 KB | Reference YAML for the upstream Microsoft graphrag CLI | **L** | Kept as inspiration for our own per-module YAML config. |

### 4.2 `indexing/`

| File | Size | Role | Risk |
|---|---|---|---|
| `loader.py` | 43 KB | `FileLoader`: discover, chunk (`TokenTextSplitter`), produce `partial_text_units.parquet` + `final_docs.parquet`; mixed-document text units with provenance tracking; S3 download/upload | **L** for chunking; **M** for S3 coupling — needs a `StorageBackend` abstraction |
| `entities_relationships.py` | 55 KB | `EntityRelationshipExtractor`: prompt formatting, concurrent LLM calls, regex parsing of tuples, entity/relationship dedup by uppercase title and `(source, target)`, GraphML export, incremental append path | **M** — parser tightly coupled to delimiter format; validate against new model outputs |
| `prompts.py` | 38 KB | All extraction/summarization/report prompts. **Every** template uses `{system_header_nirvana}`, `{system_end_nirvana}`, `{user_header_nirvana}`, `{user_end_nirvana}`, `{assistant_header_nirvana}` as message-role wrappers | **M** — strip Nirvai tokens and emit OpenAI-style `messages` list instead of a single `prompt` string |
| `incremental_community.py` | 34 KB | `IncrementalCommunityExtractor`: change-ratio scheduler (threshold 0.3) → label propagation OR localized Leiden re-run on the affected subgraph; merges new communities by overlap | **L** — this is one of the **flagship innovations**, keep semantics identical |
| `community_reports.py` | 22 KB | `CommunityReportGenerator`: build CSV-style context per community, call LLM, parse JSON, 3-pass JSON correction with an LLM fallback (`JSON_CORRECTION_PROMPT`) | **M** — direct `achain_nirvana` call inside `_correct_json` |
| `summarize_descriptions.py` | 5 KB | Entity/relationship description summarizer batches via `LLMAPIWrapper.call_llm_concurrently` | **L** |
| `communities.py` | 8 KB | Orchestrator: load graph → run Leiden → update parquet → generate reports | **L** |
| `leiden.py` | 7 KB | Hierarchical Leiden via `graspologic`, embedding-based small-community merge (DBSCAN on centroids, eps=0.5) | **L** — open-source-friendly already |
| `stable_lcc.py` | 2.4 KB | `stable_largest_connected_component`, `normalize_node_names` (uppercase, HTML unescape, strip) | **L** |
| `llm_wrapper.py` | 5 KB | **CRITICAL.** `LLMAPIWrapper` wraps `achain_nirvana` with semaphore (15 concurrent), tenacity retry, 180s timeout, rate-limit sleep (30s on HTTP 429), Qwen3 prefix injection | **H** — primary migration target; reimplement on top of `openai.AsyncOpenAI` |
| `embedding_wrapper.py` | 4.5 KB | `EmbeddingAPIWrapper` already on `openai.AsyncOpenAI` against DeepInfra | **L** — pool the client, parameterize provider |
| `defaults.py` | 1.7 KB | `LOADER_CONFIG`, `LLM_CONFIG`, `EMBEDDING_CONFIG`, `SUMMARIZER_CONFIG`, `ER_CONFIG`, `CR_CONFIG`, `COMMUNITY_CONFIG`. Default models: `deepinfra|Qwen/Qwen3-32B`, `intfloat/multilingual-e5-large` | **L** — promote to YAML configs under `grail/config/` |

### 4.3 `query/`

| File | Size | Role | Risk |
|---|---|---|---|
| `retrieval.py` | 32 KB | Low-level: entity/relationship/covariate/community ranking, filtering, dataframe assembly, `map_query_to_entities`, `build_community_context`, `build_text_unit_context` | **L** — depends on `embed_custom_openai` from Nirvai utils; replace with our embeddings client |
| `local_search.py` | 5 KB | Thin orchestrator around context builder + `achain_nirvana` for `LOCAL_SEARCH_SYSTEM_PROMPT` | **M** — replace LLM call |
| `local_search_mixed_content.py` | 21 KB | **The active local search.** `LocalSearchMixedContext.build_context()` composes conversation history + community reports + entity/relationship/covariate tables + text units with proportional token budgeting; returns `(context_text, context_data_dataframes)` | **L** — no LLM calls inside; keep as-is |
| `global_search.py` | 16 KB | Two paths: direct reduce (<100k tok) via `achain_nirvana(REDUCE_SYSTEM_PROMPT)`; map-reduce (≥100k tok) via external `ReduceMap` utility from `agents.nirvana_agents.utilities.reduce_map` | **H** — replace `achain_nirvana` and reimplement map-reduce in-house (proprietary `ReduceMap` cannot be used) |
| `local_context.py` | 12 KB | `build_entity_context`, `build_relationship_context` (in-network priority + out-network mutual scoring), `build_covariates_context` | **L** |
| `global_community_context.py` | 3.5 KB | History + community report context builder | **L** |
| `local_system_prompt.py` | 1.2 KB | `LOCAL_SEARCH_SYSTEM_PROMPT` with Nirvai role tokens | **M** — strip tokens |
| `global_reduce_prompt.py` | 5 KB | `MAP_SYSTEM_PROMPT` (extracts `{"points":[{"description","score"}]}`) and `REDUCE_SYSTEM_PROMPT` (synthesizes final answer) | **M** — strip tokens |
| `indexer_adapters.py` | 4.5 KB | Parquet dataframe → object adapters: `read_indexer_entities`, `read_indexer_relationships`, `read_indexer_reports`, `read_indexer_covariates`, `read_indexer_text_units` | **L** |
| `dfs.py` | 19 KB | Low-level deserializers: `to_str/to_int/to_list/...`, `read_entities`, `read_relationships`, `read_communities`, `read_community_reports`, `read_text_units`, `read_documents`, `store_entity_semantic_embeddings` | **L** — one stray `print("DEBUGGING2 …")` to remove |

### 4.4 `vectorstores/`

| File | Size | Role | Risk |
|---|---|---|---|
| `lancedb.py` | 4 KB | `LanceDBVectorStore` implementing `BaseVectorStore`: PyArrow schema `id|text|vector|attributes(json str)`; Euclidean distance; ID prefilter via `where(prefilter=True)` | **L** — keep, but elevate `BaseVectorStore` to an explicit `abc.ABC` with `@abstractmethod` decorators and add `ChromaDB` + `FAISS` backends |

### 4.5 `testing/`

| File | Role | Reusability |
|---|---|---|
| `test_create_grail.py` | Unit-style: load local `ANOLE_short.txt`, build graphrag, extract entities/relationships, extract communities | **HIGH** — refactor into `tests/integration/test_end_to_end.py` and use as README quickstart |
| `test_create_agent_grail.py` | E2E with GRAIL class on S3-hosted CV dataset | **MEDIUM** — preserved as architectural reference; rewrite without S3 |
| `test_increment_grail.py` | Append a new file to an existing graph, run incremental Leiden | **MEDIUM** — re-template with local file |
| `test_query_grail.py` | Run `asearch(query, search_type="global")` on a pre-indexed agent | **LOW** — needs prebuilt fixture |
| `test_edit_grail.py`, `test_delete_grail.py` | Direct loader-level batch edit/delete + downstream re-extraction | **MEDIUM** — depend on doc IDs; parameterize |
| `test_*_agent_grail.py` (append/edit/delete) | Thin `grail.anirvana_edit(...)` wrappers | **LOW** — drop; supersede with proper integration tests |
| `gpt4mini_results`, `llama_32_11b_results` | Raw log-style entity/relationship extraction outputs for two models on the CV corpus | Useful as **benchmark baselines** — convert to JSON and keep under `examples/benchmarks/baselines/` |

---

## 5. Data schemas (must remain stable across migration)

These are the load-bearing structures every layer depends on. Migration must not silently change column names or types.

### 5.1 Python schema objects (`schemas.py`)

```python
Identified         id, short_id
Named(Identified)  + title
Entity(Named)      + type, description, description_embedding, name_embedding,
                     graph_embedding, community_ids, text_unit_ids, document_ids,
                     rank, attributes
Relationship       id, short_id, source, target, weight, description,
                     description_embedding, text_unit_ids, document_ids, attributes
Covariate          id, short_id, subject_id, subject_type, covariate_type,
                     text_unit_ids, document_ids, attributes
TextUnit           id, short_id, text, text_embedding, entity_ids, relationship_ids,
                     covariate_ids (dict), n_tokens, document_ids, attributes
SearchResult       response, context_data (dict[str, DataFrame]), context_text,
                     completion_time, llm_calls
GlobalSearchResult + map_responses, reduce_context_data, reduce_context_text
```

### 5.2 Parquet artifacts (produced under `<root_dir>/<output_folder>/`)

| File | Produced by | Key columns |
|---|---|---|
| `final_docs.parquet` | `FileLoader` | `id, text_unit_ids, raw_content, title, path, mapping` |
| `partial_text_units.parquet` | `FileLoader` | `id, text, n_tokens, document_id, document_ids` |
| `final_text_units.parquet` | `EntityRelationshipExtractor` | + `entity_ids, relationship_ids` |
| `final_entities.parquet` | `EntityRelationshipExtractor` | `id, name, type, description, human_readable_id, graph_embedding, text_unit_ids, description_embedding, degree` |
| `final_relationships.parquet` | `EntityRelationshipExtractor` | `id, source, target, description, weight, text_unit_ids, human_readable_id, source_degree, target_degree, rank` |
| `final_nodes.parquet` | `CommunityExtractor` | per-level node assignments (community, level, degree, title) |
| `final_communities.parquet` | `CommunityExtractor` | community membership |
| `final_community_reports.parquet` | `CommunityReportGenerator` | JSON-encoded reports + `rank` |
| `entity_relationship_graph.graphml` | `EntityRelationshipExtractor` | NetworkX graph |
| `mapping.json` | `FileLoader` | source-file → metadata bridge (used by search to cite sources) |

### 5.3 LanceDB table

PyArrow schema: `id (string), text (string), vector (list<float64>), attributes (string, JSON-serialized)`. Entity description embeddings only. Distance metric: Euclidean. Score normalized as `1 - abs(_distance)`.

### 5.4 LLM identifier convention (post-refactor)

**Endpoint and model are separate first-class fields.** GRAIL speaks one
protocol (OpenAI's Chat Completions / Embeddings API) and treats every
deployment of that protocol — OpenAI Inc., vLLM, SGLang, Ollama, your private
proxy — as an interchangeable named endpoint. Examples:

```yaml
llm:
  endpoint: openai            # references endpoints.<openai> for base_url + key env
  model: gpt-4o-mini          # whatever model name the endpoint accepts
```

A pipe-shorthand `endpoint|model` is still recognised in code paths (e.g.
`await llm.execute(messages=[...], model="vllm|my-llama")`) for terse one-liners,
but configs and docs **must** lead with the explicit split form. The pipe is a
convenience, not the contract.

The legacy code used a single `"provider|model"` string everywhere; the port
keeps that working as a power-user shortcut and as the canonical "model id" in
the cost ledger (`UsageRecord.model = "openai|gpt-4o-mini"`).

---

## 6. Proprietary boundaries — what MUST be stripped

Inventory (with origin) of every symbol that ties the codebase to Nirvai infrastructure. Each must be replaced or removed before the first public commit.

### 6.1 Imports to eliminate (verbatim, from legacy)

```python
# LLM chain executor — replaced by grail/llm/wrapper.py
from agents.nirvana_agents.chains.base_nirvana_chains import achain_nirvana, openai_servers
# Async progress / token-accounting callback manager — replaced by a slim local class
from agents.nirvana_agents.agents.callback_manager import AsyncCallbackManager
# Generic utils — replace each call site explicitly
from agents.nirvana_agents.utils import (
    generate_guid, get_data_type, tiktoken_len, unzip_file, list_files,
    TokenTextSplitter, embed_custom_openai, calculate_credits, format_replace,
)
# Tool framework
from agents.nirvana_agents.schemas import BaseTool
# Internal model registry & pricing
from agents.nirvana_agents.agents.clash.constants import nirvana_models, comissions
# External map-reduce helper used in global_search.py for >100k token contexts
from agents.nirvana_agents.utilities.reduce_map.reduce_map import ReduceMap
# Auth helper used in advancedrag_extraction.py
from utils.common import encrypt_message
```

Call sites (non-exhaustive, anchored to the legacy snapshot):
- `_legacy_source/graphrag/indexing/llm_wrapper.py` lines 12, 44, 53
- `_legacy_source/graphrag/indexing/community_reports.py` lines 6, 255
- `_legacy_source/graphrag/GRAIL.py` lines 35–69 (block of `from agents.nirvana_agents…` imports), 427 (`await achain_nirvana(...)`)
- `_legacy_source/graphrag/query/local_search.py` lines 11–14, 101
- `_legacy_source/graphrag/query/global_search.py` lines 14–22, 143–180
- `_legacy_source/graphrag/tools.py` lines 13–20 (drop the entire file)

### 6.2 Prompt placeholders to scrub

Every prompt template wraps role markers in Nirvai-specific placeholder tokens:

```
{system_header_nirvana}   {system_end_nirvana}
{user_header_nirvana}     {user_end_nirvana}
{assistant_header_nirvana}
```

Files containing these: `indexing/prompts.py` (≈18 occurrences across `ENTITY_RELATION`, `CLAIM_EXTRACTION`, `SUMMARIZE_DESCRIPTION`, `COMMUNITY_REPORT`, `CREATE_CUSTOM_ENTITIES`, `JSON_CORRECTION_PROMPT`); `query/local_system_prompt.py`; `query/global_reduce_prompt.py`; `create_entities.py`.

**Replacement strategy.** Move from a single `prompt` string to an OpenAI-style `messages = [{"role": "system", "content": ...}, {"role": "user", "content": ...}, ...]` list. The Nirvai tokens map directly to chat roles, so the migration is mechanical. After the move, the placeholders disappear entirely.

### 6.3 Branding to rename

| Old | New |
|---|---|
| `class NirvanaGraphRag` (in `GraphRag.py`) | drop the file |
| `class NirvanaAgileGraphSearch`, `class NirvanaGraphSearch` (in `tools.py`) | drop the file |
| `async def anirvana_edit(...)` (in `GRAIL.py`) | `async def aedit_index(...)` or split into `append`/`edit`/`delete` |
| `custom_ai_title: str = "Custom AI Nirvana"` | `index_title: str = "GRAIL Knowledge Base"` |
| `RichProgressReporter("Nirvana BGG GraphRag")` | `RichProgressReporter("GRAIL")` |
| Hard-coded email `users@nirvana-ai.com` in `tools.py:477` | drop with the file |
| Stray debug print `"DEBUGGING2 : document_ids_col"` in `query/dfs.py:505` | remove |

### 6.4 Storage assumptions to fix

- Hardcoded `root_dir = "/tmp/test_grail"` in `GRAIL.py:93` — make it config-driven, default `~/.grail/projects/<project_name>`.
- Hardcoded `custom_ai_path = "dev/tmp/test_files"` (S3 prefix) — abstract storage as a `StorageBackend` protocol with `LocalStorage` default and `S3Storage` optional.
- Query mode currently **requires** S3 (downloads `output.zip` and `mapping.json` from `f"{custom_ai_path}{loc}.zip"`). Local-mode users must be able to point at a directory and have it work.
- Mandatory env vars to remove from defaults: `AWS_BUCKET_NAME`, `AWS_REGION_NAME`, `API_HOST`, `EXTERNAL_USAGE_PASSWORD`.
- `LANCEDB_URI = f"{self.root_dir}/lancedb"` (`GRAIL.py:309`) — fine, but make the vectorstore backend pluggable.

---

## 7. Migration roadmap (phased)

Each phase ends in a green test suite and a commit. Do **not** combine phases; the Phase 1 LLM-wrapper swap is the riskiest single change and must be validated in isolation.

### Phase 0 — Scaffolding (1 session)
- Create `grail/` package skeleton matching §2.
- Add `pyproject.toml` with deps: `openai`, `tenacity`, `pyarrow`, `pandas`, `lancedb`, `networkx`, `graspologic`, `rich`, `tiktoken`, `pydantic>=2`, `pyyaml`, `typer` (for CLI), `httpx`.
- Copy `schemas.py`, `rich_reporter.py`, `query/dfs.py`, `query/indexer_adapters.py`, `query/local_context.py`, `query/global_community_context.py`, `query/local_search_mixed_content.py`, `vectorstores/lancedb.py`, `indexing/stable_lcc.py`, `indexing/leiden.py` — all Risk-L files. Re-anchor imports.
- Add minimal `tests/unit/` exercising schemas + adapters.

### Phase 1 — LLM wrapper (1 session, CRITICAL)
- Implement `grail/llm/wrapper.py`. Public surface mirrors `LLMAPIWrapper`:
  - `LLMClient` pydantic model: provider, model, api_key_env, base_url, timeout, semaphore_size, retry, sleep_on_rate_limit.
  - `async execute(messages, *, model=None, max_tokens, temperature, top_p=None, response_format=None, stop=None)` returning `str`.
  - `async execute_concurrently(call_specs: list[dict])` returning `list[str]`.
  - Tenacity retry decorator, semaphore, 30s sleep on HTTP 429, structured logging through `RichProgressReporter`.
  - Provider registry maps `"openai"`, `"deepinfra"`, `"together"`, `"anthropic"`, `"groq"`, `"ollama"`, `"local"` → `(api_key_env, base_url)`.
  - Optional prompt-caching support when the provider is Anthropic (use `cache_control` blocks).
- Implement `grail/llm/embeddings.py`: thin port of `EmbeddingAPIWrapper` with pooled clients.
- Smart caching: cache-key on `(model, hash(messages), temperature, max_tokens, response_format)`. Disk-backed JSON cache under `<root_dir>/cache/` keyed by hash; opt-in via config. **Session** in the legacy code is essentially "a single user-request grouping of calls"; preserve it as an optional `session_id` argument and store cache entries grouped by session for inspection/debugging.
- Port `indexing/llm_wrapper.py` + `indexing/embedding_wrapper.py` to call the new `LLMClient` instead of `achain_nirvana`.

### Phase 2 — Prompts (1 session)
- Convert every prompt from single-string + Nirvai tokens to a `messages` factory: `def build_extraction_messages(...) -> list[dict]`.
- Validate parser regex (entity/relationship tuple delimiters in `indexing/entities_relationships.py`) against fresh outputs from a small open-source model (e.g., Qwen2.5-7B-Instruct).
- Add a smoke test that runs entity extraction on a 1-paragraph fixture and asserts ≥1 entity returned.

### Phase 3 — Storage abstraction (1 session)
- `grail/storage/base.py` with `StorageBackend(Protocol)`: `read(key) -> bytes`, `write(key, bytes)`, `list(prefix)`, `delete(key)`, `exists(key)`.
- `LocalStorage` (default) — pure filesystem.
- `S3Storage` (optional) — `boto3` / `aioboto3`, only if `[s3]` extra installed.
- Refactor `FileLoader` to use the abstraction. Remove the `/tmp/custom_ai/<id>/input/` regex stripping logic (`loader.py:21`) once paths are no longer mangled.
- Remove forced S3 downloads from query mode (`GRAIL.py:271–303`). Loading a project should mean: point at `root_dir`, expect parquets + lancedb under known sub-paths, done.

### Phase 4 — Core class (1 session)
- Port `GRAIL.py` → `grail/core.py`:
  - Replace `achain_nirvana` call (entity-type discovery) with `LLMClient.execute`.
  - Replace `AsyncCallbackManager` with a slim local `CostTracker` (token counts + simple per-model pricing dict, optional).
  - Split `anirvana_edit` into explicit `append`, `edit`, `delete` async methods.
  - Drop `package_grail` (S3 upload) or move to `grail/storage/s3.py`.
- Port `query/local_search.py` and `query/global_search.py` (LLM calls → wrapper).
- Reimplement the >100k-token map-reduce path of `global_search.py` in-house (use `LLMClient.execute_concurrently` over chunked context; aggregate via `MAP_SYSTEM_PROMPT`, reduce via `REDUCE_SYSTEM_PROMPT`). Do not depend on the proprietary `ReduceMap`.

### Phase 5 — Config (1 session)
- For each module, create `grail/config/<module>.yaml` with the defaults from `indexing/defaults.py` and inline comments.
- Each YAML pairs with `grail/config/<module>.md` explaining every key (the user wants per-module markdown docs).
- Single top-level `grail.yaml` references the per-module files and lets users override paths, models, concurrency.
- Add `.env.example` listing all supported env vars (`OPENAI_API_KEY`, `DEEPINFRA_API_KEY`, `ANTHROPIC_API_KEY`, `TOGETHER_API_KEY`, `GROQ_API_KEY`, etc.) — none mandatory.

### Phase 6 — CLI (1 session)
Use `typer`. Commands:

```
grail init <project>             # scaffold project dir, config, sample .env
grail index <project>            # full pipeline on the input/ folder
grail append <project> <files>   # add new files, incremental update
grail edit <project> <files>     # replace existing files
grail delete <project> <files>   # remove files, prune entities
grail query <project> "<q>"      # --mode local|global, --format text|json
grail create-entities <project>  # derive custom entity types from corpus
grail config show <project>      # dump effective merged config
grail status <project>           # show artifact freshness, last update
```

### Phase 7 — Optional re-ranker (1 session)
- `grail/llm/reranker.py`: provider-agnostic interface, optional dependency. Initial impl: cross-encoder via `sentence-transformers/ms-marco-MiniLM-L-12-v2` or Cohere Rerank API.
- Plug into `LocalSearchMixedContext` after the candidate context is built and before the token-budget cut.

### Phase 8 — Tests + benchmark (final session)
- Refactor `testing/test_create_grail.py` into `tests/integration/test_end_to_end.py` with a small local fixture corpus.
- `grail benchmark` CLI: user supplies a `dataset.yaml` listing `(query, expected_entities, expected_documents)`; runs index + query, emits a Rich-formatted markdown report with timings, token spend, recall@k, and a per-model comparison (Qwen3, Llama 3.x, GPT-4o-mini, etc.). Convert `gpt4mini_results` and `llama_32_11b_results` into baseline JSON for this harness.

---

## 8. Conventions

- **Naming.** Snake_case for modules, PascalCase for classes, no `Nirvana` prefix anywhere. Methods drop the `a`-prefix-for-async convention if it survives; standard Python is `async def`.
- **Headers.** Every module starts with the Nirvai attribution docstring (see §1). Do not embed marketing strings inside runtime defaults.
- **Comments.** Inline comments only where the *why* is non-obvious. The wider documentation lives in a sibling Docusaurus repo (out of scope here); the per-module `.md` files under `grail/config/` are the in-repo home for usage notes.
- **Async by default.** All I/O paths are `async`. Provide sync façades (`grail.core.GRAIL.index(...)`) that wrap `asyncio.run` for CLI ergonomics.
- **Optional dependencies.** S3, vision, Anthropic prompt caching, reranking — all behind `pyproject.toml` extras (`pip install grail[s3,vision,rerank]`).

---

## 9. Important warnings & gotchas

1. **Parser format is fragile.** `EntityRelationshipExtractor` parses LLM output with strict delimiters (`("entity"<|>...)`, `##`-separated records). Any model that ignores the schema will silently emit fewer entities. The legacy code already includes JSON-correction passes for community reports; the *entity* parser does not — add a fallback before relying on small open models.
2. **`embed_custom_openai` is called from `retrieval.py`** to embed the query at search time. This must be ported to the new embedding client. Mismatched embedding models between indexing and querying will silently degrade recall — store the embedding model name in `mapping.json` and refuse to load if it differs.
3. **Two `CREATE_CUSTOM_ENTITIES` prompts exist** — one in `create_entities.py`, one in `indexing/prompts.py`. The latter is the active version. Delete the duplicate during migration.
4. **`achain_nirvana` is *not* a single function call** — it is a session-bound chain that handles cost tracking, streaming callbacks, and tool naming. The slim `LLMClient` replacement does not need all of this, but it does need a hook so callers can record (a) token usage per logical operation and (b) a "tool name" for log breadcrumbs. Design `LLMClient.execute(..., tag="entity_extraction")` from the start.
5. **Mode coupling.** `GRAIL` currently runs in three modes (`INDEX`, `CHANGE`, `QUERY`). `CHANGE` assumes a prior `INDEX` run completed and S3 has the output zip. Migrate to a single class that lazy-loads artifacts from `root_dir` and exposes individual operations.
6. **Endpoint and model are split.** Configs use `endpoint:` and `model:` separately. The pipe shorthand (`endpoint|model`) stays valid in code paths but never in config or user-facing docs. See §5.4.
7. **LanceDB lock files.** When run in parallel test processes against the same directory, LanceDB will throw on concurrent writes. Tests must use isolated temp dirs.
8. **`graspologic` versions.** `hierarchical_leiden` API has changed across versions. Pin in `pyproject.toml`.
9. **Mapping.json is the citation root.** Every search response cites sources by resolving `text_unit.document_ids → mapping[doc_id].original_path`. If this file is regenerated incorrectly during edit/delete, citations break — add a schema-validation test.
10. **Do not push to remote without confirmation.** The repo is initialized on `master` (per the user's instruction in the body of the prompt; the `init_context.md` mentioned `main` — confirm before renaming/pushing).
11. **Re-ranker is optional.** Many users will want it; many will not. Default to off, plug-and-play when enabled.
12. **Benchmark command lands last.** Per the user: "this will happen once everything else is ready since it should be one of the last commands."

---

## 10. Open questions to resolve in subsequent sessions

- **License.** Apache-2.0 recommended (matches Microsoft GraphRAG); confirm with user.
- **Branch name.** `master` (per the user's direct instruction in the conversation body) or `main` (per `init_context.md`)? Default left at `master`.
- **Caching backend.** Filesystem JSON is the simplest; sqlite is more robust. Filesystem chosen for Phase 1 with sqlite as a possible later upgrade.
- **Reranker default.** Local cross-encoder (`sentence-transformers`) vs. Cohere Rerank API. Local default avoids new accounts.
- **Map-reduce in global search.** Reimplement in-house (chosen) vs. depend on a public utility like LangChain's `MapReduceDocumentsChain`. In-house keeps the dependency tree small.
- **Vision / Excel agentic extraction.** The user mentioned this exists; it was **not located** in the indexing tree — likely it lives in the proprietary `agentic_callback_manager`-adjacent code that is out of scope. Reintroduce it via a clean adapter layer (extraction-only, no agent loops) in Phase 7 or later.
- **AdvancedRAG.** Migrate now or later? Recommendation: later — it duplicates `loader.py`'s source-mapping concerns and the value-add (CallAgent batching) is proprietary.

---

## 11. Quick reference for future sessions

- **Where the legacy code lives:** `_legacy_source/graphrag/` (gitignored mirror of `/Users/bgg/Documents/repos/nirvana/.../graphrag/`).
- **Primary entry to study:** `_legacy_source/graphrag/GRAIL.py`.
- **Primary migration target:** `_legacy_source/graphrag/indexing/llm_wrapper.py`.
- **Innovations to preserve verbatim:** `indexing/incremental_community.py`, `indexing/leiden.py`, mixed-document chunking in `indexing/loader.py`, mixed-context local search in `query/local_search_mixed_content.py`, JSON-correction loop in `indexing/community_reports.py`.
- **Files to drop entirely:** `tools.py`, `GraphRag.py`, the `nirvana_agents.utilities.reduce_map` dependency.
- **Files that are already portable (copy first):** everything marked Risk-L in §4.
- **Authorship line for new modules:** `"""Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero."""`

When in doubt, search `_legacy_source/` for the exact symbol — the snapshot is verbatim, line numbers match the analyses captured in this file.
