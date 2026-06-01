# Prompt Customization Guide

> How to fine-tune GRAIL's prompts for your domain, corpus, and use case. Covers both **indexing** (entity extraction, community reports) and **inference** (local search, global search, agent).

---

## Why Customize Prompts

GRAIL's built-in prompts are general-purpose. They work across legal text, scientific papers, code, and fiction. But for production deployments, tuning prompts to your specific domain can dramatically improve results:

- **Indexing quality**: Domain-specific extraction instructions produce richer, more precise entity descriptions and relationship types. A medical knowledge base benefits from prompts that understand drug-target interactions; a legal one benefits from prompts that capture regulatory hierarchies.
- **Search relevance**: A search prompt that knows your domain's vocabulary and answer structure produces more focused, useful responses.
- **Agent efficiency**: An agent prompt tuned to your knowledge base's structure makes better tool-selection decisions, reducing unnecessary iterations and cost.

The gains are compounding: better extraction produces a better graph, which produces better community reports, which produces better search context, which produces better answers.

---

## Architecture Overview

Every GRAIL prompt is a Python module with three exports:

```python
NAME = "entity_relation"              # Registry key (must match filename)
REQUIRED_PARAMS = ["entity_types", "input_text"]  # Validated before call

def build_messages(**params) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "..."},
        {"role": "user",   "content": "..."},
    ]
```

The `PromptRegistry` resolves prompts by name. Custom prompts override built-ins:

```
custom_paths (in order) → builtin → KeyError
```

To override a prompt, create a `.py` file with the same `NAME` in your custom directory:

```yaml
# grail.yaml
prompts:
  custom_paths:
    - ./my_prompts
  strict: false    # true = ALL 10 built-in names must be present
```

```
my_prompts/
├── entity_relation.py     # overrides built-in
├── local_search.py        # overrides built-in
└── (everything else falls back to built-in)
```

---

## Part 1: Indexing Prompts

Indexing prompts control how the knowledge graph is built. They run during `grail index`, `grail append`, and `grail edit`. Changes here require re-indexing to take effect.

### 1.1 Entity & Relationship Extraction (`entity_relation`)

**What it does:** Given a text chunk and a list of entity types, extracts structured entities and relationships in a delimited tuple format.

**When to customize:** When the default extraction misses domain-specific patterns, produces too many/few entities, or generates poor descriptions.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entity_types` | `list[str]` or `str` | Yes | Target entity types (e.g., `["PERSON", "DRUG", "DISEASE"]`) |
| `input_text` | `str` | Yes | The text chunk to extract from |
| `tuple_delimiter` | `str` | No | Field separator (default `<\|>`) |
| `record_delimiter` | `str` | No | Record separator (default `##`) |
| `start_delimiter` | `str` | No | Output start tag (default `<extracted_data>`) |
| `completion_delimiter` | `str` | No | Output end tag (default `</extracted_data>`) |
| `extract_relationship_types` | `bool` | No | Enable typed relationships (default `false`) |
| `relationship_types` | `list[str]` | No | Constrained vocabulary for relationship types |

**Output format (parser contract):**

```
<extracted_data>
("entity"<|>NAME<|>TYPE<|>DESCRIPTION<|>RETRIEVAL_QUERIES)##
("relationship"<|>SOURCE<|>TARGET<|>DESCRIPTION<|>STRENGTH)##
</extracted_data>
```

**Critical constraint:** The parser in `grail.indexing.entities_relationships` reads `DEFAULT_DELIMITERS` from this module. If you change delimiters, export them as `DEFAULT_DELIMITERS` or wire them into the extractor's `delimiters` kwarg directly. Mismatched delimiters between prompt and parser will silently produce zero entities.

#### Tuning Strategies

**A. Add domain-specific examples**

The built-in prompt includes 3 examples (narrative fiction, scientific paper, code). Replace or supplement these with examples from your domain:

