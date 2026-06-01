---
name: grail
description: |
  Build queryable knowledge graphs from documents OR maintain agent memory
  across sessions using GRAIL (Graph RAG). Use this skill WHENEVER the user
  wants to: index a corpus, answer questions over their documents, append /
  edit / delete sources in an existing index, build a knowledge base from
  PDFs / markdown / code, OR remember things across conversations
  (observations, entities, relationships), recall them later by date / folder
  / tag, consolidate memory into communities, accept or reject proposed
  groupings, list known GRAIL projects, or query an agent's accumulated
  memory. Triggers include: "index these documents", "build a knowledge
  graph", "ingest this corpus", "what does my corpus say about X", "remember
  that ...", "save this observation", "what did I learn about Y last week",
  "recall everything tagged pricing", "consolidate my memory",
  "what do I know about Z", "show my GRAIL projects", "find similar
  entities". This skill drives both knowledge-base and memory-mode GRAIL
  projects and routes by the project's declared mode.
version: 1.0.0
---

# GRAIL

GRAIL is a graph-RAG engine with two project modes:

| Mode | Write path | Triggers |
|---|---|---|
| `knowledge_base` | `grail index` over `./input/` (LLM extraction) | "index these PDFs", "build a KB from this corpus" |
| `memory` | tool-driven SDK writes under `./memories/` | "remember that ...", "what did I observe last week" |

Both modes produce the same parquet artefacts, so every search mode
(`local`, `cascade`, `global`, `document`, `agent`, `recall`) works on
either kind of project. The skill routes on the project's declared mode.

## Before any action

1. **Setup once per session.** `bash scripts/setup.sh` (idempotent — safe to
   call every time the agent starts).
2. **Discover projects.** `python scripts/list_grail_projects.py` returns
   the known projects from `~/.grail/registry.json` (their id, name, mode,
   path).
3. **If the user names a project**, every subsequent script call accepts
   `--project <ref>` where `<ref>` is a path, a registry name, or a ULID
   prefix.
4. **Resolve mode.** `python scripts/status.py --project <ref>` returns
   `{mode, artefact counts, last_indexed_at}`. Route on `mode`:
   - `knowledge_base` → see `references/kb_mode.md`
   - `memory` → see `references/memory_mode.md`

## Creating a new project

```bash
# Knowledge base (default): scaffolds ./input/ for batch indexing
python scripts/init_project.py --project ./my-kb --name my-kb

# Memory mode: scaffolds ./memories/ for tool-driven writes (+ git init)
python scripts/init_project.py --project ./my-mem --memory --name my-mem
```

Both write `grail.yaml`, `meta.json`, and register the project in
`~/.grail/registry.json`.

## Routing summary

- **The user gives you a folder of PDFs/markdown to index** → KB mode.
  See `references/kb_mode.md`. Pipeline: `init` → `index` → `query`.
- **The user wants to save / recall things across conversations** →
  memory mode. See `references/memory_mode.md`. Pipeline:
  `init --memory` → `memory/add_observation` → `memory/recall` →
  `memory/consolidate`.
- **The user is querying an existing project** → check its mode first
  via `status.py`, then use `query.py` with the appropriate mode.

## Search modes (both project kinds)

See `references/search_modes.md` for the full catalogue. Quick picks:

- `--mode cascade` — most robust default for KB queries (entity-gated +
  text rescue). Use when the user asks a specific factual question.
- `--mode global` — broad thematic questions ("what are the themes").
- `--mode document` — questions scoped to one source file.
- `--mode recall` — temporal / structural slice with **zero LLM cost**.
  Use for "show me everything tagged pricing under work/clients/**".
- `--mode agent` — let the LLM pick tools across local / cascade /
  global / document.

Filter flags compose with any mode: `--since 1h`, `--before 7d`,
`--category 'work/clients/**'`, `--tag pricing`, `--entity-name ALICE`,
`--type PERSON`, `--min-confidence 0.7`.

## Memory mode workflow (one-paragraph version)

Agent writes a memory: `python scripts/memory/add_observation.py
--project <ref> --title "..." --content "..." --category work/clients/acme
--entities '[{"name":"JOHN","type":"PERSON","description":"..."}]'`.
Before writing, optionally call `memory/find_similar_entity.py` to check
for duplicates. Later, `memory/recall.py` retrieves by date / folder /
tag without an LLM call. When the corpus is large enough,
`memory/consolidate.py` proposes new communities and alias merges; the
agent reviews via `memory/list_proposals.py` and acts via
`memory/apply_proposal.py --accept|--reject`.

## Pitfalls

- **Never edit `meta.json` by hand** — let the scripts manage it.
- **`scripts/setup.sh` failed** → GRAIL isn't installed; see
  `INSTALL.md`.
- **`grail consolidate` refuses below 30 entities** by default — that
  threshold is in `memory.min_entities_for_consolidate`. Communities
  only become useful at scale; below it, read the underlying memory
  files directly.
- **Memory mode without embeddings configured** → `add_*` calls succeed
  but emit a warning; `find_similar_entity` falls back to edit-distance
  matching; cascade/local search returns degraded results until you set
  `embeddings` in `grail.yaml`.
- **Mixing modes** → running `index` on a memory project is allowed but
  warned. Running `consolidate` on a KB project is allowed but warned.
- **API runtime (no network)** → this skill needs `pip install graphgrail`,
  so it works in Claude Code, Codex, and Hermes but **not** in the
  Anthropic API code-execution container.

## Verification

Every script returns a JSON envelope on stdout:

```json
{
  "ok": true,
  "mode": "memory",
  "project": {"id": "01HF...", "name": "work-memory", "path": "/Users/..."},
  "data": { ... },
  "warnings": ["..."],
  "next_steps": ["scripts/..."]
}
```

Always check `ok` before claiming success. On failure the shape is
`{"ok": false, "error": "...", "data": {...optional context...}}`.

## References

- `references/kb_mode.md` — knowledge-base workflow
- `references/memory_mode.md` — memory workflow
- `references/search_modes.md` — local / cascade / global / document / agent / recall
- `references/query_optimization.md` — WHO + WHAT + SPECIFIC formula; mode-pick heuristics
- `references/memory_tools.md` — `add_observation` / `add_entity` etc. schema
- `references/proposals.md` — consolidate proposal review workflow
- `references/config_reference.md` — `grail.yaml` fields the agent might touch
- `references/troubleshooting.md` — common failures + fixes
