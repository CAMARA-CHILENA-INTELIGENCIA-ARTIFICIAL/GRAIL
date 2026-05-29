"""
Textual widgets for the GRAIL chat TUI.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import json
from typing import Any

from rich.markdown import Markdown
from rich.text import Text
from textual import events
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Collapsible, Input, Markdown as MarkdownWidget, Static


class ChatLog(VerticalScroll):
    """VerticalScroll with optional logging for every mouse event we trace.

    Used as the conversation container.  When ``GRAIL_CHAT_DEBUG`` is set,
    scroll-related events are written to ``/tmp/grail_chat_mouse.log`` so
    we can confirm whether wheel reports actually reach the scrollable
    widget at the framework level (vs only the App-level handler).
    When the env var is unset, ``_log`` short-circuits — no I/O, no
    string formatting.
    """

    def _log(self, where: str, event) -> None:
        import logging
        logger = logging.getLogger("grail.cli_chat.mouse")
        if not logger.handlers:
            return  # debug logging off — skip all work
        attrs = []
        for a in ("x", "y", "button", "delta_x", "delta_y", "ctrl", "shift"):
            if hasattr(event, a):
                attrs.append(f"{a}={getattr(event, a)}")
        try:
            sy = round(self.scroll_y, 1)
            my = round(self.max_scroll_y, 1)
        except Exception:
            sy = my = "?"
        logger.debug(
            f"[{where:>20}] {type(event).__name__:<22} {' '.join(attrs):<60} "
            f"on=ChatLog scroll={sy}/{my}"
        )

    # NOTE: Widget._on_mouse_scroll_{down,up} are *sync* (return None).
    # We must match that signature — making these `async def` and then
    # `await super()` would raise "object NoneType can't be used in 'await'".
    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._log("ChatLog._scroll_dn", event)
        super()._on_mouse_scroll_down(event)
        import logging
        logging.getLogger("grail.cli_chat.mouse").debug(
            f"[ChatLog._scroll_dn] after super: scroll_y={round(self.scroll_y, 1)}"
        )

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._log("ChatLog._scroll_up", event)
        super()._on_mouse_scroll_up(event)
        import logging
        logging.getLogger("grail.cli_chat.mouse").debug(
            f"[ChatLog._scroll_up] after super: scroll_y={round(self.scroll_y, 1)}"
        )

    async def _on_mouse_down(self, event: events.MouseDown) -> None:
        self._log("ChatLog._mouse_dn", event)
        await super()._on_mouse_down(event)

    async def _on_mouse_up(self, event: events.MouseUp) -> None:
        self._log("ChatLog._mouse_up", event)
        await super()._on_mouse_up(event)

    # Drag detection: we use the public `on_mouse_move` hook (which Textual
    # dispatches through `on_event`) rather than overriding `_on_mouse_move`,
    # because `Widget` does not define a private `_on_mouse_move` — calling
    # `super()._on_mouse_move()` would AttributeError.
    def on_mouse_move(self, event: events.MouseMove) -> None:
        # Only log drag motions; logging every move floods the file.
        if getattr(event, "button", 0):
            self._log("ChatLog.on_mouse_mv(drag)", event)


def _file_icon(filename: str) -> str:
    """Return a colored emoji-free single-glyph icon for a file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("pdf",):
        return "📕"
    if ext in ("docx", "doc"):
        return "📘"
    if ext in ("xlsx", "xls", "csv", "tsv"):
        return "📗"
    if ext in ("py", "js", "ts", "json", "yaml", "yml", "toml", "xml", "html"):
        return "📜"
    if ext in ("png", "jpg", "jpeg", "gif", "svg", "webp"):
        return "🖼️"
    if ext in ("md", "markdown", "rst", "txt", "log"):
        return "📄"
    return "📎"


