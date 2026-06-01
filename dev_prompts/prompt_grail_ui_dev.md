# GRAIL Chat UI — Development Context

> **Purpose**: This prompt gives a new Claude Code session full context to continue developing the GRAIL chat web interface. Read this before making any changes.

---

## What exists

A full-stack chat application for querying GRAIL knowledge graphs, modeled after ChatGPT/OpenAI's interface.

### Backend (`grail/apps/chat/`)

**Tech**: FastAPI + SQLite (aiosqlite) + JWT auth (python-jose + passlib) + SSE streaming (sse-starlette)

**Files**:
- `server.py` — FastAPI app factory, all routes, SSE streaming chat endpoint, static file serving for SPA
- `auth.py` — JWT (HS256, 24h expiry), auto-generated secret at `~/.grail/jwt_secret`, bcrypt password hashing
- `database.py` — SQLite at `~/.grail/chat.db`, tables: users, sessions, messages. Async CRUD functions
- `schemas.py` — Pydantic v2 request/response models

**API endpoints**:
```
GET  /api/auth/status          → { needs_setup: bool }
POST /api/auth/setup           → { access_token, user }     (first-run only)
POST /api/auth/login           → { access_token, user }
GET  /api/auth/me              → { id, username }

GET  /api/sessions             → [{ id, title, mode, created_at, updated_at, message_count }]
POST /api/sessions             → { id, title, mode, created_at, updated_at }
GET  /api/sessions/{id}        → { id, title, mode, messages: [...] }
PATCH /api/sessions/{id}       → { id, title, mode }
DELETE /api/sessions/{id}      → 204

POST /api/chat                 → SSE stream (see below)
GET  /api/config               → { project_name, modes, has_reranker, version }
GET  /api/documents            → [{ id, title, path }]

GET  /{path}                   → SPA catch-all (serves frontend/dist/index.html)
```

**SSE streaming (`POST /api/chat`)**:
The chat endpoint uses `asyncio.Queue` + `asyncio.create_task` to stream LLM tokens in real-time. The GRAIL search runs in a background task while chunks are yielded to the client as they arrive from the LLM.

Events sent:
```
event: user_message       data: { id, role, content, created_at }
event: status             data: { status: "searching", mode: "agent" }
event: assistant_chunk    data: { content: "partial token" }        ← real-time streaming
event: assistant_message  data: { id, role, content, metadata, created_at, session_title? }
event: error              data: { detail: "..." }
event: done               data: {}
```

The streaming callback is implemented via `contextvars` in `grail/llm/wrapper.py` — `set_stream_callback(cb)` sets an async callback that receives each token chunk from the OpenAI stream. The server sets this before running the search and clears it after.

**Dependencies** (optional `pip install 'graphgrail[ui]'`): fastapi, uvicorn[standard], python-jose[cryptography], passlib[bcrypt], aiosqlite, sse-starlette, bcrypt==4.0.1

### Frontend (`grail/apps/chat/frontend/`)

**Tech**: Vite 6 + React 19 + TypeScript 5.8 + Tailwind CSS v4 + zustand 5 + lucide-react + react-markdown + remark-gfm + framer-motion

**Font**: Plus Jakarta Sans (loaded from Google Fonts in index.html)

**Color scheme**: Dark theme. Background `#09090b` (zinc-950), surfaces zinc-900/800, primary teal-500 (`#14b8a6`), gradient `#5eead4 → #14b8a6 → #0d9488`. Subtle grain texture via CSS pseudo-element.

**State management** (zustand, `src/lib/store.ts`):
- `useAuthStore` — user, isAuthenticated, needsSetup, login/setup/logout/checkAuth
- `useSessionStore` — sessions[], activeSessionId, messages[], CRUD, addMessage
- `useChatStore` — isStreaming, streamingContent, statusText, currentMode (default "agent"), useRerankerMode, documentScope, config, documents, showInfo, sendMessage

**Key store details**:
- `SearchMode = "local" | "global" | "agent"` — document search is NOT a mode, it's a separate `documentScope` field
- When `documentScope` is set, `sendMessage` uses `mode="document"` with `document=<title>` under the hood
- When `useRerankerMode=true` + mode is local, passes `use_reranker=true`
- Agent is the default mode
- `sendMessage` streams SSE events: `user_message` → `addMessage`, `assistant_chunk` → append to `streamingContent`, `assistant_message` → `addMessage` (final)

**API client** (`src/lib/api.ts`):
- JWT stored in localStorage, injected as Bearer token
- `api.get/post/patch/delete/stream` methods
- `parseSSE` async generator — **important**: strips `\r` from lines (sse-starlette uses `\r\n` endings)

