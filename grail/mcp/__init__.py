"""
GRAIL MCP server — expose GRAIL as Model Context Protocol tools.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This is the *reach* layer that complements the agent skill (``skills/grail/``).
The skill is the primary surface for shell-capable coding agents (it carries
GRAIL's routing/judgement guidance as on-demand instructions); this MCP server
exposes the same operations as typed tools so GRAIL is attachable from any MCP
client — Claude Desktop, Cursor, Cline, hosted services, and other frameworks —
without a Python harness on the client side.

Both surfaces are thin wrappers over the same core (``GRAIL`` / ``MemoryProject``)
and return the same ``Reply(ok, data, warnings, next_steps, error)`` shape.

Entry point: ``grail-mcp`` (see ``[project.scripts]`` in ``pyproject.toml``).
Run with ``--profile kb|memory|all`` to pick the toolset.
"""
from grail.mcp.server import build_server, main

__all__ = ["build_server", "main"]
