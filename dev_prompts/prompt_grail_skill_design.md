# GRAIL Skill — Cross-Framework Design Context

> **Purpose**: A new session continuing this thread should be able to read this single file and pick up the skill design work without needing prior conversation history. This document captures (a) the universal agent-skill format that works across Claude Code, Codex, and Hermes; (b) GRAIL's public surface that the skill will wrap; (c) the proposed folder layout for the GRAIL skill; (d) open design questions that still need a call.
>
> **Companion doc**: `dev_prompts/prompt_grail_agentic_memory_design.md` describes Memory Mode itself (which a separate session is building). This doc is about how *both* modes get packaged as a portable skill. The two are independent: skill folder shape can be finalised before memory-mode code lands.
>
> **Status**: design-stage. No skill code written yet.

---

## TL;DR

Anthropic, OpenAI Codex, and Hermes all use the same on-disk skill format: a folder containing a `SKILL.md` file with YAML frontmatter, plus optional `scripts/`, `references/`, `assets/`. Each framework adds *additive* extensions (Codex has an `agents/openai.yaml` sidecar; Hermes adds extra frontmatter keys), but a skill that respects the shared core works in all three. Discovery paths differ per framework, which is solved at install time, not in the skill itself.

Decisions captured here:

1. **One skill folder** named `grail`, routing internally to KB or memory workflow via `references/kb_mode.md` and `references/memory_mode.md`. (Pending final confirmation — see Open Questions.)
2. **Scripts call GRAIL's Python SDK**, not its CLI. Memory-mode tools don't all exist as CLI commands, and atomic multi-step writes need a single SDK call.
3. **Each project gets a `meta.json`** for stable identity (ULID, name, mode, timestamps). `grail.yaml` stays the human-edited configuration. A workspace registry at `~/.grail/registry.json` caches known projects.
4. **All scripts accept `--project <ref>`** where `<ref>` resolves to path | name | id. The agent never has to remember mode — every script returns it in a JSON envelope.
5. **Dependency model**: bundle `requirements.txt` + idempotent `setup.sh`. The skill instructs the agent to run setup once per session before any script.
6. **Distribution**: ship the skill at `skills/grail/` inside the GRAIL repo, plus a `grail skill install [--framework ...]` CLI command that copies/symlinks it to the right path per framework.

---

## Part 1 — The universal skill format

### The cross-framework reality

| Aspect | Claude Code / claude.ai / Anthropic API | OpenAI Codex | Hermes (Nous Research) |
|---|---|---|---|
| Entry file | `SKILL.md` | `SKILL.md` | `SKILL.md` |
| Required frontmatter | `name`, `description` | `name`, `description` | `name`, `description`, `version` |
| Discovery paths | `~/.claude/skills/<name>/`<br>`.claude/skills/<name>/` | `.agents/skills/<name>/`<br>`~/.agents/skills/<name>/`<br>`/etc/codex/skills/<name>/` | Hermes Skills Hub (agentskills.io-compatible) |
| Optional layout | `scripts/`, `references/`, `assets/` | same + `agents/openai.yaml` sidecar | same + `templates/`, plus extra frontmatter keys |
| Standard claimed | de-facto reference | "open agent skills standard" | agentskills.io open standard |
| Runtime network | Full (Claude Code) / None (API) | Full | Full |
| Distribution | Folder, zip upload (claude.ai), or Skills API | Folder, or Codex Plugin bundle | Skills Hub repo |

**The standard is real.** A folder with `SKILL.md` + `scripts/` + `references/` is read by all three. Framework-specific sidecars are additive — they don't break the others, so we include them in one folder.

### The universal SKILL.md format

```yaml
---
name: skill-name              # required; lowercase + hyphens; max 64 chars
                               # MUST NOT contain "anthropic" or "claude"
description: |                 # required; max 1024 chars
  What this skill does AND when to use it. Must be "pushy" —
  agents under-trigger by default. Enumerate trigger phrases.
                               # optional framework-additive keys below:
version: 1.0.0                 # required by Hermes; ignored by others
platforms: [macos, linux]      # Hermes; ignored by others
metadata:                      # Hermes config block; ignored by others
  hermes:
    tags: [...]
    config: [...]
required_environment_variables: # Hermes; ignored by others
  - name: GRAIL_LLM_API_KEY
    prompt: "..."
---

# Skill Title

## When to use
Trigger conditions — concrete user phrases, not abstract scenarios.

## Procedure
Numbered steps. Reference scripts by relative path.
"Run `scripts/foo.py --arg X`. Parse the returned JSON."

## Pitfalls
Known failure modes and how to handle them.

## Verification
How to confirm the task succeeded.
```