```python
# my_prompts/entity_relation.py
SYSTEM_TEMPLATE = """\
...existing role/context/task/format sections...

<examples>
Example 1 — Clinical Guidelines:

Entity_types: [drug, disease, treatment, biomarker, guideline]
Text:
Pembrolizumab is recommended as first-line treatment for patients with 
metastatic NSCLC whose tumors express PD-L1 (TPS ≥50%), with no EGFR 
or ALK genomic aberrations, based on KEYNOTE-024 results.

Output:
{start_delimiter}
("entity"{tuple_delimiter}"PEMBROLIZUMAB"{tuple_delimiter}"drug"{tuple_delimiter}\
"A PD-1 immune checkpoint inhibitor recommended as first-line treatment for \
metastatic NSCLC with high PD-L1 expression."{tuple_delimiter}\
"What is the first-line treatment for PD-L1-high NSCLC?; When is pembrolizumab \
recommended?"){record_delimiter}
("entity"{tuple_delimiter}"METASTATIC NSCLC"{tuple_delimiter}"disease"{tuple_delimiter}\
"Non-small cell lung cancer that has spread beyond the primary site."\
{tuple_delimiter}"What treatments exist for metastatic NSCLC?"){record_delimiter}
...
{completion_delimiter}
</examples>"""
```

**Why this works:** LLMs extract entities in the style of the examples they see. Domain-matched examples teach the model what level of detail to capture, how to phrase descriptions, and what constitutes a meaningful relationship in your context.

**B. Refine the description instructions**

The default prompt says: *"A self-contained description of what this entity is and what it does in context."* For specific domains, be more prescriptive:

```python
# For a legal corpus:
"""
- entity_description: A self-contained legal definition. Include:
  (1) what the entity is (article, institution, fund, procedure),
  (2) its legal basis (which law/article establishes it),
  (3) its primary function or obligation.
  Write as if the reader has no access to the source statute.
"""

# For a codebase:
"""
- entity_description: A developer-facing summary. Include:
  (1) what the entity does (function, class, module purpose),
  (2) its inputs/outputs or key interfaces,
  (3) its relationship to the broader system.
"""
```

**C. Tune retrieval queries**

The `retrieval_queries` field (2-3 questions per entity) is embedded alongside the entity description and directly impacts search quality. The default prompt says to write them *"in the same language as the source text"* and to *"reflect the specific role of the entity in this passage."*

For better retrieval, add guidance on query style:

```python
"""
- retrieval_queries: Write 2-3 questions a user would actually ask that this
  entity helps answer. Use natural, conversational language — not keyword dumps.
  Good: "What funding sources support cancer treatment in Chile?"
  Bad: "funding sources cancer treatment Chile"
  Good: "How does pembrolizumab compare to chemotherapy for NSCLC?"
  Bad: "pembrolizumab NSCLC comparison"
"""
```

**D. Control extraction aggressiveness**

The default prompt says: *"Extract ALL entities of the specified types that carry meaningful information."* If you're getting too many noisy entities, tighten this:

```python
"""
- Extract only entities that are CENTRAL to the passage's meaning.
  Skip entities that are mentioned in passing without substantive context.
- Minimum threshold: an entity must have at least 2 sentences of context
  to merit extraction.
"""
```

Or if you're missing entities, loosen it:

```python
"""
- Extract aggressively. Even brief mentions are valuable if the entity
  is a named, specific concept. One sentence of context is sufficient.
- When in doubt, extract — downstream deduplication handles redundancy.
"""
```

**E. Configure entity types**

Before customizing the prompt, consider tuning entity types via config — it's simpler and doesn't require a custom prompt file:

```yaml
# grail.yaml → indexing section
entity_types:
  - person
  - organization
  - drug
  - disease
  - treatment
  - biomarker
  - clinical_study
  - guideline

# Or let the LLM discover types from your corpus:
discover_entity_types: true
max_entity_types: 12
```

`PERSON` and `ORGANIZATION` are always injected automatically. All types are normalized to `UPPER_SNAKE_CASE`.

**F. Configure relationship types**

Enable typed relationships when your domain has clear relationship categories:

```yaml
# grail.yaml → indexing section
extract_relationship_types: true

# Option 1: Let the LLM pick types freely
relationship_types: []

# Option 2: Constrain to a vocabulary (RELATED is always added as fallback)
relationship_types:
  - REGULATES
  - FUNDS
  - TREATS
  - MEMBER_OF
  - IMPLEMENTS
  - OVERSEES
  - AMENDS
```

This changes the extraction format from 5-field (untyped) to 6-field (typed) tuples. The parser handles both formats automatically.

---

### 1.2 Community Reports (`community_report`)

**What it does:** Given a cluster of related entities and their relationships, generates a narrative JSON report with title, summary, rating, and findings.

**When to customize:** When reports are too generic, miss domain-specific insights, or use the wrong rating scale for your use case.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `input_text` | `str` | Yes | Pre-formatted community data (entities + relationships in CSV format) |

**Output format (parser contract):**

```json
// Wrapped in <report_json>...</report_json> tags
{
  "title": "string",
  "summary": "string (max 5 lines)",
  "rating": 0-10,
  "rating_explanation": "one sentence",
  "findings": [
    {"summary": "one-line headline", "explanation": "paragraph with [Data: ...] citations"}
  ]
}
```

#### Tuning Strategies

**A. Domain-specific rating scale**

The default scale is generic (0-2 routine, 3-5 moderate, 6-8 significant, 9-10 critical). Replace it with your domain's priorities:

```python
"""
Rating scale:
- 0-2: Boilerplate / administrative connections with no analytical value
- 3-5: Standard regulatory relationships (expected, documented)
- 6-8: Cross-jurisdictional connections, funding dependencies, compliance gaps
- 9-10: Active conflicts, unresolved legal ambiguities, patient safety risks
"""
```

**B. Domain-specific finding structure**

Guide what findings should focus on:

```python
"""
<rules>
...
- Each finding should identify one of:
  (1) A causal chain: entity A causes/enables/blocks entity B
  (2) A dependency: entity A requires entity B to function
  (3) A conflict: entity A contradicts or undermines entity B
  (4) A gap: expected relationship between A and B is absent
- Do NOT write findings that merely restate entity descriptions.
...
</rules>
"""
```

**C. Change the example**

The built-in example uses a cancer drug community (Bevacizumab/VEGF/Colorectal Cancer). Replace it with an example from your domain to calibrate the model's output style:

```python
"""
<example>
Input:
Entities

id,entity,description
0,LEY 20.850,Ley Ricarte Soto — establishes financial protection for high-cost diagnoses and treatments
1,FONASA,Fondo Nacional de Salud — manages public health funding
2,SISTEMA DE PROTECCIÓN FINANCIERA,Financial protection system for high-cost health treatments

Relationships

id,source,target,description
0,LEY 20.850,SISTEMA DE PROTECCIÓN FINANCIERA,Ley 20.850 creates and regulates the financial protection system
1,FONASA,SISTEMA DE PROTECCIÓN FINANCIERA,FONASA administers the financial protection system

Output:
<report_json>
{
  "title": "Ley Ricarte Soto and Chile's Financial Protection System for High-Cost Treatments",
  "summary": "This community describes the legal framework ...",
  ...
}
</report_json>
</example>
"""
```

---

### 1.3 Description Summarization (`summarize_description`)

**What it does:** When the same entity is extracted from multiple chunks with different descriptions, this prompt consolidates them into one comprehensive summary.

