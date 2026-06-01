# GRAIL as Agentic Memory — Design Context

> **Purpose**: A new Claude Code session continuing this thread should be able to read this single file and pick up the design discussion without needing the prior conversation history. Below is what we've settled, what we ruled out, what's still open, and the proposed order of implementation. **No code has been written for this feature yet** — only the framework that pre-existed (incremental pipeline, cascade search, agent tools, chat TUI) has shipped. Everything in this document is design-stage.

> **Doc version note**: this revision (v2) supersedes an earlier framing where memory was an "SDK-first, tools-later" extension and `consolidate()` was an automatic incremental Leiden re-run. The current framing is: **tools are the primary write surface**, and `consolidate()` is a **proposal generator** the agent reviews. See "What changed since v1" below.

---

## TL;DR

GRAIL's existing artefact layer (parquet + FAISS + NetworkX) and its five search modes (local, cascade, global, document, agent) are *exactly the right primitive* for agentic memory. What needs to change is the **write path**: instead of an LLM-driven indexing pipeline that extracts entities/relationships/communities from chunks, the agent writes them directly via **tools**. Same artefacts, same downstream search code, different ingest.

The key shifts:

1. **One schema, two write paths.** KB mode writes via the indexing pipeline. Memory mode writes via tools. Both produce the same parquet artefacts so every existing search mode works on a memory project with zero code change.
2. **Folders declare communities.** `memories/work/clients/acme/` *is* a community. Entities live in multiple folders → multi-membership is first-class.
3. **`consolidate()` becomes a proposal generator.** It runs Leiden + edge-density + co-occurrence + alias-detection over the current graph and emits a structured proposal file. The agent reviews and accepts/rejects each item. Nothing mutates without consent.
4. **`recall` is a new search mode AND a filter modifier.** Standalone for pure temporal/structural queries; prefix to local/cascade/global/document to narrow their candidate pool.
5. **CLI splits via a flag.** `grail init <project> --memory` produces a memory-profile project. Other commands work in both modes with warnings when the user mixes them up.

**Total estimate**: 4–6 focused days. Schema + frontmatter loader (1d), tools surface with validation (1d), recall mode (1d), proposal generator (1d), CLI flag + mode validation (1d), per-framework skill (variable, kept in Phase 5).

---

## What changed since v1 of this doc

The earlier draft proposed an SDK with direct-write methods (`add_entity`, `add_relationship`, etc.) called from agent code, with `consolidate()` running automatic Leiden re-clustering when triggered. After deeper review of the incremental community code (`grail/indexing/incremental_community.py`) and a data-scientist re-examination of what makes GRAIL superior to Letta/Zep/mem0, three pivots:

| v1 framing | v2 framing |
|---|---|
| SDK first, tools wrap it later | Tools are the conversation primitive; SDK is the implementation layer |
| `consolidate()` runs Leiden automatically | `consolidate()` generates proposals; agent accepts/rejects |
| Communities = Leiden output | Communities = folders (declared) + accepted proposals (discovered) |
| Multi-membership via `final_communities.entity_ids` only | Add `community_ids: list[str]` column to `final_entities` (Option 2) for one read path |
| `grail memory <subcommand>` tree | `grail init --memory` flag; main verbs work in both modes |
| Incremental change-ratio scheduler stays | Memory mode bypasses it; folder assignment is direct |

The v1 incremental-Leiden assumption (70%+ of data exists at first indexing) actually fails differently than expected: not at steady-state but at cold-start (first ~10 entities trigger full re-cluster fallback) and at 1-hop neighbourhood blow-up (high-degree entities pull in half the graph). For memory, this is the wrong tool. See "Consolidate as a proposal generator" below.

---

## The three superiority axes to preserve

GRAIL beats Letta/Zep/mem0 on three orthogonal data-science dimensions. All three must survive in memory mode:

1. **RAG assimilation** — chunked text units with BM25 + cosine fallback (cascade). Memory mode change: chunks come from markdown bodies, but `final_text_units` is identical.
2. **Global thematic context** — community reports give the LLM topic-level summarisation (global search). Memory mode change: report source switches (meta.md / accepted proposal / Leiden) but `final_community_reports` is unchanged.
3. **Cross-entity reasoning** — graph traversal + typed relationships + multi-hop. Memory mode change: edges come from tool calls instead of LLM extraction, but the NetworkX graph is the same.

If memory mode preserves all three, every existing search mode works on a memory project with zero code change. **That's the binding contract.**

---

## What GRAIL already does well for memory

These existing strengths map onto agentic memory needs — no changes required:

- **Incremental append with merge by entity name** — `append_extract()` in `grail/indexing/entities_relationships.py` merges new extractions into existing entities by uppercase name.
- **Orphan pruning on edit** — `_prune_orphan_entities()` removes entities whose last text-unit reference is gone. Exactly what's needed when an agent corrects/supersedes a memory.
- **Per-event source provenance** — every text unit ID stays attached to every entity that came from it.
- **`retrieval_queries` enrichment** — each entity stores 2-3 anticipated questions in its embedding text. No competing memory framework does this. **This is the differentiator.**
- **Cascade search** — entity-gate + text rescue. Critical for memory recall where exact entity matches are flaky.
- **Source extraction in API output** — `extract_source_references()` already returns `[{id, title, path}]`. Agent can see which memory files contributed to a response.

