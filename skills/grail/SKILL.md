---
name: grail
description: |
  GRAIL IS INSTALLED — the user opted in to persistent memory + queryable
  knowledge graphs across sessions. Be proactive. RE-READ THIS SKILL AT
  THE START OF EVERY USER MESSAGE; Claude Code can drop skill context
  between turns. USE IT WHEN: (1) user says remember / recall / "last
  time" / "we discussed" / "what did I learn" / save / my notes / my
  projects / index / knowledge base / corpus / graph RAG / GRAIL; (2)
  user shares save-worthy content (decisions, preferences, contacts,
  dated facts, meeting notes, findings) — propose "want me to save this
  to memory?"; (3) user asks a question that could live in their
  projects — run list_grail_projects + status + recall/cascade BEFORE
  answering from training data; (4) at session start, run
  list_grail_projects.py once to know what exists. If zero projects,
  propose creating one (memory by default). Triggers: remember, recall,
  index, save this, my memory, my KB, "what did I", "last week", "we
  said", "I noted", consolidate, GRAIL, graphgrail.
version: 1.0.2
---

# GRAIL — knowledge graphs + agentic memory

GRAIL is a graph-RAG engine with two project modes that share one search
engine:

| Mode | Write path | Triggers |
|---|---|---|
| `memory` | tool-driven SDK writes under `./memories/` (no LLM at write time) | "remember that ...", "save this", "what did I learn last week" |
| `knowledge_base` | `grail index` over `./input/` (LLM extracts entities + relationships) | "index these PDFs", "build a KB from this corpus" |

Both produce the same parquet artefacts, so every search mode
(`recall`, `local`, `cascade`, `global`, `document`, `agent`) works on
either kind of project.

## Proactive behaviours (do these without being asked)

**The user installed this skill on purpose. Treat that as standing
consent to suggest memory + KB use.** Be pushy but not annoying — one
clear suggestion per save-worthy moment, accept "no" gracefully.

### At the start of EVERY user message

1. Re-anchor on this skill. Do not assume context survives between turns.
2. **If this is your first script call this session**, run:
   ```bash
   python scripts/session_start.py
   ```
   It returns one JSON envelope with: (a) graphgrail install state +
   version, (b) every registered project with mode / path / entity +
   observation counts + pending proposals, (c) directive `next_steps`
   tailored to what it finds.
   **CACHE the result for the rest of the session.** Do not re-run
   `setup.sh` or `list_grail_projects.py` separately — they're subsumed
   by `session_start.py`. Only re-run `session_start.py` if you create
   or delete a project mid-session.

3. **If `setup.ok` is false**, run `bash scripts/setup.sh` first; then
   re-run `session_start.py`.

4. **If zero projects exist** AND this is a real conversation (not a
   one-shot question), propose creation:
   > "I notice you have GRAIL installed but no projects yet. Want me to
   > set up a memory project so I can remember things across our
   > sessions? It takes one command."
   Then if they agree (bare name → lands at `~/.grail/projects/<name>/`):
   ```bash
   python scripts/init_project.py --project my-memory --memory
   ```
   After creating, re-run `session_start.py` so the cached state
   reflects the new project.

### When the user asks a question

Before answering from your own training, check if the answer could be in
their projects:

- Question references a past conversation, a person, a project, a date,
  a document they own, a decision they made → **search first**.
- Run `scripts/query.py --project <ref> --query "..." --mode cascade` or
  `--mode recall --category ... --since ...`.
- If the search returns relevant content, lead with that and cite it. If
  it returns nothing, say "I checked your <project> and didn't find
  anything on this — answering from general knowledge instead."

Default search mode = `cascade` for KB projects, `recall` (for date/tag
slicing without an LLM call) or `cascade` (for semantic questions) for
memory projects. See `references/search_modes.md`.

### When the user shares save-worthy content

Watch for: **decisions**, **preferences**, **dated facts**, **contacts**,
**research findings**, **meeting notes**, **important code snippets**, or
anything the user says "remember this" / "important" / "for later" about.

Propose recording, but **don't ask permission three times**:

> "This sounds worth keeping. Want me to add it to your `work-memory`
> project so we can recall it later?"

If yes, call `scripts/memory/add_observation.py` with a sensible title,
category, tags, and the entities you can extract from the conversation.
See `references/memory_tools.md` for the JSON shape.

### When a memory folder grows past ~30 entities

After accumulating observations, suggest consolidation:

> "Your `work-memory` project now has 47 entities. Want me to run
> consolidate to surface communities and possible alias merges?"

```bash
python scripts/memory/consolidate.py --project <ref>
python scripts/memory/list_proposals.py --project <ref>
# then per-proposal:
python scripts/memory/apply_proposal.py --project <ref> --id <prefix> --accept|--reject
```

## First-time install — venv strongly recommended

`setup.sh` will pip-install `graphgrail` on first use. Run it against a
**fresh virtual environment**, not the system Python — modern Python
distributions (Homebrew, Debian/Ubuntu, recent Fedora) mark the system
interpreter as PEP 668 *externally-managed* and refuse pip installs.

```bash
# uv (recommended — fast, no extra step):
uv venv .venv && source .venv/bin/activate

# Or stdlib:
python3 -m venv .venv && source .venv/bin/activate

# Then trigger the skill's setup:
bash scripts/setup.sh
```

