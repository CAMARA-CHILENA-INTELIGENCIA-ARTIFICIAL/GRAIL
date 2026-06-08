# GRAIL Agent Skill — Development Story & Continuation Brief

> **Purpose**: A new Claude Code session continuing this thread should be able
> to read this single file and pick up the skill maintenance / evolution work
> without needing prior conversation history. It documents the complete arc
> from initial design through the v0.1.3 release, every architectural
> decision, every fix, and what's still open.
>
> **Companion docs** (also in `dev_prompts/`):
> * `prompt_grail_skill_design.md` — the original design brief (universal
>   skill format research; folder shape; SDK-not-CLI rationale)
> * `prompt_grail_agentic_memory_design.md` — Memory Mode internals (the SDK
>   the skill scripts wrap)
>
> **Status**: the skill is **published, installable, and used by Claude Code**
> as of v0.1.3 (graphgrail on PyPI; cchia_skills repo on GitHub).

---

## TL;DR

GRAIL ships as a **cross-framework agent skill** (Claude Code, Codex, Hermes)
plus the underlying Python package on PyPI. Two install paths:

```bash
# npx (Claude Code, easiest)
npx skills add CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills --skill grail

# Manual (any framework)
git clone <GRAIL repo> && ln -s "$(pwd)/skills/grail" ~/.claude/skills/grail
```

The skill auto-installs `graphgrail` from PyPI on first use via `setup.sh`,
then exposes a tree of scripts that wrap `MemoryProject` / `GRAIL` SDKs and
return JSON envelopes on stdout.

Key technical decisions, in chronological order of discovery:

1. **One skill folder** routed internally by `meta.json.mode` — KB and memory
   share the same skill (not two siblings).
2. **Scripts call the Python SDK, not the CLI** — atomic multi-step ops + typed
   returns.
3. **PyPI distribution name = `graphgrail`**; Python import name stays `grail`.
   The `grail` name on PyPI was taken by an unrelated test framework.
4. **Default install location for projects: `~/.grail/projects/<name>/`** —
   predictable for the agent, simple to discover. Custom paths still work.
5. **Setup refuses cleanly on PEP 668 system Python** (Homebrew, Debian) when
   no venv is active. Emits a JSON envelope pointing at `uv venv`.
6. **The skill description is "pushy"** — explicit re-read instruction every
   user message, proactive memory proposals, search before answering.
7. **CI/CD is tag-driven**: `git push origin vX.Y.Z` triggers `publish.yml`
   which builds and publishes to PyPI via Trusted Publishing (no token in CI).

---

## Part 1 — Where things stand on disk

Two repositories, both at `/Users/bgg/Documents/repos/cchia/opensource_comission/projects/`:

### GRAIL repo (upstream skill + Python package)

```
GRAIL/
├── pyproject.toml                          name = "graphgrail", version = "0.1.3"
├── docs/
│   └── releasing.md                        the PyPI release runbook
├── grail/                                  the Python package (import as ``import grail``)
│   ├── _version.py                         reads from importlib.metadata
│   ├── core.py                             GRAIL class
│   ├── memory/                             MemoryProject + analyses + proposals
│   ├── indexing/                           extractor, loader, schema migration
│   ├── query/                              search modes, retrieval, recall_filter
│   └── cli/main.py                         grail CLI
└── skills/
    └── grail/                              the skill (canonical source)
        ├── SKILL.md                        ultra-pushy description + body
        ├── INSTALL.md                      per-framework + venv guide
        ├── requirements.txt                graphgrail[faiss] >= 0.1
        ├── agents/openai.yaml              Codex sidecar
        ├── assets/                         starter yaml + observation template
        ├── references/                     8 markdown files (kb_mode, memory_mode, ...)
        └── scripts/
            ├── setup.sh                    PEP 668-aware idempotent installer
            ├── _common.py                  Reply + discover_projects + resolve_project_ref
            ├── env_check.py
            ├── list_grail_projects.py      home-dir + registry, dedupes by ULID
            ├── session_start.py            one-call session probe (setup + projects + stats)
            ├── init_project.py             home-dir default for bare names
            ├── status.py                   per-project artefact counts
            ├── index.py / append.py / edit.py / delete.py
            ├── query.py                    universal — all search modes
            ├── explore.py                  graph shape report
            └── memory/
                ├── add_observation.py
                ├── add_entity.py
                ├── add_relationship.py
                ├── add_community.py
                ├── find_similar_entity.py
                ├── recall.py
                ├── consolidate.py
                ├── list_proposals.py
                └── apply_proposal.py
```

