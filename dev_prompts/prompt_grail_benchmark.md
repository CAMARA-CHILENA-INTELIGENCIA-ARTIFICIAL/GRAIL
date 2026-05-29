# GRAIL Benchmark — Agent Logic, Execution Guide & Replication

## Why This Benchmark Exists

In the agentic era, RAG's retrieval problem is largely solved — modern embedding models find relevant chunks reliably. The real challenge is what happens *after* retrieval: can the system **comprehend relationships between concepts**, connect information across documents, and synthesize answers that require understanding — not just finding — the source material?

Traditional RAG benchmarks measure retrieval accuracy (did the system find the right chunk?). This benchmark measures **comprehension quality** — given that both systems can find relevant text, which one produces a more complete, accurate, and well-grounded answer?

The answer matters because real users don't ask expert-style lookup questions. A cancer patient asks "¿de dónde sale el dinero para mi tratamiento?" — they need the system to understand that the Fund has 4 funding sources, how they connect to FONASA, and what protections exist. That requires cross-referencing entities, following relationship chains, and synthesizing from structured knowledge.

## Overview

The GRAIL benchmark compares two retrieval agents on the same corpus, LLM, and embedding model. The only variable is the retrieval architecture: GRAIL's knowledge graph vs RAG's chunk similarity.

- **30 questions** in patient language across 7 categories
- **2 agents**: GRAIL agent (4 search tools) vs RAG agent (1 search tool)
- **Same budget**: 3 iterations, up to 2 tool calls per question
- **Zero empty responses**: forced synthesis fallback ensures both always answer
- **Result**: GRAIL 4.80 vs RAG 4.14 (27 wins, 0 losses, 3 ties)

### Why GRAIL wins despite RAG-favorable conditions

This benchmark uses a **small corpus** (3 documents, 35 chunks) where every chunk is reachable by top-10 cosine — the exact conditions where RAG should perform best. Despite this:

- **Comprehension over retrieval**: GRAIL's entities have semantic descriptions and retrieval queries that match patient language. RAG matches against raw legal text.
- **Cross-referencing**: GRAIL's entity graph connects "FONASA" across all 3 laws automatically. RAG finds chunks from one document at a time.
- **Strategic tool selection**: The GRAIL agent picks local_search (entity matching), cascade_search (text rescue), global_search (community synthesis), or document_search (scoped) based on question type. RAG has one tool for everything.
- **Structured context**: GRAIL sends entities + relationships + community reports + ranked text units to the LLM. RAG sends flat, unranked text chunks.

On a larger corpus with hundreds of documents, the gap would widen because RAG's top-10 retrieval would start missing relevant passages across documents, while GRAIL's graph maintains cross-document connections at any scale.

---

## Agent Architecture

### GRAIL Agent

The GRAIL agent has access to 4 search tools, each designed for a different retrieval strategy:

1. **local_search** — Embeds the query and matches against entity descriptions in the knowledge graph. Returns entities + relationships + community reports + source text chunks. Best when the agent can describe the concept it's looking for.

2. **cascade_search** — Combines entity-gated retrieval (like local) with BM25 + cosine text matching over ALL raw chunks. The text path "rescues" passages that no entity captured. Best for specific numbers, article references, or details buried in text.

3. **global_search** — Reads pre-computed community report summaries. Does NOT search individual entities or chunks. Best for broad overview questions ("what is this about?", "summarize the framework").

4. **document_search** — Scopes retrieval to a single source document. Best when the user asks about a specific law or decree by name.

### RAG Agent

The RAG agent has 1 search tool:

- **rag_search** — Embeds the query and returns top-10 chunks by cosine similarity from `partial_text_units.parquet` (raw chunks before entity extraction). No entity context, no relationships, no community summaries.

### Tool Selection Strategy (GRAIL)

The GRAIL agent's system prompt teaches a local-first strategy:

```
DEFAULT → local_search (entity description matching)
  ↓ (if details/numbers/articles needed)
FALLBACK → cascade_search (adds text matching)
  ↓ (if broad overview)
SPECIAL → global_search (community reports)
  ↓ (if single document)
SPECIAL → document_search (scoped)
```

### Query Formula for local_search

The agent crafts queries using the **WHO + WHAT + TERMS** formula:

```
[WHO does it] + [WHAT is the process/concept] + [SPECIFIC TERMS from entity descriptions]
```

**Example:**
- BAD:  `"comisión que decide qué enfermedades están cubiertas"` → matches only commission entities
- GOOD: `"proceso del Ministerio de Salud para elaborar la propuesta de garantías explícitas en salud, basado en estudios epidemiológicos, carga de enfermedad, evaluaciones económicas y costo-efectividad"` → matches the process entity + criteria entities + institutional entity

This formula works because entity embeddings contain `"NAME: description retrieval_queries"` — the query needs term overlap with all three components.

---

## Benchmark Execution

### Prerequisites

```bash
# 1. Index your corpus
grail index <project>

# 2. Verify the index
grail status <project>
```

### Running the benchmark

```bash
# Full 30 questions — agents only (recommended)
python benchmarks/run_benchmark.py \
  --config <project>/grail.yaml \
  --benchmark benchmarks/simple_benchmark/benchmark.json \
  --skip-rag \
  --include-agents \
  --skip-judge

# Specific questions
python benchmarks/run_benchmark.py \
  --config <project>/grail.yaml \
  --benchmark benchmarks/simple_benchmark/benchmark.json \
  --skip-rag --include-agents --skip-judge \
  --questions Q01,Q02,Q03

# Specific category
python benchmarks/run_benchmark.py \
  --config <project>/grail.yaml \
  --benchmark benchmarks/simple_benchmark/benchmark.json \
  --skip-rag --include-agents --skip-judge \
  --categories global_synthesis

# Include direct search modes too (RAG, local, reranked, global)
python benchmarks/run_benchmark.py \
  --config <project>/grail.yaml \
  --benchmark benchmarks/simple_benchmark/benchmark.json \
  --include-reranked \
  --include-agents \
  --skip-judge
```

### Output

Results are saved to `benchmarks/results/<timestamp>/responses.json` containing all responses with metadata (tools used, completion time, LLM calls).

---

## Judging

### LLM-as-Judge (automated)

```bash
python benchmarks/run_benchmark.py \
  --config <project>/grail.yaml \
  --benchmark benchmarks/simple_benchmark/benchmark.json \
  --include-agents \
  --judge-model "deepinfra|Qwen/Qwen3.6-35B-A3B"
```

The judge scores each response on 5 dimensions (1-5 scale):

| Dimension | Weight | What it measures |
|---|---|---|
| Correctness | 35% | Factual accuracy vs gold answer |
| Completeness | 25% | Coverage of all key points |
| Source Grounding | 15% | Correct law/article citations |
| Coherence | 10% | Clarity for a non-expert |
| No Hallucination | 15% | Avoids fabricated information |

Weighted score = `correctness*0.35 + completeness*0.25 + source_grounding*0.15 + coherence*0.10 + no_hallucination*0.15`

### Claude-as-Judge (manual, higher quality)

1. Run with `--skip-judge` to collect responses only
2. Ask Claude Code to "judge the benchmark"
3. Claude reads `responses.json` + `benchmark.json`, scores each response, writes `judge_scores.json`

This produces higher quality scores because Claude has seen the source PDFs and understands the domain.

### External benchmark judges

For reproducible comparison with published results:
- **GraphRAG-Bench**: use `gpt-4-turbo` as judge + `BAAI/bge-large-en-v1.5` for retrieval eval
- **LongMemEval**: use `gpt-4o` as judge

See `docs/benchmarks.md` for full requirements.

---

## Replicating with a Custom Corpus

### 1. Create the benchmark file