**When to customize:** When summaries are losing critical details, or when you need a specific description format.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entities` | `list[dict]` | Yes | List of `{index, name, descriptions}` dicts |

#### Tuning Strategies

**A. Control summary length**

Default is 3-5 lines. For domains with complex entities that need more detail:

```python
"""
Each summary must be 5-8 lines. Capture every distinct fact across all
descriptions. For medical entities, always include: mechanism of action,
approved indications, and key clinical trial references.
"""
```

**B. Prioritize specific information**

```python
"""
When consolidating descriptions, prioritize in this order:
1. Legal definitions and statutory references
2. Quantitative data (amounts, thresholds, dates, deadlines)
3. Relationships to other named entities
4. General descriptive context
Never drop quantitative data even if it appears in only one description.
"""
```

---

### 1.4 Entity Deduplication (`entity_dedup`)

**What it does:** When entities with similar embeddings are found, this prompt asks the LLM to determine which are true duplicates and which are distinct.

**When to customize:** When the deduplication is either too aggressive (merging distinct entities) or too conservative (leaving obvious duplicates).

#### Tuning Strategies

**A. Domain-specific merge rules**

```python
"""
<rules>
- In this legal corpus, laws referenced by different names are duplicates:
  "LEY 20.850" = "LEY RICARTE SOTO" = "RICARTE SOTO LAW"
- BUT: different articles of the same law are NOT duplicates:
  "ARTÍCULO 12 LEY 19.966" ≠ "ARTÍCULO 24 LEY 19.966"
- Drug names: merge brand names with generic names:
  "BEVACIZUMAB" = "AVASTIN" (same drug)
- Disease stages are NEVER duplicates:
  "STAGE IIA" ≠ "STAGE IIB" ≠ "STAGE III"
</rules>
"""
```

---

### 1.5 Entity Discovery (`create_custom_entities`)

**What it does:** Reads corpus samples and proposes domain-appropriate entity types.

**When to customize:** When the default discovery produces overly generic or overly specific types.

#### Tuning Strategies

**A. Provide domain context**

Add a description of your corpus to the system prompt so the model understands the domain before reading samples:

```python
"""
<context>
...
This corpus consists of Chilean health legislation — laws, decrees, and
regulations governing public health systems, pharmaceutical coverage,
and patient rights. Entity types should capture the legal and institutional
structure: legislative instruments, government bodies, financial mechanisms,
medical concepts referenced in legal context, and patient rights.
</context>
"""
```

---

## Part 2: Inference Prompts

Inference prompts control how GRAIL answers questions. They run during `grail query` and affect response quality without requiring re-indexing.

### 2.1 Local Search (`local_search`)

**What it does:** System prompt for entity-gated RAG. Receives retrieved context (entities, relationships, community reports, text units) and the user's question. Generates the final answer.

**When to customize:** When answers are too verbose/terse, miss the right tone, or need domain-specific instructions.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `context_data` | `str` | Yes | Pre-formatted retrieved context |
| `user_query` | `str` | Yes | The user's question |
| `assistant_name` | `str` | No | Name shown to user (default `"GRAIL"`) |
| `artifact_instructions` | `str` | No | Extra instructions injected into `<context>` |
| `conversation_history` | `list[dict]` | No | Previous turns for multi-turn conversations |
| `prefix_initial` | `str` | No | Prefill the assistant's response |

#### Tuning Strategies

**A. Set the persona**

The `<role>` section defines who the assistant is. Replace it for your use case:

```python
"""
<role>
You are a clinical decision support assistant specializing in oncology 
treatment guidelines. You help oncologists find evidence-based treatment 
recommendations from indexed clinical guidelines (NCCN, ESMO, ASCO). 
You are precise, cite guideline versions, and flag when evidence quality 
is low (e.g., category 2B recommendations).
</role>
"""
```

**B. Add answer structure rules**

```python
"""
<rules>
...
- Structure answers as:
  1. Direct answer to the question (1-2 sentences)
  2. Supporting evidence with citations
  3. Caveats or limitations (if any)
- For treatment questions, always include:
  - Recommended regimen
  - Evidence level (category 1, 2A, 2B, 3)
  - Key contraindications
- For questions about specific articles or laws, quote the relevant
  text verbatim when it appears in the data.
...
</rules>
"""
```

**C. Control citation style**

```python
"""
<rules>
...
- Cite sources using this format: (Source: [document name], Art. [number])
- When multiple sources support the same claim, cite all of them.
- If a claim appears only in community reports but not in source text,
  note it as "(inferred from graph analysis)"
...
</rules>
"""
```

**D. Handle domain-specific edge cases**

```python
"""
<rules>
...
- If the question asks about drug interactions, check ALL relationships
  involving the mentioned drugs before answering. Missing a contraindication
  is worse than a verbose answer.
- If the question mentions a date, check whether the information in the
  data predates or postdates it — guidelines change frequently.
- If the data contains conflicting information from different sources,
  present both positions and identify the conflict explicitly.
...
</rules>
"""
```

**E. Use `artifact_instructions` for runtime context**

You can inject per-query instructions without modifying the prompt file:

```python
result = await grail.search(
    query="What treatment is recommended?",
    search_type="local",
    artifact_instructions=(
        "The user is a medical professional. "
        "Use technical terminology. Include dosing information."
    ),
)
```

---

### 2.2 Global Search — Map Phase (`global_map`)

**What it does:** Extracts relevant points from community reports, scoring each by relevance (0-100).

**When to customize:** Rarely needed. The map phase is a relevance filter. Customize only if the scoring scale doesn't match your priorities.

#### Tuning Strategies

**A. Adjust the scoring rubric**

```python
"""
Score scale for this legal knowledge base:
- 0-20: Tangentially related — no direct legal relevance
- 21-50: Background context — helps understand the legal framework
- 51-80: Directly relevant — addresses the legal question being asked
- 81-100: Dispositive — provides the specific legal answer (article, ruling, definition)
"""
```

---

### 2.3 Global Search — Reduce Phase (`global_reduce`)

**What it does:** Synthesizes the final answer from community reports (direct mode) or map-phase extracted points (map-reduce mode for large contexts).

**When to customize:** When global search answers need different structure, tone, or level of detail.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `context_data` | `str` | Yes | Community reports or extracted points |
| `user_query` | `str` | Yes | The user's question |
| `assistant_name` | `str` | No | Name shown to user (default `"GRAIL"`) |
| `extra_knowledge` | `str` | No | Set to `GENERAL_KNOWLEDGE_INSTRUCTION` to allow real-world knowledge with `[LLM: verify]` tags |
| `conversation_history` | `list[dict]` | No | Previous turns |

#### Tuning Strategies

**A. Enable external knowledge (with guardrails)**

By default, global search uses ONLY indexed data. For use cases where supplementing with LLM knowledge is acceptable:

```python
from grail.prompts.builtin.global_reduce import GENERAL_KNOWLEDGE_INSTRUCTION

