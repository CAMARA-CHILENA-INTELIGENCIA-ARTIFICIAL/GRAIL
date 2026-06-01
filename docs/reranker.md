# Reranker

GRAIL supports an optional cross-encoder re-ranker that improves entity and
text-unit selection during local search. After the initial vector similarity
retrieval returns a broad candidate set, the reranker scores each candidate
against the query using a cross-encoder model, then keeps only the top-k most
relevant items. This produces a higher-quality context window for the LLM.

## Why rerank?

Vector similarity (embedding cosine/Euclidean) is a fast but coarse signal. A
cross-encoder reads the query and each candidate together, producing a more
accurate relevance score. In practice this means:

- Entities whose descriptions are semantically close but not the best match get
  demoted in favor of truly relevant ones.
- Text units (source passages) are ordered by query relevance rather than
  first-match position, so the token budget is spent on the most informative
  chunks.

## How it works

```
Query
  │
  ├─ 1. Embed query → vector similarity → top 30 entities (overfetch 3×10)
  │
  ├─ 2. Reranker scores 30 (query, entity_description) pairs
  │     └─ Keep top 10 by reranker score
  │
  ├─ 3. Filter text units by entity mention
  ├─ 4. Reranker scores (query, text_unit) pairs
  │     └─ Reorder by relevance
  │
  └─ 5. Token-budgeted context building on reranked order → LLM
```

The reranker is called twice per local search query:
1. **Entity re-ranking** — over-fetches `top_k × overfetch_factor` entities,
   reranks, trims to `top_k`.
2. **Text unit re-ranking** — reorders the filtered text units by relevance
   before the token-budget cut.

Both stages can be toggled independently via `rerank_entities` and
`rerank_text_units` in the config.

## Config

Add to your project's `grail.yaml` or create `configs/reranker.yaml`:

```yaml
reranker:
  enabled: true
  endpoint: deepinfra
  model: Qwen/Qwen3-Reranker-0.6B
  overfetch_factor: 3
  rerank_entities: true
  rerank_text_units: true
  request_timeout: 30.0
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Master switch. |
| `endpoint` | str | `deepinfra` | Endpoint name from `endpoints.yaml` — used to resolve the API key. |
| `model` | str | `Qwen/Qwen3-Reranker-0.6B` | Cross-encoder model name. |
| `base_url` | str? | `null` | Full URL override. When null, auto-derived from endpoint. |
| `overfetch_factor` | int | `3` | Multiplier for initial vector retrieval. `top_k_entities × factor` candidates are fetched, reranked, and trimmed. |
| `rerank_entities` | bool | `true` | Rerank entity candidates. |
| `rerank_text_units` | bool | `true` | Rerank text unit candidates. |
| `request_timeout` | float | `30.0` | HTTP timeout in seconds. |

## Per-query toggle

You don't need to change config to A/B test. Override per-query:

**CLI:**
```bash
# Force reranking on (requires reranker.enabled: true in config)
grail query myproject "What is X?" --rerank

# Force reranking off (even if config says enabled)
grail query myproject "What is X?" --no-rerank
```

**Python API:**
```python
grail = GRAIL.from_config("myproject")

result_off = await grail.search("What is X?", mode="local", use_reranker=False)
result_on  = await grail.search("What is X?", mode="local", use_reranker=True)
```

## Supported models

The reranker client speaks the DeepInfra inference API format:
`POST /v1/inference/{model}` with `{query, documents}` → `{results: [{index, relevance_score}]}`.

Tested models:
- `Qwen/Qwen3-Reranker-0.6B` (default, 0.6B params, 32k context)
- `Qwen/Qwen3-Reranker-4B`
- `Qwen/Qwen3-Reranker-8B`

Any model served behind this API format will work. Self-hosted options include
vLLM with `task="score"` or Hugging Face TEI (Text Embeddings Inference) with
the reranker endpoint.

## Cost

The reranker API call is tracked in the cost ledger under the `rerank_entities`
and `rerank_text_units` tags. Most reranker models are very cheap (the 0.6B
model processes thousands of documents per dollar). Token-level cost tracking
depends on whether the provider returns usage metadata — DeepInfra does not for
reranker calls, so the cost appears as `Undefined` unless you supply
`extra_pricing` rates.

## Dependencies

The API-based reranker needs no extra dependencies — it uses `httpx` (already a
core dependency). For future local cross-encoder inference via
`sentence-transformers`, install with `pip install 'graphgrail[rerank]'`.
