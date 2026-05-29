# GRAIL as Agentic Memory — Design Context

> **Purpose**: A new Claude Code session continuing this thread should be able to read this single file and pick up the design discussion without needing the prior conversation history. Below is what we agreed, what we ruled out, what's still open, and the proposed order of implementation. **No code has been written for this feature yet** — only the framework that pre-existed (incremental pipeline, cascade search, agent tools, chat TUI) has shipped. Everything in this document is design-stage.

---

## TL;DR

GRAIL's existing incremental pipeline is closer to being a great agentic-memory primitive than initially appeared. The plan is **NOT a rewrite** — it's a series of additive, backward-compatible extensions:

1. Add `relationship_type`, `observed_at`, `confidence`, `source` columns to the parquet schema.
2. Make `FileLoader` read YAML frontmatter from markdown files.
3. Build a `grail/memory/` module with direct-write APIs that don't require an extraction LLM.
4. Make the indexing LLM optional in config (memory mode uses only embeddings).
5. Add temporal search as a peer to `cascade`/`local`/`global` modes.
6. Add `grail memory init` CLI to scaffold a memory project with the right defaults.
7. Community reports become markdown alongside parquet (agent-editable without LLM calls).

**Total estimate**: 2-3 days of focused work. The hard parts (incremental Leiden, source provenance, FAISS, retrieval_queries) are already done.

---

## What GRAIL already does well for memory

These are existing strengths that map perfectly to agentic memory needs — no changes required:

- **Incremental append with merge by entity name** — `append_extract()` in `grail/indexing/entities_relationships.py` merges new extractions into existing entities by uppercase name. Same agent observation referenced twice becomes one entity with two text_unit_ids attached. No duplication, no manual dedup needed.
- **Orphan pruning on edit** — `_prune_orphan_entities()` removes entities whose last text-unit reference is gone. This is exactly what's needed when an agent corrects/supersedes a memory.
- **Local Leiden re-run vs full re-cluster** — `IncrementalCommunityExtractor` measures change ratio (default 0.3) and only re-runs Leiden on the affected subgraph. This is the difference between sub-second memory writes and 30-second batch reindexing.
- **Per-event source provenance** — every text unit ID stays attached to every entity that came from it. Always know *when* the agent learned a fact.
- **`retrieval_queries` enrichment** — each entity stores 2-3 anticipated questions in its embedding text. For memory, "what could I ask later that this helps with?" is captured at write time. This is genuinely better than Letta/Zep/mem0 patterns that only embed the raw text.
- **Cascade search** — entity-gate + text rescue handles "this exact observation isn't in any top-K entity but matches keywords" cases. Critical for memory recall where exact entity matches are flaky.
- **Source extraction in API output** — `extract_source_references()` already returns `[{id, title, path}]` from any `context_data`. The agent can see which memory files contributed to a response.

---

## Where the current design hits friction for memory

Documented gaps that the new work addresses:

1. **`entity_types` is closed-set.** `IndexingConfig.entity_types` is validated with `MANDATORY_ENTITY_TYPES = ("PERSON", "ORGANIZATION")`. Extractions of unknown types pass through but there's no formal channel for the agent to register new types at runtime.
2. **Relationships are untyped.** Schema is `(source, target, description, weight)` — no `relationship_type` column. Typed edges (`WORKS_AT`, `OBSERVED_AT`, `SUPERSEDES`) are needed for structured recall.
3. **Community detection assumes settled graph.** Leiden + LLM report generation are batch operations. Even the incremental path makes 1 LLM call per affected community per append. At memory write frequency (100s/hour), this dominates cost.
4. **No notion of recency or decay.** All facts equal-weight at retrieval. Memory typically wants "what did I see in the last hour" to outrank "what I read 3 weeks ago".
5. **No contradiction detection.** Two opposing facts both get embedded as separate evidence.
6. **Append cost** — each observation = entity embeddings + (maybe) summarizer call to merge descriptions + (maybe) community report. Memory wants ~200ms writes.
7. **`entity_types` discovery only at batch time** — `create_entity_types()` works on a corpus sample, not on a live stream of observations.

---

## Agreed architecture: two modes from one codebase

