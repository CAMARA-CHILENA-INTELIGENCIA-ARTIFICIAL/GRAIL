# GRAIL CLI Chat

An interactive terminal-based chat for GRAIL.  Streams responses, renders
agent tool calls as collapsible cards, supports slash commands, persists
sessions to the same SQLite database the web app uses (CLI sessions are
flagged `source='cli'` so the two surfaces never mix).

---

## Quick start

```bash
grail chat <project_dir>
```

Common flags:

| Flag | Default | Description |
|---|---|---|
| `--mode / -m` | `agent` | Initial search mode: `agent`, `cascade`, `local`, `global`, `document`. Change anytime with `/mode`. |
| `--session / -s` | _(new)_ | Resume a session by id-prefix.  Use `/resume` inside chat to list. |
| `--db` | `<project>/.grail/chat.db` | Override SQLite location (e.g. share across projects). |

Examples:

```bash
grail chat examples/quickstart                  # new session, agent mode
grail chat examples/quickstart --mode cascade   # start in cascade mode
grail chat examples/quickstart --session a1b2   # resume that session
GRAIL_CHAT_DEBUG=1 grail chat examples/quickstart   # write event log
```

---

## Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ █▀▀ █▀█ █▀█ █ █     Graph RAG with Advanced Integration …       │  ← logo (2 rows)
│ █▄█ █▀▄ █▀█ █ █▄▄                                                │
├──────────────────────────────────────────────────────────────────┤
│ GRAIL · quickstart · mode: agent · tools: L C G D · cost: $0.01  │  ← status bar
├──────────────────────────────────────────────────────────────────┤
│  Connected to quickstart · mode: agent · session: a1b2 — New ... │
│                                                                  │
│  ❯ you  Tell me about Bevacizumab.                               │
│                                                                  │
│  ▣ cascade_search "tell me about bevacizumab" · running…         │  ← tool card
│                                                                  │
│  ✦ grail Bevacizumab (Avastin) is a monoclonal antibody…         │
│                                                                  │ ← chat log
│                                                          (3/47)  │
├──────────────────────────────────────────────────────────────────┤
│ sources: 📕 SEOM_2023_cachexia.pdf  📕 SEOM_2023_gliomas.pdf      │  ← sources
├──────────────────────────────────────────────────────────────────┤
│ ╭────────────────────────────────────────────────────────────╮   │
│ │ Ask anything…  (type /help for commands)                   │   │  ← input
│ ╰────────────────────────────────────────────────────────────╯   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Slash commands