class ChatInput(Input):
    """Input subclass for the GRAIL chat TUI.

    Two extras over Textual's stock Input:

    1. **Forwards wheel events** received while the cursor is over the
       Input to a scroll target (the chat log) — convenience.

    2. **Suppresses the ``app.cursor_position`` update** that Textual's
       ``Input._watch_selection`` performs on every cursor movement.

       Background: Textual moves the *terminal* cursor to follow the
       Input's text cursor (so blinking-cursor terminals show the
       insertion point).  In Warp, the row containing the terminal
       cursor is treated as the active input prompt, and Warp filters
       mouse events for that area — wheel, click, and drag never reach
       the TUI.  When focus moves elsewhere (e.g. user presses Esc),
       Textual stops repositioning the cursor and Warp's filter
       releases — which is why "the wheel works after Esc" in Warp.

       Skipping the cursor_position update keeps the terminal cursor
       parked outside the Input region, so Warp sees the Input row as
       normal TUI content and forwards wheel events to it.  Textual's
       Input still renders its own visual cursor via the
       ``input--cursor`` CSS class (a styled span), independent of the
       terminal cursor — so visual feedback while typing is unchanged.

       In iTerm2 / Alacritty / kitty this override has no behavioral
       impact: those terminals route mouse by cursor position, not by
       terminal-cursor position.
    """

    def __init__(self, *args, scroll_target=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._scroll_target = scroll_target

    def set_scroll_target(self, widget) -> None:
        self._scroll_target = widget

    def _watch_selection(self, selection) -> None:
        """Override Textual's selection watcher to skip cursor positioning.

        Replicates ``Input._watch_selection`` *except* for the line that
        sets ``self.app.cursor_position`` — see the class docstring for
        why this matters in Warp.  Other side-effects (selection clear,
        scroll-to-cursor for long inputs) are preserved.
        """
        from textual.geometry import Region
        try:
            self.app.clear_selection()
        except Exception:
            pass
        # SKIP: self.app.cursor_position = self.cursor_screen_offset
        # That line is what Warp latches onto.  Keep the cursor parked
        # at (0, 0) so Warp doesn't see the Input row as a prompt.
        if not getattr(self, "_initial_value", False):
            try:
                self.scroll_to_region(
                    Region(self._cursor_offset, 0, width=1, height=1),
                    force=True,
                    animate=False,
                )
            except Exception:
                pass

    def _log(self, where: str, event) -> None:
        import logging
        logger = logging.getLogger("grail.cli_chat.mouse")
        if not logger.handlers:
            return  # debug logging off — skip all work
        attrs = []
        for a in ("x", "y", "button", "delta_x", "delta_y", "ctrl", "shift"):
            if hasattr(event, a):
                attrs.append(f"{a}={getattr(event, a)}")
        logger.debug(
            f"[{where:>20}] {type(event).__name__:<22} {' '.join(attrs):<60} "
            f"on=ChatInput"
        )

    # Sync to match Widget._on_mouse_scroll_{down,up} signature.
    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._log("ChatInput._scroll_dn", event)
        if self._scroll_target is not None:
            before = self._scroll_target.scroll_y
            self._scroll_target.scroll_down(animate=False)
            after = self._scroll_target.scroll_y
            import logging
            logging.getLogger("grail.cli_chat.mouse").debug(
                f"[ChatInput._scroll_dn] forwarded scroll {before} → {after}"
            )
            event.stop()
            event.prevent_default()

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._log("ChatInput._scroll_up", event)
        if self._scroll_target is not None:
            before = self._scroll_target.scroll_y
            self._scroll_target.scroll_up(animate=False)
            after = self._scroll_target.scroll_y
            import logging
            logging.getLogger("grail.cli_chat.mouse").debug(
                f"[ChatInput._scroll_up] forwarded scroll {before} → {after}"
            )
            event.stop()
            event.prevent_default()

    async def _on_mouse_down(self, event: events.MouseDown) -> None:
        self._log("ChatInput._mouse_dn", event)
        await super()._on_mouse_down(event)


# ---------------------------------------------------------------------------
# GrailLogo — compact 2-line ASCII brand mark for the top of the chat TUI.
# ---------------------------------------------------------------------------

# Two-line block-letter GRAIL, designed to be slim and recognizable.
# Each glyph uses Unicode half-block characters (▀ ▄ █) so we cram the brand
# into 2 terminal rows while keeping the block-letter aesthetic of the full
# 6-row banner used by `grail index`, `grail query`, etc.
_GRAIL_LOGO_LINES: tuple[str, str] = (
    "█▀▀ █▀█ █▀█ █ █    ",
    "█▄█ █▀▄ █▀█ █ █▄▄  ",
)

# Same teal gradient as the splash banner in `grail/cli/banner.py`.
_LOGO_GRADIENT: tuple[str, str] = ("#5eead4", "#14b8a6")


class GrailLogo(Static):
    """A compact gradient-coloured GRAIL logo for the top of the chat TUI.

    Two rows tall.  Render renders each row in its own gradient shade so
    the logo has a subtle vertical fade matching the full-size banner.
    Sits above the status bar; total header height is therefore 3 rows
    (2 logo + 1 status bar).
    """

    DEFAULT_CSS = """
    GrailLogo {
        height: 2;
        padding: 0 2;
        background: transparent;
    }
    """

    def render(self) -> Text:
        t = Text(no_wrap=True, overflow="ellipsis")
        for i, line in enumerate(_GRAIL_LOGO_LINES):
            t.append(line, style=f"bold {_LOGO_GRADIENT[i]}")
            t.append("  ")
            if i == 0:
                t.append("Graph RAG with Advanced Integration and Learning",
                         style="dim")
            if i < len(_GRAIL_LOGO_LINES) - 1:
                t.append("\n")
        return t


class UserBubble(Static):
    """A user message bubble — right-aligned, teal accent."""

    DEFAULT_CSS = """
    UserBubble {
        margin: 1 0 0 0;
        padding: 0 2;
        color: $text;
    }
    UserBubble > .user-label {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def render(self) -> Text:
        t = Text()
        t.append("❯ you  ", style="bold #14b8a6")
        t.append(self._content)
        return t


class AssistantBubble(Vertical):
    """An assistant message bubble — left-aligned, supports streaming updates."""

    DEFAULT_CSS = """
    AssistantBubble {
        margin: 1 0 0 0;
        padding: 0 2;
        height: auto;
    }
    AssistantBubble > .assistant-label {
        color: $accent;
        text-style: bold;
        margin-bottom: 0;
    }
    AssistantBubble > MarkdownWidget {
        margin: 0;
        padding: 0;
        background: transparent;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._buffer = ""
        self._md_widget: MarkdownWidget | None = None
        self._label: Static | None = None

    def compose(self):
        self._label = Static(Text("✦ grail", style="bold #14b8a6"), classes="assistant-label")
        yield self._label
        self._md_widget = MarkdownWidget("")
        yield self._md_widget

    def append_token(self, token: str) -> None:
        """Append a streaming token and re-render the markdown."""
        self._buffer += token
        if self._md_widget is not None:
            self._md_widget.update(self._buffer)

    def set_content(self, content: str) -> None:
        """Replace the full content."""
        self._buffer = content
        if self._md_widget is not None:
            self._md_widget.update(content)

    def get_content(self) -> str:
        return self._buffer


class ToolCallCard(Collapsible):
    """A collapsible card for an agent tool call.

    Shows a one-line summary by default.  Expanding reveals the full
    arguments, status log, and result preview.
    """

    DEFAULT_CSS = """
    ToolCallCard {
        margin: 1 2 0 4;
        background: $surface;
        border-left: thick $accent 40%;
    }
    ToolCallCard CollapsibleTitle {
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    ToolCallCard .tool-args, ToolCallCard .tool-status, ToolCallCard .tool-result {
        margin: 0 0 0 2;
        color: $text-muted;
    }
    """

    def __init__(self, tool_name: str, args: dict[str, Any]) -> None:
        self._tool_name = tool_name
        self._args = args
        self._status_lines: list[str] = []
        self._result_summary = ""
        self._done = False
        self._error = False
        super().__init__(title=self._compose_title(), collapsed=True)

    def _compose_title(self) -> str:
        icon = "▣" if not self._done else ("✗" if self._error else "✓")
        color = "yellow" if not self._done else ("red" if self._error else "green")
        query_preview = ""
        if "query" in self._args:
            q = str(self._args["query"])
            if len(q) > 50:
                q = q[:47] + "…"
            query_preview = f' "{q}"'
        suffix = f"  •  {self._result_summary}" if self._result_summary else "  •  running…"
        return f"[{color}]{icon}[/{color}] [bold]{self._tool_name}[/bold]{query_preview}{suffix}"

    def compose(self):
        yield Static(self._render_args(), classes="tool-args")
        self._status_widget = Static("", classes="tool-status")
        yield self._status_widget
        self._result_widget = Static("", classes="tool-result")
        yield self._result_widget

    def _render_args(self) -> Text:
        t = Text()
        t.append("  args: ", style="dim")
        formatted = ", ".join(f"{k}={json.dumps(v)}" for k, v in self._args.items())
        t.append(formatted)
        return t

    def add_status(self, level: str, message: str) -> None:
        symbol = {"info": "·", "success": "✓", "warning": "⚠", "error": "✗", "debug": "·"}.get(
            level, "·"
        )
        color = {
            "info": "dim",
            "success": "green",
            "warning": "yellow",
            "error": "red",
            "debug": "dim",
        }.get(level, "dim")
        self._status_lines.append(f"[{color}]{symbol}[/{color}] {message}")
        if hasattr(self, "_status_widget"):
            self._status_widget.update("\n".join(self._status_lines))

    def mark_done(self, summary: str, error: bool = False) -> None:
        self._result_summary = summary
        self._done = True
        self._error = error
        self.title = self._compose_title()


class StatusBar(Static):
    """Top status bar showing project, mode, enabled tools, cost."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.project_name = ""
        self.mode = "agent"
        self.cost = "—"
        self.enabled_tools: set[str] = set()
        self.last_mouse: str = ""

    def render(self) -> Text:
        t = Text()
        t.append("GRAIL ", style="bold #14b8a6")
        t.append("· ")
        t.append(self.project_name, style="bold")
        t.append("  ·  mode: ")
        t.append(self.mode, style="cyan")
        if self.mode == "agent" and self.enabled_tools:
            tool_short = {"local_search": "L", "cascade_search": "C", "global_search": "G", "document_search": "D"}
            indicators = " ".join(
                f"[green]{tool_short.get(t, t[0])}[/green]" if t in self.enabled_tools else f"[dim]{tool_short.get(t, t[0])}[/dim]"
                for t in ["local_search", "cascade_search", "global_search", "document_search"]
            )
            t.append("  tools: ")
            t.append_text(Text.from_markup(indicators))
        t.append(f"  ·  cost: ")
        t.append(self.cost, style="dim")
        # Mouse activity indicator — proves whether the terminal sends events.
        if self.last_mouse:
            t.append("  ·  mouse: ")
            t.append(self.last_mouse, style="green")
        else:
            t.append("  ·  mouse: ")
            t.append("off", style="red")
        return t


class SourcesPanel(Static):
    """Bottom panel showing source documents from the last assistant message."""

    DEFAULT_CSS = """
    SourcesPanel {
        height: auto;
        max-height: 3;
        background: $boost;
        color: $text;
        padding: 0 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.sources: list[dict[str, str]] = []

    def set_sources(self, sources: list[dict[str, str]]) -> None:
        self.sources = sources or []
        self.refresh()

    def render(self) -> Text:
        if not self.sources:
            return Text("sources: —", style="dim")
        t = Text()
        t.append("sources: ", style="dim")
        for i, s in enumerate(self.sources):
            if i > 0:
                t.append("  ")
            icon = _file_icon(s.get("title", ""))
            t.append(f"{icon} ")
            t.append(s.get("title", "?"), style="cyan")
        return t