```
                    ┌─────────────────────────────────────┐
                    │  GRAIL Core (unchanged)             │
                    │  parquet · FAISS · NetworkX         │
                    │  cascade · local · global · doc     │
                    └────────────┬────────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                │                                 │
        ┌───────▼───────┐               ┌─────────▼─────────┐
        │ KB profile     │               │ Memory profile     │
        │ - chunked docs │               │ - observations     │
        │ - LLM extract  │               │ - agent extract    │
        │ - eager reports│               │ - deferred reports │
        │ - cascade dflt │               │ - recall dflt      │
        └────────────────┘               └────────────────────┘
```

**Same store, two write paths.** The user could even index the same project in both modes simultaneously by running both pipelines against the same `output/`.

### Config flags that differ between the two profiles

| Config field | knowledge base | memory |
|---|---|---|
| `chunking.chunk_size` | 1200 | 200-400 (observations are short) |
| `community.regenerate_on_append` | `true` | `false` (deferred / on-demand) |
| `extraction.use_caller_llm` | `false` | `true` (caller-supplied extractions) |
| `extraction.allow_unknown_types` | `false` | `true` (open-set discovery) |
| `search.default_mode` | `cascade` | `recall` (new temporal mode) |
| `schema.time_columns` | optional | required |
| `git.auto_commit` | `false` | `true` (opt-in but default-on for memory) |

---

## The big architectural shift: agent-driven extraction

**This is the single most important insight from the discussion.**

Current model:
> GRAIL is a black box. User configures an LLM endpoint, GRAIL calls it for extraction, summarization, community reports. User pays for every LLM call.

Memory model:
> GRAIL is a graph store + embedding + retrieval layer. The *calling agent* does extraction because it already has the context, LLM access, and reasoning. GRAIL just persists and retrieves.

### Why this matters

- Today: indexing 100 chunks ≈ 150 LLM calls (extraction + summarization + reports)
- With agent-driven extraction: ≈ 0 LLM calls (only embeddings)
- For an agent making 1000 observations/day: difference between "expensive" and "negligible"

### What this requires

**1. Direct-write APIs that bypass the extraction LLM:**

```python
memory.add_entity(name, type, description, retrieval_queries=None, attributes=None)
memory.add_relationship(source, target, type, description, weight=1.0)
memory.add_observation(text, entities=[...], relationships=[...])  # bundle
memory.update_entity(name, **fields)
memory.delete_entity(name)  # records SUPERSEDED_BY relationship, doesn't hard-delete
memory.set_community_report(community_id, title, full_content, findings)
```

**2. `LLMConfig` optional in `grail.yaml`.** Memory mode requires only `EmbeddingsConfig`. Every LLM-call site checks `if config.llm is None: skip` or `delegate to caller`.

**3. The summarizer, community report generator, and description-merger all become optional pipeline stages** that no-op when no LLM is configured.

### Why this differentiates GRAIL from existing memory frameworks

Letta, Zep, mem0 hard-couple to an OpenAI-style extraction step. GRAIL can offer both:
- "Just tell me what to store" path (agent-driven, free)
- "Read this document and figure out what's in it" path (LLM-driven, requires config)

Both modes from one codebase.

---

## The big workflow shift: memory is markdown files, GRAIL is the index

The cleanest mental model. Every observation is a markdown file under `memories/`. We never invent a "synthetic text unit" abstraction.

- **Agent writes**: `memories/work/clients/acme/2026-05-27T15-30_meeting_notes.md`
- **GRAIL indexes**: standard pipeline picks up the file, chunks, extracts (or accepts caller-supplied extractions), embeds, updates FAISS. Provenance preserved through `document_ids`.
- **Agent re-reads**: just opens the file. Convenience wrapper `memory.read(key)` available.
- **Agent edits**: overwrites the file. `edit_extract` re-processes only affected chunks.

### Why files-as-source-of-truth

1. **Edit-by-key replaces append-with-duplication.** Filename = `<ISO_timestamp>_<title_slug>.md`. Agent looks up by slug, edits in place. No "did I already write this?" check needed.
2. **Long memories work naturally.** A 500+ token observation is just a longer markdown file. No special handling.
3. **Git versioning becomes trivial.** Files in a git repo → every commit is a memory snapshot. Branches = parallel memory streams. `git diff` = memory delta.
4. **Agent has filesystem access already.** No special tool needed for read-back; the agent's `read_file` tool works directly.
5. **The "synthetic TU" abstraction disappears.** Cleaner, less to maintain.

---

## Proposed folder structure