**Frontmatter rules:**
- `name`: lowercase letters, numbers, hyphens only. Max 64 chars. Reserved words: `anthropic`, `claude`.
- `description`: max 1024 chars. MUST include both *what* the skill does AND *specific contexts when to use it*. Anthropic's skill-creator guide explicitly warns: agents under-trigger; make descriptions "pushy" — list keywords/phrases that should trip the skill.
- Hermes-specific fields (`version`, `platforms`, `metadata.hermes`, `required_environment_variables`) are additive — Claude Code and Codex ignore unknown frontmatter.

**Body rules:**
- ≤ 500 lines / ~5k tokens. If exceeded, split into `references/*.md` and link from SKILL.md.
- "When to use" + "Procedure" + "Pitfalls" + "Verification" sections are required by Hermes; recommended for all frameworks.
- Reference other files by relative path (`scripts/foo.py`, `references/advanced.md`). The agent will navigate to them via bash.

### Folder anatomy

```
my-skill/
├── SKILL.md            ← required; entry point
├── requirements.txt    ← optional but recommended for Python skills
├── INSTALL.md          ← human-readable install guide per framework
│
├── agents/             ← optional; Codex sidecar
│   └── openai.yaml
├── hermes.yaml         ← optional; Hermes extra frontmatter overflow
│
├── references/         ← Level 3 — loaded only when explicitly read
│   ├── advanced.md     ← detailed reference material
│   └── troubleshooting.md
│
├── scripts/            ← Level 3 — executable code, output JSON
│   ├── setup.sh        ← idempotent dep install
│   └── do_thing.py
│
└── assets/             ← templates, icons, examples used in output
    └── template.html
```

**Progressive disclosure — the three loading levels:**

| Level | When loaded | Token cost | Content |
|---|---|---|---|
| 1: Metadata | Always at startup | ~100 tokens per skill | `name`, `description` from frontmatter |
| 2: Instructions | When skill triggered | < 5k tokens | SKILL.md body |
| 3: Resources & scripts | On-demand via bash | Effectively unlimited | `references/`, `scripts/`, `assets/` |

Scripts are especially efficient: the agent executes them via bash and only the **output** enters context, not the script source.

### Framework-specific extensions

**Codex** (`agents/openai.yaml`):
```yaml
interface:
  display_name: "Skill Display Name"
  short_description: "One-liner"
  icon_small: "assets/icon-32.png"
  icon_large: "assets/icon-128.png"
  brand_color: "#3b82f6"
  default_prompt: "Walk me through using this skill"
policy:
  allow_implicit_invocation: true
dependencies:
  tools:
    - type: "mcp"
      value: "some-mcp-server"
      transport: "stdio"
      url: "..."
```

**Hermes** — extra frontmatter fields go in SKILL.md itself (above table). Required content sections are stricter: "When to Use", "Procedure", "Pitfalls", "Verification".

**Anthropic** — no sidecar; everything lives in SKILL.md + bundled files.

### Dependency handling — there is no standard

The most surprising research finding: **no framework formalises Python dependency installation**. Anthropic's own published PDF skill just writes `Requires: pip install pytesseract pdf2image` inline in SKILL.md. None of the official skills ship a `requirements.txt`.

**Recommended pattern (what this skill will use):**