| Command | Description |
|---|---|
| `/help` | Show all commands. |
| `/clear` | Clear the visible chat (history kept in SQLite). |
| `/new` | Start a fresh session. |
| `/sessions` | List recent sessions. |
| `/resume [<id>]` | List recent chats (no arg) or resume one by id-prefix. |
| `/load <id>` | Same as `/resume <id>` (older alias). |
| `/mode <name>` | Change search mode for the next message: `agent`, `cascade`, `local`, `global`, `document`. |
| `/tools` | Show the agent's enabled tools (✓ enabled, ✗ disabled). |
| `/enable <tool>` | Enable an agent tool (`local_search`, `cascade_search`, `global_search`, `document_search`). |
| `/disable <tool>` | Disable an agent tool — useful for steering the agent away from a path. |
| `/cost` | Cumulative LLM spend since the chat started. |
| `/sources` | Show source documents from the last response. |
| `/quit`, `/exit` | Exit (also `Ctrl+C`). |

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Enter` | Send the current message. |
| `Esc` | Move focus to the chat log (= **scroll mode**). |
| `Tab` | Toggle focus between input and chat log. |
| _any printable key_ | While in scroll mode, refocuses input and appends the character — **just start typing**. |
| `Page Up` / `Page Down` | Scroll the chat by a page (works in either focus). |
| `Shift+↑` / `Shift+↓` | Scroll line-by-line. |
| `Ctrl+End` | Jump to the bottom. |
| `Ctrl+Home` | Jump to the top. |
| `Ctrl+L` | Clear the visible chat (= `/clear`). |
| `Ctrl+C` | Quit. |

The auto-refocus on printable keys means scrolling and typing flow
naturally — you never need to remember to press `Tab` after `Esc`.

---

## Search modes inside chat

The `--mode` flag and `/mode` command both accept the same values used by
`grail query`.  See [`docs/search_modes.md`](search_modes.md) for the full
description; quick reminders:

| Mode | When to use |
|---|---|
| `agent` (default) | LLM picks which tools to call.  Best for most questions. |
| `cascade` | Entity-gated retrieval + BM25/cosine text rescue.  Most robust factual mode. |
| `local` | Entity-gated only (fastest). |
| `global` | Community-report synthesis for broad / thematic questions. |
| `document` | Scoped to one document — requires `/mode document` and you'll be asked which. |

In `agent` mode, you can restrict the agent's toolbox with `/disable` and
`/enable`.  E.g. to force the agent to only use the cascade tool:

```
/disable local_search
/disable global_search
/disable document_search
/tools
```

---

## Session persistence

| What | Where |
|---|---|
| Sessions and messages | `<project>/.grail/chat.db` (SQLite, WAL mode). |
| User record | Auto-created on first run as `_cli_<os-username>` with a sentinel password hash that cannot authenticate against the web. |
| Source filter | All CLI sessions carry `source='cli'`.  The web UI lists only `source='web'`, so the two never mix. |
| Override DB path | `grail chat <proj> --db /custom/path/chat.db`. |

Resuming a session restores the full message history (excluding agent
tool-call intermediates) into the chat log and re-applies the session's
saved mode.

---

## Streaming behaviour

LLM tokens are batched in `_drain_tokens` (`grail/apps/cli_chat/app.py`)
and flushed to the visible markdown widget every **60 ms** *or* every
**32 characters**, whichever comes first.  This keeps the streaming
animation smooth (~16 fps) without saturating the render loop — typing,
scrolling, and mouse events stay responsive during long generations.

The streaming callback uses `set_stream_callback()` from
`grail/llm/wrapper.py` — the same hook the web app uses for SSE.

---

## Terminal compatibility

The TUI is built on [Textual](https://textual.textualize.io) and runs in
the terminal's alternate-screen buffer.  Mouse / scroll behaviour depends
on what your terminal forwards.

### Recommended: iTerm2, Alacritty, kitty, Ghostty, WezTerm

All mouse features work out of the box: wheel scroll, scrollbar drag,
focus follow.  Hold `Shift` while dragging if you want the terminal to
own the selection (e.g. to copy text into your system clipboard).

### Warp on macOS — extra setup required

Warp needs two settings turned on for TUI mouse support to work:

1. **Settings → Features → Terminal → Enable Mouse Reporting** — must be ON.
2. **Settings → Features → Terminal → Enable Scroll Reporting** — only
   appears once mouse reporting is on; turn it on too.
3. Hold **Shift** to keep mouse events in Warp (e.g. for native text
   selection of scrollback).

Even with both on, [Warp issue #2906](https://github.com/warpdotdev/Warp/issues/2906)
documents that mouse-button drag events may not forward reliably, so the
scrollbar drag can be flaky.  The wheel, however, works.

**The keyboard-only path always works**: `Esc` to enter scroll mode,
`PageUp/Down` or wheel, then just start typing to come back to the input.

### Why Warp behaves differently than iTerm2

iTerm2 routes mouse events by cursor *position* — wherever the mouse
pointer is, that widget receives the event.  Warp instead treats the row
containing the *terminal* cursor as the active "input prompt" and filters
mouse events for that area.

Textual's stock `Input._watch_selection` (`textual/widgets/_input.py:513`)
writes `self.app.cursor_position = self.cursor_screen_offset` on every
keystroke.  That makes Textual reposition the terminal cursor onto the
Input row on every render, which trips Warp's filter.

The GRAIL `ChatInput` widget overrides `_watch_selection` to skip that
single line.  Selection clearing and scroll-to-cursor still happen — only
the cursor-position write is suppressed.  In iTerm2 / Alacritty / kitty
the override is a no-op (those terminals don't route by terminal-cursor
row); in Warp it un-sticks the wheel-events-when-input-focused case.

This change is purely cosmetic to Textual's behaviour — the visible
caret you see while typing is rendered by Textual via the
`input--cursor` CSS class, *not* by the real terminal cursor.

---

## Diagnostic event log (optional)

For diagnosing terminal compatibility issues, set the env var
`GRAIL_CHAT_DEBUG=1` when launching the chat:

```bash
GRAIL_CHAT_DEBUG=1 grail chat examples/quickstart
```

Behaviour:

- A file at `/tmp/grail_chat_mouse.log` is truncated and (re)opened on
  every launch.
- Every event reaching the App is recorded with its type, key/character
  (for `Key` events), x/y/button/delta (for mouse events), focused
  widget, hover widget under the cursor, and the chat log's
  `scroll_y/max_scroll_y` at that moment.
- Focus changes (`DescendantFocus`, `DescendantBlur`) are logged too.

When the env var is unset (default), the entire logging path
short-circuits — no file is created, no per-event formatting work runs.
Production users see no overhead.

`tail -f /tmp/grail_chat_mouse.log` in a second window is the most useful
way to read it.

---

## Architecture

```
grail/cli/main.py                       (@app.command() chat)
  └─► grail/apps/cli_chat/__init__.py
        └─► run_chat()
              ├─► _reset_event_log()    (opt-in)
              └─► ChatApp(Textual App).run()

