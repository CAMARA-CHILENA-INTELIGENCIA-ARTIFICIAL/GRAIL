# Prompts

> **Scope.** How GRAIL prompts are structured, where they live, and how to override them. Configures: ``configs/prompts.yaml``. Code: ``grail/prompts/``.

## Design

Every GRAIL prompt is a **Python module** — not a YAML file, not a string in code — that exposes three names:

```python
NAME = "entity_relation"
REQUIRED_PARAMS = ["entity_types", "input_text"]

def build_messages(**params) -> list[dict]:
    return [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
    ]
```

This is the only contract. The function returns an OpenAI-compatible chat
messages array. ``REQUIRED_PARAMS`` is validated by :class:`PromptRegistry.build`
before the module's ``build_messages`` is called, so missing keys surface as a
clear ``KeyError`` rather than a string-format crash deep in the LLM call.

Many prompts expose additional module-level constants — delimiters, JSON
schemas, etc. — that downstream parsers read. The :mod:`grail.indexing.entities_relationships`
parser, for example, imports ``DEFAULT_DELIMITERS`` from
:mod:`grail.prompts.builtin.entity_relation` so the prompt and the parser cannot
drift.

## Built-in pack

Lives under ``grail/prompts/builtin/``. The nine canonical names:

| Name                       | Used by                                       | Required params                                                 |
|----------------------------|------------------------------------------------|------------------------------------------------------------------|
| ``entity_relation``        | EntityRelationshipExtractor                    | ``entity_types``, ``input_text``                                |
| ``summarize_description``  | SummarizeExtractor                             | ``entity_name``, ``description_list``                            |
| ``community_report``       | CommunityReportGenerator                       | ``input_text``                                                  |
| ``json_correction``        | CommunityReportGenerator (repair pass)         | ``json_string``, ``exception``                                  |
| ``create_custom_entities`` | GRAIL.create_entity_types                      | ``texts``                                                       |
| ``local_search``           | LocalSearch                                    | ``context_data``, ``user_query``                                |
| ``global_map``             | GlobalSearch (map phase)                       | ``context_data``, ``user_query``                                |
| ``global_reduce``          | GlobalSearch (reduce phase)                    | ``context_data``, ``user_query``                                |
| ``claim_extraction``       | Optional covariate pipeline (not on by default)| ``entity_specs``, ``claim_description``, ``input_text``         |

Run ``PromptRegistry().discover()`` to print the resolved file path for each name.

## Customizing — per-file override

Drop a Python file with the same ``NAME`` into a directory:

```
my_prompts/
├── community_report.py        # NAME = "community_report"
└── local_search.py            # NAME = "local_search"
```

Point ``configs/prompts.yaml`` at it:

```yaml
custom_paths:
  - ./my_prompts
strict: false
```

Only ``community_report`` and ``local_search`` are overridden — every other name
falls back to the built-in.

## Customizing — strict mode (full pack)

Set ``strict: true`` to require **every** built-in to be present in your custom
directory. Loading fails fast otherwise. Use this when you're shipping a fully
translated prompt pack and want any missing file to fail the build rather than
silently fall back to English defaults.

## Custom-pack example

```python
# my_prompts/entity_relation.py
"""Greek-tuned entity extraction."""

NAME = "entity_relation"
REQUIRED_PARAMS = ["entity_types", "input_text"]
DEFAULT_DELIMITERS = {
    "tuple_delimiter": "<|>",
    "record_delimiter": "##",
    "completion_delimiter": "<|COMPLETE|>",
}

def build_messages(**params):
    p = {**DEFAULT_DELIMITERS, **params}
    return [
        {"role": "system", "content": "Είσαι ένας ειδικός εξαγωγής οντοτήτων..."},
        {"role": "user", "content": f"Κείμενο:\n{p['input_text']}"},
    ]
```

**Important:** if you change tuple/record delimiters, the parser in
:mod:`grail.indexing.entities_relationships` reads them from this module — keep
``DEFAULT_DELIMITERS`` exported, or wire your custom delimiters into the
extractor's ``delimiters`` kwarg directly.

## Programmatic use

```python
from grail.prompts import PromptRegistry

registry = PromptRegistry(custom_paths=["./my_prompts"])
messages = registry.build(
    "entity_relation",
    entity_types=["person", "concept"],
    input_text="Some text…",
)
# messages → list[dict] ready for LLMClient.execute(messages=messages)
```
