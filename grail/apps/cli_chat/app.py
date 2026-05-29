"""
GRAIL chat — Textual app.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Interactive terminal chat with streaming responses, tool call rendering,
slash commands, and session persistence.  Reuses the SQLite session DB
from the web app (with a ``source='cli'`` filter so the two surfaces
don't mix).
"""
from __future__ import annotations

import asyncio
import getpass
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Markdown as MarkdownWidget, Static
from textual.widgets import Input  # noqa: F401  — used by isinstance & on_input_submitted signature

from grail.apps.cli_chat.commands import ALL_TOOLS, dispatch
from grail.apps.cli_chat.reporter import ReporterEvent, TextualReporter
from grail.apps.cli_chat.widgets import (
    AssistantBubble,
    ChatInput,
    ChatLog,
    GrailLogo,
    SourcesPanel,
    StatusBar,
    ToolCallCard,
    UserBubble,
)
from grail.apps.chat.database import (
    configure_db_path,
    create_message,
    create_messages_batch,
    create_session,
    create_user,
    get_messages,
    get_session,
    get_user_by_username,
    init_db,
    list_sessions,
    update_session,
)
from grail.config import Config, load_config
from grail.core import GRAIL

log = logging.getLogger("grail.cli_chat")

CLI_USER_SENTINEL_HASH = "__cli_user_no_login__"

# Optional event-flow log for diagnosing terminal mouse / focus issues.
#
# Disabled by default — logging is a no-op unless the environment variable
# ``GRAIL_CHAT_DEBUG`` is set to a truthy value when ``grail chat`` runs.
# When enabled, mouse / focus / key events are written to
# ``/tmp/grail_chat_mouse.log`` (truncated on every launch).
#
# History: this instrumentation was added while diagnosing why mouse-wheel
# scrolling didn't work in Warp.  Root cause turned out to be Warp's
# input-position filter combined with Textual's per-keystroke
# ``app.cursor_position`` updates from ``Input._watch_selection`` — see
# ``docs/cli_chat.md`` for the full story.
_MOUSE_LOG_PATH = Path("/tmp") / "grail_chat_mouse.log"
_mouse_logger = logging.getLogger("grail.cli_chat.mouse")
_mouse_logger.setLevel(logging.DEBUG)
_mouse_logger.propagate = False


def _debug_enabled() -> bool:
    """True iff event-flow logging is requested via env var."""
    val = os.environ.get("GRAIL_CHAT_DEBUG", "").strip().lower()
    return val not in ("", "0", "false", "no", "off")


def _reset_event_log() -> None:
    """Truncate and reattach the event log if debug mode is enabled.

    Always called from :func:`run_chat`; quick-exits without touching the
    filesystem when ``GRAIL_CHAT_DEBUG`` is unset.  Keeps the production
    path zero-overhead.
    """
    # Tear down any pre-existing handlers either way so we never leak file
    # descriptors between invocations in the same process.
    for h in list(_mouse_logger.handlers):
        try:
            h.flush()
            h.close()
        except Exception:
            pass
        _mouse_logger.removeHandler(h)

    if not _debug_enabled():
        # No handlers attached → every _mouse_logger.debug() call is a
        # cheap no-op (the logger's handler list is empty).
        return

    try:
        _MOUSE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MOUSE_LOG_PATH.write_text("")
        handler = logging.FileHandler(_MOUSE_LOG_PATH, mode="w")
        handler.setFormatter(
            logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S")
        )
        _mouse_logger.addHandler(handler)
        import datetime as _dt
        _mouse_logger.debug(
            f"=== grail chat session started {_dt.datetime.now().isoformat(timespec='seconds')} "
            f"→ {_MOUSE_LOG_PATH} ==="
        )
        _mouse_logger.debug(
            "Columns: [phase] EventType  attrs  target=W  focused=F  hover=H  scroll_y=Y/MaxY"
        )
    except Exception:
        pass


