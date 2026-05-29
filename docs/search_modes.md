# GRAIL — Indexing Pipeline & Search Modes

---

## Part 1: The Indexing Pipeline

Before any search can happen, `grail index` processes your source documents
through a multi-stage pipeline that builds a knowledge graph and all the
artifacts search depends on.  Every search mode reads from these artifacts —
understanding how they're built explains why each mode works the way it does.

### Pipeline Overview

```
SOURCE FILES (PDF, DOCX, TXT, MD, CSV, ...)
  │
  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 1: File Loading & Chunking                                    │
│                                                                      │
│  FileLoader reads each file, preprocesses non-text formats           │
│  (PDF → text via pypdf, DOCX → text via python-docx), then          │
│  splits into overlapping token-based chunks (text units).            │
│                                                                      │
│  Produces:                                                           │
│    partial_text_units.parquet  — chunks with document back-pointers  │
│    final_docs.parquet          — one row per source file             │
│    mapping.json                — doc_id → {title, path, extension}   │
└──────────────────────────────────────────┬───────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 2: Entity & Relationship Extraction                           │
│                                                                      │
│  Each chunk is sent to the LLM with the entity_relation prompt.      │
│  The LLM reads the chunk and outputs structured tuples:              │
│                                                                      │
│    ("entity"<|>NAME<|>TYPE<|>DESCRIPTION<|>RETRIEVAL_QUERIES)        │
│    ("relationship"<|>SOURCE<|>TARGET<|>DESCRIPTION<|>STRENGTH)       │
│                                                                      │
│  The parser collects all entities and relationships across chunks,   │
│  deduplicates by name (entities) and by sorted endpoint pair         │
│  (relationships), and tracks which chunks and documents each         │
│  entity/relationship appears in.                                     │
│                                                                      │
│  Entities with multiple descriptions (from different chunks) are     │
│  sent to the summarizer for a merged single description.             │
│                                                                      │
│  Produces:                                                           │
│    final_entities.parquet       — deduplicated entities with          │
│                                   description, retrieval_queries,    │
│                                   text_unit_ids, document_ids        │
│    final_relationships.parquet  — deduplicated relationships         │
│    final_text_units.parquet     — chunks annotated with entity_ids   │
│                                   and relationship_ids               │
│    entity_relationship_graph.graphml — NetworkX graph                │
└──────────────────────────────────────────┬───────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 3: Entity Embedding                                           │
│                                                                      │
│  Each entity is embedded as a single vector:                         │
│                                                                      │
│    embed("ENTITY_NAME: description query1 query2 query3")            │
│                                                                      │
│  The retrieval_queries from the extraction prompt are concatenated    │
│  with the description so the embedding captures not just what the    │
│  entity IS, but what questions it helps answer.                      │
│                                                                      │
│  Embeddings are stored in final_entities.parquet (description_       │
│  embedding column) and indexed in FAISS for fast ANN search.         │
│                                                                      │
│  Produces:                                                           │
│    description_embedding column in final_entities.parquet             │
│    faiss/entity_descriptions.{faiss,json}                            │
└──────────────────────────────────────────┬───────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 4: Community Detection                                        │
│                                                                      │
│  Hierarchical Leiden clustering on the entity-relationship graph.     │
│  Groups entities into thematic communities at multiple hierarchy      │
│  levels.  The coarsest level produces the fewest, broadest            │
│  communities.                                                        │
│                                                                      │
│  Produces:                                                           │
│    final_nodes.parquet         — entity → community assignments      │
│    final_communities.parquet   — community membership lists          │
└──────────────────────────────────────────┬───────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 5: Community Report Generation                                │
│                                                                      │
│  For each community, the LLM receives all entities + relationships   │
│  in that community and generates a structured report with:           │
│    - title, summary                                                  │
│    - findings (structured list with explanation + evidence)           │
│    - rank (1-10 importance rating)                                   │
│    - full_content (markdown narrative)                                │
│                                                                      │
│  These reports are the ONLY artifacts global search uses.             │
│                                                                      │
│  Produces:                                                           │
│    final_community_reports.parquet                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### How Each Search Mode Uses the Pipeline

The indexing pipeline produces artifacts at different stages, and each
search mode depends on a different subset:

```
                          local  cascade  global  document  agent
                          ─────  ───────  ──────  ────────  ─────
Stage 1: Chunks            ✓       ✓              ✓         ✓
Stage 2: Entities/Rels     ✓       ✓              ✓         ✓
Stage 3: Embeddings        ✓       ✓              ✓         ✓
Stage 4: Communities       ✓       ✓                        ✓
Stage 5: Reports           ✓       ✓       ✓               ✓
         BM25 on chunks            ✓                        
         Chunk cosine              ✓                        
