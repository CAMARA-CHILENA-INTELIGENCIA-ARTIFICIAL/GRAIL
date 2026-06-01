# Memory-mode tool schemas

Each `scripts/memory/*.py` wraps one method on `grail.memory.MemoryProject`.
This doc is the canonical reference for what each tool accepts and what
it returns. The agent should consult this when constructing JSON
arguments for `add_observation`'s `--entities` and `--relationships`.

## `add_observation.py`

Writes a markdown file under `memories/<category>/<timestamp>_<slug>.md`,
parses its frontmatter, appends to the parquets, and updates the audit
log. **Atomic** — never half-writes.

Flags:

| Flag | Required | Notes |
|---|---|---|
| `--project` | yes | path / name / ULID prefix |
| `--title` | yes | display name; also drives the slug |
| `--content` | yes | markdown body. Prefix with `@` to read from a file |
| `--category` | no | folder community (e.g. `work/clients/acme`) |
| `--tag` | no | repeatable; many-to-many labels |
| `--observed-at` | no | ISO-8601; defaults to now |
| `--confidence` | no | `0.0`–`1.0`; defaults to `1.0` |
| `--source` | no | provenance string (`agent-claude`, `user`, ...) |
| `--entities` | no | JSON array; see schema below |
| `--relationships` | no | JSON array; see schema below |

Entity JSON shape:

```json
{
  "name": "JOHN_SMITH",
  "type": "PERSON",
  "description": "Acme procurement lead.",
  "retrieval_queries": [
    "who is the contact at Acme?",
    "who handles pricing for Acme?"
  ],
  "community_ids": ["work/clients/acme"]
}
```

`retrieval_queries` and `community_ids` are optional. When `--category`
is set, the category is automatically appended to each entity's
`community_ids`.

Relationship JSON shape:

```json
{
  "source": "JOHN_SMITH",
  "target": "ACME",
  "relationship_type": "WORKS_AT",
  "description": "John works at Acme.",
  "weight": 1.0
}
```

`relationship_type` is optional (defaults to `RELATED`). When the
project's `indexing.relationship_types` is non-empty, the tool warns
when the type isn't in that vocab.

## `add_entity.py`

Declare an entity without an underlying observation file. Use sparingly
— the resulting row has no `text_unit_ids` and no `document_ids`, so
search can't surface it with context. Better: write an observation.

## `add_relationship.py`

Declare a typed edge between two existing entities. Refuses if either
endpoint is missing. Self-loops are blocked. Warns when the type isn't
in the configured vocab.

## `add_community.py`

Declare a community (typically folder-as-community) with optional
report content. Used when:

- The agent wants to give a folder an explicit report (meta.md style).
- The agent wants to declare a community that doesn't follow folder
  shape (`kind=discovered` or `kind=manual`).

## `find_similar_entity.py`

Read-only. Returns up to N candidates by similarity:

| Method | When it fires | Threshold |
|---|---|---|
| `exact` | name matches (case-insensitive) | always |
| `edit_distance` | Jaro-Winkler ≥ 0.85 | always |
| `embedding` | cosine ≥ 0.7, embeddings configured | optional |

Call this before `add_entity` to avoid silently creating duplicates.

## `recall.py`

Defaults to `--mode recall` (no LLM). Composes with the search modes
(`--mode cascade`, etc.) when `--query` is supplied. See
`references/search_modes.md` for the filter-flag catalogue.

## `consolidate.py`

Pure read pass. Runs every enabled analysis from
`MemoryConfig.enable_*`, applies the per-kind confidence floors, dedups
by payload, and writes a yaml file. Returns the path + a count by kind.

## `list_proposals.py` + `apply_proposal.py`

See `references/proposals.md` for the proposal lifecycle.

## Validation contract

Every memory tool returns a `Reply` envelope. The agent should:

1. Check `ok` first. If `false`, surface `error` and stop.
2. Read `warnings` and use them to inform follow-up actions.
3. Use `next_steps` as a hint for the natural next call.

Warnings are common in memory mode — examples:

- `"Entity has no underlying observation — consider add_observation()."`
- `"No embeddings client configured — entities written without description_embedding."`
- `"folder 'work/clients/acme' now has 5 observations — consider writing memories/work/clients/acme/meta.md"`
- `"relationship_type 'MARRIED_TO' not in indexing.relationship_types."`