**Components**:

| File | Role |
|------|------|
| `App.tsx` | Auth gate, loads config + documents after auth |
| `Layout.tsx` | Sidebar + main area + InfoPanel overlay |
| `Sidebar.tsx` | ASCII logo header, new chat button, sessions grouped by date, delete on hover, logout |
| `WelcomeView.tsx` | Shown when no active session. Gradient title "Search. Discover. Learn.", ChatInput, 3 explanation cards (Agent/Local/Global). Creates session + sends message on submit |
| `ChatView.tsx` | Message list with auto-scroll, status bar, StreamingBubble, pinned ChatInput |
| `ChatInput.tsx` | Auto-resizing textarea, ModeChips + DocumentScope + info button + send button in toolbar |
| `ModeSelector.tsx` | Exports `ModeChips` (inline pills: Agent★, Local, Local+Rerank, Global) and `DocumentScope` (doc picker dropdown) |
| `MessageBubble.tsx` | User messages (teal, right) + assistant messages (dark, left with MarkdownRenderer). `StreamingBubble` for live streaming with loading dots |
| `MarkdownRenderer.tsx` | Custom react-markdown component overrides: headings, lists, code blocks with copy button + language label, tables with copy-as-markdown, blockquotes, links, images |
| `InfoPanel.tsx` | Slide-up modal explaining search modes with styled cards |
| `LoginView.tsx` | Login/setup form with GRAIL ASCII logo |

**Build**: `cd grail/apps/chat/frontend && npm run build` → outputs to `frontend/dist/` which FastAPI serves as static files.

**Dev mode**: `grail ui <project> --dev` enables CORS for Vite dev server. Run `cd grail/apps/chat/frontend && npm run dev` separately for hot reload on port 5173.

### CLI command

```bash
grail ui <project_dir> [--host 127.0.0.1] [--port 8765] [--dev]
```

Defined in `grail/cli/main.py`. Prints GRAIL banner, shows project/URL info, starts uvicorn.

### How GRAIL search works (for the UI)

The GRAIL class (`grail/core.py`) exposes:
```python
result = await grail.search(query, mode="local|global|document", conversation_history=[...], document=None, use_reranker=None)
result = await grail.agent_search(query, conversation_history=[...])
```

`SearchResult` has: `.response` (str), `.completion_time` (float), `.llm_calls` (int), `.context_data` (dict), `.context_text` (str)

The server builds conversation history from the last 10 turns of the session's messages.

---

## Design principles

- **Target audience**: Non-technical users (oncology researchers). UI must be self-explanatory with cards/tooltips explaining what things do.
- **Visual standard**: OpenAI/Vercel/Supabase quality. Sleek, modern, dark theme. Plus Jakarta Sans font. framer-motion for entrance animations and micro-interactions.
- **Mode system**: Agent (default, recommended with ★), Local, Local+Rerank (only if `config.has_reranker`), Global. Document scope is separate from modes.
- **Streaming**: Real token-by-token streaming via SSE. User sees tokens appear as the LLM generates them.

---

## Known issues and pending work

### Bugs to verify/fix
1. **Test the streaming end-to-end**: The SSE parser bug (`\r\n` line endings) was fixed. Verify user bubble appears immediately, streaming dots show, tokens stream in, final message renders with metadata.
2. **Session title update**: When auto-titled (first message), the sidebar session title should update. The server sends `session_title` in the `assistant_message` event — verify the frontend updates the sidebar.
3. **Document scope**: When a document is selected via the `📄` button, verify the search actually scopes to that document. The backend receives `mode="document"` + `document=<title>`.

