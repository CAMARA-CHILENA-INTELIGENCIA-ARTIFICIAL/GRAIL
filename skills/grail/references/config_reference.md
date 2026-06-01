# `grail.yaml` keys the agent might touch

The skill never edits `grail.yaml` automatically; that file is the
user's. But sometimes the agent needs to suggest a config change — this
doc lists the most-touched keys.

## Mode

```yaml
mode: knowledge_base | memory
```

Set by `init_project.py --memory` vs. default. Drives skill routing.
Never change after init unless you know what you're doing.

## LLM + embeddings

```yaml
llm:
  endpoint: deepinfra        # any name from configs/endpoints.yaml or your own
  model: Qwen/Qwen3-32B
  request_timeout: 180.0
  extra_pricing:             # optional — populates the cost ledger
    "deepinfra|Qwen/Qwen3-32B": [0.15, 0.95]

embeddings:
  endpoint: deepinfra
  model: Qwen/Qwen3-Embedding-0.6B
```

`llm: null` is allowed in memory mode for a fully zero-LLM project.

## Indexing (KB and memory)

```yaml
indexing:
  parse_frontmatter: true    # required for memory; safe for KB
  entity_types: [PERSON, ORGANIZATION, LOCATION, EVENT, CONCEPT]
  relationship_types:        # bounded vocab; empty = LLM picks freely
    - RELATED
    - WORKS_AT
    - LOCATED_IN
  chunk_size: 2000
  chunk_overlap: 50
```

## Search defaults

```yaml
search:
  local_max_tokens: 32000
  local_top_k_entities: 10
  use_community_summary: false   # false = full reports; true = one-line summary
```

## Memory tuning

```yaml
memory:
  min_entities_for_consolidate: 30
  enable_edge_density: true
  enable_alias_detect: true
  enable_membership: true
  enable_folder_split: true
  confidence_threshold_discover_community: 0.6
  confidence_threshold_merge_aliases: 0.85
  confidence_threshold_move_entity: 0.6
  confidence_threshold_split_folder: 0.55
  alias_min_jaro_winkler: 0.92
  alias_min_embedding_cosine: 0.93
  folder_split_min_entities: 20
  auto_commit: false           # set true to ``git commit -am`` after each tool write
```

## Storage

```yaml
storage:
  backend: local
  root: /path/to/project
```

`backend: s3` exists but requires the `[s3]` extra; not part of the
skill's default install.

## Vector store

```yaml
vectorstore:
  backend: faiss               # default; lancedb / chromadb also supported
  distance_fn: cosine
```

## Env-var substitution

Any value can reference an env var via `${VAR}` or `${VAR:-default}`.
Useful for API keys:

```yaml
llm:
  endpoint: openai
  # OPENAI_API_KEY is read by the openai endpoint definition; no need to
  # mention it here.
```

The skill expects keys to be present via the runtime environment (Claude
Code, Codex, Hermes all expose this).
