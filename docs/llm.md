# LLM and embedding clients

> **Scope.** How GRAIL talks to chat-completion and embedding APIs. Configures: ``configs/llm.yaml``, ``configs/embeddings.yaml``, ``configs/endpoints.yaml``. Code: ``grail/llm/``.

## The model story in one sentence

**GRAIL speaks the OpenAI API protocol. An "endpoint" is just a deployment of
that protocol — its base URL and how to authenticate. A "model" is whatever
name that endpoint accepts in the request body. The two are separate fields.**

This means OpenAI Inc. is no more privileged than your local vLLM cluster.
Point GRAIL at any compatible server (vLLM, SGLang, Ollama, LM Studio, your
own proxy, …) by adding one entry to ``endpoints.yaml``.

## Config shape

```yaml
# configs/endpoints.yaml — define deployments by name
openai:
  base_url: https://api.openai.com/v1
  api_key_env: OPENAI_API_KEY

vllm:
  base_url: http://localhost:8000/v1
  api_key_env: VLLM_API_KEY
  requires_key: false

my-internal-cluster:
  base_url: https://llm.internal.corp/v1
  api_key_env: INTERNAL_KEY

# configs/llm.yaml — reference an endpoint by name + pick a model
endpoint: openai
model: gpt-4o-mini
concurrent_requests: 15
...

# configs/embeddings.yaml — same shape
endpoint: deepinfra
model: intfloat/multilingual-e5-large
```

Per-stage overrides (entity extraction, community reports, search) live in
``configs/indexing.yaml``, ``configs/community.yaml``, and ``configs/search.yaml``.
Each accepts ``*_endpoint`` and ``*_model`` keys; ``null`` inherits from
``configs/llm.yaml``. Mix and match — e.g. run extraction on Groq for speed and
the headline community-report on OpenAI for fidelity.

## Built-in endpoints

The defaults that ship in :mod:`grail.llm.providers` and ``configs/endpoints.yaml``:

| Name        | Base URL                              | Env var               | Requires key |
|-------------|----------------------------------------|-----------------------|--------------|
| openai      | https://api.openai.com/v1              | OPENAI_API_KEY        | ✓            |
| anthropic   | https://api.anthropic.com/v1           | ANTHROPIC_API_KEY     | ✓            |
| deepinfra   | https://api.deepinfra.com/v1/openai    | DEEPINFRA_API_KEY     | ✓            |
| together    | https://api.together.xyz/v1            | TOGETHER_API_KEY      | ✓            |
| groq        | https://api.groq.com/openai/v1         | GROQ_API_KEY          | ✓            |
| openrouter  | https://openrouter.ai/api/v1           | OPENROUTER_API_KEY    | ✓            |
| ollama      | http://localhost:11434/v1              | OLLAMA_API_KEY        | ✗            |
| vllm        | http://localhost:8000/v1               | VLLM_API_KEY          | ✗            |
| sglang      | http://localhost:30000/v1              | SGLANG_API_KEY        | ✗            |
| lmstudio    | http://localhost:1234/v1               | LMSTUDIO_API_KEY      | ✗            |
| local       | http://localhost:8000/v1               | LOCAL_API_KEY         | ✗            |

User-defined entries in ``endpoints.yaml`` **add** to this list (deep merge per
endpoint name). To override a built-in, write a partial entry — only the keys
you specify change:

```yaml
endpoints:
  openai:
    base_url: https://my-openai-proxy.corp/v1   # api_key_env still inherits OPENAI_API_KEY
```

## Power-user shorthand

In Python code you can pass a pipe-separated string anywhere a model is accepted:

```python
await llm.execute(messages=[...], model="vllm|my-llama")
```

This is shorthand for ``endpoint="vllm", model="my-llama"``. Configs and CLI
arguments should prefer the explicit split form; the pipe is for terse one-liners.

## Concurrency, timeouts, retries

```yaml
# configs/llm.yaml
concurrent_requests: 15      # global semaphore for the LLMClient
request_timeout: 180.0       # per-call timeout in seconds
max_retries: 10              # tenacity attempt count for transient errors
max_retry_wait: 10.0
sleep_on_rate_limit: 30.0    # sleep before re-raising a 429
```

Retry covers ``asyncio.TimeoutError``, ``APIError``, ``APIConnectionError``,
``RateLimitError``. Use :meth:`LLMClient.execute_safe` for a ``None`` instead of
an exception after persistent failure.

## Caching

```yaml
llm:
  cache_enabled: true
  cache_dir: null   # null → {root_dir}/cache/llm
```

Cache keys hash ``(endpoint|model, messages, temperature, max_tokens, response_format, top_p, stop)``.
Entries are grouped by ``session_id`` — pass one via ``LLMClient.execute(..., session_id="...")``
to bucket calls from a single logical request.

## Cost tracking

Every call records a :class:`UsageRecord`. Pull by tag, model, or session:

```python
print(grail.cost_tracker.summary(by="tag"))
print(grail.cost_tracker.total_cost_usd())
```

Pricing is best-effort and matches against bare model names; unknown models
record tokens with ``cost_usd=0.0``. Extend on construction:

```python
from grail.llm.cost import CostTracker, DEFAULT_PRICING
tracker = CostTracker(pricing={**DEFAULT_PRICING, "my-model": (0.10, 0.40)})
```

## Embeddings

``EmbeddingClient`` mirrors :class:`LLMClient`: same endpoint registry, same
concurrency/retry knobs, same ``endpoint=`` / ``model=`` split. Defaults are
``deepinfra | intfloat/multilingual-e5-large``.

**Indexing and querying must use the same embedding model.** Mismatched
dimensions silently degrade recall. A later phase will persist the embedding
``(endpoint, model)`` pair in ``mapping.json`` and refuse to load mismatches.
