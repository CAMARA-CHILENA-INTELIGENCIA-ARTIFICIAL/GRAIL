# GRAIL — Benchmarks

---

## Internal Benchmark: `simple_benchmark`

Located at `benchmarks/simple_benchmark/benchmark.json`. 30 questions across 7
categories designed to compare GRAIL search modes against a naive RAG baseline.

See `benchmarks/run_benchmark.py --help` for usage.

---

## External Benchmarks (Roadmap)

GRAIL should be evaluated against established external benchmarks to produce
comparable, publishable results. **Critical rule: use the exact same evaluation
stack (judge model, embedding model, metrics) the original authors used.**
Results are only comparable when the eval infrastructure matches.

### 1. GraphRAG-Bench

**Paper:** "When to use Graphs in RAG: A Comprehensive Analysis for Graph
Retrieval-Augmented Generation" — arXiv:2506.05690 (June 2025)

**Dataset:** `GraphRAG-Bench/GraphRAG-Bench` on HuggingFace
- 4,072 questions: Medical (2,060) + Novel (2,012)
- 4 difficulty levels: Fact Retrieval → Complex Reasoning → Contextual Summarization → Creative Generation

**Evaluation stack to replicate:**

| Component | Exact version | Why it matters |
|---|---|---|
| Retrieval embedding | `BAAI/bge-large-en-v1.5` | Retrieval eval computes semantic similarity with this model |
| LLM judge | `gpt-4-turbo` | Generation eval scores are calibrated to this judge |
| Metrics | Accuracy, ROUGE-L, Coverage, Factual Score | Per-level metrics differ |

**Output format required:**
```json
{
  "id": "Medical-73586ddc",
  "question": "What is the most common type of skin cancer?",
  "source": "Medical",
  "context": "<retrieved context from GRAIL>",
  "evidence": ["evidence_1", "evidence_2"],
  "question_type": "Fact Retrieval",
  "generated_answer": "<GRAIL's answer>",
  "gold_answer": "Basal cell carcinoma (BCC) is the most common type of skin cancer."
}
```

**Baselines they tested:** LightRAG, fast-graphrag, hipporag2

**Key finding from their paper:** GraphRAG frequently underperforms vanilla RAG
on fact retrieval (Level 1) but excels on complex reasoning (Level 2) and
contextual summarization (Level 3). Our cascade search mode is designed to
solve the Level 1 weakness by combining entity-gated retrieval with direct
text scoring.

**Eval commands (from their repo):**
```bash
# Retrieval evaluation
python -m Evaluation.retrieval_eval \
  --model gpt-4-turbo \
  --base_url https://api.openai.com/v1 \
  --bge_model BAAI/bge-large-en-v1.5 \
  --data_file ./results/grail.json \
  --output_file ./results/evaluation_results.json

# Generation evaluation
python -m Evaluation.generation_eval \
  --model gpt-4-turbo \
  --base_url https://api.openai.com/v1 \
  --bge_model BAAI/bge-large-en-v1.5 \
  --data_file ./results/grail.json \
  --output_file ./results/evaluation_results.json
```

---

### 2. LongMemEval v1 (Memory Mode Validation)

**Paper:** arXiv:2410.10813 (ICLR 2025)  
**Repo:** https://github.com/xiaowu0162/LongMemEval  
**Dataset:** `xiaowu0162/longmemeval-cleaned` on HuggingFace

**Status:** Blocked on GRAIL memory mode implementation. Run after Phases 2-3 of
the agentic memory design ship (see `dev_prompts/prompt_grail_agentic_memory_design.md`).

**Dataset:** 500 human-curated QA pairs, each with its own haystack of 40-500
chat sessions (Size S: ~115K tokens, Size M: ~1.5M tokens per question).

**5 memory ability categories:**
- Information Extraction (single-session recall)
- Multi-Session Reasoning (aggregate across sessions)
- Knowledge Updates (recognize changed facts)
- Temporal Reasoning (time-aware queries)
- Abstention (correctly say "I don't know")

**Why this maps to GRAIL memory mode:**

| Category | GRAIL Feature |
|----------|---------------|
| Multi-Session Reasoning | Entity graph connects concepts across sessions (count, aggregate) |
| Knowledge Updates | `SUPERSEDES` relationship + `edit_extract` + orphan pruning |
| Temporal Reasoning | `recall --since/--before` + `observed_at` on entities |
| Information Extraction | Cascade search + `retrieval_queries` enrichment |
| Abstention | Empty cascade → "I don't know" |

**Evaluation stack to replicate:**

| Component | Exact version | Why it matters |
|---|---|---|
| LLM judge | `gpt-4o` (`gpt-4o-2024-08-06`) | Binary yes/no, >97% human agreement |
| Retrieval eval | Recall@k, NDCG@k (k=5,10,50) | Session-level retrieval quality |

**Baselines to beat:**
- Best RAG: K=V+fact with Stella V5 1.5B → **0.720 accuracy** (GPT-4o, Top-10)
- Full-context GPT-4o: 0.606 (S tier) — drops 30% from oracle
- Multi-session reasoning is the hardest category for all baselines

**Cost estimate:**
- Embedding-only mode (500 questions): ~$1.50
- Graph mode with Gemma-4-26B (500 questions): ~$26
- Both are per the small tier (40 sessions/question)

**Two-run comparison:**
1. GRAIL embedding-only (no entity extraction) — baseline, competitive with Stella
2. GRAIL graph mode (entity extraction on sessions) — should dominate on
   multi-session reasoning where graph structure connects entities across sessions

**Relevance to GRAIL:** This is the primary validation benchmark for the agentic
memory feature. Multi-session reasoning ("How many instruments do I own?") is
where entity graphs should crush flat RAG — the graph links `GUITAR`, `PIANO`,
`VIOLIN` entities across separate sessions. No other benchmark tests this at
scale for memory systems.

---

## Running External Benchmarks

When implementing a runner for these benchmarks:

1. **Do not substitute the judge model.** GPT-4-turbo and GPT-4o produce
   different score distributions. Using a different judge invalidates
   comparisons with published baselines.

2. **Do not substitute the retrieval embedding.** BGE-large-en-v1.5 is the
   shared retrieval eval backbone for GraphRAG-Bench. Our internal embedding
   model (Qwen3-Embedding) is for GRAIL's own retrieval, not for evaluation.

3. **Report the exact stack.** In any benchmark results, include: GRAIL version,
   LLM model, embedding model, judge model, and whether reranking was enabled.

4. **Use `OPENAI_API_KEY` for eval.** Both benchmarks require OpenAI models for
   judging. Set this separately from GRAIL's inference key.
