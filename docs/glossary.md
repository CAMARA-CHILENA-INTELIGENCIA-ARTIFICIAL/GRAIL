# GRAIL glossary

Every config key, every model identifier convention, every command flag —
documented in one place. Use this as the lookup for "what does *that* parameter
actually do?". Per-module docs in `docs/*.md` explain *why* you'd change a key;
this file is the dictionary.

> Source of truth: ``grail/config.py``. If the type or default here doesn't
> match the Pydantic schema, the schema wins.

---

## Project basics

| Key | Type | Default | What it controls |
|---|---|---|---|
| `project_name` | str | `"default"` | Human-readable label, used in logs and the rich reporter prefix. |
| `root_dir` | path | `~/.grail/projects/default` | The on-disk root for input/output/cache/lancedb. `~` is expanded. |

---

## endpoints — where to send LLM/embedding calls

Each entry under the top-level `endpoints:` block describes one deployment of
the OpenAI Chat Completions / Embeddings API.

| Key | Type | Default | What it controls |
|---|---|---|---|
| `base_url` | str | _required_ | The HTTPS root the OpenAI SDK posts to. Must end in `/v1` (or whatever the endpoint expects). |
| `api_key_env` | str \| null | varies | Environment variable name to read the API key from. `null` means no key needed. |
| `requires_key` | bool | `true` | If `true`, GRAIL errors when the env var isn't set. Set `false` for self-hosted servers. |
| `notes` | str | `""` | Free-text label that surfaces in `grail config show`. |

**Built-in endpoint names**: `openai`, `anthropic`, `deepinfra`, `together`,
`groq`, `openrouter`, `ollama`, `vllm`, `sglang`, `lmstudio`, `local`. See
[llm.md](llm.md) for base URLs.

User entries **deep-merge** with built-ins: providing only `base_url:` for an
existing name keeps the original `api_key_env`.

---

## llm — chat completion client defaults

| Key | Type | Default | What it controls |
|---|---|---|---|
| `endpoint` | str | `"openai"` | Endpoint name (must exist in `endpoints`). Where the LLM calls go. |
| `model` | str | `"gpt-4o-mini"` | Model name within that endpoint. Whatever string the endpoint accepts. |
| `concurrent_requests` | int | `15` | Global semaphore size — max parallel LLM calls in flight. |
| `request_timeout` | float | `180.0` | Per-call timeout in seconds. Raised → retried via tenacity. |
| `max_retries` | int | `10` | tenacity attempt count for transient errors (timeout, 429, network). |
| `max_retry_wait` | float | `10.0` | Fixed seconds between retries. |
| `sleep_on_rate_limit` | float | `30.0` | Sleep before re-raising HTTP 429 errors (so tenacity backs off harder). |
| `debug` | bool | `false` | If true, the reporter prints LLM responses to console. Verbose. |
| `cache_enabled` | bool | `false` | Disk cache for `(endpoint, model, messages, params)` tuples. Useful in iteration. |
| `cache_dir` | path \| null | `null` | Cache location. `null` → `{root_dir}/cache/llm`. |

---

## embeddings — vector encoding client defaults

| Key | Type | Default | What it controls |
|---|---|---|---|
| `endpoint` | str | `"deepinfra"` | Endpoint name. |
| `model` | str | `"intfloat/multilingual-e5-large"` | Model name within that endpoint. |
| `encoding_format` | str | `"float"` | `"float"` for raw vectors, `"base64"` for compact transport. |
| `max_batch_size` | int | `1024` | Max texts per HTTP call. Split larger lists into batches. |
| `concurrent_requests` | int | `30` | Semaphore size. |
| **Cost tracking** | — | — | The same `CostTracker` instance is shared with `LLMClient`, so the manifest's `llm.by_tag` block lists embeddings (`entity_embedding`, `query_embedding`) alongside chat completions. When the (endpoint, model) pair has no entry in `llm.extra_pricing` / `DEFAULT_PRICING`, the call records `cost_resolved=False` and the manifest reports `Undefined` for that stage. |
| `request_timeout` | float | `180.0` | Per-call timeout. |
| `max_retries` | int | `10` | tenacity attempts. |
| `max_retry_wait` | float | `10.0` | Seconds between retries. |
| `sleep_on_rate_limit` | float | `30.0` | 429 backoff sleep. |

**Invariant:** indexing and querying must use the **same** embedding model.
Mismatched dimensions silently degrade recall.

---

## indexing — chunking and extraction

