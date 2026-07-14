"""Tests for the GRAIL MCP server.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import asyncio

import pytest

mcp = pytest.importorskip("mcp", reason="MCP extra not installed")

from grail.mcp.server import build_server  # noqa: E402


def _tool_names(profile: str) -> set[str]:
    server = build_server(profile=profile)
    return {t.name for t in asyncio.run(server.list_tools())}


def test_profiles_register_expected_toolsets():
    shared = {"grail_list_projects", "grail_status"}
    memory = _tool_names("memory")
    kb = _tool_names("kb")
    allp = _tool_names("all")

    assert shared <= memory and shared <= kb
    assert "memory_add_observation" in memory and "memory_recall" in memory
    assert "kb_index" in kb and "kb_query" in kb
    # Profiles are disjoint apart from the shared pair.
    assert "kb_index" not in memory
    assert "memory_add_observation" not in kb
    assert allp == memory | kb


async def _call(server, name, args):
    res = await server.call_tool(name, args)
    return res[1] if isinstance(res, tuple) and len(res) > 1 else res


def test_memory_roundtrip(tmp_path):
    """create_project -> add_observation -> recall -> status through call_tool."""
    server = build_server(profile="memory")
    proj = str(tmp_path / "mem")

    async def scenario():
        created = await _call(server, "memory_create_project", {"name": proj})
        assert created["ok"] is True
        assert created["mode"] == "memory"

        added = await _call(
            server,
            "memory_add_observation",
            {
                "project": proj,
                "title": "Acme chose Postgres",
                "content": "Acme picked Postgres over DynamoDB for billing.",
                "category": "work/clients/acme",
                "tags": ["decision"],
                "entities": [
                    {"name": "Acme", "type": "ORGANIZATION"},
                    {"name": "Postgres", "type": "TECHNOLOGY"},
                ],
                "relationships": [
                    {"source": "Acme", "target": "Postgres", "relationship_type": "CHOSE"}
                ],
            },
        )
        assert added["ok"] is True
        assert "slug" in added["data"]

        recalled = await _call(server, "memory_recall", {"project": proj, "tags": ["decision"]})
        assert recalled["ok"] is True
        assert len(recalled["data"]["observations"]) == 1

        status = await _call(server, "grail_status", {"project": proj})
        assert status["ok"] is True
        assert status["data"]["observations"] == 1

    asyncio.run(scenario())


def test_unknown_project_does_not_silently_succeed():
    server = build_server(profile="memory")

    async def scenario():
        # Resolution failure must surface — either as a raised tool error or an
        # ``ok: False`` envelope, never a silent success.
        try:
            res = await _call(server, "memory_recall", {"project": "does-not-exist-xyz"})
        except Exception:  # noqa: BLE001 - any failure mode is acceptable here
            return
        assert res.get("ok") is False

    asyncio.run(scenario())