---

## Where the current design hits friction for memory

1. **`entity_types` is closed-set.** Validated against `MANDATORY_ENTITY_TYPES = ("PERSON", "ORGANIZATION")`. Tools need to register new types at runtime.
2. **Relationships are untyped.** Schema is `(source, target, description, weight)` — no `relationship_type` column. Default today is implicitly `RELATED`. Typed edges (`WORKS_AT`, `OBSERVED_AT`, `SUPERSEDES`) are needed for structured recall.
3. **Community detection assumes a settled graph.** Leiden + LLM report generation are batch operations. Even the incremental path makes 1 LLM call per affected community per append. At memory write frequency (100s/hour), this dominates cost.
4. **No notion of recency or decay.** All facts equal-weight at retrieval. Memory wants "last hour" to outrank "3 weeks ago".
5. **No contradiction detection.** Two opposing facts both get embedded as separate evidence.
6. **Append cost** — each observation = embeddings + (maybe) summarizer + (maybe) community report. Memory wants ~200ms writes.
7. **Single-membership communities.** `final_nodes.community: str` is one value. Entities that span folders need multi-membership.

---

## Agreed architecture: same schema, two write paths

```
                    ┌─────────────────────────────────────┐
                    │  GRAIL Core (unchanged)             │
                    │  parquet · FAISS · NetworkX         │
                    │  local · cascade · global · doc ·   │
                    │  agent · recall (new)               │
                    └────────────┬────────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                │                                 │
        ┌───────▼───────┐               ┌─────────▼─────────┐
        │ KB profile     │               │ Memory profile     │
        │ - chunked docs │               │ - markdown obs     │
        │ - LLM extract  │               │ - tool writes      │
        │ - eager reports│               │ - meta.md reports  │
        │ - Leiden       │               │ - proposals on     │
        │   communities  │               │   demand           │
        │ - default      │               │ - folder           │
        │   cascade      │               │   communities      │
        └────────────────┘               └────────────────────┘
```

**Same store, two write paths.** A user can index the same project in both modes simultaneously (KB pipeline against `input/`, tools writing to `memories/`, both feeding the same parquet artefacts). The `mode` field in `grail.yaml` only controls CLI defaults and which warnings fire.

### Config flags that differ between the two profiles

| Config field | knowledge base | memory |
|---|---|---|
| `mode` | `knowledge_base` | `memory` |
| `chunking.chunk_size` | 1200 | 200-400 (observations are short) |
| `community.regenerate_on_append` | `true` | `false` (proposals are on-demand) |
| `community.source` | `leiden` | `folder + proposals` |
| `extraction.use_caller_llm` | `false` | `true` (caller-supplied via tools) |
| `extraction.allow_unknown_types` | `false` | `true` (open-set discovery) |
| `search.default_mode` | `cascade` | `recall` |
| `schema.time_columns` | optional | required (`observed_at` populated everywhere) |
| `git.auto_commit` | `false` | `true` (opt-in but default-on for memory) |

---

## The big architectural shift: tools, not extraction pipeline

**This is the single most important insight.**

KB model:
> GRAIL is a black box. User configures an LLM endpoint, GRAIL calls it for extraction, summarization, community reports. User pays for every LLM call.

Memory model:
> GRAIL exposes **tools** that the agent calls. Each tool validates inputs, mutates files and parquet atomically, and returns `{result, warnings, next_steps}`. The agent already has the context, the LLM access, and the reasoning. GRAIL just persists, validates, and retrieves.

### Why this matters

- KB indexing 100 chunks ≈ 150 LLM calls (extraction + summarization + reports).
- Tools-driven memory writes ≈ 0 LLM calls (only embeddings).
- For an agent making 1000 observations/day: the difference between "expensive" and "negligible".

### Why differentiated vs Letta/Zep/mem0

Those frameworks hard-couple to an OpenAI-style extraction LLM. GRAIL offers both:
- **"Just tell me what to store"** — agent-driven via tools, free
- **"Read this document and figure out what's in it"** — LLM-driven via the indexing pipeline, requires config

Both modes from one codebase.

---

## Tools surface

Each tool: **validates → mutates files + parquet atomically → returns `{result, warnings, next_steps}`**. Warnings nudge but don't block; the agent stays in control.

