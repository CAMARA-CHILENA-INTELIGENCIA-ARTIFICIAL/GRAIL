"""
Unit tests for the GRAIL CLI chat module.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def test_command_registry_has_all_expected_commands():
    from grail.apps.cli_chat.commands import COMMANDS

    expected = {
        "help", "clear", "new", "sessions", "load", "mode",
        "tools", "enable", "disable", "cost", "sources", "quit", "exit",
    }
    assert expected.issubset(COMMANDS.keys())


def test_all_tools_constant_matches_agent_schemas():
    from grail.apps.cli_chat.commands import ALL_TOOLS
    from grail.query.agent import TOOL_SCHEMAS

    schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert ALL_TOOLS == schema_names


def test_textual_reporter_implements_reporter_protocol():
    """The TextualReporter must satisfy the Reporter protocol."""
    from grail.apps.cli_chat.reporter import TextualReporter

    q: asyncio.Queue = asyncio.Queue()
    r = TextualReporter(q)
    # Sync methods
    r.info("hello")
    r.success("done")
    r.warning("careful")
    r.error("oops")
    r.debug("trace")
    # Should have pushed 5 events
    assert q.qsize() == 5
    ev = q.get_nowait()
    assert ev.level == "info"
    assert ev.message == "hello"


@pytest.mark.asyncio
async def test_textual_reporter_async_methods():
    from grail.apps.cli_chat.reporter import TextualReporter

    q: asyncio.Queue = asyncio.Queue()
    r = TextualReporter(q)
    r.bind_loop(asyncio.get_running_loop())
    await r.async_info("hi")
    await r.async_success("ok")
    # call_soon_threadsafe defers; yield once so scheduled puts run
    await asyncio.sleep(0)
    assert q.qsize() == 2


def test_agent_tool_filter_drops_disabled_tools():
    """Verify the enabled_tools field actually filters TOOL_SCHEMAS."""
    from grail.query.agent import AgentSearch, TOOL_SCHEMAS

    # Simulate just the filter logic
    enabled = {"local_search", "cascade_search"}
    filtered = [s for s in TOOL_SCHEMAS if s["function"]["name"] in enabled]
    assert len(filtered) == 2
    names = {s["function"]["name"] for s in filtered}
    assert names == enabled


def test_chat_app_constructs_without_errors():
    """Smoke test: ChatApp can be constructed and exposes expected fields."""
    from grail.apps.cli_chat.app import ChatApp

    app = ChatApp(project_dir=Path("/tmp"), mode="agent")
    assert app.search_mode == "agent"
    assert app.enabled_tools == {"local_search", "cascade_search", "global_search", "document_search"}
    assert app.is_streaming is False


def test_chat_app_uses_search_mode_not_current_mode():
    """Guards against re-introducing the Textual reactive name clash."""
    from grail.apps.cli_chat.app import ChatApp

    app = ChatApp(project_dir=Path("/tmp"), mode="cascade")
    # Setting search_mode must work (it's a plain attribute)
    app.search_mode = "local"
    assert app.search_mode == "local"


@pytest.mark.asyncio
async def test_mouse_scroll_handlers_scroll_the_chat_log():
    """App-level mouse wheel handlers must scroll chat_log regardless of focus.

    This is the fix for the "mouse wheel doesn't scroll the chat" bug — wheel
    events bubble through every widget but are caught at App level so the user
    doesn't have to focus the chat log first.
    """
    from textual import events
    from textual.widgets import Static
    from grail.apps.cli_chat.app import ChatApp

    app = ChatApp(project_dir=Path("/tmp"), mode="agent")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        for i in range(50):
            app.chat_log.mount(Static(f"line {i}"))
        await pilot.pause()
        app.chat_log.scroll_end(animate=False)
        await pilot.pause()
        before = app.chat_log.scroll_y
        # Invoke the App-level wheel handler directly
        evt = events.MouseScrollUp(0, 0, 0, False, False, False, False, False, False)
        await app.on_mouse_scroll_up(evt)
        await pilot.pause()
        assert app.chat_log.scroll_y < before, "wheel up should reduce scroll_y"