```

**Local** uses stages 1-5: entity embeddings to find entities, the graph
structure for relationships, communities for thematic context, and text
units for source text.

**Cascade** uses everything local uses, plus direct text scoring (BM25 and
cosine) on all chunks — this is the "text rescue" path that catches what
the entity gate misses.

**Global** uses only stage 5: community reports.  It never touches entities,
chunks, or the graph directly.  This is why it excels at broad thematic
questions but fails at specific factual queries.

**Document** uses stages 1-3, scoped to a single document.  No community
context because communities span across documents.

**Agent** delegates to the other modes, so it transitively uses all stages.

---

## Part 2: Search Modes

GRAIL offers five search modes, each designed for a different retrieval
strategy.  All modes read from the same set of parquet artifacts produced
during `grail index`.  The choice of mode determines which artifacts are
used, how chunks are selected for the LLM context, and how the final
answer is generated.

---

## Artifacts Reference

Every `grail index` run produces these files under `output/runs/<run_id>/`:

| File | Key Columns | Produced By |
|---|---|---|
| `final_entities.parquet` | `id`, `name`, `type`, `description`, `retrieval_queries`, `description_embedding`, `text_unit_ids`, `document_ids`, `degree` | Entity extraction + summarization |
| `final_relationships.parquet` | `id`, `source`, `target`, `description`, `weight`, `text_unit_ids`, `document_ids`, `rank` | Relationship extraction |
| `final_text_units.parquet` | `id`, `text`, `n_tokens`, `document_id`, `document_ids`, `entity_ids`, `relationship_ids` | File chunking + annotation |
| `final_nodes.parquet` | `title`, `community`, `level`, `degree` | Community detection (Leiden) |
| `final_communities.parquet` | `id`, `title`, `level`, `entity_ids`, `relationship_ids` | Community detection |
| `final_community_reports.parquet` | `community`, `title`, `summary`, `full_content`, `rank`, `findings` | LLM-generated community summaries |
| `final_docs.parquet` | `id`, `title`, `path`, `text_unit_ids` | File loader |
| `mapping.json` | `{doc_id: {title, original_path, extension, ...}}` | File loader |
| `entity_relationship_graph.graphml` | NetworkX graph of all entities + RELATED edges | Entity extraction |
| FAISS index (`faiss/entity_descriptions.{faiss,json}`) | Entity description embeddings indexed for ANN search | Entity extraction |

### Column Details

**`description_embedding`** (entities) — Vector embedding of
`"ENTITY_NAME: description retrieval_query_1 retrieval_query_2 ..."`.
Computed during indexing and cached in the parquet.  This is the primary
signal for entity retrieval across local, cascade, document, and agent modes.

**`retrieval_queries`** (entities) — List of 2-3 natural-language questions
generated by the LLM during entity extraction.  These questions reflect what
a user might ask that the entity's source text helps answer.  They are
concatenated into the embedding text to improve query-to-entity similarity.

**`entity_ids`** (text_units) — List of entity names mentioned in each chunk.
This is the link between entities and chunks — the "entity gate" that local
search uses to select which chunks to include in the context.

**`text_unit_ids`** (entities) — Reverse link: which chunks mention this entity.

**`document_ids`** (entities, relationships, text_units) — Back-pointer to the
originating source file(s).  Surfaces in the context text via `<source>` XML
tags so the LLM can cite sources.

---

## Mode 1: Local Search

```
grail query <project> "question" --mode local
```

The default mode.  Uses the knowledge graph to find entities relevant to the
query, then assembles context from those entities' neighborhoods.

### How It Works

```
Query
  │
  ▼
Embed query (with conversation history for context)
  │
  ▼
Cosine similarity: query embedding vs entity description_embeddings
  │  (via FAISS index or pandas scan)
  │
  ▼
Top-K entities (default 10)
  │
  ├─► Entity context     ─── name, type, description (CSV in <entities> tags)
  ├─► Relationship context ── edges between selected entities (CSV in <relationships> tags)
  ├─► Community context   ─── reports for communities the entities belong to (<reports> tags)
  └─► Text unit context   ─── chunks that mention selected entities (<source> tags with document_id)
  │
  ▼
Token-budgeted context assembly (entity:rel:community:text proportional split)
  │
  ▼