1. Bundle `requirements.txt` in the skill folder.
2. Bundle `scripts/setup.sh` that does an idempotent check:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   if python -c "import grail" 2>/dev/null; then
     echo '{"ok": true, "status": "already-installed"}'
     exit 0
   fi
   python -m pip install -q -r "$(dirname "$0")/../requirements.txt"
   echo '{"ok": true, "status": "installed"}'
   ```
3. SKILL.md instructs: *"Before any script call, ensure setup: `bash scripts/setup.sh`. Idempotent — safe to call every session."*

**Runtime constraints to know:**
- Anthropic API runtime: no network, no pip install at runtime — pre-installed packages only. *This skill cannot run there; document it as Claude-Code / Codex / Hermes only.*
- Claude Code: full network access, can pip install.
- Codex: full network access, can pip install.
- Hermes: full network access, can pip install.

### Distribution and installation

Each framework reads skills from a different path. The clean approach is a single install command that handles all of them.

| Framework | User-scope install path | Project-scope install path |
|---|---|---|
| Claude Code | `~/.claude/skills/<name>/` | `<repo>/.claude/skills/<name>/` |
| Codex | `~/.agents/skills/<name>/` | `<repo>/.agents/skills/<name>/` |
| Hermes | via Skills Hub or local marketplace dir | n/a |

The skill source folder is one canonical copy. Install = symlink (preferred when supported) or copy to each framework's path.

---

## Part 2 — Sample: a complete general skill

This is a minimal but realistic example showing every piece. Use it as a template when designing GRAIL's skill.

### Folder

```
csv-explorer/
├── SKILL.md
├── requirements.txt
├── INSTALL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── statistics.md
│   └── plotting.md
├── scripts/
│   ├── setup.sh
│   ├── _common.py
│   ├── summarize.py
│   ├── plot.py
│   └── filter.py
└── assets/
    └── plot_template.html
```

### `SKILL.md`

```markdown
---
name: csv-explorer
description: |
  Analyze CSV files: compute statistics (mean, median, percentiles, correlations),
  filter rows, and produce plots (histograms, scatter, boxplots). Use this skill
  WHENEVER the user mentions CSV, spreadsheet, dataframe, tabular data, "summarize
  this data", "plot the distribution", "filter rows where", "correlation between
  X and Y", or hands over a .csv file. Trigger even if the user does not say "CSV"
  explicitly but provides tabular data.
version: 1.0.0
---

# CSV Explorer

## When to use
- User provides a .csv file or pastes CSV/TSV text
- User asks for descriptive statistics, distributions, or correlations on tabular data
- User wants a plot from tabular data (histogram, bar, scatter, line, box)
- User wants to filter, sort, or aggregate rows of a CSV

## Before any action
Run `bash scripts/setup.sh` once per session. It is idempotent.

## Procedure

1. **Inspect first.** Run `python scripts/summarize.py --file <path>` to get
   `{columns, dtypes, n_rows, head, basic_stats}`. Use this to decide the
   next step.

2. **Statistics.** For correlations or per-column distributions, run
   `python scripts/summarize.py --file <path> --columns col1,col2 --detail full`.
   See `references/statistics.md` for the full output schema.

3. **Filtering.** Use `python scripts/filter.py --file <path> --expr "age > 30 and city == 'Berlin'"`.
   Returns a temp file path you can pass to subsequent commands.

4. **Plotting.** Use `python scripts/plot.py --file <path> --kind hist --column age`.
   Returns the saved image path. See `references/plotting.md` for available kinds.

## Pitfalls
- Files larger than 1 GB: `summarize.py` automatically samples. Pass `--no-sample` only
  if you have memory budget.
- Non-UTF8 encodings: pass `--encoding latin-1` or `--encoding cp1252`.
- Date columns are not auto-detected; pass `--parse-dates col1,col2` if needed.

## Verification
- Every script returns `{"ok": true, ...}` on success or `{"ok": false, "error": "..."}` on failure.
- For plots: confirm the returned path exists on disk before claiming success.
```

### `requirements.txt`

```
pandas>=2.0
numpy>=1.24
matplotlib>=3.7
```

### `scripts/setup.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if python -c "import pandas, matplotlib" 2>/dev/null; then
  echo '{"ok": true, "status": "already-installed"}'
  exit 0
fi
python -m pip install -q -r "$SCRIPT_DIR/../requirements.txt"
echo '{"ok": true, "status": "installed"}'
```

### `scripts/_common.py`

```python
"""Shared helpers: argument parsing, JSON envelope, error handling."""
import json
import sys
import traceback
from dataclasses import dataclass, asdict


