# GRAIL MCP server — context & handoff (`grail/mcp/`)

> Self-contained context for any session working on the GRAIL MCP server and
> its distribution through the **cchia-mcp** catalog repo. Read this cold and
> you have everything you need.

---

## 1. Why this exists (the skill-vs-MCP decision)

GRAIL ships two agent surfaces over the **same core**:

- **Skill** (`skills/grail/`) — the *primary* surface. On-demand instructions +
  scripts with progressive disclosure. Carries GRAIL's judgement (search-mode
  routing, the `WHO+WHAT+TERMS` query formula, troubleshooting) as prose the
  model reads when relevant. Cheapest on context. Works wherever the `SKILL.md`
  convention is supported *and* the client can run scripts (Claude Code, Codex…).
- **MCP server** (`grail/mcp/`) — the *reach* layer. Typed tools over the MCP
  protocol so GRAIL is attachable from **any** MCP client — Claude Desktop chat,
  Cursor, Cline, hosted/remote, other frameworks — with no Python harness on the
  client side. Add it when reach beyond shell-capable coding agents matters.

**Rule:** skill-first; MCP for reach. Never duplicate logic — both are thin
wrappers over `GRAIL` / `MemoryProject`, and both return the identical
`{ok, data, warnings, next_steps, error}` envelope. The MCP tool *descriptions*
carry a condensed form of the skill's routing guidance so the MCP surface keeps
the judgement layer.

Anthropic's own guidance: loading every tool's schema up front is wasteful —
which is exactly why skills exist and why this MCP server uses **profiles** to
keep the per-session tool surface lean.

---

## 2. What was built

| File | Role |
|---|---|
| `grail/mcp/__init__.py` | Exports `build_server`, `main`. |
| `grail/mcp/_shared.py` | Project resolution (path / name / ULID prefix), discovery, mode detection, the `reply(...)` envelope, `reply_from_core` (wraps `grail.memory.Reply`), `search_result_data` (compacts `SearchResult`). Mirrors `skills/grail/scripts/_common.py` but lives in the package (importable, shipped in the wheel, eager `grail` import). |
| `grail/mcp/server.py` | FastMCP server. `build_server(profile, default_project)` registers tools; `main()` is the `grail-mcp` console entry point. |

**Packaging (`pyproject.toml`):**
- `[project.optional-dependencies] mcp = ["mcp>=1.2"]` — the FastMCP SDK.
- `[project.scripts] grail-mcp = "grail.mcp.server:main"`.
- Decision: **one package + profiles**, NOT two packages. Reuses the core
  directly so there's no version skew with the library.

**Profiles** (`--profile`):
- `memory` — 16 tools (create/observe/entity/relationship/community, recall,
  list_*, consolidate, proposals) + the 2 shared tools.
- `kb` — 8 tools (create/index/append/edit/delete/query) + the 2 shared.
- `all` — 22 tools (default).
- Shared in every profile: `grail_list_projects`, `grail_status`.

**Binding:** `--project <ref>` defaults every tool's `project` arg to it, and
(when `--profile` is omitted) auto-selects the profile from the project's mode.

**Transports:** `stdio` (default, local) and `streamable-http` (`--port`, remote).

### Tool → core mapping (keep 1:1 with the skill scripts)

| MCP tool | Core call | Skill script |
|---|---|---|
| `grail_list_projects` | `discover_projects()` | `list_grail_projects.py` |
| `grail_status` | filesystem parquet scan | `status.py` |
| `memory_create_project` | `MemoryProject(path)` ctor | `init_project.py --memory` |
| `memory_add_observation` | `await mp.add_observation` | `memory/add_observation.py` |
| `memory_add_entity` | `await mp.add_entity` | `memory/add_entity.py` |
| `memory_add_relationship` | `await mp.add_relationship` | `memory/add_relationship.py` |
| `memory_add_community` | `mp.add_community` (sync) | `memory/add_community.py` |
| `memory_find_similar_entity` | `await mp.find_similar_entity` | `memory/find_similar_entity.py` |
| `memory_recall` | `await mp.recall` | `memory/recall.py` |
| `memory_list_observations/entities/categories/communities` | sync `mp.list_*` | (SDK) |
| `memory_consolidate` | `mp.consolidate` (sync) | `memory/consolidate.py` |
| `memory_list_proposals` | `mp.list_proposals` (sync) | `memory/list_proposals.py` |
| `memory_apply_proposal` | `mp.accept_proposal` / `reject_proposal` | `memory/apply_proposal.py` |
| `kb_create_project` | subprocess `grail init` | `init_project.py` |
| `kb_index` | `await grail.index` | `index.py` |
| `kb_append` / `kb_edit` / `kb_delete` | `await grail.{append,edit,delete}` | `append/edit/delete.py` |
| `kb_query` | `await grail.search` / `agent_search` | `query.py` |