```
my-workspace/
├── work-memory/                       ← one memory project
│   ├── grail.yaml                     (memory profile)
│   ├── .git/                          (auto-init, auto-commit when enabled)
│   ├── memories/                      ← THE source of truth
│   │   ├── work/
│   │   │   ├── clients/
│   │   │   │   └── acme/
│   │   │   │       ├── 2026-05-27T15-30_meeting_notes.md
│   │   │   │       └── 2026-05-28T09-15_followup_email.md
│   │   │   └── projects/
│   │   │       └── grail-redesign/
│   │   └── personal/
│   ├── output/                        ← derived; safe to delete & reindex
│   │   ├── current.json
│   │   └── runs/<id>/
│   │       ├── final_entities.parquet
│   │       ├── final_relationships.parquet
│   │       ├── final_text_units.parquet
│   │       ├── final_communities.parquet
│   │       └── community_reports/     ← markdown one-per-community,
│   │           ├── C42.md             agent-editable
│   │           └── C43.md
│   ├── faiss/
│   └── _history.jsonl                 ← append-only audit log (timestamp,
│                                         file, operation, git SHA)
│
├── personal-memory/
│   └── ...
│
└── client-acme-kb/                    ← knowledge base, same project shape
    ├── grail.yaml                     (kb profile)
    ├── input/                         ← instead of memories/, batch-indexed
    │   ├── contracts.pdf              source docs
    │   └── product_spec.pdf
    └── output/
```

The differences between memory and KB projects:
- `memories/` (hierarchical, agent-writable) vs `input/` (flat, batch-loaded)
- `grail.yaml` profile (memory vs kb)
- Community reports stored as markdown alongside parquet (memory) vs only parquet (KB) — though we may always do both
- `_history.jsonl` audit log (memory) vs run-folder manifests (KB)

---

## Frontmatter convention for observation files

Each markdown observation has YAML frontmatter that the loader lifts into the `documents` parquet as columns:

```markdown
---
title: Meeting with Acme
category: work/clients/acme
tags: [meeting, pricing, Q2]
observed_at: 2026-05-27T15:30:00Z
confidence: 0.9
source: agent-claude
related_to: [acme, john_smith]    # optional entity-name hints for extraction
---

# Meeting with Acme

John said pricing should drop 15% for Q2. Sarah pushed back...
```

The body (after the frontmatter delimiter) becomes the text content for chunking. The frontmatter keys we plan to recognize:

- `title` — display name; used to derive the filename slug
- `category` — primary folder path (mirrors actual folder; redundancy is OK)
- `tags` — many-to-many labels for filtering at recall time
- `observed_at` — ISO 8601 timestamp; used for recency-decay scoring
- `confidence` — 0.0-1.0, defaults to 1.0
- `source` — who/what produced this observation (`agent-claude`, `user`, etc.)
- `related_to` — optional entity-name hints to help the LLM extraction (or to force entity links when agent-driven)

Unknown frontmatter keys are preserved into a JSON column `attributes` for future use.

---

## Bounded relationship-type vocabulary

Concern: free-text relationship types explode in cardinality. Solution: closed-set defaults + configurable extension.

**Default vocabulary (~12 types)**:
`MENTIONS`, `WORKS_AT`, `OWNS`, `LOCATED_IN`, `CAUSES`, `PART_OF`, `CONTRADICTS`, `SUPERSEDES`, `OBSERVED_AT`, `ASSOCIATED_WITH`, `DEPENDS_ON`, `RELATED` (fallback for "I'm not sure").

**Configurable extension**: `IndexingConfig.relationship_types` mirrors `entity_types` — users add domain-specific types (`PRESCRIBED_FOR`, `MERGES_WITH`) up to a cap (~25 total).

**Dedup key extension**: relationships dedup by `(src, tgt)` today. With types, it becomes `(src, tgt, type)`. So a `WORKS_AT` and `OWNS` between the same pair are separate edges.

**Why typed edges matter for memory recall**:

Recalling "tell me about Alice" with typed edges produces:
```
Alice WORKS_AT Acme · LOCATED_IN Berlin · OBSERVED_AT 2026-05-26
```
Instead of a paragraph of free-text relationship descriptions. Much cheaper for the agent to consume.

---

## New search mode: `recall` (temporal)

Not a filter — a peer mode to cascade/local/global.

```bash
grail recall <project> --since "1 hour ago"           # all observations
grail recall <project> --since 7d --type PERSON       # filtered by entity type
grail recall <project> --before "yesterday" --entity ALICE
grail recall <project> --category work/clients/**     # path glob
grail recall <project> --tag pricing --min-confidence 0.7
```

