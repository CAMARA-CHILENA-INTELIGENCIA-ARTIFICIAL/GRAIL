# Configuration

> **Scope.** How GRAIL configs are structured, loaded, and merged. Configures: anything under ``configs/``. Code: ``grail/config.py``.

## File layout

There are two ways to write a config:

### One file

```yaml
# my-project/grail.yaml
project_name: example
root_dir: ./my-project
llm:
  default_model: openai|gpt-4o-mini
  concurrent_requests: 8
indexing:
  chunk_size: 1500
  entity_types: [person, organization, technology]
search:
  local_max_tokens: 6000
```

Load with ``load_config("my-project/grail.yaml")``.

### Directory layout (recommended)

```
my-project/
├── grail.yaml             # master — project_name, root_dir, any section inlined
├── llm.yaml               # optional per-module overrides
├── indexing.yaml
├── community.yaml
├── search.yaml
├── storage.yaml
├── prompts.yaml
└── vectorstore.yaml
```

Load with ``load_config("my-project/")``. Per-module YAMLs are merged into the
matching sections of the master file, so you can keep concerns separated. The
reference per-module files live in the top-level ``configs/`` directory; copy
any of them into your project and edit there.

## Sections

| Section        | Code class           | What it controls                                            |
|----------------|----------------------|-------------------------------------------------------------|
| ``llm``        | LLMConfig            | LLMClient (model, concurrency, retries, cache, providers)   |
| ``embeddings`` | EmbeddingsConfig     | EmbeddingClient (model, batching, retries)                  |
| ``indexing``   | IndexingConfig       | Chunking, entity types, model overrides for extraction      |
| ``community``  | CommunityConfig      | Leiden + community-report knobs                             |
| ``search``     | SearchConfig         | Local + global search token budgets and model overrides     |
| ``storage``    | StorageConfig        | local / s3 backend selection + paths                        |
| ``prompts``    | PromptsConfig        | Custom prompt search paths, strict mode                     |
| ``vectorstore``| VectorStoreConfig    | LanceDB backend / collection name / URI                     |

Defaults live in code (``grail/config.py``) and are documented inline in each
``configs/<module>.yaml``. Anything you omit from your config falls back to the
default.

## Environment variable substitution

Anywhere in the YAML, ``${VAR}`` expands to ``os.environ["VAR"]``. ``${VAR:-default}``
uses ``default`` when ``VAR`` is unset. Substitution happens after parsing, so
you can use it for paths, model strings, etc.:

```yaml
storage:
  root: ${GRAIL_PROJECT_ROOT:-~/.grail/projects/example}
llm:
  default_model: ${GRAIL_LLM:-openai|gpt-4o-mini}
```

This is independent of ``.env`` — GRAIL doesn't auto-load ``.env``. Use
``python-dotenv``, ``direnv``, or your shell's profile to populate the environment
before invoking the CLI.

## Python API

```python
from grail.config import Config, load_config, dump_config

cfg = load_config("./examples/quickstart")
cfg.llm.default_model = "anthropic|claude-sonnet-4-5"
cfg.indexing.entity_types = ["person", "organization", "concept"]
dump_config(cfg, "./examples/quickstart/grail.yaml")
```

The :class:`Config` schema uses Pydantic with ``extra="forbid"``, so typos in
your YAML surface as validation errors rather than silently being ignored.

## CLI helpers

```bash
uv run grail config show ./my-project          # dump effective merged config
uv run grail init ./my-project --name proj      # scaffold grail.yaml + dirs
uv run grail status ./my-project                # show artefact freshness
```