result = await grail.search(
    query="How does Chile's approach compare to other countries?",
    search_type="global",
    extra_knowledge=GENERAL_KNOWLEDGE_INSTRUCTION,
)
```

This allows the model to add real-world context tagged with `[LLM: verify]` so the user knows which claims come from indexed data and which from the model's training.

**B. Customize synthesis structure**

```python
"""
<task>
...
4. Organize the answer as follows:
   a. Executive summary (2-3 sentences answering the question directly)
   b. Detailed analysis organized by theme
   c. Limitations and gaps in the available data
5. For comparative questions, use a structured comparison:
   - Similarities
   - Differences
   - Assessment / recommendation
</task>
"""
```

---

### 2.4 Agent Search (`AGENT_SYSTEM_PROMPT`)

**What it does:** Instructs the tool-calling LLM to select between local_search, cascade_search, global_search, and document_search. Controls the agent's reasoning and iteration behavior.

**Current location:** Inlined as a constant in `grail/query/agent.py`. Not yet managed by the PromptRegistry (see Known Gaps in CLAUDE.md §12.2).

**When to customize:** When the agent makes poor tool-selection decisions, iterates too much/little, or needs domain-specific search strategies.

#### Tuning Strategies

**A. Customize tool selection strategy**

The default strategy is:

```
Specific factual question → cascade_search (most robust)
Named entity question → local_search
Broad / thematic question → global_search
Specific document question → document_search
```

For a legal corpus, you might want:

```python
"""
<strategy>
1. **Assess the question and pick a tool:**
   - Question about a specific law, article, or regulation → **document_search**
     (scope to the exact law mentioned)
   - Question about rights, obligations, or procedures → **local_search**
     (find the relevant institutional entities and their relationships)
   - Question asking for specific numbers, dates, or thresholds →
     **cascade_search** (text matching rescues exact figures)
   - Question asking "what does this system cover?" or "summarize the
     framework" → **global_search** (community-level synthesis)
   - Comparative question across laws → **global_search** first,
     then **document_search** for specifics

2. **Query formulation for local_search:**
   Use the WHO + WHAT + TERMS formula:
   - WHO: the institution or entity doing the action
   - WHAT: the process, mechanism, or concept
   - TERMS: specific vocabulary from the domain
   
   Example: "FONASA financial protection high-cost treatment coverage"
   NOT: "how does health coverage work?"
...
</strategy>
"""
```

**B. Control iteration behavior**

```python
"""
<strategy>
...
- Most questions need exactly 1 tool call. Call a second tool only if:
  (a) the first returned explicitly incomplete results, OR
  (b) the question has two distinct parts that require different tools.
- NEVER call the same tool twice with the same or similar query.
- After 2 tool calls, synthesize whatever you have. Do not iterate further
  unless the question is completely unanswered.
...
</strategy>
"""
```

**C. Add domain-specific output rules**

```python
"""
<output_format>
When synthesizing your final answer:
- For treatment-related questions, structure as:
  **Recommendation:** [direct answer]
  **Evidence:** [supporting data with citations]
  **Caveats:** [limitations, contraindications]
- Always cite the specific law and article number when available.
- Use the patient's language — avoid legal jargon unless quoting directly.
- If the knowledge base contains conflicting information, present both
  positions and explain the conflict.
</output_format>
"""
```

---

## Part 3: Practical Workflows

### 3.1 Creating a Custom Prompt Pack

```bash
# 1. Create your prompt directory
mkdir -p my_project/prompts

