# Getting started

> **Scope of this doc.** How to set up a GRAIL project, point it at some files, and run the indexing + search pipeline end-to-end. The narrative README lives elsewhere; this is the quickstart you copy/paste from.

## 1. Install

```bash
# in the repo root
uv venv --python 3.12
uv pip install -e ".[dev]"          # add ",s3" for S3 storage
cp .env.example .env                 # fill in the API keys you actually use
```

## 2. Pick an endpoint and model

GRAIL keeps **endpoint** (where to send the request — a base URL + key env) and
**model** (the model name within that endpoint) as separate fields. Endpoints
are defined in ``configs/endpoints.yaml`` (the built-ins cover openai,
anthropic, deepinfra, together, groq, openrouter, ollama, vllm, sglang,
lmstudio, local). Pick which endpoint and which model to call by default in
your project's ``grail.yaml``:

```yaml
llm:
  endpoint: openai
  model: gpt-4o-mini

embeddings:
  endpoint: deepinfra
  model: intfloat/multilingual-e5-large
```

Self-hosted is a first-class choice — point vLLM / SGLang / LM Studio at any
chat-completions-compatible server and reference it by endpoint name. To plug
in a new deployment, drop an entry into ``endpoints.yaml``:

```yaml
endpoints:
  my-vllm:
    base_url: http://my-vllm.local:8000/v1
    api_key_env: MY_VLLM_KEY
    requires_key: false
```

Common combos:

| Use case                  | endpoint    | model                                |
|---------------------------|-------------|---------------------------------------|
| Cheap defaults            | openai      | gpt-4o-mini                          |
| Open weights via cloud    | deepinfra   | Qwen/Qwen3-32B                       |
| Top quality               | anthropic   | claude-sonnet-4-5                    |
| Self-hosted vLLM          | vllm        | (whatever your server loads)         |
| Local Ollama              | ollama      | llama3.1                             |

## 3. Scaffold a project

```bash
uv run grail init ./examples/quickstart --name quickstart
```

This creates:

```
examples/quickstart/
├── grail.yaml          # project config
├── .env.example
├── input/              # drop your source files here
└── output/             # parquet/graphml/reports land here
```

## 4. Drop sources into `input/`

GRAIL v0.1 handles text-like files (``.txt``, ``.md``, ``.py``, ``.json``, etc.).
PDF and Office extraction are slated for a later phase — pre-extract for now.

## 5. Index

```bash
uv run grail index ./examples/quickstart
```

Steps run:

1. Discover + chunk files (mixed-document chunks with provenance).
2. Extract entities + relationships via the LLM.
3. Detect communities with hierarchical Leiden.
4. Generate JSON narrative community reports.

Re-run any time — it overwrites the output folder. Use ``grail append`` / ``grail edit``
/ ``grail delete`` (which currently re-index in full; smarter incremental paths land later).

## 6. Search

```bash
uv run grail query ./examples/quickstart "What are the key themes in the corpus?" --mode global
uv run grail query ./examples/quickstart "Who is Alice and what does she work on?" --mode local
```

- ``--mode local`` — entity-anchored, with citations from the original source files.
- ``--mode global`` — map-reduce over community reports; better for cross-cutting questions.

## 7. Status & costs

```bash
uv run grail status ./examples/quickstart
uv run grail config show ./examples/quickstart
```

When ``llm.cache_enabled: true`` and a ``CostTracker`` is attached (the default via
``GRAIL.from_config``), every call records prompt/completion tokens and an estimated
USD spend. ``CostTracker.summary(by="tag")`` slices the ledger by logical operation.

## 8. Customize prompts

Drop new modules into a directory and point ``prompts.custom_paths`` at it:

```yaml
# in grail.yaml
prompts:
  custom_paths:
    - ./my_prompts
  strict: false   # set true to require a full pack (all 9 built-in names)
```

Each custom file must define ``NAME``, ``REQUIRED_PARAMS``, and ``build_messages(**params)``.
See [prompts.md](prompts.md).