`setup.sh` detects the externally-managed + no-venv case and refuses
cleanly with a JSON envelope whose `next_steps` show the exact commands
above. Read its output before improvising. To force a system install
anyway (CI containers, throwaway VMs), set
`GRAIL_ALLOW_SYSTEM_INSTALL=1` before running `setup.sh`.

## Before any script call

1. **First call of the session → `python scripts/session_start.py`.**
   Returns setup state + projects + per-project stats + recommendations
   in a single JSON envelope. **Cache it.** Don't call `setup.sh` or
   `list_grail_projects.py` separately within the same session.
2. **If `data.setup.ok` is false in that result**, run
   `bash scripts/setup.sh` then re-run `session_start.py`.
3. **For any project op**, pass `--project <ref>` where `<ref>` is a
   path, a registered name, or a ULID prefix (the cached
   `session_start` payload has them).
4. **Resolve mode** from the cached payload (`data.projects[i].mode`).
   Route:
   - `knowledge_base` → see `references/kb_mode.md`
   - `memory` → see `references/memory_mode.md`

## Creating a new project

**Convention: bare names land at `~/.grail/projects/<name>/`.** Pass a
path (absolute or relative) only when the user wants the project
elsewhere — e.g. inside a specific repo or on an external drive.

```bash
# Memory mode (recommended default — bare name → ~/.grail/projects/my-memory/):
python scripts/init_project.py --project my-memory --memory

# Knowledge base (bare name → ~/.grail/projects/my-kb/):
python scripts/init_project.py --project my-kb

# Custom path when the user asks (any of these still work):
python scripts/init_project.py --project ./local-kb --name local-kb
python scripts/init_project.py --project /Users/me/research/kb --memory --name research
```

All three write `grail.yaml`, `meta.json`, and register the project in
`~/.grail/registry.json`. Discovery (`list_grail_projects.py` /
`session_start.py`) scans `~/.grail/projects/` first then merges in
registry entries pointing elsewhere — so custom-path projects show up
exactly the same way.

## Search modes

| Mode | LLM calls | Use it for |
|---|---|---|
| `recall` | 0 | "Show me everything tagged X" / "since 1h" / "in folder Y". Zero cost — try it FIRST. |
| `cascade` | 1 | Robust default for factual questions: entity gate + text rescue. |
| `local` | 1 | Anchored on a named entity. |
| `global` | 1+ | Broad / thematic questions. |
| `document` | 1 | Scoped to one source file. |
| `agent` | 2-5 | The LLM iterates across tools. |

Filter flags compose with any mode: `--since 1h`, `--before 7d`,
`--category 'work/clients/**'`, `--tag pricing`, `--entity-name ALICE`,
`--type PERSON`, `--min-confidence 0.7`.

## When NOT to use this skill

Don't push GRAIL on these (suggest alternatives instead):

| User wants | Use GRAIL? | Better |
|---|---|---|
| Q&A over a single short doc in this chat | No | Paste it; answer directly. |
| Flat FAQ search | Probably not | lancedb / chromadb directly. |
| Code grep | No | ripgrep / language-server tools. |
| One-shot factual lookup | No | Just answer. |
| Persistent memory across sessions | **Yes** | — |
| Cross-document entity relationships | **Yes** | — |
| "What did we decide about ..." | **Yes** | recall + cascade. |

## Pitfalls

- **Never edit `meta.json` by hand** — scripts manage it.
- **`scripts/setup.sh` failed** → check `INSTALL.md`. If `pip install
  graphgrail` errored, surface the error and STOP. Do not try to install
  Python dependencies individually — that masks the real failure.
- **`consolidate` refuses below 30 entities** by default. Don't lower
  the threshold without reason; communities have no signal at small N.
- **No embeddings configured** → `add_*` calls warn and write without
  `description_embedding`; `find_similar_entity` falls back to edit
  distance; `cascade`/`local` degrade. Recall mode is unaffected.
- **Mixing modes** → `index` on a memory project and `consolidate` on a
  KB project both warn but proceed. Read the warning before continuing.
- **Don't fall back to `pip install grail`** (without the `graph`
  prefix) — that's an unrelated test framework on PyPI.

## Verification

Every script returns a JSON envelope on stdout:

```json
{
  "ok": true,
  "mode": "memory",
  "project": {"id": "01HF...", "name": "work-memory", "path": "/Users/..."},
  "data": { ... },
  "warnings": ["..."],
  "next_steps": ["scripts/..."]
}
```

Always check `ok` before claiming success. On failure the shape is
`{"ok": false, "error": "...", "data": {...optional context...}}`.
Propagate the error to the user; do not improvise around it.

## References

- `references/kb_mode.md` — knowledge-base workflow
- `references/memory_mode.md` — memory workflow
- `references/search_modes.md` — local / cascade / global / document / agent / recall
- `references/query_optimization.md` — WHO + WHAT + SPECIFIC formula
- `references/memory_tools.md` — `add_observation` / `add_entity` etc. schema
- `references/proposals.md` — consolidate proposal review workflow
- `references/config_reference.md` — `grail.yaml` fields the agent might touch
- `references/troubleshooting.md` — common failures + fixes