# 2. Copy the built-in you want to customize
cp grail/prompts/builtin/entity_relation.py my_project/prompts/
cp grail/prompts/builtin/local_search.py my_project/prompts/

# 3. Edit the copies (keep NAME and REQUIRED_PARAMS unchanged)

# 4. Point your config at the directory
```

```yaml
# my_project/grail.yaml
prompts:
  custom_paths:
    - ./prompts
```

### 3.2 Testing Prompt Changes

**For indexing prompts** — test on a small subset before full re-index:

```bash
# Index just one document to validate extraction quality
grail index my_project --discover-entities

# Check the extracted entities
python -c "
import pandas as pd
df = pd.read_parquet('my_project/output/current_run/final_entities.parquet')
print(df[['name', 'type', 'description']].head(20))
"
```

**For search prompts** — use query tracing to inspect the full prompt:

```bash
# Trace captures the exact messages sent to the LLM
grail query my_project "your test question" --mode local --trace ./traces/

# Inspect the trace
python -c "
import json
trace = json.loads(open('./traces/latest.json').read())
for record in trace['records']:
    print(f'--- {record[\"tag\"]} ---')
    for msg in record['messages']:
        print(f'[{msg[\"role\"]}] {msg[\"content\"][:200]}...')
"
```

### 3.3 Iterative Prompt Development

Recommended workflow:

1. **Baseline**: Run a few representative queries with built-in prompts. Save traces.
2. **Identify gaps**: Where are the answers weak? Missing entities? Wrong tool selection? Poor synthesis?
3. **Trace the root cause**:
   - Bad entity extraction → customize `entity_relation`
   - Good entities but poor answers → customize `local_search` or `global_reduce`
   - Agent picking wrong tools → customize `AGENT_SYSTEM_PROMPT`
   - Community reports too vague → customize `community_report`
4. **Change one prompt at a time**. Test with 3-5 queries. Compare traces.
5. **Re-index only when changing indexing prompts.** Search prompt changes take effect immediately.

### 3.4 Multilingual Prompts

All built-in prompts include the rule: *"Respond in the same language as the user's question"* and *"Write in the same language as the entity descriptions."* This means:

- Entity descriptions are generated in the source document's language
- Community reports match the entity description language
- Search responses match the query language

For fully translated prompt packs (e.g., all instructions in Spanish), use `strict: true` to ensure no English fallbacks leak through:

```yaml
prompts:
  custom_paths:
    - ./prompts_es
  strict: true   # fails if any built-in name is missing from prompts_es/
