# Contributing to GRAIL

Thank you for your interest in contributing to GRAIL. This is an open-source framework developed under the [Cámara Chilena de Inteligencia Artificial](https://cchia.cl) commission, stewarded by [Nirvai](https://nirvana-ai.com). We welcome contributions across nine well-defined categories — each with a structured proposal-to-merge flow.

## TL;DR

```
1. Open an issue in the right category template
2. Wait for the team to apply `status:approved`
3. Open a PR that references the approved issue
4. Reviewers check it against the category-specific checklist
5. Merge when CI is green and review approves
```

**No PR without an approved issue.** This rule exists to save your time — we want to give design feedback *before* you write code, not after.

---

## The two-step flow

### Step 1 · Open an issue in a category template

GRAIL contributions fall into one of **nine categories**. Each has its own issue template that asks for the right information up front:

| # | Category | Examples |
|---|---|---|
| 01 | [Inference providers](.github/ISSUE_TEMPLATE/01-inference-provider.yml) | New LLM endpoint (Fireworks, Hugging Face, custom OpenAI-compat) |
| 02 | [Multimodal capabilities](.github/ISSUE_TEMPLATE/02-multimodal.yml) | Vision, audio, video — GRAIL is text-only today, this is new functionality |
| 03 | [Agentic logic](.github/ISSUE_TEMPLATE/03-agentic-logic.yml) | New agent tool, system-prompt update, tool-selection heuristics |
| 04 | [Search methods](.github/ISSUE_TEMPLATE/04-search-method.yml) | New search mode beyond local · cascade · global · document · agent · recall |
| 05 | [Indexing methods](.github/ISSUE_TEMPLATE/05-indexing-method.yml) | New chunker, extractor, community algorithm, report generator |
| 06 | [Vector stores](.github/ISSUE_TEMPLATE/06-vector-store.yml) | New `BaseVectorStore` backend — Qdrant, Weaviate, Milvus, Pinecone |
| 07 | [Cloud integrations](.github/ISSUE_TEMPLATE/07-cloud-integration.yml) | New `StorageBackend`, deploy target, secrets vault |
| 08 | [Library additions](.github/ISSUE_TEMPLATE/08-library-addition.yml) | New Python dependency — runtime, optional extra, dev-only |
| 09 | [Visual apps](.github/ISSUE_TEMPLATE/09-visual-app.yml) | Chat web UI, terminal TUI, dashboards, graph visualisations |

**For anything that doesn't fit a category** (open questions, design discussions, "what do you think about X?") use [GitHub Discussions](https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/discussions) instead.

### Step 2 · Wait for `status:approved`

Once you open an issue, a maintainer will:

- Apply the matching `category:*` label (auto-applied by the template)
- Review the proposal, ask clarifying questions if needed
- Apply **`status:approved`** if the proposal is well-formed and the maintainers want this in GRAIL
- Or apply `status:declined` with a reason — sometimes a proposal is good but not the right fit for GRAIL's scope; we'll be honest about why

This usually takes a few days. If you haven't heard back in a week, ping the issue.

### Step 3 · Open a PR

Once your issue has `status:approved`, open a PR. The [PR template](.github/PULL_REQUEST_TEMPLATE.md) will guide you through a category-specific checklist. Your PR description must:

- Include `Closes #NNN` referencing the approved issue
- Tick the matching category box
- Tick the category-specific checklist as you complete each item

### Step 4 · Review and merge

A maintainer will:

- Verify CI passes (`Build (ES + EN)`, publish gate, tests)
- Check the category checklist is honestly ticked
- Code review
- Merge when ready

If you need changes, push more commits to your PR branch — we use the squash-merge default, so PR-level history stays clean.

---

## Labels

GRAIL uses three label families:

### `category:*` — what kind of change

- `category:inference-providers`
- `category:multimodal`
- `category:agentic-logic`
- `category:search-methods`
- `category:indexing-methods`
- `category:vector-stores`
- `category:cloud-integrations`
- `category:library-addition`
- `category:visual-apps`

Auto-applied by issue templates. Stays on the PR for context.

### `status:*` — where it is in the flow

- `status:proposed` — opened, awaiting maintainer review
- `status:approved` — maintainers want this; safe to start a PR
- `status:declined` — won't proceed; reason in the comment
- `status:in-progress` — a PR is open
- `status:blocked` — waiting on something external
- `status:needs-approval` — PR opened without an approved issue

### `priority:*` (optional)

- `priority:high` · `priority:medium` · `priority:low`

Used to triage the backlog.

---

## Local setup

Python 3.12 + [uv](https://github.com/astral-sh/uv) is the recommended path:

```bash
git clone git@github.com:CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL.git
cd GRAIL
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env
# Fill in DEEPINFRA_API_KEY or OPENAI_API_KEY (whichever you'll use)
```

Verify:

```bash
uv run grail --help
uv run pytest
```

For the docs site:

```bash
cd docs-site
npm install
npm start -- --port 3001    # port 3000 may be in use locally
```

---

## Code conventions

These are firm — please match them so PRs don't get held up on style:

| Convention | Example |
|---|---|
| Snake-case modules, PascalCase classes | `entities_relationships.py`, `class GRAIL` |
| **No `Nirvana` prefix on classes** | `MemoryProject`, not `NirvanaMemoryProject` |
| Async by default for I/O paths | `async def index(self) -> dict` |
| Sync facades wrap `asyncio.run` where useful | (rarely needed today) |
| Entity types ALWAYS `UPPER_SNAKE_CASE` | `PERSON`, `ORGANIZATION`, `CLINICAL_STUDY` |
| Comments only when the **why** is non-obvious | Don't restate what the code does |
| Endpoint and model are **separate** config fields | `llm.endpoint: openai` + `llm.model: gpt-4o-mini` — never `openai\|gpt-4o-mini` in config |
| Optional dependencies live in `[extras]` | `[s3]`, `[ui]`, `[dev]` — not core install |
| Every module gets the author header | `"""Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero."""` |

---

## Testing

- `uv run pytest` — the unit test suite (currently 160+ tests). All tests must stay green.
- For new features, add unit tests under `tests/unit/`.
- For end-to-end changes (search modes, indexing methods), add coverage under `tests/integration/`.
- For schema changes, add fixtures and migration tests.

The CI workflow (`.github/workflows/`) runs the test suite + the docs site build on every PR. PRs cannot merge with a red CI.

---

## Commit message style

Follow the existing log:

```
feat: <what changed>          # new feature
fix: <what was broken>        # bug fix
docs: <what changed>          # documentation only
ci: <what changed>            # CI/CD changes
refactor: <what changed>      # no behavior change
test: <what changed>          # test additions
chore: <what changed>         # everything else
```

Keep the subject line under 72 chars. Body optional but encouraged for non-trivial changes.

---

## Dev prompts (cross-session handoff)

GRAIL is partially developed with AI-assisted sessions. For features that span multiple work sessions, the convention is to write a **dev prompt** under [`dev_prompts/`](dev_prompts/) that fully captures the design discussion so a fresh session can pick up cold. Existing examples:

- `dev_prompts/prompt_grail_agentic_memory_design.md` — design for memory mode
- `dev_prompts/prompt_grail_benchmark.md` — benchmark methodology
- `dev_prompts/prompt_grail_skill_design.md` — agent skill format

If your change is substantial enough that another contributor (human or AI) would benefit from the full context, please add one.

---

## Documentation

Two surfaces, both contribution targets:

| Surface | Audience | Where |
|---|---|---|
| **`docs-site/`** (Docusaurus) | End users | The official documentation at [grail-docs.vercel.app](https://grail-docs.vercel.app/) |
| **`docs/`** (markdown) | Contributors | Internal technical notes — architecture, design decisions, module internals |

User-facing changes (new feature, new mode, new endpoint) go to `docs-site/` and **must include both ES and EN versions** — see existing pages for the i18n structure.

Internal/architecture notes (parser contracts, schema diagrams, scratch decisions) go to `docs/`.

---

## What we ask you NOT to do

- ❌ Don't open a PR without an approved issue (we'll close it and ask you to open one)
- ❌ Don't add a runtime dependency without going through the library-addition template
- ❌ Don't add a vendor lock-in path — GRAIL is provider-agnostic by design
- ❌ Don't commit secrets — even temporarily. We will rotate keys but the history is forever
- ❌ Don't add telemetry / phone-home / analytics — GRAIL is local-first, no exceptions

---

## Author and commission

GRAIL is authored and maintained by **Benjamín González Guerrero**, founder of [Nirvai (Nirvana)](https://nirvana-ai.com), under the open-source commission of the **[Cámara Chilena de Inteligencia Artificial](https://cchia.cl)**.

For questions outside the issue / PR flow:

- 💬 [GitHub Discussions](https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/discussions) for open-ended design questions
- 🔗 [LinkedIn](https://www.linkedin.com/in/bgg-ai/) for direct contact with the author

---

Thanks for helping make GRAIL better.
