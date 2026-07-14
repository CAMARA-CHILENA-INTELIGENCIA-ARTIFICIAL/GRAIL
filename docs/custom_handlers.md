# Custom File Handlers (Multimodal Ingestion)

GRAIL reads text, code, data, PDF, and DOCX out of the box. **Handlers** let you
teach it any other format — spreadsheets, parquet, images, a domain-specific log
— without forking the library. A handler is a small Python class that claims one
or more file extensions and turns those files into graph input.

This is the extensible *mechanism*. GRAIL ships **no** built-in handlers for
tabular/image/audio formats; you write (or copy) the handler that fits your data.
A worked CSV example lives at `examples/custom_handlers/csv_handler.py`.

## Two protocols

A handler overrides **exactly one** method:

| Mode | Method | What it returns | When |
|------|--------|-----------------|------|
| `describe` (default) | `async describe(self, source, ctx) -> str` | markdown / plain text | You want the file summarised, then run through the normal chunk → LLM-extract → graph pipeline. |
| `emit` (opt-in) | `async emit(self, source, ctx) -> EmitResult` | entities + relationships | The file is structured and you want deterministic, LLM-free extraction (each row → entity, etc.). |

```python
from pathlib import Path
from grail.indexing.handlers import FileHandler, HandlerContext

class XlsxHandler(FileHandler):
    NAME = "xlsx_describe"
    EXTENSIONS = frozenset({".xlsx", ".xls"})

    async def describe(self, source: Path, ctx: HandlerContext) -> str:
        import pandas as pd
        df = pd.read_excel(source)
        return f"# {source.stem}\n\n{df.describe().to_markdown()}"

HANDLER = XlsxHandler()
```

### describe mode

The returned string is written to `input/_processed/<stem>.md` (mtime-cached,
like PDF/DOCX) and chunked like any other markdown. Output is human-inspectable —
open the `_processed/` file to see exactly what the LLM extracted from.

### emit mode

Return an `EmitResult` of plain records; GRAIL assigns IDs, **embeds the
descriptions**, synthesises a Document + TextUnit for citation provenance, and
merges everything into the graph before community detection — no LLM extraction.

```python
from grail.indexing.handlers import EmitEntity, EmitRelationship, EmitResult

async def emit(self, source, ctx) -> EmitResult:
    return EmitResult(
        entities=[EmitEntity(name="ACME CORP", type="ORGANIZATION", description="…")],
        relationships=[EmitRelationship(source="ACME CORP", target="JANE DOE",
                                        type="EMPLOYS", description="…")],
        text="One-line summary used as the citation anchor.",
    )
```

## Agentic handlers

`ctx` carries live collaborators — use them to describe a file with the model:

```python
async def describe(self, source, ctx):
    raw = source.read_text()[:4000]
    messages = [{"role": "user", "content": f"Summarise this dataset:\n{raw}"}]
    return await ctx.llm.complete(messages)
```

`HandlerContext` fields: `llm`, `embeddings`, `config`, `prompts`, `reporter`. A
pure-Python handler simply ignores `ctx`.

## Registration

**Declarative** — point the config at a directory of handler modules:

```yaml
handlers:
  custom_paths: ["handlers"]      # each .py exposes HANDLER or HANDLERS = [...]
  on_unhandled: error             # error (default) | warn | skip
  enabled: true
```

**Programmatic (SDK)** — register in-process, no file needed:

```python
g = GRAIL.from_config("grail.yaml")
g.register_handler(XlsxHandler())
await g.index()
```

Each extension may be owned by only one handler; collisions raise at load time.

## The `on_unhandled` policy

When `input/` holds a file no built-in reader **and** no handler claims:

- **`error`** (default) — indexing fails with a message naming the file(s).
  Protects you from silently dropping data you meant to index.
- **`warn`** — log a warning and skip the file.
- **`skip`** — silently ignore (legacy behaviour).

Hidden/`_`-prefixed files and the `_processed/` directory are always ignored and
never trigger the policy.

## Tooling

```bash
grail handlers list  <project>     # extension → handler → mode
grail handlers check <project>     # dry-run: classify every file in input/
grail index          <project>     # unhandled files fail cleanly under `error`
```

MCP: the `kb_handlers` tool returns the same handler list + classification, and
`kb_index` returns a structured error (with `next_steps`) when unhandled files
block the run.

## Limitations (v1)

- Handlers require the **LocalStorage** backend (they receive a real on-disk
  path). S3/remote is a follow-up.
- `emit`-mode entities with the same name across different files are stored as
  separate rows (the LLM-extraction dedup pass does not apply to emitted data).
- Editing a previously-emitted file in place is covered by orphan pruning on
  delete; full emit re-extraction on `edit` is a follow-up.
