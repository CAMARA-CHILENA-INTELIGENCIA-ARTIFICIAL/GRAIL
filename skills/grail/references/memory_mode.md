# Memory mode workflow

Memory mode is the **agent-driven write path**. Instead of running LLM
extraction over a corpus folder, the agent writes individual observations
as markdown files with YAML frontmatter, and supplies the entities +
relationships directly via tool calls. Zero LLM at write time.

## Lifecycle

```
init --memory → add_observation (loop) → recall (loop) → consolidate → apply_proposal
```

## Adding an observation

This is the most common write. Read the user, decide what to capture,
and emit one tool call:

```bash
python scripts/memory/add_observation.py --project work-memory \
  --title "Meeting with Acme on Q2 pricing" \
  --content "John pushed for 15% reduction. Sarah pushed back." \
  --category work/clients/acme \
  --tag meeting --tag pricing \
  --observed-at 2026-05-27T15:30:00Z \
  --entities '[
      {"name": "JOHN_SMITH", "type": "PERSON",
       "description": "Acme procurement lead"},
      {"name": "ACME", "type": "ORGANIZATION",
       "description": "Client — manufacturing sector"}
  ]' \
  --relationships '[
      {"source": "JOHN_SMITH", "target": "ACME",
       "relationship_type": "WORKS_AT", "description": "John works at Acme"}
  ]'
```

**Before adding entities**, the skill prompt encourages a dedup check:

```bash
python scripts/memory/find_similar_entity.py --project work-memory --name "Jon Smith"
```

If candidates come back with high similarity (≥0.85 edit distance, ≥0.9
embedding cosine), reuse that name instead of creating a new one. The
write-path tools warn but don't block — the agent decides.

## Recall (no-LLM)

```bash
python scripts/memory/recall.py --project work-memory --since 1h
python scripts/memory/recall.py --project work-memory \
  --category 'work/clients/**' --tag pricing
python scripts/memory/recall.py --project work-memory --type PERSON
```

For LLM-backed recall (e.g. cascade with a temporal pre-filter):

```bash
python scripts/memory/recall.py --project work-memory \
  --query "what did acme say about pricing" \
  --mode cascade --since 1h
```

## Consolidate (proposal generator)

When the corpus grows past `memory.min_entities_for_consolidate` (default
30), run a consolidate pass to surface structural suggestions:

```bash
python scripts/memory/consolidate.py --project work-memory
```

It returns counts by kind (`discover_community`, `merge_aliases`,
`move_entity`, `split_folder`) and the path to a yaml file under
`output/proposals/`. Inspect with `list_proposals.py`; act with
`apply_proposal.py`. See `references/proposals.md` for the per-kind
semantics.

## Folder-as-community

When you set `--category work/clients/acme`, every entity in that
observation automatically gets `work/clients/acme` appended to its
`community_ids`. So:

- The same `JOHN_SMITH` can be in `work/clients/acme` and
  `personal/friends` simultaneously.
- `recall --category work/clients/**` returns him; so does
  `recall --category personal/friends`.
- `consolidate` may later propose a `discover_community` if multiple
  cross-folder entities are densely connected.

## Frontmatter shape (`memories/<category>/<file>.md`)

The agent rarely hand-writes the markdown — `add_observation.py` does
it. But for reference:

```markdown
---
title: Meeting with Acme on Q2 pricing
category: work/clients/acme
tags: [meeting, pricing, Q2]
observed_at: 2026-05-27T15:30:00Z
confidence: 0.9
source: agent-claude
related_to: [acme, john_smith]   # optional entity-name hints
---

# Meeting with Acme on Q2 pricing

Body content here.
```

`assets/observation.md.tpl` ships a blank template for humans who want
to author by hand.

## Pitfalls

- **Embeddings unconfigured** → `add_observation` warns; entities are
  written without `description_embedding`. Recall (no-LLM) works
  unchanged; semantic search on memory degrades.
- **Below the consolidate threshold** → `consolidate.py` refuses. Either
  add more observations or lower
  `memory.min_entities_for_consolidate` in `grail.yaml`.
- **Multi-membership** is the default behaviour, not a special case. The
  `community_ids` column on entities is a list. Don't try to "fix"
  entities that show up in multiple folders.
- **`split_folder` proposals don't move files** — they generate a shell
  script under `output/proposals/<id>_apply.sh` that the agent must
  review and run.