### cchia_skills repo (distribution mirror)

```
cchia_skills/
└── skills/
    └── grail/                              byte-identical mirror of GRAIL/skills/grail/
        + README.md (Spanish)               cchia convention requirement
        + README.en.md (English)            cchia convention requirement
```

The cchia copy adds bilingual READMEs per the
[CONTRIBUTING.md](https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills/blob/master/CONTRIBUTING.md)
of that repo. The skill files themselves are identical between the two repos.

**Critical**: when you change `skills/grail/*` in the GRAIL repo, mirror to
`../cchia_skills/skills/grail/*`. Both must match for users to get the same
behaviour from either install path.

---

## Part 2 — The cross-framework skill format

We confirmed Claude Code, Codex, and Hermes all use the same on-disk format:
a folder with `SKILL.md` (required) + optional `scripts/`, `references/`,
`assets/`. Framework-specific extensions are additive — they don't break the
others, so we ship them all in one folder.

| Surface | Loaded when | Token budget |
|---|---|---|
| `description` frontmatter | Every session start | ~100 tokens, **hard cap 1024 chars** |
| SKILL.md body | When skill triggers | ~5k tokens |
| `references/*.md` | Agent reads explicitly | unlimited |
| `scripts/*` | Executed via bash | output-only enters context |

**Distribution paths** by framework:

| Framework | User-scope | Project-scope |
|---|---|---|
| Claude Code | `~/.claude/skills/grail/` | `<repo>/.claude/skills/grail/` |
| Codex | `~/.agents/skills/grail/` | `<repo>/.agents/skills/grail/` |
| Hermes | Skills Hub directory | n/a |

The `npx skills add` CLI installs to `~/.claude/skills/<name>/` by default.

---

## Part 3 — The pushy SKILL.md

A key learning: **Claude Code can drop skill context between user turns**.
Standard "describe what the skill does" frontmatter under-triggers — the
agent forgets the skill exists mid-session.

The fix is to make the description **prescriptive about agent behaviour**,
not just descriptive. Current description is 991/1024 chars and reads:

> GRAIL IS INSTALLED — the user opted in to persistent memory + queryable
> knowledge graphs across sessions. Be proactive. RE-READ THIS SKILL AT THE
> START OF EVERY USER MESSAGE; Claude Code can drop skill context between
> turns. USE IT WHEN: (1) user says remember / recall / "last time" /
> "we discussed" / ...; (2) user shares save-worthy content (decisions,
> preferences, contacts, dated facts, meeting notes, findings) — propose
> "want me to save this to memory?"; (3) user asks a question that could
> live in their projects — run list_grail_projects + status +
> recall/cascade BEFORE answering from training data; (4) at session
> start, run list_grail_projects.py once to know what exists. If zero
> projects, propose creating one (memory by default). Triggers: ...

The body opens with `## Proactive behaviours (do these without being asked)`
containing four sub-sections:

1. At the start of every user message → run `session_start.py`, cache the
   result
2. When the user asks a question → search GRAIL **first**, then answer
3. When the user shares save-worthy content → propose `add_observation`
   with verbatim "want me to save this?" line
4. When a memory folder grows past ~30 entities → propose `consolidate`

This pattern (description = behavioural directive, not description) is the
single biggest change for skill effectiveness in Claude Code.

---

## Part 4 — PyPI release flow

### Why `graphgrail` and not `grail`

The `grail` PyPI name was taken (an unrelated test-script framework). PyPI
distribution name (what pip installs) and Python import name (what code
calls) are independent — we publish as `graphgrail`, users still write:

```python
pip install graphgrail
from grail import GRAIL, MemoryProject
grail              # CLI binary stays "grail"
```

Setup follows the pattern of `python-dateutil` → `import dateutil`, or
`Pillow` → `import PIL`.