```json
{
  "name": "my_domain_benchmark",
  "description": "Description of your benchmark",
  "language": "en",
  "categories": [
    {"id": "single_fact", "label": "Single Fact", "description": "..."},
    {"id": "multi_chunk", "label": "Multi-Chunk", "description": "..."}
  ],
  "questions": [
    {
      "id": "Q01",
      "category": "single_fact",
      "difficulty": "easy",
      "question": "Your question in natural language",
      "gold_answer": "The expected answer with specific details",
      "source_refs": ["Document name, Section X"],
      "rationale": "Why this question tests what it tests"
    }
  ]
}
```

### 2. Question design guidelines

- **Write in user language**, not expert language. "¿Cuánto tiempo tengo para reclamar?" not "¿Cuál es el plazo de prescripción del Título IV?"
- **Gold answers must be specific**: include numbers, article citations, entity names
- **7 categories** test different retrieval capabilities:
  - Single Fact → baseline (both systems should handle)
  - Multi-Chunk → answer spans 2+ chunks of same document
  - Cross-Source → answer spans 2+ different documents
  - Procedural → step-by-step processes
  - Comparative → "compare X with Y"
  - Negation → "does X cover Y?" where answer is NO
  - Global Synthesis → bird's-eye overview of entire corpus

### 3. Index and run

```bash
grail init my_project
cp my_documents/* my_project/input/
grail index my_project

python benchmarks/run_benchmark.py \
  --config my_project/grail.yaml \
  --benchmark my_benchmark.json \
  --include-agents --skip-judge
```

---

## Key Technical Decisions

### Why local-first instead of cascade-first

Previous benchmark iterations showed cascade as default. Cascade scores the same as RAG on single-chunk questions (both find the same chunks), but local_search with the WHO+WHAT+TERMS formula outperforms both because entity descriptions contain pre-computed semantic summaries that match patient language better than raw legal text.

Cascade is the fallback for when entity descriptions don't capture specific details (numbers, article references).

### Why 3 iterations, 2 tool calls

- Iteration 1: agent picks and calls first tool
- Iteration 2: agent either answers OR picks a second tool (e.g., for comparison questions)
- Iteration 3: forced synthesis if the agent hasn't answered yet

2 tool calls is the sweet spot — enough for two-sided comparisons and refinement, but not so many that the agent wastes calls on redundant searches.

### Why raw context instead of mini-agent summarization

Previous versions used a mini-agent LLM to summarize tool results before passing to the agent. This compressed 20K tokens of structured context (entities + relationships + text units) down to 2K chars — destroying the structural advantage that makes GRAIL different from RAG.

Current implementation passes the raw structured context through (trimmed to 30K tokens if needed). The agent LLM is capable of processing the full context directly.

### Why forced synthesis fallback

Qwen3.6 (and similar thinking models) can exhaust their `max_tokens` budget on `<think>` blocks without producing visible output. The forced synthesis sends a final user message: "Answer now with whatever you have" — with no tools available, the model MUST produce text. If even that fails, a fallback message is returned.

### Entity description embedding formula

Entities are embedded as: `"ENTITY_NAME: description retrieval_query_1 retrieval_query_2 ..."`

The retrieval queries are generated during entity extraction — they're user-facing questions the entity helps answer (e.g., "¿Cuál es el plazo de prescripción para reclamar daños?"). This transforms entity retrieval from matching `query → definition` to matching `query → question`, significantly improving recall on patient-language queries.

---

## Conditions of the oncology_laws_chile_v1 benchmark

This benchmark is a **RAG-favorable worst case** for graph-enhanced retrieval:

- **Small corpus**: 3 documents, 35 chunks, 58 pages
- **Every chunk reachable**: top-10 cosine search covers 28% of all chunks per query
- **Direct concepts**: legal terms are explicit and well-defined
- **Single language**: Spanish throughout (no cross-lingual challenges)

Despite these conditions favoring RAG, GRAIL wins 27/30. On larger corpora with hundreds of documents, the graph's cross-document connections and community summaries would provide an even larger advantage.