**Async note:** `MemoryProject` write/recall/find methods and all `GRAIL`
pipeline/search methods are `async`; `add_community`, `consolidate`,
`list_*`, `accept/reject_proposal`, `GRAIL.status` are sync. FastMCP runs tool
coroutines in its own loop — `await` directly, do NOT wrap in `asyncio.run`.

---

## 3. Friendly install (the `npx skills add` parallel)

Universal denominator = **PyPI + console entry point + uvx zero-install**:

```bash
# Claude Code
claude mcp add grail-memory -- uvx --from "graphgrail[mcp]" grail-mcp --profile memory
claude mcp add grail-kb     -- uvx --from "graphgrail[mcp]" grail-mcp --profile kb

# Generic mcpServers JSON (Claude Desktop, Cursor, Cline, Windsurf, …)
{
  "mcpServers": {
    "grail-memory": {
      "command": "uvx",
      "args": ["--from", "graphgrail[mcp]", "grail-mcp", "--profile", "memory"]
    }
  }
}
```

Plus: publish to the **official MCP registry** (`server.json` + `mcp-publisher`)
for discovery, and optionally a `.mcpb` bundle for one-click Claude Desktop.

---

## 4. Sync with the `cchia-mcp` catalog repo (NOT yet created)

`cchia-mcp` mirrors the `cchia-skills` pattern: a catalog/distribution repo
(GitHub org `CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL`, slug `cchia-mcp`) that
makes MCP servers installable across any agentic framework. **Its first
available server is `grail`.** Canonical source stays here in the GRAIL repo;
cchia-mcp catalogs it and points at the published `graphgrail[mcp]` package.

Proposed layout (parallel to cchia-skills):

```
cchia-mcp/
├── README.md / README.en.md     # catalog table + per-framework install
├── CONTRIBUTING.md              # one PR = one server, bilingual
├── servers/
│   ├── _template/
│   └── grail/
│       ├── server.json          # MCP registry manifest (points at graphgrail[mcp])
│       └── README.md            # install snippets per framework + profiles
```

`servers/grail/server.json` (registry manifest — verify exact schema against
registry.modelcontextprotocol.io before publishing):

```json
{
  "name": "io.github.camara-chilena-inteligencia-artificial/grail",
  "description": "Queryable knowledge graphs + agentic memory over GRAIL.",
  "repository": { "url": "https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL", "source": "github" },
  "packages": [
    {
      "registry_type": "pypi",
      "identifier": "graphgrail",
      "version": "0.1.4",
      "transport": { "type": "stdio" },
      "runtime_hint": "uvx",
      "package_arguments": [{ "type": "named", "name": "--from", "value": "graphgrail[mcp]" }]
    }
  ]
}
```

**Sync checklist when this server changes:**
1. Bump `graphgrail` version on PyPI (the MCP server ships inside it).
2. Update `version` in `servers/grail/server.json` and re-`mcp-publisher publish`.
3. Keep the install snippets in cchia-mcp's `servers/grail/README.md` identical
   to the ones in GRAIL's `README.md` "MCP server" section and this doc.
4. If tools are added/removed/renamed, update the tool table in §2 and the
   cchia-mcp catalog description.

---

## 5. Verify

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[mcp]"
grail-mcp --version
python -c "from grail.mcp.server import build_server; import asyncio; \
print(len(asyncio.run(build_server(profile='all').list_tools())), 'tools')"
uv run pytest tests/unit/test_mcp_server.py -q
# Interactive: npx @modelcontextprotocol/inspector uvx --from "graphgrail[mcp]" grail-mcp --profile memory
```

---

## 6. Follow-ups / known gaps

1. **Docs-site pages** — add `docs-site/.../start/mcp-quickstart.mdx` (ES + EN
   i18n) mirroring `skill-quickstart.mdx`; add to the docs index/sidebar.
2. **Create the cchia-mcp repo** per §4 and publish `graphgrail[mcp]` so the
   `uvx` install line resolves from PyPI (it currently resolves only locally).
3. **`.mcpb` bundle** for one-click Claude Desktop (`@anthropic-ai/mcpb`).
4. **MCP resources** — expose community reports / the graph as read-only MCP
   *resources* (a fit MCP has and the skill doesn't).
5. **MCP prompt** — register a FastMCP `@mcp.prompt()` carrying the full
   search-mode routing guide, so clients can surface it on demand.
6. **kb_query on memory projects** — memory recall routes through
   `MemoryProject.recall` (zero-LLM, no grail.yaml needed); `kb_query` needs a
   grail.yaml. Document this split; consider a unified `grail_query` later.