class ChatApp(App):
    """The GRAIL CLI chat application."""

    CSS = """
    Screen {
        background: $background;
        layout: vertical;
    }
    #chat_log {
        height: 1fr;
        padding: 0 1;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 2;
        scrollbar-background: $background;
        scrollbar-background-hover: $boost;
        scrollbar-background-active: $boost;
        scrollbar-color: $accent 50%;
        scrollbar-color-hover: $accent 80%;
        scrollbar-color-active: $accent;
    }
    #chat_log > * {
        height: auto;
    }
    #chat_log:focus {
        background: $background;
    }
    Input {
        border: round $accent 50%;
        margin: 1 2;
    }
    Input:focus {
        border: round $accent;
    }
    .system-message {
        margin: 1 2;
        padding: 0 1;
        color: $text-muted;
        background: $boost;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        # Focus toggle — both Esc and Tab are visible in the footer so users
        # who scrolled with the wheel know how to get back to the input.
        Binding("escape", "focus_chat_log", "Scroll mode", show=True, priority=True),
        Binding("tab", "toggle_focus", "Focus input ⇄ chat", show=True, priority=False),
        # Scroll bindings — priority=True so they fire even when Input has focus.
        Binding("pageup", "scroll_page_up", "Scroll ↑", show=True, priority=True),
        Binding("pagedown", "scroll_page_down", "Scroll ↓", show=True, priority=True),
        Binding("shift+up", "scroll_up", "Up", show=False, priority=True),
        Binding("shift+down", "scroll_down", "Down", show=False, priority=True),
        Binding("ctrl+home", "scroll_top", "Top", show=False, priority=True),
        Binding("ctrl+end", "scroll_bottom", "Bottom", show=False, priority=True),
    ]

    def __init__(
        self,
        project_dir: Path,
        mode: str = "agent",
        session_id: Optional[str] = None,
        db_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.project_dir = project_dir.resolve()
        self.search_mode = mode
        self.initial_session_id = session_id
        self.db_path = db_path or (self.project_dir / ".grail" / "chat.db")
        self.enabled_tools: set[str] = set(ALL_TOOLS)
        self.grail: GRAIL | None = None
        self.user_id: str = ""
        self.active_session_id: str = ""
        self.active_session_title: str = "New Chat"
        self.last_sources: list[dict[str, str]] = []
        self.is_streaming = False
        self._reporter_queue: asyncio.Queue = asyncio.Queue()
        self._token_queue: asyncio.Queue = asyncio.Queue()
        self._active_tool_card: ToolCallCard | None = None
        self._active_assistant: AssistantBubble | None = None
        self._reporter = TextualReporter(self._reporter_queue)
        # Mouse-event counters — used to detect terminals that swallow wheel/click.
        self._mouse_move_count = 0
        self._mouse_click_count = 0
        self._mouse_wheel_count = 0

    # ================================================================ compose

    def compose(self) -> ComposeResult:
        # Plain vertical layout (no docking) so mouse events route cleanly to
        # whichever widget is under the cursor.
        # 2-line gradient GRAIL logo, then the 1-line status bar.
        yield GrailLogo()
        self.status_bar = StatusBar()
        self.status_bar.project_name = self.project_dir.name
        self.status_bar.mode = self.search_mode
        self.status_bar.enabled_tools = self.enabled_tools
        yield self.status_bar

        self.chat_log = ChatLog(id="chat_log")
        self.chat_log.can_focus = True
        yield self.chat_log

        self.sources_panel = SourcesPanel()
        yield self.sources_panel

        # select_on_focus=False so that when the auto-refocus hook moves
        # focus back to the input (after the user typed in scroll mode),
        # the freshly-appended characters aren't selected and replaced by
        # the next keystroke.
        self.input = ChatInput(
            placeholder="Ask anything…  (type /help for commands)",
            scroll_target=self.chat_log,
            select_on_focus=False,
        )
        yield self.input

    # ================================================================ event logging

    def _bump_mouse_indicator(self, kind: str) -> None:
        """Mark in the status bar that a mouse event was received."""
        self.status_bar.last_mouse = kind
        self.status_bar.refresh()

    def _widget_under_cursor_name(self) -> str:
        """Return the class name of the widget under the current mouse position."""
        try:
            screen = self.screen
            if screen is None:
                return "?"
            x, y = self.mouse_position
            widget, _region = screen.get_widget_at(x, y)
            return type(widget).__name__
        except Exception:
            return "?"

    def _log_event(self, phase: str, event) -> None:
        """Log an event to /tmp/grail_chat_mouse.log with full propagation context.

        Short-circuits when no handlers are attached to the diagnostic
        logger (the default state when ``GRAIL_CHAT_DEBUG`` is unset),
        so the per-event cost in production is one attribute lookup.
        """
        if not _mouse_logger.handlers:
            return
        try:
            cls = type(event).__name__
            attrs = []
            # Include key name / character for Key events so we can see what
            # the user pressed (essential for diagnosing focus-related bugs).
            for a in ("key", "character", "x", "y", "button", "ctrl", "shift", "meta", "delta_x", "delta_y"):
                if hasattr(event, a):
                    v = getattr(event, a)
                    if a == "character" and v is not None and not v.isprintable():
                        v = f"\\x{ord(v):02x}"
                    attrs.append(f"{a}={v!r}" if a in ("key", "character") else f"{a}={v}")
            try:
                target = getattr(event, "control", None) or getattr(event, "widget", None)
                target_name = type(target).__name__ if target else "?"
            except Exception:
                target_name = "?"
            try:
                focused = type(self.focused).__name__ if self.focused else "None"
            except Exception:
                focused = "?"
            try:
                scroll_y = round(self.chat_log.scroll_y, 1)
                max_y = round(self.chat_log.max_scroll_y, 1)
                scroll_info = f"{scroll_y}/{max_y}"
            except Exception:
                scroll_info = "?"
            hover = self._widget_under_cursor_name()
            _mouse_logger.debug(
                f"[{phase:>20}] {cls:<22} {' '.join(attrs):<60} "
                f"target={target_name:<18} focused={focused:<12} "
                f"hover={hover:<14} scroll={scroll_info}"
            )
        except Exception as exc:
            try:
                _mouse_logger.debug(f"[{phase}] failed to log {type(event).__name__}: {exc}")
            except Exception:
                pass

    async def on_key(self, event: events.Key) -> None:
        """Auto-refocus the input when the user starts typing in scroll mode.

        After scrolling the chat (which requires focus on ``chat_log``),
        most users naturally start typing their next question.  Without
        this hook they would type into empty space — the input wouldn't
        appear to "wake up" until they hit Tab.  Detecting any
        printable single-character key while ``chat_log`` is focused
        forwards the keystroke to the input and refocuses it.
        """
        try:
            if (
                self.focused is self.chat_log
                and event.character is not None
                and len(event.character) == 1
                and event.character.isprintable()
            ):
                ch = event.character
                # Append the character to the input's value, place cursor
                # at the end, then refocus.  Doing this BEFORE focus
                # change means the value mutation has settled by the
                # time Input gets focus and processes any follow-up
                # keystrokes.  We avoid `insert_text_at_cursor` because
                # the cursor reactive hasn't updated when called from an
                # un-focused state.
                self.input.value = (self.input.value or "") + ch
                try:
                    self.input.cursor_position = len(self.input.value)
                except Exception:
                    pass
                self.input.focus()
                event.stop()
                event.prevent_default()
        except Exception:
            pass

    async def on_event(self, event: events.Event) -> None:
        """Catch-all hook to log EVERY event that reaches the App.

        Mouse moves are sampled (every 30th) to avoid log flooding while still
        proving they are reaching the App layer.
        """
        try:
            if isinstance(event, events.MouseMove):
                self._mouse_move_count += 1
                if self._mouse_move_count <= 3 or self._mouse_move_count % 30 == 0:
                    self._log_event(f"on_event#{self._mouse_move_count}", event)
                if self._mouse_move_count == 1:
                    self._bump_mouse_indicator(f"moves=1")
            elif isinstance(event, events.MouseEvent):
                # All non-move mouse events: log every one
                self._log_event("on_event", event)
            elif isinstance(event, (events.Focus, events.Blur, events.DescendantFocus, events.DescendantBlur)):
                self._log_event("on_event", event)
            elif isinstance(event, events.Key):
                # Keys: log so we can correlate "after Escape" timing
                self._log_event("on_event", event)
        except Exception:
            pass
        await super().on_event(event)

    # ----- explicit handlers retained so we can confirm dispatch -----

    async def on_mouse_down(self, event: events.MouseDown) -> None:
        self._log_event("on_mouse_down", event)
        self._mouse_click_count += 1
        self._bump_mouse_indicator(f"click#{self._mouse_click_count}")

    async def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._log_event("on_scroll_dn", event)
        self._mouse_wheel_count += 1
        self._bump_mouse_indicator(f"wheel↓ #{self._mouse_wheel_count}")
        before = self.chat_log.scroll_y
        self.chat_log.scroll_down(animate=False)
        after = self.chat_log.scroll_y
        _mouse_logger.debug(
            f"[on_scroll_dn  ] manual scroll {before} → {after} "
            f"(max={self.chat_log.max_scroll_y})"
        )

    async def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._log_event("on_scroll_up", event)
        self._mouse_wheel_count += 1
        self._bump_mouse_indicator(f"wheel↑ #{self._mouse_wheel_count}")
        before = self.chat_log.scroll_y
        self.chat_log.scroll_up(animate=False)
        after = self.chat_log.scroll_y
        _mouse_logger.debug(
            f"[on_scroll_up  ] manual scroll {before} → {after} "
            f"(max={self.chat_log.max_scroll_y})"
        )

    # ================================================================ lifecycle

    async def on_mount(self) -> None:
        self._reporter.bind_loop(asyncio.get_running_loop())
        self.input.focus()
        _mouse_logger.debug(
            f"on_mount: focused={type(self.focused).__name__ if self.focused else 'None'}"
        )
        # NOTE: We deliberately do NOT write mouse-mode escapes or
        # cursor-hide sequences directly to stdout. Textual already manages
        # the terminal state through its synchronized driver; any extra raw
        # writes race with that driver and corrupt mouse-report parsing in
        # GPU-rendered terminals like Warp.
        # Boot in background so the UI shows immediately
        self.run_worker(self._boot(), exclusive=True, name="boot")
        # Start the background drainers
        asyncio.create_task(self._drain_reporter())
        asyncio.create_task(self._drain_tokens())

    # ----- focus tracking (helps correlate "after Escape" symptom) -----
    def on_focus(self, event: events.Focus) -> None:
        self._log_event("App.on_focus", event)

    def on_blur(self, event: events.Blur) -> None:
        self._log_event("App.on_blur", event)

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        try:
            new_name = type(event.widget).__name__ if event.widget else "?"
        except Exception:
            new_name = "?"
        _mouse_logger.debug(f"[ descendant_focus  ] focus now on {new_name}")

    def on_descendant_blur(self, event: events.DescendantBlur) -> None:
        try:
            old_name = type(event.widget).__name__ if event.widget else "?"
        except Exception:
            old_name = "?"
        _mouse_logger.debug(f"[ descendant_blur   ] blur from {old_name}")

    async def _boot(self) -> None:
        """Initialize the database, user, GRAIL instance, and session."""
        self.show_system_message("_Initializing GRAIL…_")

        # Set up DB
        configure_db_path(self.db_path)
        await init_db()
        self.user_id = await self._ensure_cli_user()

        # Load GRAIL config + instance
        try:
            config = load_config(self.project_dir)
        except Exception as exc:
            self.show_system_message(f"[red]Failed to load config:[/red] {exc}")
            return

        try:
            self.grail = GRAIL.from_config(config, reporter=self._reporter)
        except Exception as exc:
            self.show_system_message(f"[red]Failed to instantiate GRAIL:[/red] {exc}")
            return

        # Load or create session. The default is ALWAYS a new session — past
        # sessions are reachable explicitly via the /resume slash command.
        resumed = False
        if self.initial_session_id:
            await self._load_session(self.initial_session_id)
            resumed = True

        if not resumed:
            session = await create_session(
                self.user_id, title="New Chat", mode=self.search_mode, source="cli",
            )
            self.active_session_id = session["id"]
            self.active_session_title = session["title"]

        resume_note = "_resumed_" if resumed else "_new session_"
        self.show_system_message(
            f"_Connected to_ **{self.project_dir.name}**  ·  _mode_: **{self.search_mode}**  ·  "
            f"_session ({resume_note}_): `{self.active_session_id[:8]}`  —  "
            f"**{self.active_session_title}**\n\n"
            "_Type your question below. Use_ `/help` _for commands._  "
            "_Type_ `/resume` _to list past chats and pick one._\n"
            "**Scroll:** mouse wheel · `PageUp`/`PageDown` · `Shift+↑/↓` · `Ctrl+End`  ·  "
            "**Focus chat:** `Esc`  ·  **Focus input:** `Tab` _(or just start typing)_  ·  "
            "**Select text:** hold `Shift` while dragging."
        )
        # Warp-specific hint — Warp needs mouse + scroll reporting enabled in
        # Settings → Features → Terminal for mouse-wheel to work in TUIs.
        if os.environ.get("TERM_PROGRAM", "") == "WarpTerminal":
            self.show_system_message(
                "⚠ **Warp detected.** If the mouse wheel doesn't scroll the chat, "
                "open **Settings → Features → Terminal** and enable "
                "**Mouse Reporting** + **Scroll Reporting**.  Keyboard shortcuts "
                "(`PageUp`/`PageDown`, `Esc` + wheel) work regardless."
            )
        if _debug_enabled():
            self.show_system_message(
                f"_Debug logging on → `{_MOUSE_LOG_PATH}` "
                "(unset `GRAIL_CHAT_DEBUG` to silence)._"
            )
        self.refresh_status()

    async def _ensure_cli_user(self) -> str:
        """Auto-create a system CLI user if it doesn't exist."""
        username = f"_cli_{getpass.getuser()}"
        existing = await get_user_by_username(username)
        if existing:
            return existing["id"]
        user = await create_user(username, CLI_USER_SENTINEL_HASH)
        return user["id"]

    async def _load_session(self, session_id: str) -> None:
        session = await get_session(session_id, self.user_id)
        if not session:
            self.show_system_message(f"[red]Session `{session_id}` not found.[/red]")
            return
        self.active_session_id = session["id"]
        self.active_session_title = session["title"]
        self.search_mode = session.get("mode", self.search_mode)
        messages = await get_messages(session_id)
        for m in messages:
            if m["role"] == "user":
                await self.chat_log.mount(UserBubble(m["content"]))
            elif m["role"] == "assistant" and not m.get("tool_calls"):
                bubble = AssistantBubble()
                await self.chat_log.mount(bubble)
                bubble.set_content(m["content"])
        self.chat_log.scroll_end(animate=False)

    # ================================================================ helpers

    def show_system_message(self, content: str) -> None:
        widget = MarkdownWidget(content, classes="system-message")
        self.run_worker(self._mount_widget(widget), exclusive=False)

    async def _mount_widget(self, widget) -> None:
        was_at_bottom = self._is_at_bottom()
        await self.chat_log.mount(widget)
        if was_at_bottom:
            self.chat_log.scroll_end(animate=False)

    def _is_at_bottom(self) -> bool:
        """True if the chat log is scrolled to (or near) the bottom."""
        try:
            scroll_y = self.chat_log.scroll_y
            max_y = self.chat_log.max_scroll_y
            return (max_y - scroll_y) < 3
        except Exception:
            return True

    def _maybe_scroll_to_end(self) -> None:
        if self._is_at_bottom():
            self.chat_log.scroll_end(animate=False)

    def clear_chat_log(self) -> None:
        for child in list(self.chat_log.children):
            child.remove()

    def refresh_status(self) -> None:
        self.status_bar.mode = self.search_mode
        self.status_bar.enabled_tools = self.enabled_tools
        if self.grail and self.grail.cost_tracker.records:
            self.status_bar.cost = self.grail.cost_tracker.render_total_cost()
        self.status_bar.refresh()

    # ================================================================ input

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.input.value = ""
        if self.is_streaming:
            self.show_system_message("[yellow]Wait for the current response to finish.[/yellow]")
            return
        if dispatch(self, text):
            return
        await self._send_message(text)

    async def _send_message(self, text: str) -> None:
        if self.grail is None:
            self.show_system_message("[red]GRAIL is not initialized yet.[/red]")
            return

        await self.chat_log.mount(UserBubble(text))
        self.chat_log.scroll_end(animate=False)
        await create_message(self.active_session_id, "user", text)

        # Auto-title session from first message
        if self.active_session_title == "New Chat":
            new_title = text[:50].strip() + ("…" if len(text) > 50 else "")
            await update_session(self.active_session_id, self.user_id, title=new_title)
            self.active_session_title = new_title

        # Create the assistant bubble we'll stream into
        bubble = AssistantBubble()
        await self.chat_log.mount(bubble)
        self.chat_log.scroll_end(animate=False)
        self._active_assistant = bubble
        self.is_streaming = True
        self._active_tool_card = None

        self.run_worker(self._run_search(text), exclusive=True, name="search")

    # ================================================================ search execution

    async def _run_search(self, query: str) -> None:
        from grail.llm.wrapper import set_stream_callback, set_debug_mode
        assert self.grail is not None

        async def on_chunk(token: str) -> None:
            await self._token_queue.put(token)

        # Build conversation history from DB (last N turns)
        history: list[dict[str, Any]] = []
        try:
            recent = await get_messages(self.active_session_id)
            for m in recent[-40:]:
                if m["role"] not in ("user", "assistant"):
                    continue
                if m.get("tool_calls"):
                    continue
                history.append({"role": m["role"], "content": m["content"]})
            # Trim last user message (the one we just sent)
            if history and history[-1]["role"] == "user":
                history.pop()
        except Exception:
            pass

        result = None
        error: Exception | None = None
        try:
            # Set callback for every mode — execute_with_tools now streams too.
            set_stream_callback(on_chunk)
            try:
                if self.search_mode == "agent":
                    result = await self.grail.agent_search(
                        query,
                        conversation_history=history,
                        enabled_tools=self.enabled_tools if self.enabled_tools != ALL_TOOLS else None,
                    )
                else:
                    result = await self.grail.search(
                        query,
                        mode=self.search_mode,
                        conversation_history=history,
                    )
            finally:
                set_stream_callback(None)
                set_debug_mode(False)
        except Exception as exc:
            error = exc
            log.exception("Search failed")

        # Drain remaining tokens
        await asyncio.sleep(0.05)

        if error:
            self.show_system_message(f"[red]Error:[/red] {error}")
            self.is_streaming = False
            return

        # If the stream didn't fill the bubble (e.g. provider lacks stream support
        # for tools), fall back to the full response text.
        if result and self._active_assistant is not None:
            response_text = result.response if isinstance(result.response, str) else json.dumps(result.response)
            if not self._active_assistant.get_content().strip() and response_text:
                self._active_assistant.set_content(response_text)

        # Persist assistant message
        if result is not None:
            response_text = result.response if isinstance(result.response, str) else json.dumps(result.response)

            # Extract sources
            from grail.query.retrieval import extract_source_references, load_artifacts_for_search
            source_refs: list[dict[str, str]] = []
            if isinstance(result.context_data, dict):
                try:
                    artifacts = load_artifacts_for_search(self.grail.storage, self.grail._output_folder())
                    source_refs = extract_source_references(
                        result.context_data,
                        documents=artifacts.documents,
                        mapping=artifacts.mapping,
                    )
                except Exception:
                    pass

            self.last_sources = source_refs
            self.sources_panel.set_sources(source_refs)

            metadata: dict[str, Any] = {
                "completion_time": result.completion_time,
                "llm_calls": result.llm_calls,
                "mode": self.search_mode,
                "sources": source_refs,
            }

            # Persist agent tool-call messages too
            agent_msgs = (result.context_data or {}).get("agent_messages") if isinstance(result.context_data, dict) else None
            if agent_msgs:
                try:
                    await create_messages_batch(self.active_session_id, agent_msgs)
                except Exception:
                    log.exception("Failed to persist agent tool messages")

            await create_message(
                self.active_session_id, "assistant", response_text, metadata=metadata,
            )

        self.is_streaming = False
        self.refresh_status()

    # ================================================================ drainers

    async def _drain_tokens(self) -> None:
        """Drain streaming tokens and batch-flush to the active bubble.

        Every token triggers a full Markdown re-render of the assistant
        bubble.  At LLM streaming rates (~50-100 tokens/sec for fast
        models) this is too much render work per second and the UI lags —
        manual scrolling stutters because the render loop is saturated.

        We accumulate tokens and flush either every ~60ms or once the
        pending buffer crosses ~32 chars (whichever comes first).  This
        keeps the visible streaming animation smooth while freeing CPU
        for mouse/scroll responsiveness.
        """
        import time as _time
        pending = ""
        last_flush = _time.perf_counter()
        FLUSH_INTERVAL_S = 0.06     # max ms between renders
        FLUSH_CHAR_THRESHOLD = 32   # force flush after this many buffered chars

        while True:
            try:
                # Wait briefly for the next token. Timeout lets us flush
                # the pending buffer between rapid token bursts.
                token = await asyncio.wait_for(
                    self._token_queue.get(), timeout=FLUSH_INTERVAL_S
                )
                pending += token
            except asyncio.TimeoutError:
                # No new token during the window — fall through to flush.
                pass
            except asyncio.CancelledError:
                # Drain anything pending before exiting.
                if pending and self._active_assistant is not None:
                    try:
                        self._active_assistant.append_token(pending)
                    except Exception:
                        pass
                return

            now = _time.perf_counter()
            if pending and (
                (now - last_flush) >= FLUSH_INTERVAL_S
                or len(pending) >= FLUSH_CHAR_THRESHOLD
            ):
                if self._active_assistant is not None:
                    try:
                        self._active_assistant.append_token(pending)
                        self._maybe_scroll_to_end()
                    except Exception:
                        pass
                pending = ""
                last_flush = now

    async def _drain_reporter(self) -> None:
        """Drain reporter events and route to the active tool card or chat log."""
        tool_call_re = re.compile(r"Calling tool: (\w+)\((.*)\)")
        tool_done_re = re.compile(r"(\w+) returned \((\d+) LLM calls?\)")

        while True:
            try:
                event: ReporterEvent = await self._reporter_queue.get()
            except asyncio.CancelledError:
                return

            # Detect agent tool call boundaries
            m = tool_call_re.match(event.message)
            if m:
                tool_name = m.group(1)
                args_str = m.group(2)
                args_dict = self._parse_args(args_str)
                card = ToolCallCard(tool_name, args_dict)
                try:
                    was_at_bottom = self._is_at_bottom()
                    await self.chat_log.mount(card)
                    if was_at_bottom:
                        self.chat_log.scroll_end(animate=False)
                except Exception:
                    pass
                self._active_tool_card = card
                continue

            m = tool_done_re.match(event.message)
            if m and self._active_tool_card is not None:
                tool_name = m.group(1)
                llm_calls = m.group(2)
                self._active_tool_card.mark_done(f"done · {llm_calls} LLM call(s)")
                self._active_tool_card = None
                continue

            # Otherwise route to active tool card or as a system status line
            if self._active_tool_card is not None:
                try:
                    self._active_tool_card.add_status(event.level, event.message)
                except Exception:
                    pass
            else:
                # Background info from search setup — show subtly
                if event.level in ("warning", "error"):
                    self.show_system_message(f"[{event.level}]{event.message}[/{event.level}]")

    def _parse_args(self, args_str: str) -> dict[str, Any]:
        """Parse 'key=value, key2=value2' format used by the reporter."""
        out: dict[str, Any] = {}
        # Simple split on top-level commas
        depth = 0
        current = ""
        parts = []
        for ch in args_str:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += ch
        if current.strip():
            parts.append(current)
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                # Strip surrounding quotes if present
                if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                    v = v[1:-1]
                out[k] = v
        return out

    # ================================================================ actions

    async def action_clear_chat(self) -> None:
        self.clear_chat_log()
        self.show_system_message("_Chat cleared._")

    def action_focus_chat_log(self) -> None:
        """Move focus to the chat log so its scrollbar is interactive."""
        self.chat_log.focus()

    def action_toggle_focus(self) -> None:
        """Toggle focus between input and chat log."""
        if self.focused is self.input:
            self.chat_log.focus()
        else:
            self.input.focus()

    def action_scroll_page_up(self) -> None:
        self.chat_log.scroll_page_up(animate=False)

    def action_scroll_page_down(self) -> None:
        self.chat_log.scroll_page_down(animate=False)

    def action_scroll_up(self) -> None:
        self.chat_log.scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        self.chat_log.scroll_down(animate=False)

    def action_scroll_top(self) -> None:
        self.chat_log.scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        self.chat_log.scroll_end(animate=False)

    async def action_new_session(self) -> None:
        session = await create_session(
            self.user_id, title="New Chat", mode=self.search_mode, source="cli",
        )
        self.active_session_id = session["id"]
        self.active_session_title = "New Chat"
        self.clear_chat_log()
        self.sources_panel.set_sources([])
        self.last_sources = []
        self.show_system_message(f"_New session_: `{session['id'][:8]}`")

    async def action_list_sessions(self) -> None:
        sessions = await list_sessions(self.user_id, source="cli")
        if not sessions:
            self.show_system_message("_No saved sessions._")
            return
        lines = ["**Sessions for this user:**", ""]
        for s in sessions[:20]:
            marker = "← current" if s["id"] == self.active_session_id else ""
            lines.append(
                f"- `{s['id'][:8]}` ({s['message_count']} msgs)  **{s['title']}**  {marker}"
            )
        lines.append("")
        lines.append("Use `/load <id>` to resume one.")
        self.show_system_message("\n".join(lines))

    async def action_load_session(self, session_id: str) -> None:
        # Match by prefix if user gave 8-char id
        all_sessions = await list_sessions(self.user_id, source="cli")
        match = next((s for s in all_sessions if s["id"].startswith(session_id)), None)
        if not match:
            self.show_system_message(f"_Session `{session_id}` not found._")
            return
        self.clear_chat_log()
        self.sources_panel.set_sources([])
        await self._load_session(match["id"])
        self.show_system_message(f"_Loaded session_ `{match['id'][:8]}` — **{match['title']}**")
        self.refresh_status()

    async def action_resume(self, args: str) -> None:
        """Resume a past session, or list options if no id given.

        Lists the most recent sessions with a preview of the first user message
        so the user can tell them apart, then accepts ``/resume <id-prefix>``.
        """
        target = args.strip()
        sessions = await list_sessions(self.user_id, source="cli")
        if not sessions:
            self.show_system_message("_No past sessions for this project._")
            return

        if not target:
            # No id — list recent sessions with first message preview.
            lines = ["**Recent chats — pick one with** `/resume <id>`:", ""]
            for s in sessions[:15]:
                first = await self._first_user_message(s["id"])
                preview = (first[:70] + "…") if len(first) > 70 else (first or "_(empty)_")
                marker = " ← current" if s["id"] == self.active_session_id else ""
                lines.append(
                    f"- `{s['id'][:8]}` · {s['message_count']} msg · {preview}{marker}"
                )
            self.show_system_message("\n".join(lines))
            return

        # Resume by id prefix
        match = next((s for s in sessions if s["id"].startswith(target)), None)
        if not match:
            self.show_system_message(
                f"_No session starting with_ `{target}`_. Type_ `/resume` _to list._"
            )
            return
        self.clear_chat_log()
        self.sources_panel.set_sources([])
        await self._load_session(match["id"])
        self.show_system_message(
            f"_Resumed session_ `{match['id'][:8]}` — **{match['title']}**"
        )
        self.refresh_status()

    async def _first_user_message(self, session_id: str) -> str:
        """Return the first user message in a session, or empty string."""
        try:
            msgs = await get_messages(session_id)
            for m in msgs:
                if m["role"] == "user":
                    return (m["content"] or "").strip().replace("\n", " ")
        except Exception:
            pass
        return ""


def run_chat(
    project_dir: Path,
    *,
    mode: str = "agent",
    session_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Launch the GRAIL chat TUI."""
    # Reset the debug event log so each chat invocation starts fresh.
    _reset_event_log()
    app = ChatApp(
        project_dir=project_dir,
        mode=mode,
        session_id=session_id,
        db_path=db_path,
    )
    app.run()