| Key | Type | Default | What it controls |
|---|---|---|---|
| `chunk_size` | int | `2000` | Tokens per text unit. Driven by `encoding_name`. |
| `chunk_overlap` | int | `50` | Tokens shared between adjacent chunks. Smooths boundary entity references. |
| `encoding_name` | str | `"cl100k_base"` | tiktoken encoding for counting. `cl100k_base` matches GPT-3.5/4. |
| `document_boundary` | str | `"\n\n---DOCUMENT_BOUNDARY---\n\n"` | Marker inserted between concatenated documents so chunks can span them with a clear breadcrumb. |
| `input_folder` | str | `"input"` | Subdir under `root_dir` where source files live. |
| `output_folder` | str | `"output"` | Where parquet artefacts are written. |
| `cache_folder` | str | `"cache"` | Where the LLM cache lives (when enabled). |
| `entity_relation_endpoint` | str \| null | `null` | Override the extraction LLM endpoint. `null` → inherit from `llm`. |
| `entity_relation_model` | str \| null | `null` | Override the extraction model. |
| `summarization_endpoint` | str \| null | `null` | Override for entity/relationship description summarization. |
| `summarization_model` | str \| null | `null` | Same, model side. |
| `entity_types` | list[str] | `["PERSON", "ORGANIZATION"]` | Types the extractor asks for. Normalized to UPPER_SNAKE_CASE; `PERSON` and `ORGANIZATION` are always force-injected at the head (`MANDATORY_ENTITY_TYPES` in `grail/config.py`). Use `grail create-entities` to expand. |
| `max_summarization_tokens` | int | `756` | Output token budget for summarizing merged descriptions. |
| `max_gleanings` | int | `0` | Number of "did you miss anything?" re-asks per chunk. `0` = single pass. Costly. |

---

## community — Leiden and report generation

| Key | Type | Default | What it controls |
|---|---|---|---|
| `max_cluster_size` | int | `50` | graspologic hierarchical Leiden cap. Bigger clusters get split. |
| `use_lcc` | bool | `false` | Restrict to the largest connected component before clustering. Drops orphans. |
| `strategy` | str | `"leiden"` | Reserved; only Leiden is implemented today. |
| `seed` | int \| null | `null` | Random seed for reproducible clustering. `null` = nondeterministic. |
| `community_report_endpoint` | str \| null | `null` | Override the report-writer LLM endpoint. |
| `community_report_model` | str \| null | `null` | Same, model side. |
| `json_corrector_endpoint` | str \| null | `null` | Endpoint used by the JSON-repair fallback. Falls back to the report endpoint. |
| `json_corrector_model` | str \| null | `null` | Same, model side. |
| `max_report_length` | int | `4000` | Output token cap for community reports. |
| `include_covariates` | bool | `false` | Include claims (covariates) in report context. Off by default — covariate extraction isn't wired yet. |
| `incremental_change_threshold` | float | `0.3` | If `(changed entities) / (total entities) ≥ this`, run full Leiden on the affected subgraph; else label-propagate. |
| `min_community_size` | int | `10` | Communities smaller than this get merged via DBSCAN over centroids. |
| `embedding_merge_eps` | float | `0.5` | DBSCAN ε for the centroid-merge step. Larger → more aggressive merging. |
| `community_level` | str \| int | `"coarsest"` | Which Leiden hierarchy level to summarise. `"coarsest"` (default, fewest broadest communities), `"finest"` (most granular), `"all"` (every level, legacy GraphRAG behaviour), or an int (specific level). |
| `min_report_size` | int | `3` | Skip community reports for communities with fewer than this many entities. Defends against the long tail of singleton "communities" from isolated entities. Set to `0` to disable. |

---

## search — local and global query knobs

| Key | Type | Default | What it controls |
|---|---|---|---|
| `local_search_endpoint` | str \| null | `null` | Override LLM endpoint for local search synthesis. |
| `local_search_model` | str \| null | `null` | Same, model side. |
| `global_search_endpoint` | str \| null | `null` | Override LLM endpoint for global map/reduce. |
| `global_search_model` | str \| null | `null` | Same, model side. |
| `local_max_tokens` | int | `12000` | Total context budget for local search (entities + relationships + communities + sources). |
| `local_text_unit_prop` | float | `0.5` | Fraction of `local_max_tokens` reserved for raw text-unit citations. |
| `local_community_prop` | float | `0.1` | Fraction reserved for community-report context. |
| `local_conversation_history_max_turns` | int | `5` | How many prior turns to include in the local-search context. |
| `local_top_k_entities` | int | `10` | Top entities pulled by semantic similarity. |
| `local_top_k_relationships` | int | `10` | Top relationships per selected entity. |
| `use_community_summary` | bool | `false` | When false (default), community reports include the full LLM-generated content with detailed findings. When true, only the one-line summary is used (legacy behaviour for tight token budgets). |
| `global_map_max_tokens` | int | `2000` | Output budget per map chunk. |
| `global_reduce_max_tokens` | int | `8192` | Output budget for the reduce synthesis call. |
| `global_chunk_size` | int | `100000` | Token threshold — above this we switch from single-reduce to map-reduce. |
| `global_concurrency` | int | `5` | Map-phase concurrency cap. |
| `response_max_tokens` | int | `16384` | Maximum tokens the LLM can generate in its response. |
| `response_type` | str | `"Multiple Paragraphs"` | Free-text instruction injected as the `artifact_instructions` block. |

