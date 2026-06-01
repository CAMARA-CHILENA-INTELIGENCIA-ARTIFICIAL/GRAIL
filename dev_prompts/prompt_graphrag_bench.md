# GraphRAG-Bench — Integration Plan & Cost Analysis (KB Mode)

> For the memory-mode benchmark (LongMemEval v1), see the dedicated section at the end of this file.

## What It Is

GraphRAG-Bench (arXiv:2506.05690, ICLR 2026) is a benchmark that evaluates **when** graph-based RAG outperforms vanilla RAG. It tests the entire GraphRAG pipeline — graph construction, retrieval, and answer generation — across 4 difficulty levels.

**Paper:** "When to use Graphs in RAG: A Comprehensive Analysis for Graph Retrieval-Augmented Generation"  
**Repo:** `https://github.com/GraphRAG-Bench/GraphRAG-Benchmark`  
**Dataset:** `GraphRAG-Bench/GraphRAG-Bench` on HuggingFace (MIT license)

---

## Why This Benchmark Matters for GRAIL

MS-GraphRAG (GRAIL's ancestor) is already benchmarked and **performs poorly**:
- Global search: **36.92%** accuracy on Novel Fact Retrieval
- Local search: **~47%** accuracy on Novel

Other graph RAG baselines tested: LightRAG, fast-graphrag, hipporag2, RAPTOR, Lazy-GraphRAG, KGP, StructRAG, KET-RAG. The paper's key finding is that GraphRAG frequently **underperforms** vanilla RAG on simple fact retrieval but excels on multi-hop reasoning. GRAIL's cascade search mode is specifically designed to solve that Level 1 weakness.

If GRAIL beats MS-GraphRAG numbers, it's a direct "we improved the original" narrative for the open-source release.

---

## Dataset Structure

### Corpora

| Domain | Documents | Tokens (o200k) | Chunks (2K) | Source |
|--------|-----------|----------------|-------------|--------|
| **Novel** | 20 novels | 1,116,795 | ~572 | Project Gutenberg (pre-20th-century, lesser-known works) |
| **Medical** | 1 monolith | 218,464 | ~112 | NCCN clinical guidelines |
| **Total** | 21 | 1,335,259 | ~684 | |

Novel documents range from 22,806 to 108,871 tokens each (full-length books).  
Medical is a single concatenated document covering multiple cancer types.

### Questions

| Domain | Fact Retrieval (L1) | Complex Reasoning (L2) | Contextual Summarize (L3) | Creative Generation (L4) | Total |
|--------|--------------------|-----------------------|--------------------------|-------------------------|-------|
| Novel | 971 | 610 | 362 | 67 | 2,010 |
| Medical | 1,098 | 509 | 289 | 166 | 2,062 |
| **Total** | **2,069** | **1,119** | **651** | **233** | **4,072** |

### Question Format

```json
{
  "id": "Novel-73586ddc",
  "source": "Novel-44557",
  "question": "Which plant known as Erica vagans is also referred to by what common name?",
  "answer": "Cornish heath",
  "question_type": "Fact Retrieval",
  "evidence": ["The plant known as Erica vagans is referred to as Cornish heath."],
  "evidence_triple": ["(erica vagans, is also known as, Cornish heath)."]
}
```

The `evidence_triple` field contains gold knowledge-graph triples — this is what makes it a graph RAG benchmark. For medical questions the field is `evidence_relations`.

### Output Format Required

```json
{
  "id": "Novel-73586ddc",
  "question": "Which plant known as Erica vagans is also referred to by what common name?",
  "source": "Novel-44557",
  "context": ["<retrieved context from GRAIL>"],
  "evidence": ["<from dataset>"],
  "question_type": "Fact Retrieval",
  "generated_answer": "<GRAIL's answer>",
  "ground_truth": "Cornish heath"
}
```

---

## Evaluation Stack

Three evaluation modules in their repo. **Critical: use their exact models for comparable results.**

### Generation Eval (`Evaluation/generation_eval.py`)

| Level | Metrics |
|-------|---------|
| Fact Retrieval | Accuracy (ACC) + ROUGE-L |
| Complex Reasoning | Accuracy + ROUGE-L |
| Contextual Summarize | Accuracy + Coverage |
| Creative Generation | Accuracy + Faithfulness Score + Coverage |

- **LLM Judge:** `gpt-4o-mini` (from their README; `docs/benchmarks.md` says `gpt-4-turbo` — verify before running)
- **Embedding for eval:** `BAAI/bge-large-en-v1.5`
- Answers are boxed: model should output `\boxed{answer}`

### Retrieval Eval (`Evaluation/retrieval_eval.py`)

- **Evidence Recall:** Do all gold evidence components appear in retrieved context?
- **Context Relevance:** Semantic similarity between query and retrieved context

### Indexing Eval (`Evaluation/indexing_eval.py`)

- Graph structure metrics: node count, edge count, avg degree, clustering coefficient, density
- Supports multiple graph formats including graphml (GRAIL uses this)

### Eval Commands

```bash
# Generation evaluation
python -m Evaluation.generation_eval \
  --mode API --model gpt-4o-mini \
  --base_url https://api.openai.com/v1 \
  --embedding_model BAAI/bge-large-en-v1.5 \
  --data_file ./results/grail.json \
  --output_file ./results/grail_gen_eval.json

# Retrieval evaluation
python -m Evaluation.retrieval_eval \
  --mode API --model gpt-4o-mini \
  --base_url https://api.openai.com/v1 \
  --embedding_model BAAI/bge-large-en-v1.5 \
  --data_file ./results/grail.json

# Indexing evaluation
python -m Evaluation.indexing_eval \
  --graph_file ./output/entity_relationship_graph.graphml \
  --format graphml
```

---

## Models Required by Each Benchmark

### GraphRAG-Bench

| Role | Model | Price (per M tokens) | Notes |
|------|-------|---------------------|-------|
| **Reader** (generates answers) | `gpt-4o-mini` | $0.15 in / $0.60 out | Their Table 2 uses this; framework rankings stay consistent across models |
| **Judge** (scores answers) | `gpt-4-turbo` | $10 in / $30 out | Paper says gpt-4-turbo; their repo README shows gpt-4o-mini — **verify before committing $200** |
| **Eval embeddings** | `BAAI/bge-large-en-v1.5` | Free (local) | Used for retrieval eval's semantic similarity |
| Secondary reader | `Qwen2.5-14B` | Free (local) | Their Appendix B — shows rankings are model-agnostic |

**Does changing the reader invalidate comparison?** Partially. Their leaderboard uses gpt-4o-mini. Using Gemma as reader means your numbers are an internal validation, not publishable against their table. However, their eval pipeline still works — you just compare GRAIL-with-Gemma vs RAG-with-Gemma (same reader, different retrieval).

### LongMemEval v1

| Role | Model | Price (per M tokens) | Notes |
|------|-------|---------------------|-------|
| **Reader** (generates answers) | `GPT-4o` (primary) | $2.50 in / $10 out | Their strongest baseline row |
| **Reader** (alternative) | `Llama 3.1 8B Instruct` | ~$0.05 in / $0.08 out | Also in their tables — valid comparison |
| **Retrieval** | `dunzhang/stella_en_1.5B_v5` | Free (local) | Their default dense retriever (Stella V5 1.5B) |
| **Judge** (scores answers) | `gpt-4o` (`2024-08-06`) | $2.50 in / $10 out | Binary yes/no, >97% human agreement |

**Does changing the reader invalidate comparison?** No. They report results per reader model. Compare GRAIL's GPT-4o results against their GPT-4o row, or GRAIL's Llama-8B results against their Llama-8B row.

---

## Cost Estimates — Three Tiers

Based on real SEOM indexing manifests, scaled by token count.

### Tier 1: Testing (internal validation, cheapest)

Use GRAIL's default models (Gemma-4-26B for extraction/reader, gpt-4o-mini as judge). Results are valid for comparing GRAIL modes against each other but NOT publishable against their leaderboard.

### Tier 2: Comparable Reader (publishable retrieval comparison)

Use their reader model (gpt-4o-mini for GraphRAG-Bench, GPT-4o for LongMemEval) but a cheaper judge. Results show GRAIL vs their baselines with the same reader, but judge scores may differ slightly.

### Tier 3: Fully Official (publishable, directly comparable)

Use their exact reader + judge. Results are directly comparable to their published numbers.

---

## GraphRAG-Bench Cost Breakdown

### Indexing Cost (GRAIL internal, one-time)

| Model | Novel (572 chunks) | Medical (112 chunks) | Both |
|-------|-------------------|---------------------|------|
| **Gemma-4-26B-A4B** ($0.07/$0.34 per M tok) | **$0.67** | **$0.12** | **$0.79** |
| Qwen3.6-35B-A3B ($0.15/$0.95 per M tok) | $9.63 | $1.86 | $11.49 |

Gemma is the default. Qwen3.6 is 14x more expensive due to thinking tokens (~80% output is `<think>`).

**Breakdown (Gemma, Novel):**
- Entity extraction: 572 calls, $0.43 (65% of cost)
- Summarization: 286 calls, $0.08
- Entity dedup: 143 calls, $0.06
- Community reports: ~80 calls, $0.10
- Embeddings: negligible

**Wall time (Gemma, 8 concurrent):** ~45–60 minutes for Novel. Qwen3.6: 2–3 hours.

### Query + Judge Cost (per tier)

| Tier | Reader model | Reader cost (4,072 q) | Judge model | Judge cost (4,072 q) | **Total (index + queries + judge)** |
|------|-------------|----------------------|-------------|---------------------|------|
| **Testing** | Gemma-4-26B ($0.07/$0.34) | $8.47 | gpt-4o-mini ($0.15/$0.60) | $3.05 | **$12** |
| **Comparable** | gpt-4o-mini ($0.15/$0.60) | $17.10 | gpt-4o-mini ($0.15/$0.60) | $3.05 | **$21** |
| **Official** | gpt-4o-mini ($0.15/$0.60) | $17.10 | gpt-4-turbo ($10/$30) | $183.24 | **$201** |

### Preview Cost (20 questions, Novel only)

| Tier | Total |
|------|-------|
| Testing | **$0.85** |
| Comparable | $0.89 |
| Official | $1.77 |

### Agent Mode (3 iterations per question, multiply reader cost by ~3)

| Tier | Total (4,072 q) |
|------|-----------------|
| Testing | **$29** |
| Comparable | $55 |
| Official | $235 |

**Recommendation:** Start with **Testing tier** to validate the integration. Then run **Comparable tier** to produce publishable numbers with gpt-4o-mini reader. Only commit to **Official tier** after verifying the judge model discrepancy (paper says gpt-4-turbo, repo README shows gpt-4o-mini — check their latest code before spending $183 on judging).

---

## Precise Cost Summary (with Qwen3.6-35B-A3B for testing)

Testing uses our default model (Qwen3.6-35B-A3B at $0.15/$0.95 per M tokens). This model uses thinking tokens — ~80% of output is `<think>` blocks, so output is ~8K tokens per query instead of ~2K.

### GraphRAG-Bench — Separated Indexing vs Inference

**Architecture:** 1 shared index, queried 4,072 times.

**Indexing (one-time, Qwen3.6):** $11.49
- Entity extraction: 684 calls, $8.38
- Summarization: 342 calls, $1.54
- Entity dedup: 171 calls, $1.08
- Community reports: 90 calls, $0.49

**Inference (per-query):**
- Qwen3.6 reader: $0.0106/query (20K in + 8K out thinking)
- gpt-4o-mini judge: $0.0008/query
- gpt-4-turbo judge: $0.045/query (official, expensive)

| Scenario | Indexing | Inference | **TOTAL** |
|----------|---------|-----------|-----------|
| Testing 30q (Qwen3.6 reader + 4o-mini judge) | $11.49 | $0.34 | **$11.83** |
| Testing FULL 4,072q (Qwen3.6 reader + 4o-mini judge) | $11.49 | $46.22 | **$57.70** |
| Official 30q (4o-mini reader + 4-turbo judge) | $11.49 | $1.48 | **$12.96** |
| Official FULL 4,072q (4o-mini reader + 4-turbo judge) | $11.49 | $200.34 | **$211.83** |

**Bottleneck:** The $183 gpt-4-turbo judge cost dominates the official full run. For testing, it's the 4,072 × $0.0106 Qwen3.6 reader calls ($43).

---

## Integration Plan

### Step 1: Data Setup

```bash
# Clone their repo
git clone https://github.com/GraphRAG-Bench/GraphRAG-Benchmark.git
cd GraphRAG-Benchmark

# Or download just the data from HuggingFace
python -c "
from datasets import load_dataset
ds = load_dataset('GraphRAG-Bench/GraphRAG-Bench', config_name='novel')
ds.save_to_disk('./data/novel')
"
```

The corpus files are at `Datasets/Corpus/novel.json` and `medical.json`. Each JSON has entries with `corpus_name` and `context` (full text).

### Step 2: Corpus Preparation

Each Novel entry is a full book (22K–109K tokens). Two approaches:

**Option A — Index each novel as a separate document (recommended):**
- Create a GRAIL project with `input/` containing 20 text files, one per novel
- `grail index` processes them as separate documents with provenance tracking
- This is how GRAIL is designed to work

**Option B — Index as one combined corpus:**
- Concatenate all novels into one file
- Simpler but loses document-level provenance

For Medical, it's already one document.

### Step 3: Build `benchmarks/graphrag_bench/run_benchmark.py`

Core logic (~150 lines):

```python
import json
from grail.core import GRAIL

async def run_benchmark(
    project_dir: str,
    questions_file: str,
    search_mode: str = "local",  # or "cascade", "global", "agent"
    output_file: str = "results/grail.json",
    sample: int | None = None,
    question_types: list[str] | None = None,
):
    grail = await GRAIL.from_config(project_dir)
    questions = json.loads(Path(questions_file).read_text())
    
    if question_types:
        questions = [q for q in questions if q["question_type"] in question_types]
    if sample:
        questions = questions[:sample]
    
    results = []
    for q in questions:
        result = await grail.search(
            query=q["question"],
            search_type=search_mode,
        )
        results.append({
            "id": q["id"],
            "question": q["question"],
            "source": q["source"],
            "context": [result.context_text],
            "evidence": q["evidence"],
            "question_type": q["question_type"],
            "generated_answer": result.response,
            "ground_truth": q["answer"],
        })
    
    Path(output_file).write_text(json.dumps(results, indent=2))
```

### Step 4: Run

```bash
# Index the Novel corpus
grail init graphrag_bench_novel --template low_cost_setup
# Copy novel text files to graphrag_bench_novel/input/
grail index graphrag_bench_novel

# 20-question preview
python benchmarks/graphrag_bench/run_benchmark.py \
  --project graphrag_bench_novel \
  --questions Datasets/Questions/novel_questions.json \
  --mode local --sample 20 \
  --output results/grail_novel_preview.json

# Full run
python benchmarks/graphrag_bench/run_benchmark.py \
  --project graphrag_bench_novel \
  --questions Datasets/Questions/novel_questions.json \
  --mode local \
  --output results/grail_novel_full.json

# Evaluate with their scripts
cd GraphRAG-Benchmark
python -m Evaluation.generation_eval \
  --mode API --model gpt-4o-mini \
  --base_url https://api.openai.com/v1 \
  --embedding_model BAAI/bge-large-en-v1.5 \
  --data_file ../results/grail_novel_full.json \
  --output_file ../results/grail_novel_eval.json
```

### Step 5: Compare Multiple Search Modes

Run the benchmark with different GRAIL search modes to find the best per level:

| Question Type | Expected Best Mode | Why |
|---------------|--------------------|-----|
| Fact Retrieval (L1) | `cascade` | Combines entity matching with direct text search — solves the classic GraphRAG L1 weakness |
| Complex Reasoning (L2) | `local` or `agent` | Multi-hop needs entity-relationship traversal |
| Contextual Summarize (L3) | `global` | Community reports synthesize across documents |
| Creative Generation (L4) | `agent` | Needs multiple search strategies + reasoning |

---

## Technical Considerations

### Language

Both corpora are **English**. This is an advantage over our Chilean law benchmark — no cross-lingual entity embedding issues. Entity descriptions and retrieval queries will match the query language natively.

### Corpus Size

The Novel corpus (1.1M tokens) is ~20x larger than our SEOM benchmark (3 PDFs). This will test GRAIL at a meaningful scale for the first time. Key things to watch:

- **Entity count:** Expect 2,000–5,000 entities across 20 novels. Our FAISS cosine vectorstore should handle this fine.
- **Community structure:** 20 separate novels → expect largely disconnected subgraphs (one per novel). The Leiden algorithm should produce natural per-novel clusters.
- **Cross-document questions:** Some questions may require information from multiple novels. GRAIL's graph handles this naturally via entity deduplication (if the same character/concept appears in multiple works).

### `\boxed{}` Answer Format

Their eval expects answers wrapped in `\boxed{...}`. Add this instruction to the search prompt or post-process the response:

```python
# Either instruct the LLM in the system prompt:
# "Wrap your final answer in \\boxed{your answer here}"
# Or post-process:
answer = f"\\boxed{{{result.response.strip()}}}"
```

### Evidence Triples

Each question includes gold `evidence_triple` entries like `(erica vagans, is also known as, Cornish heath)`. These map directly to GRAIL's entity-relationship pairs. The retrieval eval can measure how many of these triples appear in GRAIL's retrieved context — a direct test of graph construction quality.

### Questions Per Source Document

Each question has a `source` field (e.g., `Novel-44557`) mapping to one corpus entry. For the Novel domain, this means we can evaluate per-novel performance and identify which novels GRAIL handles well vs. poorly.

---

## Strategic Positioning

### What to Highlight if GRAIL Wins

1. **"GRAIL solves GraphRAG's Level 1 problem."** MS-GraphRAG global scored 36.92% on Fact Retrieval. If GRAIL's cascade search beats vanilla RAG on L1 while maintaining L2-L4 advantages, it demonstrates a fundamental improvement over the original.

2. **"Same pipeline, better architecture."** GRAIL uses the same core pipeline (entities → communities → reports) but with better context budgeting, mixed-content local search, and agent mode. Apples-to-apples comparison.

3. **"Agent mode adapts per question."** The agent can pick local (entity matching) for L2, global (community reports) for L3, and cascade (text rescue) for L1 — all in one system.

### What to Watch For

- **L1 (Fact Retrieval):** This is where GraphRAG systems historically fail. If GRAIL's cascade search still underperforms RAG here, investigate whether entity extraction missed the key fact.
- **L3 (Contextual Summarize):** This should be GRAIL's strongest level — community reports are literally designed for summarization.
- **L4 (Creative Generation):** Only 67 Novel + 166 Medical questions. Small sample, high variance.

---

## Files Reference

| File | Purpose |
|------|---------|
| `benchmarks/graphrag_bench/run_benchmark.py` | Main runner (to be built) |
| `benchmarks/graphrag_bench/prepare_corpus.py` | Convert novel.json → individual text files (to be built) |
| `benchmarks/graphrag_bench/README.md` | Replication instructions (to be built) |
| `docs/benchmarks.md` | External benchmark roadmap (already exists, update with cost estimates) |
| External: `GraphRAG-Benchmark/Evaluation/` | Their eval scripts (use as-is) |
| External: `GraphRAG-Benchmark/Datasets/` | Corpus + questions |

---

## Decisions to Make Before Running

1. **Which search modes to benchmark?** Recommend: local, cascade, global, agent (4 runs per domain).
2. **Which model for GRAIL inference?** Recommend: Gemma-4-26B-A4B-it (cheap) for the first run, then optionally repeat with Qwen3.6 to measure thinking model impact.
3. **Which judge model?** Their code defaults to `gpt-4o-mini`. Their README shows this. The `docs/benchmarks.md` says `gpt-4-turbo` — **verify from their latest code before running.** Using the wrong judge invalidates comparison.
4. **Entity types?** The Novel corpus is literature — standard `PERSON, ORGANIZATION, LOCATION, EVENT, CONCEPT` should work. Medical may benefit from domain-specific types (`DRUG, DISEASE, TREATMENT, GENE, BIOMARKER`).
5. **Reranker?** Run with and without to measure impact. Expect reranker to help L1 (Fact Retrieval) the most.
6. **`\boxed{}` formatting?** Must be handled — their eval extracts the boxed answer. Add to system prompt or post-process.

---
---

# LongMemEval v1 — Memory Mode Validation Benchmark

> Blocked on memory mode implementation. Run after Phases 2-3 of `dev_prompts/prompt_grail_agentic_memory_design.md` ship.

## What It Is

LongMemEval (arXiv:2410.10813, ICLR 2025) tests long-term memory of chat assistants — whether an agent can recall personal facts, aggregate information across sessions, track knowledge updates, and reason temporally about past interactions.

**Repo:** `https://github.com/xiaowu0162/LongMemEval`  
**Dataset:** `xiaowu0162/longmemeval-cleaned` on HuggingFace (MIT license)

---

## Why It Fits GRAIL Memory Mode

GRAIL's planned agentic memory feature (markdown observations → entity graph → temporal recall) maps directly to LongMemEval's categories:

| LongMemEval Category | GRAIL Memory Feature | Why Graph Helps |
|-----|------|------|
| **Multi-Session Reasoning** ("How many instruments do I own?") | Entity graph connects concepts across sessions | Graph links GUITAR, PIANO, VIOLIN as separate entities across 40+ sessions — structural aggregation |
| **Knowledge Updates** ("I changed my trip to Paris") | `SUPERSEDES` relationship + `edit_extract` + orphan pruning | Graph tracks which facts replaced which |
| **Temporal Reasoning** ("How long since my last museum visit?") | `recall --since/--before` + `observed_at` timestamps | Temporal filters on entity/text_unit metadata |
| **Information Extraction** (single-session recall) | Cascade search + `retrieval_queries` enrichment | Anticipated questions embedded alongside content |
| **Abstention** ("I don't know") | Empty cascade result → explicit "insufficient data" | No hallucination when graph has no matching entities |

---

## Dataset Structure

**500 questions total** across 5 abilities (7 sub-types):

| Category | Approx. Count | Difficulty |
|----------|---------------|------------|
| Information Extraction (single-session-user) | ~135 | Easy — single needle |
| Information Extraction (single-session-assistant) | ~80 | Easy |
| Information Extraction (single-session-preference) | ~30 | Medium — personalization |
| Multi-Session Reasoning | ~135 | **Hard** — aggregation across sessions |
| Knowledge Updates | ~55 | Hard — detect superseded facts |
| Temporal Reasoning | ~70 | Hard — time-aware computation |
| Abstention | 30 | Medium — identify unanswerable |

**Two tiers:**

| Tier | Sessions/Question | Tokens/Question | Total Data |
|------|-------------------|-----------------|------------|
| **S (small)** | ~40 | ~115K | ~3 GB |
| M (medium) | ~500 | ~1.5M | ~3 GB |

We run **S tier** for cost efficiency.

**Per-question structure:**
- Each question has its OWN unique haystack (different mix of evidence sessions + distractors)
- Evidence is in 1-6 "needle" sessions buried among 34-39 distractor sessions
- Distractors: 25% ShareGPT + 25% UltraChat + 50% simulated non-conflicting
- Each session: multi-turn dialogue (up to 10 rounds)

**Question format:**
```json
{
  "question_id": "q_042",
  "question_type": "multi-session",
  "question": "How many musical instruments do I currently own?",
  "answer": "4",
  "question_date": "2024-03-15T10:00:00",
  "haystack_sessions": [...],
  "answer_session_ids": ["s_012", "s_087", "s_201", "s_345"]
}
```

---

## Models Required

| Role | Model | Price (per M tokens) | Notes |
|------|-------|---------------------|-------|
| **Reader** (primary) | `GPT-4o` (`gpt-4o-2024-08-06`) | $2.50 in / $10 out | Their strongest baseline (0.720 accuracy) |
| **Reader** (alternative) | `Llama 3.1 8B Instruct` | ~$0.05 in / $0.08 out (DeepInfra) | Also in their tables — valid comparison row |
| **Reader** (alternative) | `Llama 3.1 70B Instruct` | ~$0.20 in / $0.30 out (DeepInfra) | Middle-ground baseline |
| **Retrieval** | `dunzhang/stella_en_1.5B_v5` | Free (local) | Their default dense retriever |
| **Judge** | `gpt-4o` (`gpt-4o-2024-08-06`) | $2.50 in / $10 out | Binary yes/no, >97% human agreement |

**Does changing the reader invalidate comparison?** No. They report results per reader model. Compare your GPT-4o reader results against their GPT-4o row, Llama 8B against their Llama 8B row.

---

## Cost Estimates (S Tier)

Per question: 40 sessions × ~2,800 tokens = **112K tokens** → ~57 chunks at 2000-token chunk size.

### Precise Costs (Qwen3.6 for testing)

**Architecture:** 500 SEPARATE indexes (one per question). Use Gemma for bulk indexing (cheap), Qwen3.6 for reading (quality). DO NOT use Qwen3.6 for indexing — thinking tokens × 500 indexes = $419.

**Per-question costs:**
- Indexing (Gemma, graph): $0.056/question
- Indexing (embed-only): ~$0 (negligible)
- Reader (Qwen3.6, 20K in + 8K out thinking): $0.0106/query
- Reader (GPT-4o, 20K in + 2K out): $0.070/query
- Judge (GPT-4o, binary yes/no): $0.006/query

### Separated Indexing vs Inference

| Scenario | Indexing | Inference | **TOTAL** |
|----------|---------|-----------|-----------|
| **Testing 30q GRAPH** (Gemma idx + Qwen3.6 read + 4o judge) | $1.68 | $0.50 | **$2.18** |
| **Testing 30q EMBED** (Qwen3.6 read + 4o judge) | ~$0 | $0.50 | **$0.50** |
| **Testing FULL GRAPH** (Gemma idx + Qwen3.6 read + 4o judge) | $28.03 | $8.30 | **$36.33** |
| **Testing FULL EMBED** (Qwen3.6 read + 4o judge) | ~$0 | $8.30 | **$8.33** |
| **Official FULL GRAPH** (Gemma idx + GPT-4o read + 4o judge) | $28.03 | $38.00 | **$66.03** |

### Key Insight (OUTDATED — see "Fair Comparison" section below)

The above estimates used Gemma/Qwen3.6 for internal testing. For a publishable benchmark that competes against Zep, use the "Fair Comparison" flow below.

---

## Fair Comparison Against Zep (Correct Approach)

### Why This Matters

Zep (Graphiti) is the state-of-the-art on LongMemEval with **71.2% accuracy** (gpt-4o reader). To produce a publishable, apples-to-apples comparison, GRAIL must use the **same model** for indexing as Zep uses (`gpt-4o-mini`). The only variable should be the **retrieval architecture**.

### Zep's Architecture (from arXiv:2501.13956)

Zep processes each chat message with **5 sequential LLM calls** (all `gpt-4o-mini`):

1. **Entity extraction** — extract entities from current message + 4 previous messages
2. **Entity resolution** — compare each new entity against existing graph (dedup)
3. **Fact extraction** — extract relationship facts between identified entities
4. **Fact resolution** — dedup new facts against existing edges
5. **Temporal extraction** — assign `valid_at` / `invalid_at` timestamps

Storage: Neo4j graph + BGE-M3 embeddings (1024-dim)
Retrieval: Cosine + BM25 + BFS traversal → RRF/MMR reranking → top 20 edges+entities
Context sent to reader: ~1.6K tokens (compact facts)

### GRAIL's Architecture (for this benchmark)

GRAIL processes each session with **1 LLM call** (single-pass extraction):

1. **Entity + relationship extraction** — one prompt extracts everything: entities, relationships, types, descriptions, retrieval_queries

Storage: Parquet + FAISS (cosine) + NetworkX graph
Retrieval: Cascade search (entity-gate + BM25/cosine text rescue)
Context sent to reader: ~8-20K tokens (entities + relationships + community reports + text units)

### Why GRAIL Is 11x Cheaper on Indexing

| | Zep | GRAIL |
|---|---|---|
| Granularity | Per message (280 tokens each) | Per chunk (2000 tokens each) |
| Calls per unit | 5 (sequential pipeline) | 1 (single-pass) |
| Units per question | 400 messages | 60 chunks |
| **Total calls / question** | **2,000** | **~65** |
| **Total calls / 500 questions** | **1,000,000** | **36,500** |

Same model (`gpt-4o-mini`), same quality extraction — but GRAIL's single-pass prompt gets entities + relationships in one shot instead of 5 separate steps. This isn't cutting corners — it's better prompt engineering.

### Cost Breakdown (Fair Comparison, gpt-4o-mini for indexing)

**INDEXING (both using gpt-4o-mini):**

| System | Calls | Cost |
|--------|-------|------|
| **GRAIL** | 36,500 (extraction + summarization + community reports) | **$49** |
| **Zep** (estimated) | 1,000,000 (5 calls × 400 messages × 500 questions) | **~$525** |

GRAIL indexing breakdown:
- Extraction: 30,000 calls, $42
- Summarization: 5,000 calls, $3
- Community reports: 1,500 calls, $4
- Embeddings: ~$0.03

**INFERENCE (same for both systems):**

| Reader model | Reader cost (500q) | Judge cost (500q) | Total inference |
|---|---|---|---|
| gpt-4o-mini | $2.10 | $3.00 | **$5.10** |
| gpt-4o | $35.00 | $3.00 | **$38.00** |

**TOTAL COSTS:**

| Scenario | 30-question preview | Full 500 questions |
|----------|--------------------|--------------------|
| **GRAIL (gpt-4o-mini reader)** | **$3.22** | **$54** |
| **GRAIL (gpt-4o reader)** | **$5.19** | **$87** |
| Zep estimated (gpt-4o-mini reader) | — | ~$530 |
| Zep estimated (gpt-4o reader) | — | ~$563 |

### The Narrative

> "Same model (`gpt-4o-mini`), same benchmark (LongMemEval S tier, 500 questions), same evaluation (GPT-4o judge, binary accuracy). GRAIL achieves [X]% accuracy at $54 total cost. Zep reported 71.2% at an estimated $530+ cost (10x more expensive). The architectural difference: GRAIL's single-pass extraction replaces Zep's 5-step sequential pipeline, producing the same graph quality with 11x fewer LLM calls."

### Zep's Reported Results (Targets to Beat)

| Category | Zep (gpt-4o-mini) | Zep (gpt-4o) | Full-context baseline |
|----------|-------------------|--------------|-----------------------|
| single-session-user | 92.9% | 92.9% | 81.4% |
| single-session-assistant | 75.0% | 80.4% | 81.8% / 94.6% |
| single-session-preference | 53.3% | 56.7% | 30.0% / 20.0% |
| multi-session | 47.4% | 57.9% | 40.6% / 44.3% |
| knowledge-update | 74.4% | 83.3% | 76.9% / 78.2% |
| temporal-reasoning | 54.1% | 62.4% | 36.5% / 45.1% |
| **AGGREGATE** | **63.8%** | **71.2%** | 55.4% / 60.2% |

**Zep's weakness:** single-session-assistant (-18% vs full-context with gpt-4o). Their entity extraction misses assistant-provided information. GRAIL's full-text cascade search should handle this better.

**Where GRAIL should dominate:** multi-session reasoning (entity graph connects facts across sessions) and temporal reasoning (if `observed_at` timestamps are wired).

---

## Evaluation Stack

**Judge:** GPT-4o (`gpt-4o-2024-08-06`)  
**Method:** Binary yes/no per question with type-specific prompts  
**Agreement:** >97% with human experts

Type-specific evaluation rules:
- **Standard types:** "answer yes if response contains the correct answer"
- **Temporal:** allows off-by-one errors in day/week/month calculations
- **Knowledge update:** correct if updated answer is present (even alongside old info)
- **Preference:** correct if it recalls and utilizes user's personal info
- **Abstention:** correct if it identifies the question as unresolvable

**Metrics:**
- Task-averaged accuracy (mean of per-category means)
- Overall accuracy (flat mean across 500)
- Per-category breakdown

---

## Baselines to Beat

| System | Retrieval | Reader | Accuracy |
|--------|-----------|--------|----------|
| K=V+fact (best RAG) | Stella V5 1.5B | GPT-4o Top-10 | **0.720** |
| K=V (standard RAG) | Stella V5 1.5B | GPT-4o Top-10 | 0.670 |
| Full context | None (entire 115K) | GPT-4o | 0.606 |
| Full context | None | Llama 3.1 8B | 0.454 |

**Target:** Beat 0.720 overall, specifically dominate multi-session reasoning (their hardest category for all baselines).

---

## Integration Plan

### Architecture

Each of the 500 questions has its own haystack. For each question:

1. Convert its 40 sessions into markdown observation files (with `observed_at` timestamps from session metadata)
2. Index the observations with GRAIL (embedding-only OR graph mode)
3. Query with the question using cascade/recall search
4. Format the answer
5. Evaluate with their judge

### Two-Run Comparison

**Run 1 — Embedding-only (memory mode, no LLM extraction):**
- Tests GRAIL as a pure memory store with cascade text-rescue
- Baseline: should be competitive with Stella V5 (0.670-0.720)
- Validates the text-rescue path handles needle-in-haystack

**Run 2 — Graph mode (entity extraction on sessions):**
- Tests whether entity graphs help memory recall
- Should dominate multi-session reasoning (entity aggregation across sessions)
- Should improve knowledge updates (SUPERSEDES relationships)
- Should improve temporal reasoning (entity timestamps + temporal filters)

### Output Format

```jsonl
{"question_id": "q_042", "hypothesis": "4 instruments"}
{"question_id": "q_043", "hypothesis": "The user's email is alice@example.com"}
```

### Eval Commands

```bash
# Generate answers
python run_longmemeval.py --mode graph --tier s --output results/grail_graph.jsonl

# Evaluate
python evaluate_qa.py gpt-4o results/grail_graph.jsonl data/longmemeval_s_cleaned.json

# Print metrics
python print_qa_metrics.py gpt-4o results/grail_graph.jsonl.log data/longmemeval_s_cleaned.json
```

---

## Strategic Positioning

### The Headline Result

If GRAIL graph mode scores **>0.75 on multi-session reasoning** while embedding-only scores ~0.65, that's the proof that entity graphs provide structural memory advantages that flat retrieval cannot match.

The narrative: *"Flat RAG retrieves the 10 most similar chunks and hopes the LLM can count instruments across them. GRAIL's graph already extracted GUITAR, PIANO, VIOLIN, DRUMS as separate entities linked to the user — the aggregation happened at index time, not inference time."*

### What to Watch For

- **Multi-session reasoning is the money category.** If graph mode doesn't beat embedding-only here, the memory feature's value proposition weakens.
- **Knowledge updates depend on SUPERSEDES.** If the graph doesn't detect contradictions, it may serve stale facts.
- **Temporal reasoning depends on `observed_at` implementation.** Without timestamps on entities, this category falls back to text matching.
- **Abstention is hard for graph systems.** Graphs tend to find *something* related. Need to calibrate the "insufficient evidence" threshold.

---

## Prerequisites (Memory Mode Features Required)

Before this benchmark can run, these features from `prompt_grail_agentic_memory_design.md` must ship:

- [ ] Phase 1: Schema migration (`observed_at`, `confidence`, `source` columns)
- [ ] Phase 1: Frontmatter-aware loader (markdown observations with timestamps)
- [ ] Phase 2: Memory SDK (`add_observation`, `recall`)
- [ ] Phase 2: `LLMConfig` optional (embedding-only mode)
- [ ] Phase 3: Temporal recall mode (`--since`, `--before` filters)
- [ ] Cascade search composable with temporal filters

Optional but helpful:
- [ ] `SUPERSEDES` relationship type (improves Knowledge Updates category)
- [ ] Entity-level `observed_at` timestamps (improves Temporal Reasoning category)