@dataclass
class Reply:
    ok: bool
    data: dict | list | None = None
    warnings: list[str] = None
    next_steps: list[str] = None
    error: str | None = None

    def emit(self) -> None:
        out = {k: v for k, v in asdict(self).items() if v is not None}
        print(json.dumps(out, default=str))
        sys.exit(0 if self.ok else 1)


def run(fn):
    """Wraps a script's main() to enforce JSON envelope on every exit path."""
    try:
        result = fn()
        if isinstance(result, Reply):
            result.emit()
        else:
            Reply(ok=True, data=result).emit()
    except Exception as e:
        Reply(
            ok=False,
            error=f"{type(e).__name__}: {e}",
            data={"traceback": traceback.format_exc()},
        ).emit()
```

### `scripts/summarize.py`

```python
"""python scripts/summarize.py --file path/to.csv [--columns a,b] [--detail basic|full]"""
import argparse
import pandas as pd
from _common import Reply, run


def main() -> Reply:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--columns", default=None)
    ap.add_argument("--detail", choices=["basic", "full"], default="basic")
    ap.add_argument("--encoding", default="utf-8")
    args = ap.parse_args()

    df = pd.read_csv(args.file, encoding=args.encoding)
    cols = args.columns.split(",") if args.columns else df.columns.tolist()

    data = {
        "columns": df.columns.tolist(),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "n_rows": len(df),
        "head": df.head(5).to_dict(orient="records"),
    }
    if args.detail == "full":
        data["describe"] = df[cols].describe(include="all").to_dict()
        data["correlations"] = df[cols].select_dtypes("number").corr().to_dict()

    warnings = []
    if len(df) > 1_000_000:
        warnings.append("dataset > 1M rows; consider sampling for plots")

    return Reply(
        ok=True,
        data=data,
        warnings=warnings,
        next_steps=["plot.py", "filter.py"],
    )


if __name__ == "__main__":
    run(main)
```

### `references/statistics.md`

(Detailed schema documentation for the JSON output of `summarize.py`, covering
percentiles, correlation interpretation, missing-data handling, etc. Not loaded
unless the agent explicitly reads it.)

### `agents/openai.yaml`

```yaml
interface:
  display_name: "CSV Explorer"
  short_description: "Statistics and plots for CSV data"
  brand_color: "#10b981"
  default_prompt: "Summarize the columns of @data.csv"
policy:
  allow_implicit_invocation: true
```

### What this sample demonstrates

1. **Frontmatter is pushy** — explicit triggers in `description`, including non-obvious ones ("user pastes CSV/TSV text", "trigger even if user does not say CSV explicitly").
2. **SKILL.md body is short** — ~50 lines. Detail lives in `references/`.
3. **Every script returns JSON** via `_common.Reply`. The agent never has to parse prose.
4. **Setup is idempotent** — safe to call every session, no-ops if deps are installed.
5. **Codex sidecar is present but additive** — Claude Code and Hermes ignore it.
6. **Progressive disclosure** — `references/statistics.md` exists but is only read when the agent wants depth.

---

## Part 3 — GRAIL's surface (what the skill will wrap)

### CLI subcommands (from `grail/cli/`)

Core: `init`, `index`, `query`, `append`, `edit`, `delete`, `create-entities`, `status`, `config show`, `explore`, `viz`, `export-neo4j`, `prompt list`, `prompt show`, `ui`, `chat`.

Each accepts a project directory positionally. `--log-level` and `GRAIL_LOG_LEVEL` env var are global.

### Python SDK (`grail/core.py` + `grail/__init__.py`)

The `GRAIL` class is the entry point. Skill scripts will import this directly.

```python
from grail import GRAIL, load_config, Config, SearchResult

cfg = load_config("./my-project")           # discovers grail.yaml + per-module YAMLs
grail = GRAIL.from_config(cfg)              # factory

