# Model Selection for GRAIL — How to Reproduce This Analysis

This document explains how the model selection report was generated so that
any user can replicate and extend it with their own candidate models.

## Prerequisites

1. An API key from [Artificial Analysis](https://artificialanalysis.ai/) (free, 1,000 requests/day).
2. The **`benchmark-artificialanalysis`** skill from
   [cchia_skills](https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills).
3. Python 3.11+.

## Install the skill

```bash
# Option A: via npx (recommended — installs to ~/.claude/skills/)
npx skills add CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills \
  --skill benchmark-artificialanalysis

# Option B: clone the repo
git clone https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills.git
```

## Set your API key

```bash
export ARTIFICIAL_ANALYSIS_API_KEY="your_key_here"
```

## Step-by-step reproduction

The skill exposes three scripts under
`skills/benchmark-artificialanalysis/scripts/`. All commands below assume
`$SKILL` points to that directory.

### 1. Fetch current model data

```bash
python3 $SKILL/scripts/fetch_models.py --output /tmp/aa_models.json
```

This downloads benchmark scores, pricing, and speed metrics for 500+ models
from the Artificial Analysis API into a single JSON file.

### 2. Search by use case — Entity Extraction

GRAIL's entity/relationship extraction needs models that (a) follow strict
output formats and (b) are smart enough to detect all nodes and edges. The
`entity_extraction` profile combines IFBench, tau2-Bench, MMLU-Pro, and LCR:

```bash
python3 $SKILL/scripts/search_models.py \
  --data /tmp/aa_models.json \
  --use-case entity_extraction \
  --top 15
```

### 3. Search by use case — Budget constraint

To find models under $2/1M tokens (blended) for high-volume indexing:

```bash
python3 $SKILL/scripts/search_models.py \
  --data /tmp/aa_models.json \
  --use-case entity_extraction \
  --max-price 2.0 \
  --top 15
```

### 4. Compare specific candidates

Once you have a shortlist, compare them side-by-side with use-case-relevant
benchmarks highlighted:

```bash
# Entity extraction comparison
python3 $SKILL/scripts/compare_models.py \
  --data /tmp/aa_models.json \
  --models "GPT-5.4 (xhigh),GPT-5.4 mini (xhigh),Qwen3.6 27B (Reasoning),Qwen3.6 35B A3B (Reasoning),Gemma 4 31B (Reasoning),Gemma 4 26B A4B (Reasoning),MiniMax-M2.7" \
  --use-case entity_extraction

# JSON output for programmatic use
python3 $SKILL/scripts/compare_models.py \
  --data /tmp/aa_models.json \
  --models "GPT-5.4 (xhigh),MiniMax-M2.7,Qwen3.6 35B A3B (Reasoning)" \
  --use-case entity_extraction \
  --json
```

### 5. Sort by specific benchmarks

For community report generation (condensing + JSON format):

```bash
python3 $SKILL/scripts/search_models.py \
  --data /tmp/aa_models.json \
  --sort intelligence \
  --has-benchmark ifbench \
  --max-price 2.0 \
  --top 10
```

For inference (low hallucination, factual accuracy):

```bash
python3 $SKILL/scripts/search_models.py \
  --data /tmp/aa_models.json \
  --sort gpqa \
  --has-benchmark ifbench \
  --top 10
```

## Benchmarks used and why

| Benchmark | What it measures | GRAIL stage |
|-----------|-----------------|-------------|
| **IFBench** | Strict instruction/format following | Entity extraction, Community reports |
| **tau2-Bench** | Tool use / function calling compliance | Entity extraction |
| **Intelligence Index** | Overall reasoning capability | Community reports, Query inference |
| **GPQA Diamond** | Factual accuracy on expert-level questions | Query inference (hallucination proxy) |
| **Long Context Recall** | Retrieval from long documents | Entity extraction, Query inference |
| **HLE** | Frontier reasoning difficulty | Query inference (hard queries) |

## Extending with your own models

To add a model that isn't in the Artificial Analysis database, you can run
GRAIL's own benchmark (`grail benchmark`) against a small test corpus and
compare entity recall, format compliance, and latency directly. The report
in `report.md` provides the baseline numbers from Artificial Analysis; your
own benchmarks provide the ground truth for your specific use case.

---

Data source: [Artificial Analysis](https://artificialanalysis.ai/).
Skill: [`benchmark-artificialanalysis`](https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills).