Pure SQL-style filters over the `observed_at`, `category`, `tags`, `confidence` columns. No LLM call, no embedding call required for the pure-temporal case.

Composable with cascade: `recall --mode cascade --since 1h --query "what did acme say"` runs cascade over only the temporally-filtered candidate pool.

---

## Community reports — agent-editable, two paths

The agent decides when to incur LLM cost:

**Option 1: GRAIL generates the report (LLM cost):**
```python
memory.consolidate(community_id="auto")    # all affected since last consolidation
memory.consolidate(community_id="C42")     # one specific community
```

**Option 2: Agent generates from its own context (no LLM cost):**
```python
memory.set_community_report(
    community_id="C42",
    title="Acme client interactions",
    full_content="# Acme client interactions\n\n...",
    findings=[...],
)
```

The agent typically already has the chunks in context (just retrieved them). Writing the report is free at that point.

Reports get cached in BOTH `final_community_reports.parquet` AND `output/runs/<id>/community_reports/C42.md`. The markdown is the agent-editable surface; the parquet is the cache for fast retrieval.

**Open question**: do we always co-store as markdown (for all projects, KB + memory), or only in memory mode? Lean toward always — KB users would benefit from being able to hand-edit a wrong report too.

---

## Git as the versioning layer

**Strongly recommended, made one-command easy, but not mandatory.**

Why not mandatory:
- Sandbox environments (ephemeral containers, Lambdas) may not have git.
- The memory folder may live inside an existing git repo with its own conventions.

But `grail memory init --git` (default on) would:
- `git init` the project
- Auto-commit on every observation/edit/delete via `config.memory.auto_commit`
- Auto-tag on every `consolidate()`
- Append the commit SHA to `_history.jsonl`

The agent then has `git log`, `git diff`, `git show <SHA>` to reason about its own memory evolution. Branches enable "what if I had observed this differently?" experiments. This is the deepest possible separation between memory state and inference logic.

---

## Multiple memory projects per agent — the workspace concept

An agent operates in a *workspace* of one or more GRAIL projects:

