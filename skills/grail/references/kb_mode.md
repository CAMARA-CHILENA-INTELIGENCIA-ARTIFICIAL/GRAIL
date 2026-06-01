# KB mode workflow

Use the knowledge-base mode when the user wants to **index a corpus of
documents** and **answer questions over it**. Pipeline: drop files into
`input/`, run `index`, then `query` against the resulting graph.

## Lifecycle

```
init → drop files into input/ → index → query → (append | edit | delete) → query
```

1. **Create the project** if it doesn't exist:
   ```bash
   python scripts/init_project.py --project ./my-kb --name my-kb
   ```
   This scaffolds `grail.yaml`, `meta.json`, `input/`, `output/`.

2. **Drop source files into `<project>/input/`**. Supported types: text
   (`.txt`, `.md`, `.markdown`, `.csv`, `.tsv`, `.json`, `.jsonl`, code),
   PDF (`.pdf`), and DOCX (`.docx`). PDFs and DOCX are converted to
   markdown on the fly under `input/_processed/`.

3. **Index the corpus**:
   ```bash
   python scripts/index.py --project ./my-kb
   ```
   This makes LLM calls — costs tokens. The script returns counts +
   `cost`.

4. **Query**:
   ```bash
   python scripts/query.py --project ./my-kb --query "what does X say about Y"
   ```
   Default mode is `cascade` (the most robust default for factual
   questions). See `references/search_modes.md` for the alternatives.

5. **Incrementally maintain**:
   ```bash
   python scripts/append.py --project ./my-kb --files new-report.pdf
   python scripts/edit.py   --project ./my-kb --replace report.pdf=updated.pdf
   python scripts/delete.py --project ./my-kb --files outdated.md
   ```
   These re-run only the affected sub-graphs — no full re-index.

## When to use which search mode

| Question shape | Mode | Why |
|---|---|---|
| "What is X?" or "What did X say about Y?" | `cascade` | Entity gate + text rescue; robust to entity-gate misses. |
| "What are the main themes?" | `global` | Community-level synthesis. |
| Scoped to one document | `document` | Filters everything to that document_id. |
| Complex / multi-step | `agent` | LLM picks tools across local + cascade + global + document. |
| "Show me everything tagged X" | `recall` | Zero-LLM structural slice. |

## What lives where

- `<project>/grail.yaml` — configuration. The user edits this; the skill
  does not.
- `<project>/meta.json` — machine-managed identity. **Never** edit by hand.
- `<project>/input/` — your source files (and `_processed/` cache for
  PDFs/DOCX).
- `<project>/output/runs/<run_id>/` — parquet artefacts from the last
  index call. Each `index` writes a fresh run.
- `<project>/output/current.json` — points at the active run.
- `<project>/mapping.json` — document_id → original_path map used for
  source citations in search results.

## Pitfalls

- **No LLM key configured** → `index.py` fails. Set the environment
  variable referenced by your `grail.yaml`'s `llm.endpoint`.
- **Indexing fails halfway** → the run folder under `output/runs/` is
  still there; you can inspect it but it may be partial. Re-running
  `index` creates a fresh run.
- **Different embedding model between index and query** → silent recall
  degradation. The model name is stored in `mapping.json`; the loader
  refuses to mix them.
- **Token budgets** → `extraction_max_tokens`, `local_max_tokens`,
  `global_reduce_max_tokens` in `grail.yaml`. Tune them for the model
  you're using.