await grail.index()                          # full pipeline
await grail.search(query, mode="cascade")    # search, returns SearchResult
await grail.agent_search(query, ...)         # agent loop
await grail.append(files=[...])              # incremental add
await grail.edit(replacements={...})         # incremental replace
await grail.delete(filenames=[...])          # incremental drop
grail.status()                               # dict of artifact counts
```

Re-exports from `grail/__init__.py`: `GRAIL`, `LLMClient`, `EmbeddingClient`, `PromptRegistry`, `Config`, `load_config`, `SearchResult`, `Entity`, `Relationship`, `Document`, `TextUnit`, `Community`, `CommunityReport`.

### Config discovery

`load_config()` accepts:
- `None` → defaults
- A path to a single YAML file
- A directory containing `grail.yaml` (and optional per-module YAMLs that merge in)

Env var substitution (`${VAR}` and `${VAR:-default}`) is resolved from `os.environ`. CLI auto-loads `.env` from repo root and project dir.

**Critical for the skill**: there is no `--config` CLI flag yet; config is discovered from the project directory. The skill's `_common.py` will replicate this discovery in Python (walk up looking for `grail.yaml`).

### Optional extras (`pyproject.toml`)

| Extra | Pulls in | Used for |
|---|---|---|
| `faiss` | `faiss-cpu` | FAISS vector store (recommended default) |
| `chroma` | `chromadb` | ChromaDB vector store |
| `s3` | `boto3`, `aioboto3` | S3 storage backend |
| `rerank` | `sentence-transformers` | Local reranker |
| `ui` | `fastapi`, `uvicorn`, ... | Web chat UI |
| `notebook` | `pyvis`, `matplotlib`, ... | Visualisation |

Skill's `requirements.txt` should pin `grail[faiss]` plus whatever the skill exercises (typically not `ui` or `notebook`).

### Two modes — the v2 framing

From `dev_prompts/prompt_grail_agentic_memory_design.md`:

- **Knowledge base** mode (default): `grail init` scaffolds `input/` for batch indexing. LLM-driven extraction.
- **Memory** mode: `grail init --memory` scaffolds `memories/` for tool-driven writes. Agent calls tools that validate, mutate files + parquet atomically, return `{result, warnings, next_steps}`.

Mode is declared in `grail.yaml` (`mode: knowledge_base | memory`). Both modes produce the same parquet artefacts, so every existing search mode works in both.

Memory mode tools are SDK-first by design (per the v2 framing): the CLI may eventually wrap some of them, but the skill should import the SDK directly.

### No existing JSON-RPC / MCP / OpenAPI surface

GRAIL exposes only CLI + Python SDK today. The skill is the first programmatic agent-facing wrapper. No need to wait on a server layer — scripts call the SDK directly.

---

## Part 4 — Proposed GRAIL skill structure

### Folder

```
skills/grail/                              ← canonical source in the GRAIL repo
├── SKILL.md                               ← entry: routing, safety, dep check, project discovery
├── requirements.txt                       ← grail[faiss] + minimal extras
├── INSTALL.md                             ← per-framework install notes
│
├── agents/
│   └── openai.yaml                        ← Codex sidecar
├── hermes.yaml                            ← Hermes extra frontmatter (version, config, env vars)
│
├── references/
│   ├── kb_mode.md                         ← KB workflow: init → index → append/edit/delete → query
│   ├── memory_mode.md                     ← memory workflow: init --memory → add_observation → recall → consolidate
│   ├── search_modes.md                    ← local / cascade / global / document / agent / recall
│   ├── query_optimization.md              ← WHO + WHAT + SPECIFIC formula; mode-pick heuristics
│   ├── config_reference.md                ← grail.yaml fields an agent might touch
│   ├── memory_tools.md                    ← add_observation / add_entity / add_relationship / recall / consolidate
│   ├── proposals.md                       ← consolidate proposal review workflow
│   ├── multi_project.md                   ← workspace / cross-project queries
│   └── troubleshooting.md
│
├── scripts/
│   ├── setup.sh                           ← idempotent: `python -c 'import grail' || pip install -r requirements.txt`
│   ├── _common.py                         ← project discovery + JSON envelope + mode dispatch
│   ├── env_check.py                       ← {grail_version, project_mode, missing_extras}
│   ├── list_grail_projects.py             ← scan workspace, return JSON list
│   ├── init_project.py                    ← `grail init [--memory]` wrapper; writes meta.json
│   ├── status.py                          ← reads meta.json + grail.yaml + counts
│   ├── index.py                           ← full pipeline; returns run_id + stats
│   ├── append.py
│   ├── edit.py
│   ├── delete.py
│   ├── query.py                           ← search; flags --mode --since --category etc.
│   ├── explore.py                         ← graph stats JSON
│   └── memory/                            ← memory-mode-only scripts
│       ├── add_observation.py
│       ├── add_entity.py
│       ├── add_relationship.py
│       ├── add_community.py
│       ├── recall.py
│       ├── consolidate.py
│       ├── list_proposals.py
│       └── apply_proposal.py
│
└── assets/
    ├── grail.kb.yaml.tpl                  ← KB starter config
    ├── grail.memory.yaml.tpl              ← memory starter config (mode: memory)
    └── observation.md.tpl                 ← frontmatter observation template
