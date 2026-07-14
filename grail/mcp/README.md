# GRAIL MCP server

Exposes GRAIL as **Model Context Protocol** tools so it's attachable from any
MCP client — Claude Desktop, Cursor, Cline, hosted services, other frameworks —
with no Python harness on the client side.

This is the **reach** layer. The [agent skill](../../skills/grail/) is the
primary surface for shell-capable coding agents (it carries GRAIL's routing
guidance as on-demand instructions). Both wrap the same core and return the same
`{ok, data, warnings, next_steps, error}` envelope. See the full design and
cchia-mcp sync spec in [`dev_prompts/prompt_grail_mcp.md`](../../dev_prompts/prompt_grail_mcp.md).

## Install & run

```bash
pip install "graphgrail[mcp]"     # adds the `mcp` SDK + the `grail-mcp` binary

grail-mcp --profile memory        # agentic-memory tools
grail-mcp --profile kb            # knowledge-base tools
grail-mcp --profile all           # everything (default)
```

Attach it (zero-install, any MCP client):

```bash
# Claude Code
claude mcp add grail-memory -- uvx --from "graphgrail[mcp]" grail-mcp --profile memory
```

```jsonc
// Generic mcpServers config (Claude Desktop, Cursor, Cline, Windsurf, …)
{
  "mcpServers": {
    "grail-memory": {
      "command": "uvx",
      "args": ["--from", "graphgrail[mcp]", "grail-mcp", "--profile", "memory"]
    }
  }
}
```

## Flags

| Flag | Default | Purpose |
|---|---|---|
| `--profile {kb,memory,all}` | auto from `--project`, else `all` | Which toolset to expose. |
| `--project <ref>` | — | Bind to one project (path/name/id); tools default to it and the profile auto-selects from its mode. |
| `--transport {stdio,streamable-http}` | `stdio` | Local (stdio) or remote (HTTP). |
| `--port <n>` | `8000` | Port for `streamable-http`. |

## Tools

- **Shared:** `grail_list_projects`, `grail_status`.
- **memory:** `memory_create_project`, `memory_add_observation`, `memory_add_entity`,
  `memory_add_relationship`, `memory_add_community`, `memory_find_similar_entity`,
  `memory_recall`, `memory_list_{observations,entities,categories,communities}`,
  `memory_consolidate`, `memory_list_proposals`, `memory_apply_proposal`.
- **kb:** `kb_create_project`, `kb_index`, `kb_append`, `kb_edit`, `kb_delete`, `kb_query`.

## Develop

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[mcp,dev]"
python -m pytest tests/unit/test_mcp_server.py -q
# Interactive inspector:
npx @modelcontextprotocol/inspector uvx --from "graphgrail[mcp]" grail-mcp --profile memory
```