```python
memory.remember(project="work-memory", text="...")
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

**Agents are bad at consistent taxonomy.** Left alone they create `work/`, `Work/`, `business/`, `client_work/` for the same conceptual bucket. The folder tree degrades into noise after a few hundred observations.

**Three signals to combine**:
1. **Folder = primary category** (agent picks 1 from a small bounded list)
2. **Markdown frontmatter tags** (many-to-many)
3. **The graph itself** (entities + community detection cluster semantically regardless of folder)

The skill prompt should instruct: *"Before writing, call `list_categories()` to see existing categories. Reuse one if it fits. Only create a new category if nothing fits."* Bounds drift without enforcing a rigid schema.

`recall` then supports both: `--category work --tag pricing` (filesystem-style) AND `--query "pricing discussions with acme"` (semantic).

---

## Run management — observations don't create runs

The `output/runs/<id>/` convention was designed for batch reindexing. Memory writes happen against a single mutable run (the "active" run).

Proposed:
- Observation writes update the active run in place.
- Audit trail lives in `_history.jsonl` (append-only) with `{timestamp, file_path, operation, git_sha?}` per line.
- `grail memory reindex` creates a fresh run if the user wants a clean rebuild.

---

## Open questions still to decide

These didn't get fully resolved in the design discussion and should be settled before implementation:

1. **Frontmatter convention finalization** — exact key names, what's required vs optional, what happens with unknown keys.
2. **Community reports as markdown — when?** Always (memory + KB) or only memory? Leaning "always" but not decided.
3. **How does cross-project federation work?** Phase 2 feature, but the API shape (`recall(projects=[...])`) affects the SDK design now.
4. **`add_observation` API shape when extraction is agent-supplied** — does the agent pass `entities=[...], relationships=[...]` as Python dicts, or as a separate JSON file alongside the markdown, or as a special frontmatter section?
5. **What's the dedup story for agent-supplied entities?** If the agent calls `add_entity("Alice", "PERSON", ...)` twice with slightly different descriptions, do we merge? Do we trust the agent's name uppercase normalization? Probably reuse the existing `_merge_with_existing` logic.
6. **How does the contradiction-detection feature work?** Implicit (agent notices when recalling) or explicit (GRAIL flags conflicts)? Probably implicit for v1.
7. **What happens when memory mode's `LLMConfig` is None but a user calls a feature that needs it?** (e.g., `consolidate(auto=True)` on a project with no LLM configured.) Hard error or graceful no-op?

---

## What we explicitly DID NOT decide to do

These were considered and rejected:

1. **A separate "memory store" data backend.** No new database. Same parquet + FAISS as KB mode.
2. **Synthetic text units that aren't backed by files.** The markdown-as-source-of-truth model dissolves this — every observation is a file.
3. **Mandatory git.** Strongly recommended, but optional.
4. **Removing community generation entirely.** Just deferred / on-demand / agent-supplied for memory mode.
5. **Tools-first design.** The SDK comes first. Tools/skills for specific frameworks (Claude Code, Hermes, Manus) come after the SDK proves out.
6. **Cross-project federation in v1.** Single-project queries first; federation later if needed.

---

## Implementation order (when work starts)

When the user is ready to start coding, this is the proposed sequence:

### Phase 1 — Schema & loader (backward compatible)

1. **Schema migration**: add columns to existing parquets, all with sensible defaults so existing KB projects keep working unchanged.
   - `entities.observed_at`, `entities.confidence`, `entities.source`
   - `relationships.relationship_type`, `relationships.observed_at`, `relationships.confidence`, `relationships.source`
   - `text_units.observed_at`, `text_units.confidence`, `text_units.source`
   - `documents.category`, `documents.tags`, `documents.attributes` (JSON)
2. **Frontmatter-aware loader**: `FileLoader` reads YAML frontmatter from `.md` files, lifts known keys into `documents` columns, strips frontmatter before chunking.
3. **Tests**: every existing KB integration test must still pass with no changes.

### Phase 2 — Memory SDK (no CLI yet)

1. `grail/memory/` module with direct-write APIs (no LLM required):
   - `MemoryProject(path)` — opens or creates a project
   - `add_observation(title, content, category, tags, ...)` — writes file + triggers incremental index
   - `update_observation(slug, content)` — overwrites file + re-extracts
   - `delete_observation(slug, reason)` — records SUPERSEDED_BY, removes file
   - `add_entity(name, type, description, ...)` — direct entity write
   - `add_relationship(source, target, type, ...)` — direct relationship write
   - `set_community_report(community_id, ...)` — agent-supplied report
   - `recall(query, mode="cascade", since=None, before=None, category=None, tag=None, min_confidence=None)`
   - `list_categories()`, `list_observations(category=None)`, `list_projects()`
2. Make `LLMConfig` optional in `Config` (gracefully no-op LLM-dependent stages).
3. Pytest: prove an agent can write 1000 observations + recall them with zero LLM calls (only embedding calls).

### Phase 3 — Temporal recall mode

1. `recall` as a peer mode to `cascade`/`local`/`global`.
2. `--since`, `--before`, `--category`, `--tag`, `--min-confidence`, `--type` flags.
3. Compose-able with cascade (`--mode cascade --since 1h`).

### Phase 4 — Git integration + CLI

1. `grail memory init <project> [--git]` — scaffolds folder structure, writes memory-profile `grail.yaml`, optional `git init`.
2. Auto-commit hook (gated by `config.memory.auto_commit`).
3. `_history.jsonl` audit log.
4. `grail memory consolidate <project>` — manual community-report regeneration (when LLM is configured).

### Phase 5 — Agent tools (per framework)

1. Claude Code skill: `remember`, `recall`, `forget`, `reflect` tools that wrap the SDK.
2. Hermes / Manus equivalents.
3. Generic MCP server exposing the SDK as MCP tools.

---

## What exists today that affects this work

The framework already has these pieces; the agentic memory work builds on them. Do NOT rebuild:

- **Incremental pipeline**: `grail/indexing/entities_relationships.py:append_extract`, `edit_extract`, `delete_extract` + `_merge_with_existing` + `_prune_orphan_entities`
- **Incremental community detection**: `grail/indexing/incremental_community.py:update`, `incremental_edit`, `incremental_delete` (change-ratio threshold, label propagation, local Leiden re-run)
- **Cascade search**: `grail/query/cascade_search.py` — entity-gate + text rescue. The right default for recall.
- **`retrieval_queries` on entities**: `grail/indexing/entities_relationships.py` + `grail/prompts/builtin/entity_relation.py` — already extracts and embeds anticipated questions per entity.
- **Source extraction**: `grail/query/retrieval.py:extract_source_references` — returns `[{id, title, path}]`. Used by chat API; same shape works for memory recall results.
- **Agent loop with tool filtering**: `grail/query/agent.py:AgentSearch` with `enabled_tools: set[str]`. Memory tools slot in alongside the four existing search tools.
- **Reporter protocol**: `grail/reporting/rich_reporter.py:Reporter` — already a clean injection point. Memory operations should emit progress through this.
- **FAISS vector store with cosine**: `grail/vectorstores/faiss.py` — handles incremental adds. No changes needed.
- **Document mapping**: `mapping.json` writes per-file metadata. Frontmatter-aware loader extends this.
- **Run manifest**: `grail/indexing/run_manifest.py` — tracks runs. Memory uses the "active run" pattern (single mutable run + audit log) rather than creating new runs.

---

## Key files to read before continuing

For a new session picking up this work:

1. **`grail/indexing/entities_relationships.py`** — especially `append_extract`, `edit_extract`, `_merge_with_existing`, `_prune_orphan_entities`. Understand the incremental flow.
2. **`grail/indexing/incremental_community.py`** — change-ratio threshold logic.
3. **`grail/config.py`** — `IndexingConfig`, `MANDATORY_ENTITY_TYPES`, `_normalize_entity_types`. Understand where to plug in `relationship_types`, `observed_at`, etc.
4. **`grail/query/cascade_search.py`** — to understand how recall mode would compose with text/cosine scoring.
5. **`grail/core.py`** — `append()`, `edit()`, `delete()` methods. Memory ops are simplified variants.
6. **`docs/search_modes.md`** — the existing search modes doc. The `recall` mode would be a new section.
7. **`docs/incremental_pipeline.md`** — explains the current incremental design. Memory builds on this.
8. **`docs/cli_chat.md`** — the CLI chat doc. The chat UI could become the agent's primary memory interface (the chat IS the agent).

---

## Things to verify before writing code

1. **Does `FileLoader` already handle markdown gracefully?** Check `grail/indexing/preprocess.py` for `.md` handling. Frontmatter parsing is the only addition needed.
2. **Does `_merge_with_existing` handle agent-supplied retrieval_queries?** Yes (this was added in an earlier session) — confirm the merge logic deduplicates the queries list.
3. **How does FAISS handle incremental adds?** Check `grail/vectorstores/faiss.py:load_documents` — does it accept `overwrite=False` to append? (Answer was yes when last looked, but verify.)
4. **What's the current state of the `text_embedding` field in `final_text_units.parquet`?** Earlier sessions noted it doesn't exist — cascade re-embeds chunks at query time. Memory mode should pre-compute and cache these to avoid recurring embedding cost on every recall. Add as part of Phase 1 schema migration.
5. **Are observation files small enough that one TU == one file?** Yes for short observations (<500 tokens). Longer ones get chunked normally by `TokenTextSplitter`. The frontmatter is parsed once and applied to all chunks of that file.

---

## Conversational notes that didn't make it into a doc but matter

These are direction-setting opinions from the discussion:

- "GRAIL would be a *better* agentic-memory primitive than Letta/Zep/mem0 — those frameworks coupled themselves tightly to an OpenAI-style extraction step. GRAIL can step aside and let the calling agent own the extraction."
- "Two-day estimate is a focused 2 days, not a calendar 2 days. The schema migration alone is ~100 lines but it touches every test."
- "The `retrieval_queries` mechanism is genuinely the differentiator. No competing memory framework embeds anticipated questions alongside content. This should be marketed."
- "Markdown frontmatter is the right schema for memory because it gives the user a human-editable surface that's also machine-parseable. Don't reinvent."
- "Git is the right versioning layer because it solves 5 problems at once: undo, branching, diff, distribution, conflict resolution. Don't reinvent."
- "Don't design tools first. SDK first, then tools for each framework. Otherwise the tool API constrains the SDK."

---

## Status (as of this prompt)

- **Design**: agreed at the framing level
- **Implementation**: not started
- **Open questions**: 7 items above, all needing user input before code
- **Risk**: low — additive, backward-compatible, builds on proven incremental pipeline
- **Estimated effort**: 2-3 focused days for Phases 1-4; Phase 5 (per-framework tools) is open-ended

A new session should read this file, then ask the user which of the 7 open questions to settle before starting Phase 1.