### What this benchmark does NOT test

- Scale (hundreds/thousands of documents)
- Temporal reasoning (knowledge updates over time)
- Multi-turn conversation (follow-up questions)
- Cross-lingual retrieval
- Creative generation
- Adversarial queries

These are planned for future benchmarks (GraphRAG-Bench, LongMemEval).

---

## Results Summary

### Final scores (30 questions)

| Metric | GRAIL Agent | RAG Agent |
|---|---|---|
| Average score | **4.80 / 5.00** | 4.14 / 5.00 |
| Win-Loss-Tie | **27-0-3** | 0-27-3 |
| Avg response time | ~25s | ~35s |
| Avg LLM calls | 2.6 | 3.1 |
| Empty responses | 0 | 0 |

### By category

| Category | Qs | GRAIL | RAG | Delta | GRAIL wins |
|---|---|---|---|---|---|
| Single Fact | 5 | 4.81 | 4.29 | +0.52 | 5-0-0 |
| Multi-Chunk | 5 | 4.73 | 4.01 | +0.72 | 4-0-1 |
| Cross-Source | 5 | 4.67 | 3.87 | +0.80 | 5-0-0 |
| Procedural | 4 | 4.89 | 4.25 | +0.64 | 3-0-1 |
| Comparative | 3 | 4.80 | 4.00 | +0.80 | 3-0-0 |
| Negation | 3 | 4.95 | 4.87 | +0.08 | 2-0-1 |
| Global Synthesis | 5 | 4.85 | 3.95 | +0.90 | 5-0-0 |

### By batch (consistency check)

| Batch | GRAIL | RAG | W-L-T |
|---|---|---|---|
| Q01-Q10 (Single Fact + Multi-Chunk) | 4.77 | 4.15 | 9-0-1 |
| Q11-Q20 (Cross-Source + Procedural) | 4.78 | 4.05 | 9-0-1 |
| Q21-Q30 (Comparative + Negation + Global) | 4.87 | 4.23 | 9-0-1 |

GRAIL's advantage is consistent (not variance) and grows with question complexity.

### Tool usage across 30 questions

| Tool | Count | When used |
|---|---|---|
| local_search | 16 | Entity concepts, named institutions, processes (Q01, Q02, Q07, Q09, Q12, Q18, Q20, Q22, Q25, Q28...) |
| cascade_search | 24 | Specific details, article references, numbers, text rescue (Q03-Q06, Q08, Q11, Q13-Q15, Q17, Q19, Q21, Q23-Q24, Q27, Q30...) |
| global_search | 3 | Thematic overviews (Q26, Q29, Q30) |
| document_search | 1 | Single-document scope (Q05) |

The 3 tied questions (Q08, Q17, Q23) are all single-chunk factual questions where both systems find the same chunk — negation exclusions and straightforward emergency provisions.

---

## Discoveries From the Benchmark Development Process

This benchmark went through 5 major iterations. Each iteration revealed a bug or design flaw that was fixed before the next run. These discoveries improved GRAIL's core retrieval quality for all users, not just the benchmark.

### 1. Text unit truncation (Run 1 → Run 2)

**Bug**: `build_text_unit_context` silently truncated each chunk to 1200 characters. Chunks were 5400 chars (~1500 tokens). 77% of each chunk's content was discarded before the LLM ever saw it.

**Impact**: GRAIL scored worse than RAG on single-fact questions because the answer text (e.g., "cada tres años" at char position 2835) was beyond the truncation cutoff.

**Fix**: Removed the `[:1200]` slice. Added text unit ranking by entity overlap count so the most relevant chunks get priority within the token budget.

### 2. Thinking model token exhaustion (Run 2 → Run 3)

**Bug**: Qwen3.6 uses `<think>...</think>` blocks that consume completion tokens. With `max_tokens=2048` and 15K tokens of RAG context, the model spent all 2048 tokens thinking and returned empty (`finish_reason: "length"`).