### Release infrastructure

* **`docs/releasing.md`** is the canonical runbook. Has a §1 one-time setup
  (PyPI account, 2FA, API tokens), §2 pre-flight checklist (tests, version
  bump, stale `pip install grail[...]` grep), §3 TestPyPI dry-run, §4 real
  PyPI publish, §5 tag, §6 optional Trusted Publishing for CI, §7 post-
  release checklist, §8 common failures.
* **`.github/workflows/publish.yml`** triggers on `push: tags: ["v*"]`. Uses
  PyPI's Trusted Publishing (OIDC) — no token stored in CI.
* **The publish flow today**: bump `pyproject.toml` + `grail/_version.py`
  fallback + `skills/grail/SKILL.md version:`, commit, `git tag -a vX.Y.Z`,
  `git push && git push origin vX.Y.Z`. CI builds + uploads automatically.

### Versions shipped to PyPI

| Version | Notable |
|---|---|
| 0.1.0 | Initial release with skill |
| 0.1.1 | First skill fixes |
| 0.1.2 | Bug-fix batch: nudge lambda crash, `_version.py` stale fallback, memory-mode delete via `GRAIL.delete` (added `_sync_partial_text_units`), skill version bump |
| 0.1.3 | **Current.** Retrieval embedding-dim guard, skill home-dir convention, chat UI i18n + frontend rebuild, docs refresh |

The `grail/_version.py` reads from `importlib.metadata.version("graphgrail")`
with a hardcoded fallback that must match `pyproject.toml`. **Both must be
bumped together** — was a bug in 0.1.1.

### `pip install grail` is a footgun

There's an unrelated `grail` test framework on PyPI. If `pip install
graphgrail` ever fails (network blip, version typo) and the agent improvises
with `pip install grail`, it succeeds — and `import grail` even works — but
exposes totally different classes. `troubleshooting.md` warns explicitly.

---

## Part 5 — PEP 668 / venv handling

Modern Python distributions (Homebrew on macOS, Debian/Ubuntu, recent Fedora)
mark their system interpreter as PEP 668 *externally-managed*. `pip install`
against system Python is refused by design.

`setup.sh` detects this via the `EXTERNALLY-MANAGED` marker inside
`sysconfig.get_paths()["stdlib"]` (the marker lives *inside* stdlib, not in
its parent — was a bug initially) and emits a JSON envelope:

```json
{
  "ok": false,
  "error": "Python at /opt/homebrew/bin/python3.14 is externally-managed (PEP 668) and no virtual environment is active. ...",
  "next_steps": [
    "uv venv .venv && source .venv/bin/activate && bash scripts/setup.sh",
    "or: python3 -m venv .venv && source .venv/bin/activate && bash scripts/setup.sh",
    "or: GRAIL_ALLOW_SYSTEM_INSTALL=1 bash scripts/setup.sh  (forces --break-system-packages; risky)"
  ]
}
```

**Detection logic** (in `scripts/setup.sh`):

```bash
VENV_CHECK="$("$PY" - <<'PYEOF'
import os, sys, sysconfig
from pathlib import Path
in_venv = (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)
# Marker lives INSIDE stdlib, not its parent.
marker = Path(sysconfig.get_paths()["stdlib"]) / "EXTERNALLY-MANAGED"
externally_managed = marker.exists()
print(f"{int(in_venv)} {int(externally_managed)} {sys.executable}")
PYEOF
)"
```

The bypass `GRAIL_ALLOW_SYSTEM_INSTALL=1` exists for CI containers and
throwaway VMs. Adds `--break-system-packages` to pip.

`SKILL.md`, `INSTALL.md`, and `references/troubleshooting.md` all document
the venv requirement with `uv venv` as the recommended path.

---

## Part 6 — The home-dir convention (v0.1.3)

The biggest UX-improving change since v0.1.0.

### Before

Projects could live anywhere; `~/.grail/registry.json` indexed them. The
agent had to call `list_grail_projects.py` which read the registry, then
map names to paths. Two layers (filesystem + registry index) meant they
could drift. Stale registry entries pointing at gone paths surfaced as
errors at random times.

### After

```bash
# Bare name → ~/.grail/projects/<name>/
python scripts/init_project.py --project work-memory --memory

