# Python API

> **Scope.** Using GRAIL as a library from Python — no CLI required. Cover everything you need to embed GRAIL into your own app (FastAPI service, Streamlit demo, Jupyter notebook, custom CLI). For the CLI-first walkthrough see [getting-started.md](getting-started.md); for the conceptual map see [`CLAUDE.md`](../CLAUDE.md).

There is a runnable companion script at [`examples/quickstart/quickstart.py`](../examples/quickstart/quickstart.py).

## 1. Five-line example

```python
import asyncio
from grail import GRAIL, load_config

async def main():
    grail = GRAIL.from_config(load_config("examples/quickstart/grail.yaml"))
    await grail.index()
    result = await grail.search("What are the key themes?", mode="global")
    print(result.response)

asyncio.run(main())
```

That is the whole story. Everything below is detail.

## 2. Public surface

The package re-exports the common entry points so most users only need one import line:

```python
from grail import (
    GRAIL,                  # orchestrator
    Config, load_config,    # config
    LLMClient,              # if you want to talk to the LLM yourself
    EmbeddingClient,        # ditto for embeddings
    PromptRegistry,         # if you want to override / inspect prompts
    Entity, Relationship,   # parquet row schemas
    TextUnit, Community,    # ...
    CommunityReport,
    Document, Covariate,
    SearchResult,           # what search() returns
)
```

Submodules expose more advanced building blocks:

```python
from grail.config import (
    LLMConfig, EmbeddingsConfig, IndexingConfig,
    CommunityConfig, SearchConfig, RerankerConfig,
    StorageConfig, PromptsConfig, VectorStoreConfig,
    EndpointConfig,
)
from grail.query import LocalSearch, CascadeSearch, GlobalSearch, DocumentSearch, AgentSearch
from grail.storage import LocalStorage, get_backend
from grail.llm import CostTracker
from grail.reporting import Reporter, NullReporter
```

## 3. Building a `Config`

You have three options. They produce equivalent `Config` instances.

### a. Load a YAML file

```python
from grail import load_config

config = load_config("examples/quickstart/grail.yaml")         # single file
config = load_config("examples/quickstart")                    # directory with per-module YAMLs
config = load_config(None)                                     # all defaults
```

### b. Build the `Config` object directly (no YAML on disk)

Every section is a Pydantic submodel with sensible defaults:

```python
from grail import Config
from grail.config import LLMConfig, EmbeddingsConfig, IndexingConfig, StorageConfig

config = Config(
    project_name="my-project",
    root_dir="/tmp/grail-my-project",
    llm=LLMConfig(
        endpoint="openai",
        model="gpt-4o-mini",
        extra_pricing={"openai|gpt-4o-mini": [0.15, 0.60]},
    ),
    embeddings=EmbeddingsConfig(
        endpoint="openai",
        model="text-embedding-3-small",
    ),
    indexing=IndexingConfig(
        entity_types=["PERSON", "ORGANIZATION", "PRODUCT", "EVENT"],
        chunk_size=1500,
    ),
    storage=StorageConfig(backend="local", root="/tmp/grail-my-project"),
)
```

### c. From a dict (e.g. loaded from your own YAML / TOML / JSON)

```python
from grail import Config

config = Config.model_validate({
    "project_name": "my-project",
    "llm": {"endpoint": "openai", "model": "gpt-4o-mini"},
    "embeddings": {"endpoint": "openai", "model": "text-embedding-3-small"},
    "storage": {"backend": "local", "root": "/tmp/grail-my-project"},
})
```