### UI improvements needed
1. **Markdown rendering quality**: The `MarkdownRenderer` has basic component overrides but could use syntax highlighting for code blocks (currently renders plain text). Consider adding `highlight.js` or `shiki`.
2. **Message copy button**: Add a copy button on assistant messages (like ChatGPT's copy/thumbs up/down row under each response).
3. **Session rename**: The sidebar shows session titles but there's no inline rename. Add double-click-to-rename.
4. **Responsive polish**: Mobile sidebar overlay works but needs testing. The welcome cards should stack on small screens.
5. **Error handling UX**: SSE errors are logged to console but not shown to the user. Show a toast/banner for search errors.
6. **Loading states**: When GRAIL is initializing (first request, lazy loading), the user sees nothing. Add a "Connecting to GRAIL..." state.
7. **Agent mode visualization**: When agent mode runs, it makes multiple tool calls internally. Consider showing the agent's tool call steps (local_search, global_search calls) as collapsible steps.
8. **Keyboard shortcuts**: Cmd+K for new chat, Cmd+/ for info panel.
9. **Chat export**: Export a conversation as markdown or JSON.
10. **Empty state improvement**: The "Start the conversation" message in ChatView (when you click a session that has no messages) could show mode selector cards like the welcome view.

### Backend improvements needed
1. **Pagination**: `GET /api/sessions` returns all sessions. Add cursor-based pagination for users with many sessions.
2. **Message search**: Search across all sessions for a keyword.
3. **Rate limiting**: No rate limiting on the chat endpoint. For shared deployments, add per-user rate limiting.
4. **WebSocket alternative**: The SSE approach works but is unidirectional. For features like typing indicators or real-time collaboration, consider adding a WebSocket endpoint.
5. **Health check**: Add `GET /api/health` for monitoring.

---

## How to develop

### Setup
```bash
cd /Users/bgg/Documents/repos/cchia/opensource_comission/projects/GRAIL

# Install Python deps
uv pip install -e ".[ui]"

# Install frontend deps
cd grail/apps/chat/frontend && npm install && cd ../../../..
```

### Development workflow
```bash
# Terminal 1: Start backend in dev mode
grail ui examples/quickstart --dev --port 8765

# Terminal 2: Start frontend dev server (hot reload)
cd grail/apps/chat/frontend && npm run dev
```
Frontend dev server runs on http://localhost:5173 with API proxy to :8765.

### Production build
```bash
cd grail/apps/chat/frontend && npm run build
grail ui examples/quickstart --port 8765
# Open http://127.0.0.1:8765
```

### Testing
```bash
# Backend unit tests (from project root)
uv run pytest tests/unit/ -q

# Quick API smoke test
uv run python -c "
import asyncio
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from grail.apps.chat.server import create_app

async def test():
    app = create_app(project_dir=Path('examples/quickstart'))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        r = await c.get('/api/auth/status')
        print(f'auth status: {r.status_code} {r.json()}')
asyncio.run(test())
"
```

### Key files to read first
1. `grail/apps/chat/frontend/src/lib/store.ts` — all state management and the `sendMessage` SSE flow
2. `grail/apps/chat/server.py` — all API routes including SSE streaming
3. `grail/apps/chat/frontend/src/lib/api.ts` — API client and SSE parser
4. `grail/apps/chat/frontend/src/components/ChatInput.tsx` — the main interaction point
5. `grail/apps/chat/frontend/src/components/MarkdownRenderer.tsx` — response rendering

### Important gotchas
- **SSE line endings**: `sse-starlette` uses `\r\n`. The parseSSE function strips `\r` — do NOT remove this.
- **bcrypt version**: `bcrypt==4.0.1` is pinned because `passlib` is incompatible with bcrypt 5.x.
- **Frontend build**: The built `dist/` directory is committed so `pip install 'graphgrail[ui]'` users get it. After changing frontend code, always run `npm run build` from `grail/apps/chat/frontend/`.
- **Tailwind v4**: Uses `@import "tailwindcss"` in CSS with `@theme` blocks for custom colors. No `tailwind.config.js` file.
- **GRAIL lazy loading**: The GRAIL instance is created on first chat request (not at server startup). The first request will be slow due to loading parquet files, LanceDB, etc.
- **Database location**: `~/.grail/chat.db` and `~/.grail/jwt_secret`. Delete these to reset auth state.
- **Node modules and dist are gitignored/committed respectively**: `node_modules/` is in `.gitignore`. `frontend/dist/` is committed (root `/dist/` is gitignored for Python builds, but `grail/apps/chat/frontend/dist/` is tracked).

---

## Reference implementations

For design inspiration and patterns (do NOT copy proprietary code, only use for logic reference):
- Chat streaming: `/Users/bgg/Documents/repos/nirvana/nirvanav0/frontend/src/pages/NirvanaChatPage/ChatInput.tsx`
- Markdown rendering: `/Users/bgg/Documents/repos/nirvana/nirvanav0/frontend/src/components/common/NirvanaMarkdown.tsx` (only the component overrides for h1-h6, code, table, th, td, blockquote, a, lists — NOT the proprietary tags like artifacts, tools, citations)
- Chat body/bubbles: `/Users/bgg/Documents/repos/nirvana/nirvanav0/frontend/src/pages/NirvanaChatPage/ChatBody.tsx`
- LLM callback manager: `/Users/bgg/Documents/repos/nirvana/nirvanav0/backend_ml_cpu/agents/nirvana_agents/agents/callback_manager.py`
