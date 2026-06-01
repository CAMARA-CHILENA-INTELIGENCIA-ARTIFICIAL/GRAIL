# Search modes

All search modes share one script: `scripts/query.py`. They differ in
which parquet artefacts they touch, what the LLM sees, and what they
cost.

| Mode | LLM calls | Reads | Best for |
|---|---|---|---|
| `recall` | 0 | text_units, entities, documents | Zero-cost temporal / structural slice. |
| `local` | 1 | entities (top-K) + their relationships + texts | Entity-anchored factual questions. |
| `cascade` | 1 | entities + BM25 + cosine on chunks | Robust default — recovers when the entity gate misses. |
| `global` | 1–N | community reports | Broad / thematic ("what are the main themes"). |
| `document` | 1 | scope filtered to one document_id | Questions about one specific source file. |
| `agent` | multi | delegates to the above | Complex multi-step questions; LLM picks tools. |

## Filter flags (compose with every mode)

Every flag below filters the candidate pool *before* the expensive
scoring runs. Multiple flags AND together.

| Flag | Example | Effect |
|---|---|---|
| `--since` | `--since 1h` or `--since 2026-05-30T00:00:00Z` | Drop rows older than this. |
| `--before` | `--before 7d` | Drop rows newer than this. |
| `--category` | `--category 'work/**'` | Folder-glob filter (fnmatch). |
| `--tag` | `--tag pricing` (repeatable, any-match) | Match documents with at least one of these tags. |
| `--entity-name` | `--entity-name ALICE` (repeatable) | Restrict to specific entity names. |
| `--type` | `--type PERSON` (repeatable) | Restrict to entities of these types. |
| `--min-confidence` | `--min-confidence 0.7` | Drop rows below this confidence. |

Relative-time tokens: `1h`, `30m`, `7d`, `2w`, `2 weeks ago`, `now`,
plus any ISO-8601 absolute timestamp.

## Mode selection heuristics

```
Specific named entity in the question?           → local
Broad theme / no specific entity?                 → global
Question scoped to one document?                  → document
"Last hour" / "from work/**" / "tagged pricing"?  → recall (+ optional --query for LLM)
Complex multi-part question?                      → agent
Unsure?                                           → cascade  (most robust default)
```

## Examples

```bash
# Robust factual KB query.
python scripts/query.py --project my-kb --query "what are bevacizumab's indications"

# Broad thematic question.
python scripts/query.py --project my-kb \
  --mode global --query "what are the main themes across the corpus"

# Question scoped to one file.
python scripts/query.py --project my-kb \
  --mode document --document "report.pdf" --query "what does this conclude"

# Pure structural recall — no LLM call.
python scripts/query.py --project work-memory \
  --mode recall --since 7d --category 'work/clients/**' --tag pricing

# Cascade pre-filtered to the last hour.
python scripts/query.py --project work-memory \
  --query "what did acme say" --mode cascade --since 1h

# Let the LLM pick.
python scripts/query.py --project my-kb \
  --mode agent --query "compare early-stage vs advanced treatment"
```

## Output shape

Every call returns a JSON envelope. The interesting fields:

```json
{
  "ok": true,
  "data": {
    "search_mode": "cascade",
    "response": "Bevacizumab is approved for ...",
    "context_stats": {
      "entities": 10, "relationships": 8, "reports": 3, "sources": 12
    },
    "completion_time": 2.31,
    "llm_calls": 1,
    "cost": "$0.0042",
    "filter_active": false
  }
}
```

`response` is the textual answer. `context_stats` tell you how much
context the LLM saw. `llm_calls=0` for `recall` always.
