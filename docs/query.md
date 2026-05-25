"""
Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""

# Search & Retrieval

GRAIL provides two ways to query a knowledge graph: **simple inference** (one
search call, one answer) and **agentic search** (the LLM decides which tools
to call and iterates until it has enough context). Both modes build on three
underlying search methods.

---

## The Three Search Methods

Think of a knowledge graph as a city. Local search walks specific streets
looking for landmarks. Global search reads the city's guidebook for themes.
Document search reads a single building's floor plan.

```mermaid
graph LR
    Q[User Query] --> D{Mode?}
    D -->|local| LS["Local Search\n(entity-anchored)"]
    D -->|global| GS["Global Search\n(community-anchored)"]
    D -->|document| DS["Document Search\n(file-scoped)"]

    LS --> R[LLM Synthesis]
    GS --> R
    DS --> R
    R --> A[Answer with citations]
```

### Local Search

Best for **specific factual questions** — who is X, what is the relationship
between A and B, what happened at event Y.

The pipeline finds the entities most relevant to the query and builds a context
window around them:

```mermaid
sequenceDiagram
    participant U as User
    participant E as Embeddings
    participant VS as VectorStore
    participant CB as Context Builder
    participant LLM as LLM

    U->>E: embed(query + conversation history)
    E->>VS: similarity search
    VS-->>CB: top-k entities (ranked by description similarity)
    CB->>CB: Collect relationships touching selected entities
    CB->>CB: Collect text units mentioning selected entities
    CB->>CB: Pull community reports for those entities' communities
    CB->>CB: Pack into context with proportional token budgets
    CB->>LLM: system prompt + context + query
    LLM-->>U: Answer with source citations
```

**Proportional token budgeting.** The context window is split based on
configurable ratios, not fixed sizes. This means the budgets scale when you
increase `local_max_tokens`:

```
max_tokens (default 8192)
  ├── text_unit_prop  (default 0.5)  →  ~4096 tokens for source text
  ├── community_prop  (default 0.1)  →   ~819 tokens for community reports
  └── local_prop      (remaining)    →  ~3277 tokens split between entity + relationship tables
```

**Conversation history enrichment.** When the user asks a follow-up like
"tell me more about that", the bare query has no useful keywords for entity
matching. GRAIL prepends recent user turns from the conversation history to
the query before embedding it, so the entity selector considers
conversational context. This is capped to `local_conversation_history_max_turns`
(default 5).

**Entity filtering.** You can force-include or force-exclude specific entities:

```python
result = await grail.search(
    "What are their contributions?",
    mode="local",
    include_entity_names=["EINSTEIN", "BOHR"],  # always include these
    exclude_entity_names=["HEISENBERG"],         # never include this
)
```

Forced-include entities are added to the ranked set regardless of similarity
score. Excluded entities are removed after ranking.

### Global Search

Best for **broad, thematic, or comparative questions** — what are the main
themes across all documents, compare the approaches described in the corpus,
summarize the key findings.

Global search operates on community reports rather than individual entities.
Each community report is a pre-generated LLM summary of a cluster of related
entities.

```mermaid
flowchart TD
    Q[Query] --> C{Total report tokens?}
    C -->|"< chunk_size (100k)"| R1["Single reduce pass\n(one LLM call)"]
    C -->|">= chunk_size"| MR["Map-reduce"]

    MR --> M1["Map chunk 1 → key points + scores"]
    MR --> M2["Map chunk 2 → key points + scores"]
    MR --> M3["Map chunk N → key points + scores"]
    M1 --> S[Sort all points by score descending]
    M2 --> S
    M3 --> S
    S --> R2["Reduce: synthesize top-scoring points"]

    R1 --> A[Final answer]
    R2 --> A
```

The map step extracts `{description, score}` pairs from each chunk. The
reduce step takes the highest-scoring points and synthesizes a final answer.
This is implemented in-house — the legacy proprietary `ReduceMap` utility is
not used.

### Document Search

Best when the user asks about **a specific source file** — what does report.txt
say about X, summarize the contents of paper.pdf, find information about Y in
this particular document.

Document search restricts the entire retrieval pipeline to a single document:

```mermaid
flowchart TD
    Q["query + document='report.txt'"] --> R[Resolve document]
    R --> TU["Filter text_units\nto only those belonging\nto this document"]
    TU --> EN["Filter entities\nto only those whose\ntext_unit_ids overlap"]
    EN --> RL["Filter relationships\nto only those between\nscoped entities"]
    RL --> CB["Build context\n(entity table + rel table + source text)"]
    CB --> LLM["LLM synthesis"]
    LLM --> A["Answer scoped to\nthis document only"]
```

**Document resolution** is flexible. You can pass:
- A filename: `"report.txt"`
- A path fragment: `"reports/q4"` (matches any path containing this substring)
- A document ID: `"a3f2b1c4-..."` (exact match)

The method tries each in order: exact ID match → path contains → title match →
mapping lookup.

**How scoping works.** Given the resolved document ID(s):

1. Find all text units whose `document_ids` list includes this document
2. Find all entities whose `text_unit_ids` overlap with those text units
3. Find all relationships where both source and target are in the scoped entity set
4. Build context and run LLM synthesis within this restricted scope

This means if an entity is mentioned in both `report.txt` and `paper.pdf`, and
you search within `report.txt`, that entity will appear — but only with its
relationship to other entities also mentioned in `report.txt`.

---

## Two Modes of Operation

### Simple Inference

Call `grail.search()` with a mode. One search, one answer.

```python
# Local: specific question
result = await grail.search("Who is Einstein?", mode="local")

# Global: broad question
result = await grail.search("What are the main themes?", mode="global")

# Document: file-scoped question
result = await grail.search(
    "What does it say about quantum theory?",
    mode="document",
    document="physics_paper.pdf",
)
```

This is the right choice when you know which search mode fits the question, or
when you want predictable, single-shot behavior. The LLM sees the retrieved
context and responds — it doesn't get to choose which search to run.

### Agentic Search

Call `grail.agent_search()`. The LLM receives three tools and decides which to
call, with what parameters, and how many times.

```python
result = await grail.agent_search(
    "Compare what report.txt and paper.pdf say about quantum theory"
)
```

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent (LLM)
    participant T as Tool Executor

    U->>A: "Compare what report.txt and paper.pdf say about quantum theory"
    A->>T: document_search(query="quantum theory", document="report.txt")
    T-->>A: [context from report.txt]
    A->>T: document_search(query="quantum theory", document="paper.pdf")
    T-->>A: [context from paper.pdf]
    A->>T: local_search(query="quantum theory", include_entities=["EINSTEIN","BOHR"])
    T-->>A: [broader entity context]
    A-->>U: "Report.txt focuses on... while paper.pdf argues..."
```

The agent has three tools available:

| Tool | Parameters | When the agent uses it |
|------|------------|----------------------|
| `local_search` | `query`, `include_entities?`, `exclude_entities?`, `top_k?` | Specific factual questions; needs entity-level detail |
| `global_search` | `query` | Broad or thematic questions; needs cross-cutting synthesis |
| `document_search` | `query`, `document` | User references a specific file; needs file-scoped context |

The agent loop runs up to `max_iterations` rounds (default 5). Each round:

1. LLM sees the conversation + any previous tool results
2. LLM either calls a tool (with chosen parameters) or returns a final answer
3. If it calls a tool, the result is appended to the conversation as a `tool` message
4. Loop continues until the LLM responds without tool calls, or max iterations

**The system prompt** instructs the agent to:
- Start with the tool that best matches the question type
- Use entity filtering when it needs to focus
- Use document search when the user references a specific file
- Combine local + global when the user asks for both details and big-picture
- Synthesize a final answer citing sources when it has enough information

You can override the system prompt:

```python
result = await grail.agent_search(
    "...",
    system_prompt="You are an expert analyst. Always start with global search...",
)
```

---

## How Tool Calling Works Internally

The agentic mode uses OpenAI's native function-calling protocol. GRAIL's
`LLMClient` speaks the OpenAI Chat Completions API, so this works with any
provider that supports the same protocol (OpenAI, vLLM, SGLang, etc.).

```mermaid
flowchart TD
    subgraph "LLMClient"
        A["execute_with_tools(messages, tools)"] --> B["OpenAI chat.completions.create\nwith tools parameter"]
        B --> C{Response has tool_calls?}
        C -->|Yes| D["Return {content, tool_calls}"]
        C -->|No| E["Return {content, null}"]
    end

    subgraph "AgentSearch loop"
        F[Build messages + tools] --> A
        D --> G["Execute each tool call"]
        G --> H["Append tool results to messages"]
        H --> F
        E --> I["Return final answer"]
    end
```

The `execute_with_tools()` method on `LLMClient` (`grail/llm/wrapper.py`)
handles:
- Semaphore-bounded concurrency (same as regular `execute()`)
- Retry on transient errors and rate limits
- Cost tracking per tool-calling round
- Parsing of `tool_calls` from the response into a clean dict format

---

## Return Values

All search methods return a `SearchResult`:

```python
@dataclass
class SearchResult:
    response: str                         # The LLM's answer
    context_data: dict[str, DataFrame]    # DataFrames used as context
    context_text: str                     # The raw context string sent to the LLM
    completion_time: float                # Wall-clock seconds
    llm_calls: int                        # Total LLM invocations
```

For agentic search, `llm_calls` includes both the agent's reasoning calls and
the search tools' internal LLM calls (entity extraction, map-reduce, etc.).
`context_data` is keyed by `{tool_name}_{artifact_type}` (e.g.
`local_search_entities`, `document_search_sources`).

---

## Configuration Reference

```yaml
search:
  # Local search
  local_search_endpoint: null           # null → inherits from llm.endpoint
  local_search_model: null              # null → inherits from llm.model
  local_max_tokens: 12000               # Total context window for local search
  local_text_unit_prop: 0.5             # Proportion of tokens for source text
  local_community_prop: 0.1             # Proportion of tokens for community reports
  local_conversation_history_max_turns: 5
  local_top_k_entities: 10
  local_top_k_relationships: 10
  use_community_summary: false          # false = full reports; true = summary only

  # Global search
  global_search_endpoint: null
  global_search_model: null
  global_map_max_tokens: 2000
  global_reduce_max_tokens: 8192
  global_chunk_size: 100000             # Threshold for single-pass vs map-reduce
  global_concurrency: 5                 # Parallel map calls

  # Response generation
  response_max_tokens: 16384            # Max output tokens for the final LLM answer.
                                        # Set high for thinking models (Qwen3, etc.)
                                        # whose internal reasoning consumes token budget.
  response_type: "Multiple Paragraphs"
```

---

## CLI

```
grail query [OPTIONS] PROJECT_DIR QUESTION

Options:
  -m, --mode      local | global | document | agent  [default: local]
  -d, --document  Document name/path for --mode document.
  -o, --output    text | json                        [default: text]
```

### Local search — specific factual questions

```bash
grail query examples/quickstart "What are the main treatment options for low-grade gliomas?"
```

Local is the default mode. It embeds the query, finds the top-k entities by
similarity, collects their relationships and source text, and synthesizes an
answer. The CLI prints each step as it runs:

```
  ◆  Loading indexed artifacts…
     ✓ Loaded 489 entities, 485 relationships, 3 community reports
  ◆  Embedding query…
  ◆  Ranking top-10 entities by similarity…
  ◆  Building context window…
     ✓ Context: 10 entities, 28 relationships, 2 communities, 9 source chunks
  ◆  Generating response…
╭─ RESPONSE ───────────────────────────────────────────────────────────────────╮
│  Based on the provided clinical guidelines...                                │
╰──────────────────────────────────────────────────────────────────────────────╯
  19.2s  ·  1 LLM call  ·  $0.0031
  Context: 10 entities, 28 relationships, 9 sources, 2 reports
  Entities: SURGICAL RESECTION, EARLY SURGICAL RESECTION, SECOND SURGERY, ...
```

### Global search — broad thematic questions

```bash
grail query examples/quickstart "What are the main themes across all indexed documents?" --mode global
```

Global search reads all community reports (pre-generated LLM summaries of
entity clusters) and synthesizes a single answer. When the total context fits
in one chunk it runs a single reduce pass; otherwise it map-reduces.

```
  ◆  Loading indexed artifacts…
     ✓ Loaded 3 community reports
  ◆  Building community context…
  ◆  Single-pass reduce — context fits in one chunk
  ◆  Generating response…
╭─ RESPONSE ───────────────────────────────────────────────────────────────────╮
│  Based on the indexed documents, the main themes converge around...          │
╰──────────────────────────────────────────────────────────────────────────────╯
  12.0s  ·  1 LLM call  ·  $0.0020
  Context: 3 reports
```

### Document search — file-scoped questions

```bash
grail query examples/quickstart "What treatments are discussed?" --mode document --document "gliomas"
```

Document search restricts the entire retrieval pipeline to a single source
file. The `--document` value is matched flexibly: by filename, path fragment,
title, or document ID.

```
  ◆  Loading indexed artifacts…
  ◆  Resolving document 'gliomas'…
  ◆  Scoping to 1 document(s)…
     ✓ Scoped: 245 entities, 235 relationships, 12 text units
  ◆  Embedding query…
  ◆  Ranking top-10 entities…
  ◆  Building context window…
  ◆  Generating response…
╭─ RESPONSE ───────────────────────────────────────────────────────────────────╮
│  Based on the provided guidelines...                                         │
╰──────────────────────────────────────────────────────────────────────────────╯
  21.9s  ·  1 LLM call  ·  $0.0030
  Context: 10 entities, 10 relationships, 6 sources
```

### Agent search — LLM decides the strategy

```bash
grail query examples/quickstart "Compare treatment approaches for gliomas and cancer cachexia" --mode agent
```

The agent receives three tools (`local_search`, `global_search`,
`document_search`) and decides which to call, with what parameters, and how
many times. It iterates until it has enough context, then synthesizes a final
answer.

```
  ◆  Loading indexed artifacts…
     ✓ Loaded 489 entities, 485 relationships, 3 community reports
  ◆  Starting agent loop (max 5 iterations)…
  ◆  Iteration 1/5 — reasoning…
  ◆  Calling tool: global_search(query='treatment approaches for gliomas and cancer cachexia')
     ...
     ✓ global_search returned (1 LLM calls)
  ◆  Calling tool: local_search(query='glioma treatment approaches', top_k=10)
     ...
     ✓ local_search returned (1 LLM calls)
  ◆  Calling tool: local_search(query='cancer cachexia treatment approaches', top_k=10)
     ...
     ✓ local_search returned (1 LLM calls)
  ◆  Iteration 2/5 — reasoning…
     ✓ Agent finished — synthesizing final answer
╭─ RESPONSE ───────────────────────────────────────────────────────────────────╮
│  Glioma management focuses on oncological control (tumor removal and         │
│  molecular targeting), while cancer cachexia management focuses on           │
│  metabolic and nutritional support...                                        │
╰──────────────────────────────────────────────────────────────────────────────╯
  1m 12.9s  ·  5 LLM calls  ·  $0.0116
```

### JSON output

```bash
grail query examples/quickstart "What is IDH?" --mode local --output json
```

Returns machine-readable JSON with the response, timing, cost, context stats,
and entity names:

```json
{
  "response": "IDH (Isocitrate Dehydrogenase) is...",
  "completion_time": 12.3,
  "llm_calls": 1,
  "context_stats": {"entities": 10, "relationships": 14, "reports": 2, "sources": 6},
  "entities_used": ["IDH1 OR IDH2 MUTATIONS", "IDH-MUTANT ASTROCYTOMA", "..."],
  "cost": "$0.0032"
}
```

### More examples

```bash
# Conversation-style: force specific entities into context
grail query ./project "What are their contributions?" --mode local

# Override model for a single query (via search config in grail.yaml)
# search:
#   local_search_endpoint: openai
#   local_search_model: gpt-4o

# Document search with a path fragment
grail query ./project "Summarize findings" --mode document --document "reports/q4"

# Agent with a multi-hop question
grail query ./project "Which authors wrote about both topic A and topic B?" --mode agent
```

---

## When to Use Which

| Question Type | CLI | Why |
|---------------|-----|-----|
| "Who is X?" | `--mode local` | Entity-anchored; needs specific facts |
| "What is the relationship between A and B?" | `--mode local` | Force both entities into context via API `include_entity_names` |
| "What are the main themes?" | `--mode global` | Needs cross-cutting community-level synthesis |
| "Summarize this document" | `--mode document -d file.pdf` | File-scoped; only that source matters |
| "What does report.txt say about X?" | `--mode document -d report.txt` | File-scoped question |
| "Compare report.txt and paper.pdf on topic Y" | `--mode agent` | Needs multiple document searches + synthesis |
| "Find everything about X, starting broad then drilling down" | `--mode agent` | Agent starts with global, refines with local |
| Conversational follow-ups ("tell me more") | `--mode local` | History enrichment finds entities from prior turns (Python API only) |

---

## Architecture

```mermaid
graph TD
    subgraph "grail.search()"
        S[GRAIL.search] -->|mode=local| LS[LocalSearch]
        S -->|mode=global| GS[GlobalSearch]
        S -->|mode=document| DS[DocumentSearch]
    end

    subgraph "grail.agent_search()"
        AS[GRAIL.agent_search] --> AG[AgentSearch]
        AG -->|tool call| LS
        AG -->|tool call| GS
        AG -->|tool call| DS
    end

    subgraph "Shared Infrastructure"
        LS --> RET[retrieval.py\nContext builders]
        DS --> RET
        GS --> PR[Prompt registry]
        LS --> PR
        DS --> PR
        RET --> EMB[EmbeddingClient]
        RET --> VS[LanceDB VectorStore]
        LS --> LLM[LLMClient]
        GS --> LLM
        DS --> LLM
        AG --> LLM
    end
```

All three search methods share the same retrieval primitives
(`map_query_to_entities`, `build_entity_context`, `build_relationship_context`,
`build_text_unit_context`, `build_community_context`) and the same LLM/embedding
clients. The agent simply orchestrates calls to these methods through the
tool-calling protocol.