Endpoint definitions (`base_url`, `api_key_env`) come from `configs/endpoints.yaml`; you can override or add via `config.endpoints["my-vllm"] = EndpointConfig(...)`. See [getting-started.md §2](getting-started.md#2-pick-an-endpoint-and-model).

## 4. The `GRAIL` orchestrator

### Construction

```python
from grail import GRAIL

grail = GRAIL.from_config(config)                       # most common
grail = GRAIL.from_config("examples/quickstart")        # accepts path too
```

`from_config` instantiates and wires everything: storage backend, endpoint registry, LLM cache (if enabled), `CostTracker`, `LLMClient`, `EmbeddingClient`, `PromptRegistry`, and an optional `RerankerClient`.

After construction the collaborators are attributes you can read or replace:

```python
grail.storage         # StorageBackend
grail.llm             # LLMClient
grail.embeddings      # EmbeddingClient
grail.prompts         # PromptRegistry
grail.reporter        # Reporter
grail.cost_tracker    # CostTracker
grail.reranker        # RerankerClient | None
```

### Methods

All I/O methods are `async`. Wrap with `asyncio.run(...)` from scripts, or `await` them from async code (FastAPI handlers, Textual workers, Jupyter `await` cells).

| Method | Signature (abridged) | What it does |
|--------|----------------------|--------------|
| `index()` | `async () -> dict` | Run the full pipeline: chunk → entities/rels → communities → reports. Returns counts, run_id, cost summary. |
| `search()` | `async (query, *, mode="local", conversation_history=None, document=None, include_entity_names=None, exclude_entity_names=None, use_reranker=None) -> SearchResult` | Single search. `mode` ∈ `"local"`, `"cascade"`, `"global"`, `"document"`. |
| `agent_search()` | `async (query, *, conversation_history=None, system_prompt=None, max_iterations=5, enabled_tools=None) -> SearchResult` | LLM-driven tool-calling loop over the four search modes. |
| `append()` | `async (new_files: list[str]) -> dict` | Incrementally add files (only the new files hit the LLM). |
| `edit()` | `async (replacements: dict[str, str]) -> dict` | Incrementally replace file contents and re-extract affected text units. |
| `delete()` | `async (file_names: list[str]) -> dict` | Remove files; orphaned entities/relationships are pruned. |
| `create_entity_types()` | `async (*, sample_chars=8000, endpoint=None, model=None) -> list[str]` | LLM-driven entity-type discovery from the corpus. |
| `status()` | `sync () -> dict` | Which artefacts exist on disk and where. |

### Index

```python
result = await grail.index()
# {
#   "ok": True,
#   "operation": "index",
#   "run_id": "...",
#   "run_dir": "output/runs/.../",
#   "documents": 3, "text_units": 124, "entities": 412, "relationships": 1037,
#   "communities": 38, "reports": 38,
#   "duration_s": 412.3,
#   "total_cost_usd": 0.36,
#   "llm_summary": {...},
#   "artefacts": {"manifest": "...", "llm_calls": "...", "summary": "..."},
# }
```

Each call writes a new run folder under `output/runs/<run_id>/` and updates `output/current.json`. Subsequent searches automatically read from the active run.

### Search

All search modes return the same `SearchResult` dataclass:

```python
@dataclass
class SearchResult:
    response: str | dict | list[dict]
    context_data: str | list[pd.DataFrame] | dict[str, pd.DataFrame]
    context_text: str | list[str] | dict[str, str]
    completion_time: float
    llm_calls: int
```

The four modes:

```python
# Local — entity-anchored, best for named concepts.
r = await grail.search("Who is Alice?", mode="local")

# Cascade — entity gate + BM25/cosine text rescue, best for fact-style questions
# where the answer lives in text but no entity captured it.
r = await grail.search("What dosage does the protocol specify for X?", mode="cascade")

# Global — map-reduce over community reports, best for cross-cutting themes.
r = await grail.search("What are the main risks discussed?", mode="global")

# Document — scope retrieval to a single source file (by name, path, or doc id).
r = await grail.search("Summarize this regulation.", mode="document", document="law-21250.pdf")
```

Useful kwargs:

* `conversation_history=[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]` — multi-turn context.
* `include_entity_names=["Alice", "Bob"]` / `exclude_entity_names=[...]` — pin or exclude entities (local/cascade).
* `use_reranker=True|False|None` — override config per call (requires `reranker.enabled: true`).
* `artifact_instructions="cite all dates"` — extra system text appended to the answer prompt.

### Agent search

The agent decides which of the four search tools to call (one or more times) before synthesizing:

```python
r = await grail.agent_search(
    "Compare how early-stage vs advanced disease are treated.",
    max_iterations=5,
    enabled_tools={"local_search", "cascade_search"},   # restrict the toolset
)
print(r.response)
```

### Incremental updates

```python
# Add new files.
await grail.append(["new_paper.pdf", "extra_notes.md"])

# Replace existing file content.
await grail.edit({"law-21250.pdf": "/path/to/updated.pdf"})

# Drop files (entities with no remaining text-unit refs are pruned).
await grail.delete(["old_draft.md"])
```

Incremental ops touch only the changed text units; community detection re-runs via the change-ratio scheduler (`community.incremental_change_threshold`, default 0.3). See [incremental_pipeline.md](incremental_pipeline.md).

### Status & costs

```python
grail.status()
# {
#   "project_name": "quickstart",
#   "storage": "...",
#   "artefacts": {"documents": True, "entities": True, "communities": True, ...},
# }

grail.cost_tracker.total_cost_usd()        # 0.36
grail.cost_tracker.render_total_cost()     # "$0.36 (complete)"
grail.cost_tracker.pricing_status()        # "complete" | "partial" | "undefined"
grail.cost_tracker.summary(by="tag")       # per-operation breakdown
```

`pricing_status` is honest: it returns `"partial"` or `"undefined"` when any call hit a model whose pricing wasn't in the price book, so you never see a fake `$0.00`. Add rates via `LLMConfig.extra_pricing` (see the quickstart YAML).

## 5. Reading artefacts directly

Sometimes you want the raw parquets, not the search answer:

```python
from grail.query.retrieval import load_artifacts_for_search

artifacts = load_artifacts_for_search(grail.storage, grail._output_folder())
artifacts.entities         # pd.DataFrame
artifacts.relationships    # pd.DataFrame
artifacts.text_units       # pd.DataFrame
artifacts.communities      # pd.DataFrame
artifacts.community_reports
artifacts.documents
artifacts.nodes
```

The integration test at `tests/integration/test_grail_exploration.py` is a thorough demonstration of every artifact shape.

## 6. Embedding GRAIL in a web app

The shipped chat server at `grail/apps/chat/server.py` is the canonical reference. The pattern is:

```python
from fastapi import FastAPI
from grail import GRAIL, load_config

app = FastAPI()

@app.on_event("startup")
async def startup():
    app.state.grail = GRAIL.from_config(load_config("./my-project"))

@app.post("/ask")
async def ask(question: str):
    result = await app.state.grail.search(question, mode="cascade")
    return {"answer": result.response, "llm_calls": result.llm_calls}
```

The `GRAIL` instance is safe to reuse across requests — `LLMClient` / `EmbeddingClient` are async-safe and rate-limited internally via `concurrent_requests`.

## 7. Customising collaborators

`from_config` is the convenient path; for tests or specialised deployments you can construct `GRAIL` directly and swap any collaborator:

```python
from grail import GRAIL
from grail.config import Config
from grail.storage import StorageBackend, LocalStorage

class MyGCSBackend(StorageBackend):
    ...  # implement the seven required methods

config = Config(project_name="gcs-demo")
grail = GRAIL.from_config(config)
grail.storage = MyGCSBackend(bucket="my-bucket")
```

Custom reporters (rich progress UI, structured logs) plug in the same way:

```python
from grail.reporting import Reporter

class MyReporter(Reporter):
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    # ... etc.

grail = GRAIL.from_config(config, reporter=MyReporter())
```

Custom prompts go through `PromptsConfig.custom_paths` — see [prompt_customization.md](prompt_customization.md).

## 8. Async patterns

GRAIL is async-first. The recommended patterns:

**One-off scripts:**

```python
import asyncio
asyncio.run(my_async_main())
```

**Inside an existing event loop** (FastAPI, Textual, Jupyter):

```python
result = await grail.search("...", mode="local")
```

**From sync code that has no event loop:**

```python
import asyncio
result = asyncio.run(grail.search("...", mode="local"))
```

Avoid `asyncio.run()` inside another running loop — use `await` instead. Jupyter users on IPython ≥ 7 can `await` directly at the top level.

## 9. Where to look next

| Topic | File |
|-------|------|
| Conceptual overview | [`CLAUDE.md`](../CLAUDE.md) |
| Config field reference | [glossary.md](glossary.md) |
| Search mode semantics | [search_modes.md](search_modes.md) |
| Incremental pipeline | [incremental_pipeline.md](incremental_pipeline.md) |
| Prompt customisation | [prompt_customization.md](prompt_customization.md) |
| Vector store choices | [vectorstores.md](vectorstores.md) |
| Storage backends | [storage.md](storage.md) |
| Runnable Python example | [`examples/quickstart/quickstart.py`](../examples/quickstart/quickstart.py) |
| Library-level integration tests (good usage examples) | `tests/integration/test_grail_exploration.py` |