# Custom path → wherever you point it (still works)
python scripts/init_project.py --project ./local-kb
python scripts/init_project.py --project /Users/me/research/kb --memory
```

**Discovery** (in `_common.py`) reads `~/.grail/projects/*/meta.json`
directly, then merges in registry entries for custom-path projects. Dedupes
by ULID — **filesystem wins on conflict**. Stale registry entries auto-
skipped (unless `--include-stale`).

**Reference resolution** prefers home-dir over registry:

```python
# In _common.resolve_project_ref:
# 1. Path-shaped ref → resolve directly
# 2. Bare name → ~/.grail/projects/<ref>/meta.json (filesystem first)
# 3. Bare name → registry by name (exact, case-insensitive)
# 4. ≥8-char name → registry by ULID prefix
# 5. None match → FileNotFoundError with known-project listing
```

### Files affected

* `init_project.py` — `_resolve_project_dir(ref)` applies the default
* `list_grail_projects.py` — calls shared `discover_projects()`
* `session_start.py` — same; layers per-project quick stats on top
* `_common.py` — `discover_projects()` + updated `resolve_project_ref()`
* `SKILL.md` "Creating a new project" section + `references/memory_mode.md`
  "Where projects live" section — document the convention

### Why filesystem-first

The registry was useful when projects could live anywhere, but it adds a
class of "registry says X exists but it doesn't" failures. With the
home-dir convention, the filesystem **is** the truth for the common case.
Registry just supplements it for custom-path projects.

---

## Part 7 — Bug fixes shipped in 0.1.2 / 0.1.3

These are the cross-cutting fixes worth knowing about for any future skill
work — patterns that recur.

### Bug 1: nudge lambda + parquet round-trip (FIX1, 0.1.2)

`grail/memory/project.py` had:

```python
cat_entities = merged_e["community_ids"].apply(
    lambda cids: category in (cids or [])
).sum()
```

`cids` is a numpy array round-tripped from parquet; `cids or []` triggers
`__bool__` on the array, raising "ambiguous truth value" for multi-element
arrays.

**Fix**: use `_aslist(cids)` from `grail/memory/_merge.py`. This helper
normalises None/list/numpy-array/iterable into a plain list. We use it ~10
places in the file; missed one.

**Knock-on**: the lambda ran in step 8 of `add_observation` (folder-
threshold nudge). Steps 1–7 had already written the parquets and the
markdown file. A crash here left the parquets + .md on disk and returned
an error. The agent retried, hit the slug-collision branch, and wrote
`<title>-2.md`. **That's where the duplicate -2.md files came from.**

**Defense in depth**: moved the nudge **before** the parquet writes, so
future bugs there can't half-commit.

### Bug 2: `_version.py` hardcoded (FIX2, 0.1.2)

`pyproject.toml` was `0.1.1` but `grail/_version.py` was still
`__version__ = "0.1.0"`. The wheel metadata was correct but
`import grail; grail.__version__` lied.

**Fix**: `_version.py` now reads from `importlib.metadata.version("graphgrail")`
with hardcoded fallback for editable installs. Both fallback strings (one
in the inner try, one in the outer `except ImportError`) must be bumped on
every release.

### Bug 3: memory-mode delete via `GRAIL.delete` (FIX3, 0.1.2)

`scripts/delete.py` correctly called `grail.delete(file_names=...)` (the
fixed kwarg). But it failed with `KeyError: 'id'` on memory projects.

**Root cause**: `FileLoader.load_artifacts` reads `partial_text_units.parquet`
(KB-pipeline convention). Memory projects skip the partial stage entirely —
they write straight to `final_text_units.parquet`. So `load_artifacts`
returned an empty DataFrame, and `text_units_df["id"]` raised KeyError.

**Fix**: `MemoryProject._sync_partial_text_units()` helper called at the end
of `add_observation` and `delete_observation`. Mirrors `final_text_units →
partial_text_units` with annotation columns (`entity_ids`,
`relationship_ids`) stripped. KB-pipeline code reading the partial file
now Just Works on memory projects.

We chose to **write both files** rather than fall back in `load_artifacts`
because:
1. Local diff (memory module only) vs. shared code change (`load_artifacts`
   touches every search path)
2. Future code that uses `load_artifacts` works without further patches
3. Storage cost is negligible (~200 KB per 1000 observations)

### Bug 4: retrieval embedding dimension mismatch (0.1.3)

If a user changes `embeddings.model` in `grail.yaml` between index time and
query time, the model dimensions don't match and `_cosine` returned garbage.
Silent failure mode.

**Fix** in `grail/query/retrieval.py:map_query_to_entities`: detect
dimension mismatch and raise a helpful error suggesting either reverting
the model or re-running `grail index`. This is the kind of "wrong tool for
the job" check that pays for itself.

---

## Part 8 — The session_start.py pattern

A single-script "what does the session look like" probe. The agent calls
this once early and caches the result.

Returns:
```json
{
  "ok": true,
  "data": {
    "setup": {"ok": true, "grail_version": "0.1.3", "in_venv": true, ...},
    "projects": [
      {
        "id": "01HF...",
        "name": "work-memory",
        "mode": "memory",
        "path": "/Users/.../work-memory",
        "source": "home",
        "entities": 47,
        "observations": 12,
        "pending_proposals": 2
      },
      ...
    ],
    "summary": "graphgrail 0.1.3 installed; projects: 1 memory, 1 knowledge_base"
  },
  "next_steps": [
    "Project 'work-memory' has 47 entities — eligible for consolidate()",
    "Project 'work-memory' has 2 pending proposal(s) — review with list_proposals.py",
    "User has 2 projects. Before answering a question that could live in them, run query.py first."
  ]
}
```

The `next_steps` field is the **agent-directive** layer — concrete actions
the agent should remember for the rest of the session. This replaces what
the user originally wanted via "mutate SKILL.md to embed project state" —
same outcome (agent knows what's available) without the read-only-symlink /
char-budget / runtime-cache issues of mutating the skill file.

SKILL.md instructs: "First call of the session → `python scripts/session_start.py`.
**Cache it.** Don't call `setup.sh` or `list_grail_projects.py` separately
within the same session."

---

## Part 9 — The JSON envelope contract

Every script returns `Reply` from `_common.py`:

```json
{
  "ok": true | false,
  "mode": "memory" | "knowledge_base" | null,
  "project": {"id": "01HF...", "name": "...", "path": "/...", "mode": "..."} | null,
  "data": { ... script-specific payload ... },
  "warnings": ["..."],
  "next_steps": ["..."],
  "error": "..." | null
}
```

* `ok` is always boolean; the only mandatory field
* On failure: `data.traceback` may carry the Python traceback for diagnosis
* `warnings` are non-blocking — the agent should surface them but continue
* `next_steps` are agent-directive recommendations

**Critical for JSON parseability**: scripts use plain `print(json.dumps(...))`
not `rich.print`. Rich soft-wraps long lines and corrupts JSON. We hit this
multiple times.

---

## Part 10 — Distribution paths confirmed working

### Path A: npx (Claude Code-first)

```bash
npx skills add CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills --skill grail
```

Vercel Labs' `skills` CLI reads from the cchia_skills repo's `master` branch
HEAD and copies `skills/grail/` to `~/.claude/skills/grail/`. No metadata
file needed in the skill beyond `SKILL.md`. The skill folder is the unit.

The cchia_skills repo's main `README.md` (Spanish) and `README.en.md`
(English) skill-list tables include the GRAIL row with the install command.

### Path B: Manual git-clone + symlink

```bash
git clone git@github.com:CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL.git ~/code/GRAIL
mkdir -p ~/.claude/skills
ln -s ~/code/GRAIL/skills/grail ~/.claude/skills/grail
```

Works for any framework — point the symlink at the right path
(`~/.claude/skills/`, `~/.agents/skills/`, or project-scoped). `git pull`
updates the skill automatically.

### Path C (not built): `grail skill install` CLI

`prompt_grail_skill_design.md` proposed `grail skill install --framework
claude|codex|hermes|all`. **Not built**. Lower-priority than the other two
paths since `npx` covers Claude Code and symlink covers everyone.

---

## Part 11 — Open questions / what's NOT done

Things we discussed and decided to defer:

### 1. `~/.grail/projects/` rescan

`list_grail_projects.py --rescan` accepts the flag but doesn't implement
the rescan — it relies on the registry being maintained by `init_project.py`
and `MemoryProject.__init__`. If the registry drifts (e.g. a user manually
copies a project dir), the rescan should walk well-known paths and rebuild
from `meta.json` files. **Not implemented**; current `--rescan` just warns.

### 2. Multi-machine sync of `~/.grail/projects/`

The home-dir convention doesn't help if the user moves between machines.
A `grail sync` command (rsync or git-backed) could mirror across hosts.
**Discussed, not designed.**

### 3. Concurrent project access

If two agent sessions write to the same memory project simultaneously,
the registry can race. v1 is single-writer. Filesystem locking is a
straightforward v2 addition (e.g. `flock(meta.json)` before any mutation).
**Not built.**

### 4. Hermes-specific frontmatter

Hermes accepts extra frontmatter keys (`platforms`, `metadata.hermes`,
`required_environment_variables`). We omit them — Claude Code and Codex
ignore them, but Hermes users get a slightly worse Skills Hub UX. Adding
them is additive and safe; we just haven't.

### 5. Marketplace listings

We have not listed on:
* `agentskills.io`
* Hermes Skills Hub
* Claude Code Plugin marketplace (`/plugin install` UX)

The Claude Code plugin marketplace would need a `.claude-plugin/marketplace.json`
in the GRAIL repo. Not blocked, just not done.

### 6. CWD-aware project discovery

We discussed but rejected scanning the current working directory for
projects. The home-dir default is enough for the agent UX, and avoids the
"why does my agent know about my coworker's project I copied into my
repo?" surprise.

### 7. Anthropic API runtime support

The skill needs `pip install graphgrail`. The Anthropic API code-execution
container has **no network** — can't install. **Not supported there**; the
skill is for Claude Code, Codex, and Hermes only. Documented in `INSTALL.md`
and `references/troubleshooting.md`.

### 8. Memory `update_observation` semantics

`update_observation` is currently "delete + re-add". Preserves the slug
when the title doesn't change. Edge case: the new observation overrides
the old observation's entity descriptions but the underlying graph might
have richer descriptions from other observations referencing the same
entities. We don't merge — last write wins. **Behaviour documented; not a
bug, but worth knowing.**

---

## Part 12 — Maintenance / extension playbook

When you (a future session) need to **change the skill**:

1. **Edit `skills/grail/*` in the GRAIL repo first.** This is the canonical
   source.
2. **Mirror byte-identically to `../cchia_skills/skills/grail/*`** (except
   the bilingual READMEs, which only exist in the cchia copy).
3. **If you changed `SKILL.md`, bump `version: X.Y.Z` in the frontmatter** so
   agents on stale caches notice.
4. **If you changed Python code in `grail/`** (the package, not the skill),
   bump `pyproject.toml` and the `_version.py` fallback. See `docs/releasing.md`.
5. **Smoke test**: run a script via the venv'd Python and parse the JSON.
   The harness in `tests/unit/` covers the SDK; for the skill layer, the
   end-to-end smoke tests in `dev_prompts` (this file) are the reference.

When you need to **release a new package version**:

1. Read `docs/releasing.md` end-to-end.
2. Bump `pyproject.toml`, `grail/_version.py`'s **both** fallback strings,
   `skills/grail/SKILL.md` `version:`.
3. Commit with a `release:` prefix.
4. `git tag -a vX.Y.Z -m "..."`.
5. `git push && git push origin vX.Y.Z`.
6. CI builds + publishes via Trusted Publishing.
7. Verify install in a clean venv: `uv pip install graphgrail==X.Y.Z`.

When you need to **add a new script**:

1. Create under `skills/grail/scripts/` (or `scripts/memory/` if memory-only).
2. Use `_common.py` helpers: `Reply`, `run()`, `resolve_project_ref()`,
   `project_envelope()`, `discover_projects()`.
3. Emit JSON via `Reply.emit()` — never raw `print()` for output.
4. Add to `SKILL.md`'s available-scripts list (search for the existing
   "Available scripts" table).
5. Mirror to cchia_skills.

When you need to **add a new search mode** (in the package, not the skill):

1. Implement in `grail/query/<mode>_search.py` following the existing
   pattern (`local_search.py`, `cascade_search.py`).
2. Wire into `GRAIL.search` in `grail/core.py`.
3. Add the `--mode <name>` option to `grail/cli/main.py:query` and
   `skills/grail/scripts/query.py`.
4. Document in `references/search_modes.md` + the agent-facing tables in
   `SKILL.md`.

---

## Part 13 — Files to read first

For a new session continuing this work, in priority order:

1. **This file** — the story.
2. **`skills/grail/SKILL.md`** — what the agent actually sees. The
   description in particular sets the tone for everything else.
3. **`skills/grail/scripts/_common.py`** — the shared infrastructure. Most
   bugs and design decisions are visible here.
4. **`docs/releasing.md`** — the publish runbook. Read before any version
   bump.
5. **`skills/grail/scripts/session_start.py`** — the proactive-cache pattern.
6. **`grail/memory/project.py`** — `MemoryProject`, including the
   `_sync_partial_text_units` helper that fixed memory-mode delete.
7. **`grail/_version.py`** — small file but important; bump the fallback
   on every release.
8. **`dev_prompts/prompt_grail_skill_design.md`** — original design brief.
   Some of the "Open Questions" there are now answered; this doc is the
   newer truth.
9. **`dev_prompts/prompt_grail_agentic_memory_design.md`** — Memory Mode
   internals; the SDK the skill wraps.
10. **`../cchia_skills/skills/grail/`** — verify it's mirrored after any
    change.

---

## Part 14 — Known good states (smoke tests)

End-to-end flows that should work at any future commit:

### A. Fresh install + first project

```bash
# In a brand-new repo with Claude Code:
npx skills add CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/cchia_skills --skill grail
# Then ask Claude Code: "list my GRAIL projects"
# Expected: skill triggers, runs setup.sh (pip-installs graphgrail), then
# runs session_start.py, returns "no projects yet" with a proposal to create one.
```

### B. Bare-name project init

```bash
python ~/.claude/skills/grail/scripts/init_project.py --project work-memory --memory
# Lands at ~/.grail/projects/work-memory/. used_home_default: true.
```

### C. Custom-path project init

```bash
python ~/.claude/skills/grail/scripts/init_project.py --project ./local-kb
# Lands at ./local-kb/. used_home_default: false.
```

### D. Discovery merges both

```bash
python ~/.claude/skills/grail/scripts/list_grail_projects.py
# Returns both projects; source: "home" vs "custom".
```

### E. PEP 668 refusal

```bash
PYTHON=/opt/homebrew/bin/python3 bash ~/.claude/skills/grail/scripts/setup.sh
# Returns {"ok": false, "error": "...externally-managed...", "next_steps": [...]}
# Exit code 1.
```

### F. Memory-mode delete via the package CLI

```bash
# In a venv with graphgrail >= 0.1.2 installed:
grail delete <memory_project> <file.md>
# Was broken in 0.1.1, fixed in 0.1.2 via _sync_partial_text_units.
```

---

## Status as of this revision

* **Released**: graphgrail 0.1.3 on PyPI; tag v0.1.3 pushed.
* **Skill SKILL.md version**: 1.0.2 (both copies).
* **Unit test suite**: 268 passed + 1 chromadb-optional skip; no regressions.
* **CI/CD**: tag-driven publish via Trusted Publishing; `publish.yml`
  triggers on `v*`.
* **Working trees**: clean (last cycle); ready for next iteration.
* **Open work**: the items in Part 11 above, in priority order if
  prioritising is required.

A new session should:
1. Read this file.
2. Skim `SKILL.md` to see the current pushy description.
3. Check the user's intent (continue with one of the open items, fix a new
   bug, or evolve a different surface).
4. If editing the skill: edit GRAIL repo first, mirror to cchia_skills.
5. If editing the package: follow `docs/releasing.md` for the version bump.