grail/apps/cli_chat/
  app.py        ChatApp — boot, search loop, slash dispatch, key forwarding
  widgets.py    GrailLogo, StatusBar, ChatLog (VerticalScroll),
                ChatInput (Input + cursor-position fix), UserBubble,
                AssistantBubble, ToolCallCard, SourcesPanel
  commands.py   /help, /clear, /new, /sessions, /resume, /load, /mode,
                /tools, /enable, /disable, /cost, /sources, /quit
  reporter.py   TextualReporter — implements the GRAIL Reporter protocol;
                pushes events through an asyncio.Queue with thread-safe
                call_soon_threadsafe
```

All of this is glue around code that already existed:

| Reuses | Where |
|---|---|
| Streaming | `set_stream_callback(async_cb)` from `grail/llm/wrapper.py` — same hook the web app's SSE endpoint uses. |
| Reporter protocol | `Reporter` from `grail/reporting/rich_reporter.py`. |
| Agent loop | `AgentSearch.asearch()` from `grail/query/agent.py` — no fork; the `enabled_tools` set is a simple filter on `TOOL_SCHEMAS`. |
| DB layer | `create_session`, `create_message`, `get_messages`, `list_sessions` from `grail/apps/chat/database.py`.  Sessions table gained a `source` column so CLI and web sessions stay separate. |
| Source extraction | `extract_source_references()` from `grail/query/retrieval.py`. |
| GRAIL bootstrap | `GRAIL.from_config(config, reporter=...)` from `grail/core.py`. |

---

## Implementation notes (worth knowing)

### Tool filtering for the agent

`grail/query/agent.py:AgentSearch` accepts an optional
`enabled_tools: Optional[set[str]]`.  When set, the agent only sees a
filtered `TOOL_SCHEMAS`.  Default `None` means all four tools available.
The chat plumbs the active set through to `GRAIL.agent_search(...,
enabled_tools=...)`.

### Auto-refocus on printable keys

`ChatApp.on_key` intercepts keystrokes when `chat_log` has focus.  If the
key is a single printable character (`event.character.isprintable()` and
`len(event.character) == 1`), we:

1. Append the character to `input.value`.
2. Move the cursor to the end (`input.cursor_position = len(value)`).
3. Move focus back to the input.

`ChatInput(select_on_focus=False)` is critical here — Textual's default
`select_on_focus=True` would select all the input's text on refocus, and
the next keystroke would replace the just-appended character.

### Watch out for `_on_*` signature mismatches

Textual's base `Widget` defines:

- `_on_mouse_scroll_down/up` as **sync** (`def`, returning `None`).
- `_on_mouse_down/up` as **async**.
- No `_on_mouse_move` at all.

When subclassing, an `async def _on_mouse_scroll_down` that does
`await super()._on_mouse_scroll_down(event)` raises
`TypeError: object NoneType can't be used in 'await' expression`.  Match
the parent's sync/async signature exactly.  For `_on_mouse_move`, use the
public `on_mouse_move` hook — it's dispatched through `on_event` and
doesn't need a super call.

### Streaming-token batching, not per-token render

Earlier versions called `bubble.append_token(token)` in the
`_drain_tokens` loop, triggering a full Markdown re-render of the
assistant bubble for every LLM token.  At fast-model speeds
(~50-100 tokens/sec) this saturated the render loop and made scrolling
stutter.  We now accumulate tokens and flush every 60 ms or 32
characters — see `_drain_tokens` for the implementation.

### What we tried that DIDN'T work (so don't re-add it)

While diagnosing the Warp mouse issue, several "fixes" were tried and
abandoned because they made things worse:

- Writing duplicate mouse-mode escapes (`?1000h ?1002h ?1003h ?1006h
  ?1004h`) directly to `sys.__stdout__`, on top of Textual's own writes.
  Outcome: the raw writes raced with Textual's synchronized driver and
  corrupted mouse-report parsing.
- A 250 ms timer that re-asserted `?25l \x1b[H` (hide cursor + home)
  directly to `sys.__stdout__`.  Outcome: same race.
- Calling `self.cursor_position = Offset(0, 0)` every tick.  Outcome:
  fought Textual's per-render cursor positioning.

The fix that actually worked is the targeted `_watch_selection`
override described above — let Textual manage the terminal entirely,
just stop the Input from telling Textual to put the cursor in the
Input row.