LLM generates answer using local_search prompt
```

### Artifacts Used

| Artifact | How |
|---|---|
| `final_entities.parquet` | `description_embedding` for similarity search; `name`, `type`, `description` for entity context |
| `final_relationships.parquet` | In-network (both endpoints selected) and out-network edges for relationship context |
| `final_text_units.parquet` | Filtered by `entity_ids` overlap with selected entity names; ranked by overlap count |
| `final_nodes.parquet` | Maps entity → community for scoping community reports |
| `final_community_reports.parquet` | `full_content` or `summary` for relevant communities |
| `final_docs.parquet` + `mapping.json` | Resolves `document_ids` to titles for `<source>` tags |
| FAISS index | Fast ANN lookup for entity similarity |

### The Entity Gate

The critical mechanism: text units are selected based on whether their
`entity_ids` list overlaps with the top-K entity names.  This is efficient
and leverages graph structure, but fails when:

- The answer chunk doesn't mention any of the top-K entities
- The top-K entities are too generic and match too many chunks
- The entity `description_embedding` doesn't align with query intent

The `retrieval_queries` enrichment addresses the third failure by embedding
user-oriented questions alongside the entity description.

### Token Budget

The `max_tokens` budget (default 32,000) is split proportionally:

```
local_prop = 1.0 - community_prop - text_unit_prop
           = 1.0 - 0.1 - 0.5 = 0.4

entity budget     = max_tokens × local_prop / 2     = 6,400
relationship budget = max_tokens × local_prop / 2   = 6,400
community budget  = max_tokens × community_prop     = 3,200
text unit budget  = max_tokens × text_unit_prop      = 16,000
```

### Config

```yaml
search:
  local_search_endpoint: deepinfra
  local_search_model: Qwen/Qwen3-32B
  local_max_tokens: 32000
  local_top_k_entities: 10
  local_text_unit_prop: 0.5
  local_community_prop: 0.1
  local_conversation_history_max_turns: 5
  use_community_summary: false    # false = full_content, true = one-line summary
  response_max_tokens: 16384
```

### Optional: Reranker

When `reranker.enabled: true`, local search over-fetches entities
(`top_k × overfetch_factor`) by vector similarity, then uses a cross-encoder
model to re-rank `(query, entity_description)` pairs and trim to the best
`top_k`.  Text units can also be reranked.

```yaml
reranker:
  enabled: true
  endpoint: deepinfra
  model: Qwen/Qwen3-Reranker-0.6B
  overfetch_factor: 3
  rerank_entities: true
  rerank_text_units: true
```

---

## Mode 2: Global Search

```
grail query <project> "question" --mode global
```

Answers broad, thematic questions by synthesizing across all community reports.
Does not use entity similarity, chunk retrieval, or the knowledge graph directly.

### How It Works

```
Query
  │
  ▼
Load all community reports (sorted by rank descending)
  │
  ▼
Fit check: total report tokens vs chunk_size
  │
  ├── Fits in one chunk ──► Single-pass reduce (one LLM call)
  │
  └── Exceeds chunk_size ──► Map-reduce:
       │
       ├── MAP: each chunk → extract scored key points (JSON)
       │   (N parallel LLM calls, concurrency-limited)
       │
       ├── Aggregate: sort all points by score descending
       │
       └── REDUCE: synthesize final answer from top points
           (one LLM call)
```

### Artifacts Used

| Artifact | How |
|---|---|
| `final_community_reports.parquet` | `full_content` or `summary` + `rank` for context |

No entity embeddings, no text units, no graph traversal.  Global search
operates entirely on the pre-computed community summaries.

### Config

```yaml
search:
  global_search_endpoint: deepinfra
  global_search_model: Qwen/Qwen3-32B
  global_chunk_size: 100000       # tokens per map chunk
  global_map_max_tokens: 2048     # per-chunk map output
  global_reduce_max_tokens: 8192  # reduce phase output
  global_concurrency: 5           # parallel map calls
```

---

## Mode 3: Document Search

```
grail query <project> "question" --mode document --document "filename.pdf"
```

Scoped retrieval within a single document.  Finds entities and text units
that belong to the specified document, then builds context from that subset.

### How It Works

```
Query + document identifier (filename, path, or doc ID)
  │
  ▼
Resolve document: match against final_docs by id/path/title
  │
  ▼
Scope all artifacts to this document:
  entities  → filter by document_ids containing doc_id
  relationships → filter by both endpoints being in scoped entities
  text_units → filter by document_id == doc_id
  │
  ▼
Same as local search from here, but on the scoped subset:
  embed query → entity similarity → context assembly → LLM
  │
  ▼
