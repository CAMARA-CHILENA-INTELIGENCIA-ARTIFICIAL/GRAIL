# Query optimisation

## The WHO + WHAT + SPECIFIC formula

Search results improve sharply when the query carries three pieces of
information: an entity-shaped anchor (WHO), an action / topic (WHAT),
and a discriminator (SPECIFIC, like a date or location). The graph is
built around named entities — queries that anchor on one match the
top-K entity ranking, which then surfaces the right text units.

| Bad | Better |
|---|---|
| "tell me about pricing" | "what did John say about Q2 pricing for Acme last week" |
| "any updates?" | "what changed in the contract terms with Acme after the May 27 meeting" |
| "biomarkers" | "which biomarkers does the cachexia guideline cite for treatment selection" |

If the user's question is genuinely broad / lacks an anchor, prefer
`--mode global` — that mode is designed for theme-level synthesis and
doesn't depend on entity matches.

## Mode selection cheat sheet

| Question pattern | Pick |
|---|---|
| Named person / org / drug / place involved | `cascade` |
| One specific document is in scope | `document` |
| "What are the themes" / "summarise" | `global` |
| "Show me from <category>" / "tagged X" / "since 1h" | `recall` |
| Multi-step / comparison / "find me ... and then ..." | `agent` |

## Composing with filters

The recall filter flags trim the candidate pool *before* the scoring
runs. Two patterns to memorise:

1. **Temporal narrowing**: `--mode cascade --since 1h` — cascade only
   considers entities/text-units observed in the last hour. Fast and
   precise when the user is asking about recent events.

2. **Scoped recall**: `--mode recall --category 'work/clients/**'` —
   pure structural listing of everything filed under that folder. No
   LLM call.

You can't sensibly compose `--mode agent` with filters — the agent
chooses its own tools.

## When cascade misses

The most common failure: the right answer lives in a text unit whose
entities don't appear in the query's top-K. Cascade has a "text rescue"
path that scores chunks by BM25 + cosine *independent of* the entity
gate, so this is usually fine. When it isn't:

- Try `--mode local --top-k-entities 30` to widen the entity gate.
- Try `--mode document` if you can name the source file.
- Try `--mode agent` and let the LLM iterate.

## Cost discipline

| Mode | Typical LLM calls per query |
|---|---|
| `recall` | 0 |
| `local` / `cascade` / `document` | 1 |
| `global` | 1 (small corpus) to N (large — map-reduce) |
| `agent` | 2–5 |

`recall` is free. Use it for "what do I have on X" probes before
committing to an LLM-backed search.

## When the user is browsing rather than asking

Suggest the agent run `recall` to **show the user what's available**
before asking a specific question. Especially useful with memory mode:

```bash
python scripts/memory/recall.py --project work-memory --category work/clients/acme
```

Returns titles, tags, and observed_at for everything under `acme`.
