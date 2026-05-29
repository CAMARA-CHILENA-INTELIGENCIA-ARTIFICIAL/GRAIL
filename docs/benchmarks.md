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

### 2. LongMemEval (Zep)

**Blog:** https://blog.getzep.com/state-of-the-art-agent-memory/

**Dataset:** LongMemEval — 500 human-curated QA pairs in scalable chat histories
- Size S: ~115,000 tokens
- Size M: ~1,500,000 tokens

**6 task categories:**
- Single-session-preference
- Single-session-assistant
- Single-session-user
- Temporal-reasoning
- Multi-session
- Knowledge-update

**Evaluation stack to replicate:**

| Component | Exact version | Why it matters |
|---|---|---|
| LLM judge | `gpt-4o` | Accuracy scores calibrated to this judge |
| Baselines | Full transcript in context, recursive summarization | Must test same baselines |
| Models | GPT-4-Turbo, GPT-4o, GPT-4o-mini | Report results per model |

**Key findings to beat:**
- +18.5% accuracy over full-context baseline (aggregate)
- +38.4-48.2% on temporal-reasoning (biggest win)
- 90% latency reduction using <2% of baseline tokens

**Relevance to GRAIL:** LongMemEval tests cross-session synthesis and temporal
reasoning — exactly where GRAIL's incremental graph updates and community
reports should excel. The knowledge-update category maps directly to GRAIL's
`edit` and `append` operations.

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