No community context (communities span documents)
```

### Artifacts Used

| Artifact | How |
|---|---|
| `final_docs.parquet` | Resolve document identifier to doc_id |
| `final_entities.parquet` | Filtered to entities with `document_ids` containing the target doc |
| `final_relationships.parquet` | Filtered to edges within scoped entities |
| `final_text_units.parquet` | Filtered to `document_id == target_doc` |
| `mapping.json` | Document path resolution |
| FAISS index | Entity similarity (with ID prefilter to scoped entities) |

### Config

```yaml
search:
  document_search_endpoint: deepinfra      # fallback: local_search_endpoint
  document_search_model: Qwen/Qwen3-32B   # fallback: local_search_model
  document_search_max_tokens: 8192
  document_search_response_max_tokens: 16384
```

---

## Mode 4: Cascade Search

```
grail query <project> "question" --mode cascade
```

Hybrid retrieval that combines the entity-gated approach (GRAIL's graph
structure) with direct text matching (RAG's lexical strength).  Designed to
solve the "entity gate excludes the answer chunk" failure pattern.

### How It Works

```
Query
  │
  ▼
Embed query
  │
  ├──────────────────────────────────────────────┐
  ▼                                              ▼
ENTITY GATE                                TEXT SCORING
  │                                              │
  ▼                                              ▼
Top-15 entities by                        BM25(query, chunk_text)
description_embedding                     + cosine(query_emb, chunk_emb)
cosine similarity                         for ALL chunks
  │                                              │
  ▼                                              │
Collect chunks that                              │
mention these entities                           │
  │                                              │
  ▼                                              ▼
RE-RANK entity-gated chunks ◄──── text scores override entity overlap
  │
  ▼
RESCUE: inject top-5 text-scored chunks NOT in entity pool
  │
  ▼
Merged candidate pool (entity-gated + rescued), sorted by text score
  │
  ▼
Context assembly (same as local: entities, relationships, communities, text units)
  │
  ▼
LLM generates answer
```

### Why Cascade Exists

Local search fails when the answer chunk has no entity overlap with the
query's top entities (Failure Pattern 1).  Pure RAG works for these cases
but loses the graph structure that helps with multi-hop and relationship
questions.  Cascade uses the entity gate as the primary candidate source
and falls back to text matching when the gate misses.

### Artifacts Used

| Artifact | How |
|---|---|
| `final_entities.parquet` | `description_embedding` for entity similarity |
| `final_text_units.parquet` | All chunks scored by BM25 + cosine; entity-gated subset + rescue |
| `final_relationships.parquet` | Relationship context for selected entities |
| `final_nodes.parquet` | Entity → community mapping |
| `final_community_reports.parquet` | Community reports for selected entities |
| `final_docs.parquet` + `mapping.json` | Document title resolution |
| FAISS index | Entity similarity |

### Performance Note

Cascade currently embeds all text units at query time for the cosine
scoring path.  A future optimization is to pre-compute and cache chunk
embeddings during indexing as `text_embedding` in `final_text_units.parquet`,
matching how entity embeddings are already cached in `description_embedding`.

### Config

Cascade reuses the `local_search_*` config fields:

```yaml
search:
  local_search_endpoint: deepinfra
  local_search_model: Qwen/Qwen3-32B
  local_max_tokens: 32000
  local_top_k_entities: 15        # cascade uses more candidates than local
  local_text_unit_prop: 0.5
  local_community_prop: 0.1
```

---

## Mode 5: Agent Search

```
grail query <project> "question" --mode agent
```

An LLM-driven tool-calling loop.  The agent decides which search mode(s)
to invoke and can call them multiple times with different parameters before
synthesizing a final answer.

### How It Works

```
Query + system prompt + tool schemas
  │
  ▼
LLM decides which tool to call
  │
  ├── local_search(query, include_entities?, exclude_entities?, top_k?)
  ├── global_search(query)
  └── document_search(query, document)
  │
  ▼
Tool executes, returns context (raw if < 8000 tokens, LLM-summarized if larger)
  │
  ▼
Agent reads result, decides: answer or call another tool?
  │  (up to max_iterations rounds)
  │
  ▼