| Tool | What it does | Validations / warnings | Next-step nudges |
|---|---|---|---|
| `add_observation(title, content, category, tags=[], entities=[], relationships=[], observed_at=None, confidence=1.0)` | Writes `memories/<category>/<slug>.md` with frontmatter; appends parquet rows; updates FAISS | Category exists? (`list_categories` hint if not). Slug collision? Confidence in [0,1]? Frontmatter ISO-8601? | "Folder `<cat>` now has N observations — consider running `update_community_report(<cat>)` or `consolidate()`" |
| `add_entity(name, type, description, retrieval_queries=[], community_ids=[])` | Appends to `final_entities.parquet` + embeds | Name uppercased + name-embedding lookup vs existing → warn if similar entity exists. Type in `entity_types`? Pass with warning if novel. | "Did you mean `<existing>`? Merge or proceed?" |
| `add_relationship(source, target, type="RELATED", description, weight=1.0)` | Appends to `final_relationships.parquet` | Both endpoints exist? Type in `relationship_types` (warn if novel)? Self-loop? Dedup by `(src, tgt, type)`. | If type novel + repeated → "consider adding `<TYPE>` to `relationship_types`" |
| `add_community(community_id, title, member_entity_names, report_content=None, level=0)` | Writes `meta.md` if a folder community; appends row to `final_communities` + `final_community_reports` | All members exist? ID matches folder path (if folder community)? `len(members) >= min_report_size`? | "Members < min_report_size — consider not generating a report yet; recall will read files directly" |
| `update_community_report(community_id, content)` | Rewrites `meta.md` and the `final_community_reports` row atomically | Community exists? | — |
| `find_similar_entity(name, top_k=5)` | Name-embedding cosine + Jaro-Winkler ranking | — | List with similarity scores; agent decides whether to merge |
| `list_categories()`, `list_entities(category=None, type=None, since=None)`, `list_communities()`, `list_observations(category=None, since=None)` | Read-only inspection | — | Used **before** any `add_*` |
| `consolidate(scope=None)` | Runs proposal generator over entity graph (full or scoped); writes `output/proposals/<timestamp>.yaml` | Refuses if entity_count < `consolidate_min_entities` (default ~30) with reason | "Skipped — only 12 entities. Re-run when you have ~30." |
| `list_proposals(status="pending")`, `accept_proposal(proposal_id)`, `reject_proposal(proposal_id, reason)` | Proposal review API | Conflict detection across pending proposals | "Proposal A conflicts with B — review both together" |
| `recall(query=None, since=None, before=None, category=None, tag=None, entity=None, type=None, min_confidence=None, mode="recall")` | New search mode; composes with other modes | — | If many hits → "narrow with `--tag` or `--since`" |

Three things this surface enforces:

1. **The agent reads before writing.** Skill prompt mandates `list_entities` / `find_similar_entity` before `add_entity`, `list_categories` before `add_observation`.
2. **Relationship types stay bounded.** `RELATED` is the default; the agent uses `WORKS_AT`, `OBSERVED_AT`, `SUPERSEDES` etc. from the configurable list. Novel types pass with a warning; repeated novel use prompts adding them to config.
3. **`consolidate()` is the only Leiden trigger.** Steady-state writes never run Leiden. Below the entity threshold consolidate refuses. Above it, it emits proposals.

---

## Folder-as-community

The cleanest mental model. Each folder under `memories/` is a community. The folder path is the community ID.

```
memories/
├── work/clients/acme/2026-05-27_meeting.md     → community: work/clients/acme
├── work/clients/acme/2026-05-28_email.md       → community: work/clients/acme
├── personal/friends/2026-05-26_dinner.md       → community: personal/friends
└── personal/family/2026-05-29_birthday.md      → community: personal/family
```

- Path depth maps to Leiden's `level`: `work` is level 0, `work/clients` is level 1, `work/clients/acme` is level 2.
- The folder's `meta.md` IS the community report. Agent writes it; GRAIL caches into `final_community_reports.parquet`.
- Reports only exist above a value threshold (`min_report_size`, default 3 entities AND ~5 observations). Below it, recall reads the underlying files directly.
- Entities live in multiple folders simultaneously — multi-membership is first-class.

### Community report lifecycle

- **Canonical**: `meta.md` on disk (human-editable, git-versioned).
- **Cache**: `final_community_reports.parquet` (fast batch reads at query time).
- **Tools write both atomically** (`add_community`, `update_community_report`).
- **`consolidate()` may regenerate the parquet** from on-disk `meta.md` (cheap, idempotent) plus accepted proposals.
- **Below threshold**: no `meta.md`, no parquet row. Recall reads observations directly.

---

## Multi-membership entities — schema decision (Option 2)

Today:
- `final_communities.entity_ids: list[str]` — already supports same-entity-in-multiple-communities at the row level
- `final_nodes.community: str` — one row per `(level, entity)`, single value
- This works for Leiden (hard partitions) but not for folder-communities where ALICE lives in both `work/clients/acme` and `personal/friends`

