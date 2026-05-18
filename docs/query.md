# Search

> **Scope.** Local and global search over an indexed project. Configures: ``configs/search.yaml``. Code: ``grail/query/``.

## Two modes

### Local search

Entity-anchored. Best for questions about specific people / things / events.

1. Embed the query.
2. Score entities by cosine similarity to their description embeddings (via the
   LanceDB vector store when available, else a pandas scan).
3. Pick the top-k entities; collect relationships that touch them and text units
   that mention them.
4. Pull in community reports for the communities those entities belong to.
5. Pack everything into a context block within proportional token budgets:

   ```
   max_tokens = local_max_tokens
     entity_token_budget         ≈ 1500
     relationship_token_budget   ≈ 1500
     community_token_budget      ≈ local_community_prop × max_tokens
     text_unit_token_budget      ≈ local_text_unit_prop × max_tokens
   ```

6. Send to the LLM with the ``local_search`` prompt.

Citations: every text unit row carries ``document_ids`` and resolves through
``mapping.json`` to the original on-disk path. The ``local_search`` prompt's
system message lists Sources with that resolved document title, so answers can
point at concrete files.

### Global search

Community-anchored. Best for broad / cross-cutting questions ("what are the main
themes?").

* If the community-report context fits in ``global_chunk_size`` tokens (default
  100 000), do a single reduce pass using the ``global_reduce`` prompt.
* Otherwise, **map-reduce**:
  * Slice the report context into chunks.
  * Map each chunk with ``global_map`` → JSON list of ``{description, score}``.
  * Sort points by score, descending. Concatenate top-N into a reduce context.
  * Run ``global_reduce`` on the consolidated points for the final answer.

The map-reduce path is implemented in-house; the legacy proprietary ``ReduceMap``
helper is not used.

## Knobs

```yaml
# configs/search.yaml
local_search_model: null      # null = fall back to llm.default_model
global_search_model: null
local_max_tokens: 8192
local_text_unit_prop: 0.5
local_community_prop: 0.1
local_top_k_entities: 10
local_top_k_relationships: 10
global_max_tokens: 6000
global_map_max_tokens: 2000
global_reduce_max_tokens: 6000
global_chunk_size: 100000
global_concurrency: 5
response_type: "Multiple Paragraphs"
```

## Python API

```python
from grail import GRAIL, load_config

grail = GRAIL.from_config("./examples/quickstart")

result = await grail.search("who is alice?", mode="local")
print(result.response)
print(result.context_data["entities"])     # the entity DataFrame used
print(result.context_data["sources"])      # text units cited
print(result.completion_time, result.llm_calls)

result = await grail.search(
    "what themes appear across all documents?",
    mode="global",
    artifact_instructions="Be concise; bullet the key themes.",
)
```

## CLI

```bash
uv run grail query <project_dir> "your question" --mode local|global --output text|json
```