Final synthesis from accumulated tool results
```

### Tool Schemas

The agent has access to four tools:

| Tool | Parameters | What It Calls |
|---|---|---|
| `local_search` | `query` (required), `include_entities`, `exclude_entities`, `top_k` | `LocalSearch.asearch()` |
| `cascade_search` | `query` (required), `include_entities`, `exclude_entities` | `CascadeSearch.asearch()` |
| `global_search` | `query` (required) | `GlobalSearch.asearch()` |
| `document_search` | `query` (required), `document` (required) | `DocumentSearch.asearch()` |

The agent's system prompt guides tool selection:
- Specific factual questions → `cascade_search` (default, most robust)
- Named entity lookups with filtering → `local_search`
- Broad thematic questions → `global_search`
- Document-specific questions → `document_search`

### Context Management

When a tool returns raw context larger than `agent_tool_context_limit`
(8,000 tokens), the agent runs a "mini-agent" — a separate LLM call that
summarizes the tool output before feeding it back to the main agent loop.
This prevents context overflow when tools return large result sets.

### Artifacts Used

All `SearchArtifacts` — the agent delegates to whichever search mode it
calls, so it transitively uses all parquet files.

### Config

```yaml
search:
  agent_search_endpoint: deepinfra       # fallback: local_search_endpoint
  agent_search_model: Qwen/Qwen3-32B    # fallback: local_search_model
  agent_search_max_tokens: 12000
  agent_search_response_max_tokens: 16384
  agent_max_iterations: 5
```

---

## Context Format

All search modes (except global) assemble context using the same XML-tagged
format before sending to the LLM:

```xml
<entities>
id,entity,type,description
0,BEVACIZUMAB,DRUG,A monoclonal antibody that inhibits VEGF-A...
1,COLORECTAL CANCER,DISEASE,A malignant neoplasm...
</entities>

<relationships>
id,source,target,description,weight
0,BEVACIZUMAB,COLORECTAL CANCER,Approved as first-line treatment...,3.00
</relationships>

<reports>
---
Report: Anti-Angiogenic Cancer Therapies (rank: 8.5)
# Community Summary
...
---
</reports>

<sources>
<source id="tu-abc123" document_id="doc-001">
Bevacizumab (Avastin) is a recombinant humanized monoclonal antibody...
</source>
<source id="tu-def456" document_id="doc-001">
First-line treatment of metastatic colorectal cancer...
</source>
</sources>
```

### Tag Semantics

- **`<entities>`** — CSV format with header row. Token-efficient for
  structured data the LLM doesn't need to process deeply.
- **`<relationships>`** — CSV format. In-network edges (both endpoints
  selected) are listed first, then out-network.
- **`<reports>`** — Markdown blocks with title and rank. Full community
  report content (or one-line summary in summary mode).
- **`<sources>`** — Individual XML tags per chunk with `document_id`
  attribute for provenance. This is where the LLM sees the original text
  and can cite source documents.

---

## Enriched Entity Embeddings

During entity extraction, the LLM generates two extra signals per entity
alongside the standard `name`, `type`, and `description`:

**`retrieval_queries`** — 2-3 natural-language questions that the entity's
source context helps answer.  Generated while the LLM reads the chunk, so
they reflect the specific role of the entity in that passage.

These queries are concatenated into the embedding text:

```
Before:  "TRATAMIENTO DE ALTO COSTO: categoría normativa que comprende medicamentos..."
After:   "TRATAMIENTO DE ALTO COSTO: categoría normativa que comprende medicamentos...
          ¿Qué condiciones debe cumplir un tratamiento para ser de alto costo?
          ¿Cómo se incorpora un tratamiento al decreto de alto costo?"
```

This transforms entity retrieval from matching `query → definition` to
matching `query → question` — significantly higher cosine similarity for
intent-aligned queries.

**Cost**: Zero extra LLM calls.  The queries are produced in the same
entity extraction pass that generates descriptions.

**Storage**: `retrieval_queries` column in `final_entities.parquet` as a
list of strings.  Included in `description_embedding` computation.

---

## Choosing a Mode

| Question Type | Recommended Mode | Why |
|---|---|---|
| Specific fact ("What is X?") | `local` | Entity gate finds the right entity directly |
| Fact that might be in unexpected chunks | `cascade` | Text rescue catches what entity gate misses |
| Broad theme ("What are the key findings?") | `global` | Community reports aggregate across the corpus |
| About a specific document | `document` | Scopes retrieval to one file |
| Complex or ambiguous question | `agent` | LLM picks the best strategy and iterates |
| Comparison across topics | `agent` | Agent can call local search twice with different entities |

---

## CLI Reference

```bash
# Local (default)
grail query <project> "question"
grail query <project> "question" --mode local

# Local with reranker
grail query <project> "question" --mode local --rerank

# Cascade (entity-gate + text rescue)
grail query <project> "question" --mode cascade

# Global (community reports)
grail query <project> "question" --mode global

# Document-scoped
grail query <project> "question" --mode document --document "file.pdf"

# Agent (LLM picks strategy)
grail query <project> "question" --mode agent

# JSON output (any mode)
grail query <project> "question" --mode cascade --output json
```