```

---

## Part 4: Reference

### All Built-in Prompts

| Name | Pipeline Stage | Purpose | Override Priority |
|------|---------------|---------|-------------------|
| `entity_relation` | Indexing | Entity & relationship extraction | **High** — most impactful on graph quality |
| `summarize_description` | Indexing | Consolidate duplicate entity descriptions | Medium |
| `community_report` | Indexing | Generate community narrative reports | **High** — directly affects global search |
| `entity_dedup` | Indexing | Judge entity duplicates for merging | Low |
| `create_custom_entities` | Indexing (optional) | Propose entity types from corpus samples | Low |
| `json_correction` | Indexing (fallback) | Repair malformed JSON from community reports | Low |
| `claim_extraction` | Indexing (optional) | Extract structured claims/covariates | Low |
| `local_search` | Inference | Local search answer synthesis | **High** — affects answer quality directly |
| `global_map` | Inference | Global search relevance scoring | Low |
| `global_reduce` | Inference | Global search final synthesis | **High** — affects answer quality directly |

### Config Fields That Affect Prompts

These config fields modify prompt behavior without requiring a custom prompt file:

| Config Path | Effect on Prompts |
|-------------|-------------------|
| `indexing.entity_types` | Injected into `entity_relation` as the type list |
| `indexing.discover_entity_types` | Triggers `create_custom_entities` before extraction |
| `indexing.extract_relationship_types` | Switches `entity_relation` to 6-field relationship format |
| `indexing.relationship_types` | Constrains relationship type vocabulary in `entity_relation` |
| `indexing.max_gleanings` | Number of "did you miss anything?" re-asks per chunk (0 = single pass) |
| `search.use_community_summary` | Controls whether `local_search` gets full reports or one-line summaries |
| `search.response_max_tokens` | Max tokens for the LLM response in search prompts |
| `search.agent_max_iterations` | Max tool-calling rounds for agent search |

### Delimiter Contract

If you change extraction delimiters in a custom `entity_relation` prompt, the parser must know. Two options:

**Option A (recommended):** Export `DEFAULT_DELIMITERS` from your custom module — the parser imports it automatically:

```python
# my_prompts/entity_relation.py
DEFAULT_DELIMITERS = {
    "tuple_delimiter": "<|>",      # must match your prompt
    "record_delimiter": "##",
    "completion_delimiter": "</extracted_data>",
    "start_delimiter": "<extracted_data>",
}
```

**Option B:** Pass custom delimiters to the extractor in code:

```python
extractor = EntityRelationshipExtractor(
    ...,
    delimiters={"tuple_delimiter": "|||", "record_delimiter": "@@", ...},
)
```

### Thinking Model Compatibility

All built-in prompts support chain-of-thought / `<think>` models (Qwen3, DeepSeek-R1, etc.). The key design patterns:

1. **Structured output is wrapped in tags** (`<extracted_data>`, `<report_json>`, `<dedup_result>`, `<entities>`, `<summaries>`). The parser extracts content from between these tags, ignoring everything outside — including `<think>` blocks.

2. **Prompts explicitly say** *"You may reason freely... then emit structured data inside tags."* This gives thinking models permission to use their reasoning mechanism without polluting the output.

3. **Token budgets must be large enough** for both thinking and output. See `docs/glossary.md` for the `extraction_max_tokens`, `max_summarization_tokens`, and `response_max_tokens` fields. Reasoning models may use 50-80% of the budget on `<think>` blocks.

When writing custom prompts, preserve these patterns. Do NOT remove the tag-wrapping or the "you may reason first" instruction — it's what makes GRAIL compatible with thinking models.