**Decision**: add `community_ids: list[str]` column to `final_entities.parquet`. KB mode populates with a single-element list (Leiden's hard assignment); memory mode populates with N elements from folder paths + accepted Leiden proposals.

Why this and not multi-row in `final_nodes`:
- Search code looks up "what communities does this entity belong to" on the entity row, not the node row.
- One read path; no behavioural change for KB mode.
- `final_nodes` keeps its existing Leiden-shape contract (one row per `level, entity`).
- `community_ids` is a denormalised mirror of `final_communities.entity_ids` — easy to recompute on consolidate.

---

## Consolidate as a proposal generator

Leiden was chosen for KB indexing because the graph was settled and a hard partition was acceptable. In memory mode:

- Entities live in multiple folders simultaneously (soft membership)
- The graph never settles
- The agent owns the structure — nothing should mutate without consent

So `consolidate()` is **an analysis pass that emits proposals**, not a mutation. Output is a structured YAML file the agent reviews:

```yaml
# output/proposals/2026-06-01T14-22Z.yaml
generated_at: 2026-06-01T14:22:18Z
graph_stats: {entities: 312, relationships: 847, communities: 18}

proposals:
  - id: prop-001
    kind: discover_community
    status: pending
    rationale: |
      ALICE, BOB, CARLOS co-occur in 8 observations across 3 folders.
      Mean cosine sim between description embeddings: 0.74.
      Edge density inside this set: 0.89 vs 0.12 graph-wide.
    members: [ALICE, BOB, CARLOS]
    suggested_id: "discovered/alice-bob-carlos"
    confidence: 0.82
    evidence:
      co_occurrence_count: 8
      observation_ids: [obs-001, obs-014, obs-022]
      shared_folders: [work/clients/acme, work/projects/grail]
    action_if_accepted:
      - write_community_row
      - write_meta_md_template: false   # agent decides to author one

  - id: prop-002
    kind: split_folder
    status: pending
    rationale: |
      Folder `work/clients/acme` has 47 entities. Internal clustering
      finds two dense subclusters.
    folder: work/clients/acme
    suggested_split:
      - sub: communications
        members: [...]
      - sub: contracts
        members: [...]
    confidence: 0.71

  - id: prop-003
    kind: merge_aliases
    status: pending
    rationale: |
      DR_SMITH and DR._J._SMITH have name-embedding cosine 0.96 and
      share 4 observations.
    aliases: [DR_SMITH, "DR._J._SMITH"]
    canonical: DR_SMITH
    confidence: 0.94

  - id: prop-004
    kind: add_community_membership
    status: pending
    rationale: |
      ALICE is currently in [work/clients/acme]. She has 11 edges,
      9 of which go to entities in personal/friends.
    entity: ALICE
    suggested_community_ids: [work/clients/acme, personal/friends]
    confidence: 0.88
```

### Internal analyses

The generator runs several signals and merges them into proposals:

- **Leiden** on the current graph → "here's a hard partition you can compare against your folders"
- **Embedding clustering** (HDBSCAN on entity embeddings) → soft thematic clusters
- **Co-occurrence statistics** (entities appearing together in N+ text units)
- **Edge-density analysis** (entities with disproportionate cross-folder edges)
- **Name-embedding aliasing** (high-sim name pairs not already merged)

Each signal produces typed proposals; proposals do not apply themselves.

### Application flow

- Tool-driven: agent calls `list_proposals()`, then `accept_proposal(id)` / `reject_proposal(id, reason)` one by one.
- Accepted proposals apply via the same write tools (`add_community`, `update_entity`, etc.) — keeps the audit trail consistent.
- Conflict detection: if two pending proposals would touch the same entity in incompatible ways, both are flagged.
- After acceptance, the proposal entry's `status` flips and the YAML file is preserved in `output/proposals/archive/`.

This kills the incremental-consolidate problem: consolidate doesn't maintain a moving Leiden state. It runs from scratch each time on the current graph snapshot — cheap to re-run, expensive to apply (because the agent decides).

---

## The big workflow shift: memory is markdown files

Every observation is a markdown file under `memories/`. We never invent a "synthetic text unit" abstraction.

- **Agent writes**: `memories/work/clients/acme/2026-05-27T15-30_meeting_notes.md`
- **GRAIL indexes**: tools-driven path picks up the file, chunks, embeds, updates FAISS, appends parquet rows. Provenance preserved through `document_ids`.
- **Agent re-reads**: just opens the file. Convenience: `read_observation(slug)`.
- **Agent edits**: overwrites the file via `update_observation` tool. Affected chunks re-extract.

### Why files-as-source-of-truth

1. **Edit-by-key replaces append-with-duplication.** Filename = `<ISO_timestamp>_<title_slug>.md`. Agent looks up by slug, edits in place.
2. **Long memories work naturally.** A 500+ token observation is just a longer markdown file.
3. **Git versioning becomes trivial.** Files in a git repo → every commit is a memory snapshot. Branches = parallel memory streams. `git diff` = memory delta.
4. **Agent has filesystem access already.** No special tool needed for read-back.
5. **The "synthetic TU" abstraction disappears.** Cleaner.

---

## Proposed folder structure

```
my-workspace/
├── work-memory/                       ← one memory project (--memory)
│   ├── grail.yaml                     (mode: memory)
│   ├── .git/                          (auto-init, auto-commit when enabled)
│   ├── memories/                      ← THE source of truth
│   │   ├── work/
│   │   │   ├── clients/
│   │   │   │   └── acme/
│   │   │   │       ├── meta.md                                ← community report
│   │   │   │       ├── 2026-05-27T15-30_meeting_notes.md
│   │   │   │       └── 2026-05-28T09-15_followup_email.md
│   │   │   └── projects/
│   │   │       └── grail-redesign/
│   │   └── personal/
│   ├── output/                        ← derived; safe to delete & reindex
│   │   ├── current.json
│   │   ├── runs/<id>/
│   │   │   ├── final_entities.parquet
│   │   │   ├── final_relationships.parquet
│   │   │   ├── final_text_units.parquet
│   │   │   ├── final_communities.parquet
│   │   │   └── final_community_reports.parquet
│   │   └── proposals/
│   │       ├── latest.yaml            (symlink)
│   │       ├── 2026-06-01T14-22Z.yaml ← pending
│   │       └── archive/
│   │           └── 2026-05-29T09-10Z.yaml
│   ├── faiss/
│   └── _history.jsonl                 ← append-only audit log
│
├── personal-memory/
│   └── ...
│
└── client-acme-kb/                    ← knowledge base, same project shape
    ├── grail.yaml                     (mode: knowledge_base)
    ├── input/                         ← batch-indexed
    └── output/
```

Differences between memory and KB projects:
- `memories/` (hierarchical, tool-writable) vs `input/` (flat, batch-loaded)
- `grail.yaml` mode field
- `meta.md` files inside `memories/` (memory) vs no such convention (KB)
- `output/proposals/` (memory) vs no such directory (KB)
- `_history.jsonl` audit log (memory) vs run-folder manifests (KB)

---

## Frontmatter convention for observation files

```markdown
---
title: Meeting with Acme
category: work/clients/acme
tags: [meeting, pricing, Q2]
observed_at: 2026-05-27T15:30:00Z
confidence: 0.9
source: agent-claude
related_to: [acme, john_smith]    # optional entity-name hints
---

# Meeting with Acme

John said pricing should drop 15% for Q2. Sarah pushed back...
```

Recognised keys (lifted into `documents` columns):

- `title` — display name; used to derive the filename slug if not given
- `category` — primary folder path (mirrors the actual folder; redundancy is OK)
- `tags` — many-to-many labels for filtering at recall time
- `observed_at` — ISO 8601 timestamp; used for recency-decay scoring
- `confidence` — 0.0-1.0, defaults to 1.0
- `source` — who/what produced this observation
- `related_to` — optional entity-name hints

Unknown frontmatter keys are preserved into a JSON `attributes` column.

---

## Bounded relationship-type vocabulary

Today's schema is `(source, target, description, weight)` — relationship type is implicitly `RELATED`.

**Default vocabulary (~12 types)**:
`MENTIONS`, `WORKS_AT`, `OWNS`, `LOCATED_IN`, `CAUSES`, `PART_OF`, `CONTRADICTS`, `SUPERSEDES`, `OBSERVED_AT`, `ASSOCIATED_WITH`, `DEPENDS_ON`, `RELATED` (fallback).

**Configurable extension**: `IndexingConfig.relationship_types` mirrors `entity_types` — users add domain-specific types (`PRESCRIBED_FOR`, `MERGES_WITH`) up to a cap (~25 total).

**Dedup key**: relationships dedup by `(src, tgt, type)`. So `WORKS_AT` and `OWNS` between the same pair are separate edges.

**Why typed edges matter for recall**: "tell me about Alice" with typed edges produces:
```
Alice WORKS_AT Acme · LOCATED_IN Berlin · OBSERVED_AT 2026-05-26
```
Instead of a paragraph of free-text descriptions. Much cheaper for the agent to consume.

---

## New search mode: `recall` (peer mode AND modifier)

`recall` is both a **standalone mode** and a **modifier prefix** on every other mode. This avoids duplicating filter logic.

### Standalone (no LLM, no embedding required)

```bash
grail query <project> --mode recall --since 7d --category work/clients/**
grail query <project> --mode recall --tag pricing --type DRUG --min-confidence 0.7
grail query <project> --mode recall --before "yesterday" --entity ALICE
```

Pure SQL-style filters over `observed_at`, `category`, `tags`, `confidence`. Returns matching files/entities with their frontmatter and short snippet.

### As modifier (composes with local/cascade/global/document)

```bash
# Cascade over temporally-filtered candidates only
grail query <project> "what did acme say about pricing" --mode cascade --since 1h

# Local but restrict entity pool to recently-observed entities
grail query <project> "alice's recent activity" --mode local --since 7d
```

Internally, `recall` produces candidate ID sets (`text_unit_ids`, `entity_names`) that other modes consume as a WHERE clause. FAISS supports `id_filter`; pandas filters are trivial. **Zero changes to local/cascade/global search code paths** — just a candidate-set arg added to their builders.

This means the new mode appears in `docs/search_modes.md` as both its own section AND as a modifier flag callable on every other mode (like `--rerank`).

---

## Mode validation in CLI

`grail.yaml` carries `mode: memory | knowledge_base` (set by `grail init` and `grail init --memory`). Commands check it and warn (not block) when mixed:

| Command | KB mode | Memory mode |
|---|---|---|
| `grail index` | runs full pipeline | warns: "memory project — observations are tool-managed; use `grail consolidate` to refresh discovered structure" |
| `grail append <file>` | adds file to `input/` | alias for `add_observation` on a file path |
| `grail edit <file>` | re-extracts file | alias for `update_observation` |
| `grail delete <file>` | drops from index | alias for `delete_observation` |
| `grail consolidate` | warns: "communities are batch-computed at indexing time — re-run `grail index` to refresh" | runs proposal generator |
| `grail query --mode recall` | warns: "no `observed_at` data — temporal filters degrade to no-op" | works fully |
| `grail tools <subcommand>` | warns: "tools API targets memory projects" | works |
| `grail query --mode local/cascade/global/document/agent` | works | works |
| `grail proposal list/accept/reject` | warns: "no proposals — KB mode doesn't generate them" | works |

Warnings, not blocks. Footgun-resistant without being patronising.

---

## Git as the versioning layer

**Strongly recommended, made one-command easy, but not mandatory.**

Why not mandatory:
- Sandbox environments (ephemeral containers, Lambdas) may not have git.
- The memory folder may live inside an existing git repo with its own conventions.

`grail init --memory --git` (default on for memory) would:
- `git init` the project
- Auto-commit on every observation/edit/delete via `config.memory.auto_commit`
- Auto-tag on every `consolidate apply`
- Append the commit SHA to `_history.jsonl`

The agent then has `git log`, `git diff`, `git show <SHA>` to reason about its own memory evolution. Branches enable "what if I had observed this differently?" experiments.

---

## Multiple memory projects per agent — the workspace concept

An agent operates in a *workspace* of one or more GRAIL projects:

```python
memory.add_observation(project="work-memory", ...)
memory.recall(project="client-acme-memory", query="...")
memory.list_projects()
```

For combined queries (KB + memory for the same client):
```python
results = await asyncio.gather(
    memory.recall(project="client-acme-kb", query=question),
    memory.recall(project="client-acme-memory", query=question),
)
```

Future federation: `recall(projects=[...])` that merges results. Start with single-project queries.

---

## Folder hierarchy — concern and proposed mitigation

**Agents are bad at consistent taxonomy.** Left alone they create `work/`, `Work/`, `business/`, `client_work/` for the same conceptual bucket.

**Three signals to combine**:
1. **Folder = primary category** (agent picks 1 from a small bounded list)
2. **Markdown frontmatter tags** (many-to-many)
3. **The graph itself** (entities + accepted proposals cluster semantically)

The skill prompt instructs: *"Before writing, call `list_categories()`. Reuse one if it fits. Only create a new category if nothing fits."* Plus consolidate proposals catch drift early via `merge_aliases` and `split_folder` proposals.

`recall` supports both: `--category work --tag pricing` (filesystem-style) AND `--query "pricing discussions with acme"` (semantic).

---

## Run management — observations don't create runs

The `output/runs/<id>/` convention was designed for batch reindexing. Memory writes happen against a single mutable run (the "active" run).

- Observation writes update the active run in place.
- Audit trail lives in `_history.jsonl` (append-only) with `{timestamp, file_path, operation, tool, git_sha?}` per line.
- `grail memory reindex` creates a fresh run if the user wants a clean rebuild.
- `consolidate()` doesn't create a new run; it writes the proposals file to `output/proposals/`.

---

## Open questions still to decide

Most v1 open questions have been resolved (see "What changed since v1"). Remaining:

1. **`consolidate` trigger policy.** Manual-only (`grail consolidate`), or also auto-trigger when N new observations since last consolidate? Lean: **manual-only in v1**, skill prompt nudges when threshold crossed.
2. **Meta.md ↔ parquet atomicity.** Tools write both, but if a crash happens between writes, which is authoritative? Lean: **meta.md canonical**, parquet recomputable. `consolidate()` reconciles inconsistencies.
3. **Asserted entities without observation backing.** Should `add_entity` allow `text_unit_ids=[]` (pure declared fact, no source)? Lean: **allow with a warning** ("no source backing — consider attaching an observation").
4. **Proposal conflict-resolution.** If proposal A says "merge DR_SMITH and DR._J._SMITH" and proposal B says "move DR._J._SMITH to community X", these interact. Spec the dependency-ordered applier (merges first, then moves on the canonical name) now or punt to implementation?
5. **Contradiction detection.** Implicit (agent notices when recalling) or explicit (`consolidate` emits `contradiction` proposals)? Lean: **implicit in v1, explicit proposal kind in v2**.
6. **What happens when memory mode's `LLMConfig` is None but a feature needs it?** (e.g., `consolidate(generate_report=True)` on a project with no LLM.) Hard error or graceful no-op? Lean: **hard error with clear message — "configure llm or pass report_content explicitly"**.
7. **Cross-project federation.** Phase 2 feature, but API shape (`recall(projects=[...])`) affects the SDK design now. Lean: **single-project in v1, add `projects: list[str]` arg as no-op shim that takes 1-element list**.

---

## What we explicitly DID NOT decide to do

1. **A separate "memory store" data backend.** No new database. Same parquet + FAISS as KB mode.
2. **Synthetic text units that aren't backed by files.** Every observation is a file.
3. **Mandatory git.** Strongly recommended, but optional.
4. **Removing community generation entirely.** Just deferred / on-demand / agent-supplied for memory mode.
5. **Automatic Leiden re-clustering on every write.** `consolidate()` is manual and proposal-emitting.
6. **`grail memory <subcommand>` subcommand tree.** Replaced by `--memory` flag on `grail init` + mode-aware main verbs.
7. **Heavy LLM-judge dedup on every entity write.** Skill-prompt discipline (read before write) + cheap fast-path; LLM judging only inside `consolidate` proposals.
8. **Cross-project federation in v1.** Single-project queries first; federation later.

---

## Implementation order (when work starts)

### Phase 1 — Schema & loader (backward compatible)

1. **Schema migration** with sensible defaults so existing KB projects keep working unchanged:
   - `entities.observed_at`, `entities.confidence`, `entities.source`, `entities.community_ids` (list[str])
   - `relationships.relationship_type` (default `RELATED`), `relationships.observed_at`, `relationships.confidence`, `relationships.source`
   - `text_units.observed_at`, `text_units.confidence`, `text_units.source`
   - `documents.category`, `documents.tags`, `documents.attributes` (JSON)
2. **Frontmatter-aware loader**: `FileLoader` reads YAML frontmatter from `.md` files, lifts known keys into `documents` columns, strips frontmatter before chunking.
3. **`mode` field in `Config`** and `grail.yaml` (default `knowledge_base`).
4. **Tests**: every existing KB integration test must still pass with no changes.

### Phase 2 — Tools surface

1. `grail/memory/tools.py` module implementing the tool table above.
2. Validation contracts (warnings, next-steps) standardised in a `ToolResult` dataclass.
3. Each tool atomically mutates files (when applicable) + parquet + FAISS.
4. Make `LLMConfig` optional in `Config` (gracefully no-op LLM-dependent stages).
5. Pytest: prove an agent can write 1000 observations + recall them with zero LLM calls (only embedding calls).

### Phase 3 — Temporal recall mode + modifier composition

1. `recall` mode in `grail/query/` as a peer to cascade/local/global.
2. `--since`, `--before`, `--category`, `--tag`, `--min-confidence`, `--type`, `--entity` flags.
3. Modifier-prefix composition: `MemoryFilter` candidate-set arg added to local/cascade/global/document builders.
4. CLI: `grail query --mode recall ...` and `grail query --mode cascade --since 1h ...`.

### Phase 4 — Proposal generator (`consolidate`)

1. `grail/memory/consolidate.py` running the five internal analyses (Leiden, HDBSCAN, co-occurrence, edge-density, name-aliasing).
2. Proposal typing: `discover_community`, `split_folder`, `merge_aliases`, `add_community_membership`, `contradiction` (v2).
3. `output/proposals/<timestamp>.yaml` writer with `latest.yaml` symlink.
4. `list_proposals`, `accept_proposal`, `reject_proposal` tools.
5. Conflict-detection across pending proposals.
6. `archive/` on application.

### Phase 5 — Git integration + CLI mode flag + validation

1. `grail init <project> --memory [--git]` — scaffolds folder structure, writes memory-profile `grail.yaml`, optional `git init`.
2. Auto-commit hook (gated by `config.memory.auto_commit`).
3. `_history.jsonl` audit log.
4. Mode-aware command warnings (the table above).

### Phase 6 — Agent skills (per framework)

1. Claude Code skill: `remember`, `recall`, `forget`, `reflect`, `consolidate` tools that wrap the SDK + write the skill prompt enforcing the read-before-write discipline.
2. Hermes / Manus equivalents.
3. Generic MCP server exposing the SDK as MCP tools.

---

## What exists today that affects this work

Do NOT rebuild:

- **Incremental pipeline**: `grail/indexing/entities_relationships.py:append_extract`, `edit_extract`, `delete_extract` + `_merge_with_existing` + `_prune_orphan_entities`
- **Incremental community detection**: `grail/indexing/incremental_community.py` — used by KB mode; **bypassed in memory mode** because folder assignment is direct
- **Leiden**: `grail/indexing/leiden.py` — reused inside `consolidate()` as one of the proposal-generation signals
- **Cascade search**: `grail/query/cascade_search.py` — the right default for recall
- **`retrieval_queries`**: already extracts and embeds anticipated questions per entity
- **Source extraction**: `grail/query/retrieval.py:extract_source_references`
- **Agent loop with tool filtering**: `grail/query/agent.py:AgentSearch` with `enabled_tools: set[str]` — memory tools slot in alongside the existing search tools
- **Reporter protocol**: `grail/reporting/rich_reporter.py:Reporter`
- **FAISS cosine vector store**: `grail/vectorstores/faiss.py` — handles incremental adds
- **Document mapping**: `mapping.json` per-file metadata
- **Run manifest**: `grail/indexing/run_manifest.py` — memory uses "active run" pattern

---

## Key files to read before continuing

For a new session picking up this work:

1. **`grail/indexing/entities_relationships.py`** — `append_extract`, `edit_extract`, `_merge_with_existing`, `_prune_orphan_entities`.
2. **`grail/indexing/incremental_community.py`** — change-ratio threshold logic. Useful to understand why memory mode bypasses it.
3. **`grail/indexing/leiden.py`** — what we'll reuse inside `consolidate()`.
4. **`grail/config.py`** — `IndexingConfig`, `CommunityConfig`, `MANDATORY_ENTITY_TYPES`, `_normalize_entity_types`.
5. **`grail/query/cascade_search.py`** — how recall mode composes with text/cosine scoring.
6. **`grail/core.py`** — `append()`, `edit()`, `delete()` methods. Tool versions are simplified variants.
7. **`docs/search_modes.md`** — existing search modes. `recall` adds a new section AND a modifier flag on each existing mode.
8. **`docs/incremental_pipeline.md`** — explains current incremental design.
9. **`docs/cli_chat.md`** — the chat UI may become the agent's primary memory interface.

---

## Things to verify before writing code

1. **Does `FileLoader` handle markdown gracefully?** Check `grail/indexing/preprocess.py`. Frontmatter parsing is the only addition needed.
2. **Does `_merge_with_existing` handle agent-supplied `retrieval_queries`?** Yes (added in earlier session) — confirm dedup of queries list.
3. **FAISS incremental adds**: confirm `load_documents(overwrite=False)` appends.
4. **`text_embedding` field in `final_text_units.parquet`**: doesn't exist today; cascade re-embeds chunks at query time. Memory mode should pre-compute and cache. Add as part of Phase 1 schema migration.
5. **Observation file size**: short observations (<500 tokens) → one TU == one file. Longer ones chunk normally via `TokenTextSplitter`. Frontmatter parsed once, applied to all chunks of the file.
6. **`final_communities.entity_ids` already a list[str]?** Yes; we're adding a denormalised mirror on `final_entities`.
7. **Does `IncrementalCommunityExtractor` read `community.incremental_change_threshold` from config?** Verify; if hard-coded, fix before memory mode lands.

---

## Conversational notes that didn't make it into a doc but matter

Direction-setting opinions from the discussion:

- "GRAIL would be a *better* agentic-memory primitive than Letta/Zep/mem0 — those frameworks coupled themselves tightly to an OpenAI-style extraction step. GRAIL can step aside and let the calling agent own the extraction."
- "The current framework is vastly superior because it can assimilate RAG results, understand global references with communities, and understand cross-relationships between entities with nodes and edges. Memory mode must preserve all three."
- "Leiden was chosen because it made sense for batch indexing. Here we need different logic, same objective. Consolidate is a proposal, not a clustering."
- "Tools, not SDK direct calls. The agent should use tools that validate, warn, and suggest next steps. He knows he's in a memory system but uses tools instead of a full indexing logic."
- "The `retrieval_queries` mechanism is genuinely the differentiator. No competing memory framework embeds anticipated questions alongside content. This should be marketed."
- "Markdown frontmatter is the right schema for memory because it gives the user a human-editable surface that's also machine-parseable. Don't reinvent."
- "Git is the right versioning layer because it solves 5 problems at once: undo, branching, diff, distribution, conflict resolution. Don't reinvent."
- "Communities gain value once you have many memories. Below the threshold, the agent reads the memory doc directly. The bootstrap doesn't need a magnet community."
- "The agent can be instructed to create a smaller community and then even divide it if necessary — splitting and merging is just file moves plus an `update_community_report` call."

---

## Status (as of this revision, 2026-06-01)

- **Design**: tools-driven write path agreed; multi-membership schema agreed (Option 2); consolidate-as-proposals agreed; CLI flag agreed; recall mode + modifier composition agreed.
- **Implementation**: not started.
- **Open questions**: 7 items above, all with leaning answers; most are implementation-detail-level rather than framing-level.
- **Risk**: low — additive, backward-compatible, builds on proven incremental pipeline and search modes.
- **Estimated effort**: 4–6 focused days for Phases 1-5; Phase 6 (per-framework skills) open-ended.

A new session should read this file, scan the "Open questions" list, pick one or two to nail down with the user, then start Phase 1.