---

## reranker — optional cross-encoder re-ranking

| Key | Type | Default | What it controls |
|---|---|---|---|
| `enabled` | bool | `false` | Master switch. When false, no reranker client is constructed. |
| `endpoint` | str | `"deepinfra"` | Endpoint name from `endpoints:` — used to resolve `api_key_env`. |
| `model` | str | `"Qwen/Qwen3-Reranker-0.6B"` | Cross-encoder model name passed to the inference API. |
| `base_url` | str \| null | `null` | Full URL override. When null, auto-derived (e.g. DeepInfra → `https://api.deepinfra.com/v1/inference/{model}`). |
| `overfetch_factor` | int | `3` | Vector retrieval fetches `top_k × factor` candidates; the reranker trims to `top_k`. Range 1–10. |
| `rerank_entities` | bool | `true` | Re-rank entity candidates in local / document search. |
| `rerank_text_units` | bool | `true` | Re-rank text unit candidates in local search. |
| `request_timeout` | float | `30.0` | HTTP timeout for the reranker API call (seconds). |

CLI override: `--rerank` / `--no-rerank` on the `query` command.
Python API override: `use_reranker=True|False` on `GRAIL.search()`.

---

## storage — where bytes live

| Key | Type | Default | What it controls |
|---|---|---|---|
| `backend` | str | `"local"` | `"local"` (filesystem) or `"s3"` (requires the `[s3]` extra). |
| `root` | path | `~/.grail/projects/default` | Local backend root. Ignored for `s3`. |
| `s3_bucket` | str \| null | `null` | S3 bucket name. |
| `s3_prefix` | str \| null | `null` | Key prefix under the bucket. |
| `s3_region` | str \| null | `null` | AWS region. Falls back to `AWS_REGION_NAME` env. |
| `s3_endpoint_url` | str \| null | `null` | Override for MinIO / S3-compatible stores. |

---

## prompts — custom prompt packs

| Key | Type | Default | What it controls |
|---|---|---|---|
| `custom_paths` | list[path] | `[]` | Directories searched **before** the built-in pack. Earlier wins. |
| `strict` | bool | `false` | If true, the custom pack must provide every built-in prompt name. Useful for translated packs. |

Built-in prompt names: `entity_relation`, `summarize_description`,
`community_report`, `json_correction`, `create_custom_entities`, `local_search`,
`global_map`, `global_reduce`, `claim_extraction`. See [prompts.md](prompts.md).

---

## vectorstore

| Key | Type | Default | What it controls |
|---|---|---|---|
| `backend` | str | `"lancedb"` | `"lancedb"` (default), `"faiss"` (requires `pip install 'graphgrail[faiss]'`), or `"chromadb"` (requires `pip install 'graphgrail[chroma]'`). |
| `collection_name` | str | `"entity_descriptions"` | Table / collection name for entity description embeddings. |
| `uri` | str \| null | `null` | Store path. `null` → `{root_dir}/{backend}`. |
| `distance_fn` | str | `"l2"` | Distance function for ChromaDB (`"l2"` or `"cosine"`). Ignored by LanceDB and FAISS. |

---

## Model identifier convention

GRAIL keeps endpoint and model **separate** in config and public API. The
canonical form in the cost ledger is `endpoint|model` (e.g.
`deepinfra|google/gemma-4-26B-A4B-it`). In Python you can pass that shorthand to
`LLMClient.execute(model=...)`, or pass them apart (`endpoint=`, `model=`).
Configs always use the split form.

---

## CLI flags

| Flag | Commands | What it does |
|---|---|---|
| `--name X` | `init` | Sets `project_name` instead of using the directory basename. |
| `--template NAME` | `init` | Scaffold from `configs/templates/NAME` (or from `--templates-dir`). |
| `--templates-dir PATH` | `init` | Extra directory of user templates to look in. |
| `--list-templates` | `init` | Print available templates and exit. |
| `--overwrite` | `init` | Replace existing files. |
| `--mode local\|global` | `query` | Pick search algorithm. |
| `--output text\|json` | `query` | Output formatter. |
| `--write` | `create-entities` | Persist the LLM-proposed entity types back into `grail.yaml`. |

---

## Reading order

1. Skim [getting-started.md](getting-started.md) for the workflow.
2. Pick a template under [`configs/templates/README.md`](../configs/templates/README.md).
3. Use **this file** when you need to know what a key does.
4. Use [llm.md](llm.md), [indexing.md](indexing.md), [query.md](query.md), etc. when you need to understand *why* a key matters.