```

### Project identity — `meta.json`

Every GRAIL project gets a `meta.json` written at init time. This is **machine-managed**; humans don't edit it. Lives alongside `grail.yaml`.

```json
{
  "schema_version": 1,
  "id": "01HFZP3J2Q7Y8R5KMNPVTXEAQD",
  "name": "work-memory",
  "mode": "memory",
  "created_at": "2026-06-01T14:22:18Z",
  "last_indexed_at": "2026-06-01T15:00:00Z",
  "grail_version": "0.4.2",
  "description": "Personal observations across work",
  "tags": ["work", "personal-agent"]
}
```

- `id` = ULID (timestamp-sortable, URL-safe, survives folder moves)
- `name` = display string (default = folder name; user-overridable)
- `mode` = mirrors `grail.yaml` for cheap reads — `list_grail_projects.py` doesn't have to parse YAML + resolve env vars on every entry
- Updated by `init_project.py`, `index.py`, `append.py`, `consolidate.py`

### Workspace registry — `~/.grail/registry.json`

Cache of known projects across the user's machine. **`meta.json` is authoritative**; the registry is a cache that gets rebuilt by `list_grail_projects.py --rescan`.

```json
{
  "schema_version": 1,
  "projects": [
    {
      "id": "01HFZP3J2Q7Y8R5KMNPVTXEAQD",
      "name": "work-memory",
      "mode": "memory",
      "path": "/Users/bgg/projects/work-memory",
      "last_seen": "2026-06-01T15:00:00Z"
    }
  ]
}
```

### Project ref resolution

Every script accepts `--project <ref>`. `_common.resolve_project_ref(ref)` tries in order:

1. **Looks like a path** (contains `/`, starts with `.` or `~`) → use as path; verify `meta.json` exists
2. **Matches a `name` in registry** (case-insensitive, exact) → resolve to path
3. **Matches an `id` prefix** (≥8 chars, unambiguous) → resolve to path
4. **None match** → JSON error listing known projects

Agent UX:
```bash
python scripts/query.py --project work-memory "what did acme say about pricing"
python scripts/query.py --project ./work-memory ...
python scripts/query.py --project 01HFZP3J ...
python scripts/memory/add_observation.py --project work-memory --title "..." --content "..."
```

### JSON envelope returned by every script

```json
{
  "ok": true,
  "mode": "memory",
  "project": {"id": "01HF...", "name": "work-memory", "path": "/Users/..."},
  "data": { ... script-specific payload ... },
  "warnings": ["folder `work/clients/acme` now has 47 entities — consider running consolidate"],
  "next_steps": ["scripts/memory/consolidate.py", "scripts/status.py"]
}
```

Failure shape:
```json
{
  "ok": false,
  "error": "ProjectNotFound: no project matches 'foo'",
  "data": {"known_projects": [...]}
}
```

### Why SDK, not CLI

Scripts internally `from grail import GRAIL, load_config`. Three reasons:

1. **Memory tools don't all exist as CLI commands.** Per the memory design doc, `add_observation`, `add_entity`, `recall`, `consolidate`, `accept_proposal` are SDK-first.
2. **Atomic multi-step operations.** `add_observation` = write markdown + parse frontmatter + append parquet + update FAISS. Single SDK call; subprocess-per-step would race.
3. **Structured outputs.** SDK returns typed objects → script serialises to JSON envelope. CLI text would need re-parsing.

CLI subprocesses are still fine for `grail init` (one-shot scaffolding) and `grail status` (read-only). Everything write-path uses SDK.

### SKILL.md routing logic

```markdown
---
name: grail
description: |
  Build queryable knowledge graphs from documents OR maintain agent memory across
  sessions using GRAIL (Graph RAG). Use this skill WHENEVER the user wants to:
  index a corpus, answer questions over documents, append/edit/delete sources from
  an existing index, build a knowledge base from PDFs/markdown/code, OR remember
  things across conversations (observations, entities, relationships) and recall
  them later, consolidate memory into communities, or query an agent's accumulated
  memory. Triggers include: "index these documents", "build a knowledge graph",
  "what does the corpus say about X", "remember that ...", "what did I learn
  about Y last week", "consolidate my memory", "what do I know about Z".