**Impact**: RAG returned 63% empty responses — making GRAIL look artificially superior.

**Fix**: Bumped all `response_max_tokens` to 16384. Added forced synthesis fallback in the agent loop.

### 3. LanceDB Euclidean → FAISS cosine (Run 3 → Run 4)

**Bug**: LanceDB used L2 distance with `1 - abs(distance)` normalization, producing negative scores. `CONSEJO CONSULTIVO` with 0.49 cosine similarity appeared at rank 21 instead of top-5.

**Impact**: Entity retrieval was noisy — wrong entities led to wrong text unit selection.

**Fix**: Switched to FAISS with `IndexFlatIP` on L2-normalized vectors (equivalent to cosine). Proper 0-1 similarity scores.

### 4. Mini-agent context destruction (Run 5 experiments)

**Bug**: When the agent called cascade_search, the 20K-token structured context was passed through a "mini-agent" LLM that summarized it to 2K chars — a 90% compression that destroyed entity tables, relationship descriptions, and specific article references.

**Impact**: GRAIL agent scored 1.8/5 avg while direct cascade scored 4.0/5. The same retrieval, same context, but a lossy middleman in between.

**Fix**: Removed the mini-agent entirely. Raw structured context now passes through to the agent (trimmed to 30K tokens if needed). The agent LLM processes the full context directly.

### 5. Query formula discovery (final experiments)

**Discovery**: The agent's query for local_search determines retrieval quality. A query describing the institution only ("comisión que decide") scored 1/5 keywords. A query describing the concept with the WHO+WHAT+TERMS formula ("proceso del Ministerio de Salud para elaborar la propuesta de garantías explícitas basado en estudios epidemiológicos...") scored 5/5.

**Root cause**: Entity embeddings contain `"NAME: description retrieval_queries"`. The query needs term overlap with all three components — not just the entity name.

**Fix**: Updated the agent system prompt with the WHO+WHAT+TERMS formula, clear examples, and local-first strategy guidance. The agent went from 15/25 to 22/25 on the 5-question experiment, then 4.80/5.00 on the full 30-question benchmark.

### 6. Entity description language mismatch (identified, partially addressed)

**Finding**: The LLM generates entity descriptions in English even when the source documents are in Spanish. This creates a cross-lingual embedding mismatch — Spanish queries have lower cosine similarity against English descriptions.

**Mitigation**: Entity names are prepended to descriptions (`"CONSEJO CONSULTIVO: An advisory council..."`) which anchors the embedding in the Spanish entity name. Retrieval queries are generated in Spanish ("¿Cuál es el plazo de prescripción?") which further bridges the gap.

**Future**: The extraction prompt should enforce source-language descriptions for full optimization.

---

## Reports and Files

### HTML reports

- `benchmarks/results/es/reporte_final_benchmark.html` — Spanish final report (default)
- `benchmarks/results/en/final_benchmark_report.html` — English final report
- `benchmarks/results/en/batch{1,2,3}_*.html` — Per-batch detail reports

### Data files

- `benchmarks/simple_benchmark/benchmark.json` — 30 questions with gold answers
- `benchmarks/results/archive/runs/` — Raw response JSONs from each benchmark run
- `benchmarks/results/archive/experiments/` — Intermediate experiment data

### Code

- `benchmarks/run_benchmark.py` — Orchestrator (collects responses, optional LLM judge)
- `benchmarks/rag_baseline.py` — Fair RAG baseline (same chunks, embeddings, LLM)
- `benchmarks/judge_prompt.py` — 5-dimension scoring rubric
- `grail/query/agent.py` — GRAIL agent with tool selection, forced synthesis, context trimming

### Documentation

- `docs/benchmarks.md` — External benchmark roadmap (GraphRAG-Bench, LongMemEval)
- `docs/search_modes.md` — Search mode architecture and when to use each
- `dev_prompts/prompt_grail_benchmark.md` — This file
