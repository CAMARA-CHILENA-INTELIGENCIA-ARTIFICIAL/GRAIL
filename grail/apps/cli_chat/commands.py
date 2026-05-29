"""
Slash command registry and dispatch for the GRAIL chat TUI.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from grail.apps.cli_chat.app import ChatApp

ALL_TOOLS = {"local_search", "cascade_search", "global_search", "document_search"}
VALID_MODES = {"agent", "local", "cascade", "global", "document"}


@dataclass
class Command:
    name: str
    description: str
    handler: Callable[["ChatApp", str], None]
    usage: str = ""


def cmd_help(app: "ChatApp", args: str) -> None:
    """List all slash commands."""
    lines = ["**Available commands:**", ""]
    for cmd in COMMANDS.values():
        usage = f" `{cmd.usage}`" if cmd.usage else ""
        lines.append(f"- `/{cmd.name}`{usage} — {cmd.description}")
    app.show_system_message("\n".join(lines))


def cmd_clear(app: "ChatApp", args: str) -> None:
    """Clear the conversation history visually (does not delete from DB)."""
    app.clear_chat_log()
    app.show_system_message("_Chat cleared._")


def cmd_new(app: "ChatApp", args: str) -> None:
    """Start a new session."""
    app.run_worker(app.action_new_session(), exclusive=True)


def cmd_sessions(app: "ChatApp", args: str) -> None:
    """List past chat sessions for this project."""
    app.run_worker(app.action_list_sessions(), exclusive=True)


def cmd_load(app: "ChatApp", args: str) -> None:
    """Alias of `/resume`."""
    cmd_resume(app, args)


def cmd_resume(app: "ChatApp", args: str) -> None:
    """List past chats (no arg) or resume one by id prefix."""
    app.run_worker(app.action_resume(args), exclusive=True)


def cmd_mode(app: "ChatApp", args: str) -> None:
    """Change search mode for the next message."""
    mode = args.strip().lower()
    if not mode:
        app.show_system_message(f"Current mode: **{app.search_mode}**. Use `/mode <name>` to change.")
        return
    if mode not in VALID_MODES:
        app.show_system_message(
            f"Unknown mode `{mode}`. Valid: {', '.join(sorted(VALID_MODES))}"
        )
        return
    app.search_mode = mode
    app.refresh_status()
    app.show_system_message(f"Mode set to **{mode}**.")


def cmd_tools(app: "ChatApp", args: str) -> None:
    """Show currently enabled agent tools."""
    enabled = sorted(app.enabled_tools)
    disabled = sorted(ALL_TOOLS - app.enabled_tools)
    lines = ["**Agent tools:**", ""]
    for tool in sorted(ALL_TOOLS):
        marker = "✓" if tool in app.enabled_tools else "✗"
        color = "green" if tool in app.enabled_tools else "red"
        lines.append(f"- {tool}: <span style='color:{color}'>{marker}</span>")
    lines.append("")
    lines.append("Use `/disable <tool>` or `/enable <tool>` to toggle.")
    app.show_system_message("\n".join(lines))


def cmd_enable(app: "ChatApp", args: str) -> None:
    """Enable an agent tool."""
    tool = args.strip()
    if tool not in ALL_TOOLS:
        app.show_system_message(f"Unknown tool `{tool}`. Valid: {', '.join(sorted(ALL_TOOLS))}")
        return
    app.enabled_tools.add(tool)
    app.refresh_status()
    app.show_system_message(f"Enabled **{tool}**.")


def cmd_disable(app: "ChatApp", args: str) -> None:
    """Disable an agent tool."""
    tool = args.strip()
    if tool not in ALL_TOOLS:
        app.show_system_message(f"Unknown tool `{tool}`. Valid: {', '.join(sorted(ALL_TOOLS))}")
        return
    if len(app.enabled_tools) == 1 and tool in app.enabled_tools:
        app.show_system_message(f"Cannot disable the last enabled tool.")
        return
    app.enabled_tools.discard(tool)
    app.refresh_status()
    app.show_system_message(f"Disabled **{tool}**.")


def cmd_cost(app: "ChatApp", args: str) -> None:
    """Show cumulative LLM cost since chat start."""
    grail = app.grail
    if grail is None or not grail.cost_tracker.records:
        app.show_system_message("No LLM calls yet.")
        return
    total = grail.cost_tracker.render_total_cost()
    n_calls = len(grail.cost_tracker.records)
    app.show_system_message(f"**Cost so far:** {total} across {n_calls} LLM calls.")


def cmd_sources(app: "ChatApp", args: str) -> None:
    """Show sources from the last assistant response."""
    if not app.last_sources:
        app.show_system_message("No sources available — send a message first.")
        return
    lines = ["**Sources from last response:**", ""]
    for s in app.last_sources:
        title = s.get("title", "?")
        path = s.get("path", "")
        lines.append(f"- **{title}** — `{path}`")
    app.show_system_message("\n".join(lines))


def cmd_quit(app: "ChatApp", args: str) -> None:
    """Exit the chat."""
    app.exit()


COMMANDS: dict[str, Command] = {
    "help": Command("help", "Show this help text.", cmd_help),
    "clear": Command("clear", "Clear the on-screen chat (DB history kept).", cmd_clear),
    "new": Command("new", "Start a new chat session.", cmd_new),
    "sessions": Command("sessions", "List past sessions for this project.", cmd_sessions),
    "load": Command("load", "Alias of /resume.", cmd_load, "/load <session_id>"),
    "resume": Command(
        "resume",
        "List past chats, or resume one by id prefix.",
        cmd_resume,
        "/resume [session_id]",
    ),
    "mode": Command("mode", "Change search mode for next message.", cmd_mode, "/mode <name>"),
    "tools": Command("tools", "Show agent tools (enabled/disabled).", cmd_tools),
    "enable": Command("enable", "Enable an agent tool.", cmd_enable, "/enable <tool>"),
    "disable": Command("disable", "Disable an agent tool.", cmd_disable, "/disable <tool>"),
    "cost": Command("cost", "Show cumulative LLM cost.", cmd_cost),
    "sources": Command("sources", "Show sources from last response.", cmd_sources),
    "quit": Command("quit", "Exit the chat.", cmd_quit),
    "exit": Command("exit", "Exit the chat.", cmd_quit),
}


def dispatch(app: "ChatApp", input_text: str) -> bool:
    """Try to dispatch a slash command. Returns True if handled."""
    if not input_text.startswith("/"):
        return False
    parts = input_text[1:].split(None, 1)
    if not parts:
        return False
    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    if name not in COMMANDS:
        app.show_system_message(f"Unknown command `/{name}`. Try `/help`.")
        return True
    COMMANDS[name].handler(app, args)
    return True