version: 1.0.0
---

# GRAIL

GRAIL has two modes. Decide which from user intent, then route.

## Before any action
1. Run `bash scripts/setup.sh` (idempotent — safe every session).
2. Run `python scripts/list_grail_projects.py` to see known projects.
3. If the user names or implies a project, pass it as `--project <ref>` to subsequent calls.
4. Run `python scripts/status.py --project <ref>` and use the returned `mode` to route.

## Mode routing
- `mode: knowledge_base` → read `references/kb_mode.md`
- `mode: memory` → read `references/memory_mode.md`

## Creating a new project
- KB: `python scripts/init_project.py --project <path> [--name <name>]`
- Memory: `python scripts/init_project.py --memory --project <path> [--name <name>]`

Both write `meta.json`, `grail.yaml`, and register the project in `~/.grail/registry.json`.

## Search modes
See `references/search_modes.md`. Default is `cascade` for KB, `recall` for memory.

## Pitfalls
- Never edit `meta.json` by hand — let scripts manage it.
- If `scripts/setup.sh` fails, GRAIL isn't installed; check `INSTALL.md`.
- Memory mode requires Phase 2 of `dev_prompts/prompt_grail_agentic_memory_design.md` to be implemented before the memory/ scripts work end-to-end.

## Verification
Every script returns `{"ok": true|false, ...}`. Check `ok` before claiming success.
```

### Distribution

- **Source of truth**: `skills/grail/` inside the GRAIL repo.
- **PyPI integration**: `pip install grail[skill]` extra adds a `grail skill install` CLI subcommand:
  ```bash
  grail skill install --framework claude         # → ~/.claude/skills/grail/
  grail skill install --framework codex          # → ~/.agents/skills/grail/
  grail skill install --framework hermes         # → Hermes Skills Hub path
  grail skill install --framework all            # → all three
  grail skill install --project                  # → ./.claude/skills/grail/ (project scope)
  ```
- The command symlinks when supported (fast updates), copies otherwise.

---

## Open questions for the next session

Most decisions are settled. These remain:

1. **One skill folder vs two siblings (`grail-kb` + `grail-memory`)?**  
   Leaning: **one folder**, routed internally. Anthropic skill-creator guidance prefers descriptions to be "pushy" enumerating multiple trigger surfaces; a single skill can list both. Two siblings cost an extra install and duplicate `setup.sh` / `_common.py`. Confirm before writing the folder.

2. **Registry home: skill-local vs GRAIL core?**  
   Leaning: **skill-local in v1**. `_common.py` writes `meta.json` and maintains `~/.grail/registry.json`. If valuable, promote to `grail projects list/add/remove` CLI later. Alternative is to build registry directly into GRAIL core now (one source of truth for humans and agents) — slightly more work upfront.

3. **Distribution surface.**  
   Leaning: **in-repo + `grail skill install` CLI** as a first step; publish to marketplaces (agentskills.io, Hermes Skills Hub, Claude Code Plugin marketplace) once the skill is proven.

4. **What to do about Anthropic API runtime (no network)?**  
   Document the skill as Claude-Code / Codex / Hermes only. Don't try to support the API code-execution container — pre-installed packages don't include `grail`.

5. **Memory-mode scripts referencing not-yet-built features.**  
   Phases 2+ of memory mode are in-flight in a parallel session. Should the skill's `scripts/memory/*` ship as stubs that return `{"ok": false, "error": "memory mode not yet implemented in this GRAIL version"}` until the SDK lands, or be added only when the SDK is ready? Leaning: **ship as stubs** so the skill folder shape is stable from v1.

6. **ULID dependency.**  
   `meta.json.id` is a ULID. Either add `python-ulid` to `requirements.txt` (tiny, no transitive deps) or hand-roll one in `_common.py`. Leaning: **hand-roll** — keeps requirements minimal.

7. **Concurrent project access.**  
   If two agent sessions write to the same memory project at the same time, the registry can race. v1 is single-writer; add filesystem locking in v2 if needed.

---

## Implementation order (when work starts)

### Phase 1 — Skeleton + sample (1 day)
1. Create `skills/grail/` folder shape.
2. Write `SKILL.md` with routing logic above.
3. Write `requirements.txt`, `setup.sh`, `INSTALL.md`.
4. Write `_common.py` with project discovery + JSON envelope + `resolve_project_ref`.
5. Write `env_check.py`, `list_grail_projects.py`, `init_project.py`, `status.py`.

### Phase 2 — KB mode scripts (1 day)
1. `index.py`, `append.py`, `edit.py`, `delete.py`, `query.py`, `explore.py`.
2. `references/kb_mode.md`, `references/search_modes.md`, `references/query_optimization.md`.
3. Codex sidecar `agents/openai.yaml`.

### Phase 3 — Memory mode stubs (0.5 day)
1. `scripts/memory/*.py` as stubs returning `not_implemented` until SDK lands.
2. `references/memory_mode.md`, `references/memory_tools.md`, `references/proposals.md`.

### Phase 4 — Distribution (1 day)
1. Add `grail skill install` CLI subcommand.
2. Add `[skill]` extra to `pyproject.toml` (just installs `grail` itself + ULID).
3. Smoke test on all three frameworks: Claude Code, Codex, Hermes.

### Phase 5 — Memory mode wiring (when memory SDK ships)
1. Replace memory stubs with real SDK calls.
2. Run end-to-end tests in memory mode.

### Phase 6 — Marketplace listings (optional)
1. agentskills.io listing.
2. Hermes Skills Hub PR.
3. Claude Code Plugin marketplace listing.

---

## Files to read before continuing

For a new session picking up this work:

1. **This file** — the design.
2. **`dev_prompts/prompt_grail_agentic_memory_design.md`** — memory mode internals; explains what `scripts/memory/*` will eventually wrap.
3. **`grail/core.py`** — the SDK entry point (`GRAIL` class) the scripts will import.
4. **`grail/config.py`** — `load_config()` and the Config schema.
5. **`grail/cli/main.py`** — how the existing CLI is wired; the `grail skill install` subcommand will sit alongside.
6. **`grail/__init__.py`** — re-exports the SDK surface.
7. **`docs/search_modes.md`** — what `references/search_modes.md` will summarise for the agent.
8. **`CLAUDE.md`** — project conventions.

### Authoritative external references

- Anthropic Agent Skills overview: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>
- Anthropic skills repo (templates + examples): <https://github.com/anthropics/skills>
- Anthropic skill-creator (best practices): <https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md>
- Codex Agent Skills: <https://developers.openai.com/codex/skills>
- Hermes Skills System: <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills>
- Open standard explainer: <https://www.agensi.io/learn/agent-skills-open-standard>

---

## Status (as of this revision, 2026-06-01)

- **Skill format research**: complete. Anthropic + Codex + Hermes formats compared and reconciled.
- **GRAIL surface mapping**: complete. CLI, SDK, config discovery, optional extras documented.
- **Skill folder shape**: proposed; pending final answer on one-vs-two skills.
- **Project identity (`meta.json`) + registry**: agreed.
- **SDK-not-CLI**: agreed.
- **Implementation**: not started.
- **Blockers**: memory mode SDK (Phase 2 of `prompt_grail_agentic_memory_design.md`) blocks Phase 5 of this work, but not Phases 1–4.
- **Estimated effort**: 3–4 focused days for Phases 1–4; Phase 5 piggybacks on memory mode work; Phase 6 open-ended.

A new session should read this file, scan Open Questions, confirm the one-vs-two split + registry home with the user, then start Phase 1.
