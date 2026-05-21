# GRAIL configuration templates

A **template** is a directory of YAML files matching the GRAIL config layout
(``grail.yaml`` + optional ``endpoints.yaml``, ``llm.yaml``, ``embeddings.yaml``,
``indexing.yaml``, ``community.yaml``, ``search.yaml``, ``storage.yaml``,
``prompts.yaml``, ``vectorstore.yaml``).

When you scaffold a project with ``grail init <project_dir> --template NAME``,
every recognised YAML in that template directory is copied into the new project
with ``{name}``, ``{root}``, and ``{date}`` placeholders substituted.

## The "everything is OpenAI API" position

GRAIL only speaks the OpenAI Chat Completions + Embeddings protocol. An
**endpoint** is just one deployment of that protocol — a base URL the SDK posts
to. Any compatible host plugs in: OpenAI itself, DeepInfra, Together, Groq,
your own vLLM / SGLang / LM Studio server.

The base URL is the ``/v1`` prefix. The SDK appends ``/chat/completions`` or
``/embeddings`` automatically. **Do not include ``/chat/completions`` or
``/embeddings`` in ``base_url``.**

Examples of valid ``base_url`` values:

| Host                  | base_url                                      |
|-----------------------|------------------------------------------------|
| OpenAI                | ``https://api.openai.com/v1``                  |
| DeepInfra             | ``https://api.deepinfra.com/v1/openai``        |
| Together              | ``https://api.together.xyz/v1``                |
| Groq                  | ``https://api.groq.com/openai/v1``             |
| Local vLLM            | ``http://localhost:8000/v1``                   |
| Local SGLang          | ``http://localhost:30000/v1``                  |

## Built-in templates

### `low_cost_setup` — the one we ship

A fully-filled GRAIL project biased for cost:

- One inference endpoint pointed at DeepInfra (swap the ``base_url`` to retarget).
- Conservative concurrency (8 in-flight calls).
- LLM disk cache **on** so re-running indexing is free.
- Single-pass extraction (``max_gleanings: 0``).
- Tighter search token budgets than the GRAIL defaults.

Files included:

```
configs/templates/low_cost_setup/
├── grail.yaml             # project identity (placeholders for {name}/{root})
├── endpoints.yaml         # one inference endpoint, shows the base_url pattern
├── llm.yaml               # chat client + cache + concurrency
├── embeddings.yaml        # embedding client (reuses the same endpoint)
├── indexing.yaml          # chunking + extraction
├── community.yaml         # Leiden + incremental thresholds + report generation
├── search.yaml            # local + global search budgets
├── storage.yaml           # local backend with {root} placeholder
├── prompts.yaml           # custom prompt-pack search paths
└── vectorstore.yaml       # LanceDB
```

Every key is documented in [docs/glossary.md](../../docs/glossary.md).

## Using a template

```bash
grail init my-project --template low_cost_setup
```

After scaffolding, fill in your API key in `.env` (or the project's `.env`),
edit `endpoints.yaml` if you want a different host, and you're ready to index.

## Writing your own template

1. Make a directory anywhere on disk, e.g. ``~/.grail/my-templates/acme/``.
2. Copy any subset of the YAMLs above into it. ``grail.yaml`` is the minimum.
3. Use placeholders ``{name}``, ``{root}``, ``{date}`` where you want them
   substituted at init time. Other ``{…}`` sequences are passed through.
4. Anything you don't include falls back to the defaults compiled into
   ``grail/config.py``.

Use with:

```bash
grail init my-project --template acme --templates-dir ~/.grail/my-templates
```

## Listing what's available

```bash
grail init --list-templates                              # built-ins only
grail init --list-templates --templates-dir ~/.grail/    # plus your own
```

## Placeholders

| Placeholder | Replaced with                                                |
|-------------|---------------------------------------------------------------|
| ``{name}``  | The ``--name`` flag (or project directory basename).          |
| ``{root}``  | The absolute path of the new project directory.               |
| ``{date}``  | ISO date at init time, e.g. ``2026-05-19``.                   |
