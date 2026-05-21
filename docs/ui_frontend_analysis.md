# UI / Frontend Analysis: Chainlit vs Custom TypeScript/React

> **Date:** 2025-05-19
> **Context:** Evaluating frontend strategy for GRAIL's two planned UI surfaces.
> **Evaluated:** Chainlit v2.11.1 (Apache 2.0, community-maintained since May 2025)

---

## Two UI surfaces

| # | Surface | Description | Security posture |
|---|---------|-------------|------------------|
| 1 | **Local dev UI** | Chat interface with sessions, simple + agentic mode. For advanced users running GRAIL locally. | Minimal — localhost only |
| 2 | **Oncology platform** | Public-facing product for searching cancer benefits, laws, etc. Rate limiting, auth, and full hardening required. | Full production security |

---

## Recommendation summary

| | Chainlit | Custom TS/React |
|---|---|---|
| Point 1 (local UI) | **Use this** — 1-2 days to MVP | Overkill — weeks of work |
| Point 2 (oncology) | Missing too many security primitives | **Use this** — you own the stack |
| Learning curve | ~4 hours for the decorator API | Already known by the team |
| Long-term risk | Community-maintained, no company | Self-maintained |

---

## What Chainlit provides out of the box

| Feature | Status |
|---|---|
| Chat sessions with persistence | Built-in (WebSocket + optional SQLAlchemy/DynamoDB) |
| Agentic mode (tool calls, intermediate steps) | Built-in `@cl.step()` with nested rendering, collapsible details |
| Multiple chat modes (simple/agent) | Chat Profiles — dropdown selector, per-profile config |
| Auth (password, OAuth, header, JWT) | Solid implementation, HTTP-only cookies, SameSite |
| File uploads with validation | MIME type + size checks + path traversal protection |
| Markdown + code + LaTeX rendering | react-markdown, highlight.js, KaTeX |
| Theming (light/dark, custom CSS/JS) | config.toml + theme.json + CSS variables |
| Python backend (FastAPI) | Direct `import grail` in message handlers |
| Custom endpoints | `app.include_router()` on the FastAPI instance |
| Zero telemetry | Confirmed, no phone-home |
| License | Apache 2.0, commercial OK |

### Tech stack

- **Frontend:** React 18, TypeScript 5.2, Vite 5, Tailwind CSS 3, Radix UI
- **Backend:** FastAPI + Uvicorn + python-socketio
- **State:** Recoil (frontend), SQLAlchemy/DynamoDB (backend, optional)
- **Communication:** WebSocket (socket.io) + HTTP REST

---

## Security gap analysis

Evaluated against the full security requirements list for Point 2 (oncology platform).

| Requirement | Chainlit status | Effort to fix |
|---|---|---|
| Rate limit per IP/account | **Missing entirely** | Need middleware (slowapi) or reverse proxy (nginx) |
| CORS | Default `allow_origins=["*"]` — permissive | Config change in `.chainlit/config.toml` (easy) |
| CSP | **Not implemented** | Custom middleware or reverse proxy header |
| HTTPS | Not handled (expects reverse proxy) | Standard — nginx/caddy in front |
| XSS Protection | `unsafe_allow_html=false` by default, but **no DOMPurify** | Frontend fork or custom build |
| CSRF Protection | **No explicit tokens** — only SameSite cookie | Custom middleware needed |
| Secure Cookies | HttpOnly, Secure (conditional), SameSite configurable | Already there |
| No exposed secrets | .env support, env vars for keys | Already there |
| Input validation | File uploads validated; general input is caller's responsibility | Backend validation needed regardless |
| Security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy) | **None implemented** | Middleware or reverse proxy |
| Route-based access control | Thread ownership checks exist; no role-based routing | Custom middleware |
| Backend authorization | Thread/session ownership verified | Sufficient for basic cases |
| HTML sanitization | **No DOMPurify** | Frontend modification needed |
| Dependency updates | Active community, but no company SLA | Monitor manually |
| Rate limiting (login/forms) | **Not implemented** | Custom middleware |
| Secure error handling | Standard FastAPI error responses | Acceptable |
| Source maps in production | Vite default (controllable) | Build config |
| Clickjacking protection (X-Frame-Options) | **Not implemented** | One header via middleware |
| SRI for external scripts | **Not implemented** | Frontend build config |

**Result: 7 of 17 security requirements are missing and would require custom work.**

---

## Community-maintenance risk

As of May 2025, Chainlit SAS (the original company) stepped back. The project is now community-maintained under a formal Maintainer Agreement:

- No company backing future security patches
- No SLA on vulnerability response (policy states 5-day ack / 90-day fix, but aspirational)
- For a health/oncology platform, depending on community volunteers for security patches is a liability
- For a local dev tool, this risk is acceptable

---

## Point 1: Local dev UI — use Chainlit

### Rationale

- Sessions, agentic tool rendering, chat profiles match the requirements exactly
- GRAIL is Python, Chainlit is Python — direct integration, no API layer needed
- Time to working prototype: **1-2 days** vs 2-3 weeks for custom React
- The decorator API is ~10 functions; learning curve is hours, not weeks
- If it doesn't fit later, the backend logic (GRAIL integration) transfers to any framework

### Minimal integration sketch

```python
import chainlit as cl
from grail import GRAIL

@cl.on_chat_start
async def start():
    grail = GRAIL.load("my_project")
    cl.user_session.set("grail", grail)

@cl.on_message
async def on_message(msg: cl.Message):
    grail = cl.user_session.get("grail")
    result = await grail.search(msg.content, mode="local")
    await cl.Message(content=result.response).send()
```

Agent mode uses `@cl.step()` for tool-call visualization and Chat Profiles to switch between simple/agent.

---

## Point 2: Oncology platform — use custom TypeScript/React

### Rationale

- The team already knows TypeScript — the "unknown library" risk disappears
- Full control over every security header, CSP policy, rate limiting, CSRF tokens
- Health data demands owning the security stack, not patching around a framework's gaps
- Rate limiting at the API layer (not just nginx) is critical to prevent embedding/LLM abuse by third parties
- Battle-tested libraries available: NextAuth.js, helmet.js, csrf-csrf, express-rate-limit
- The GRAIL backend stays as a Python API (FastAPI) — the frontend calls it over HTTP
- No dependency on community volunteers for security patches on a sensitive product

### Target architecture

```
Next.js (TypeScript)  -->  FastAPI (Python)  -->  GRAIL
       |                         |
  All security              Rate limiting
  headers, CSP,             per API key,
  CSRF, auth                usage tracking
```

### Security requirements checklist (all addressable)

- Rate limit per IP/account: `express-rate-limit` or Next.js middleware
- CORS: Next.js config + FastAPI `CORSMiddleware` with explicit origins
- CSP: `helmet.js` or Next.js `next.config.js` headers
- HTTPS: TLS termination at load balancer / reverse proxy
- XSS: React's default escaping + DOMPurify for dynamic HTML
- CSRF: `csrf-csrf` or double-submit cookie pattern
- Secure Cookies: NextAuth.js handles HttpOnly, Secure, SameSite
- Security headers: `helmet.js` (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, HSTS)
- Route-based access control: Next.js middleware + role checks
- Backend authorization: FastAPI dependency injection
- HTML sanitization: DOMPurify
- SRI: Webpack/Next.js SRI plugin
- Clickjacking: X-Frame-Options via helmet
- Source maps: disabled in production build config

---

## Hybrid path (not recommended)

Chainlit publishes `@chainlit/react-client` as an npm package. In theory, you could embed Chainlit's chat components inside a custom Next.js app for Point 2. This gives chat UI components but still requires all security work yourself — and couples you to Chainlit's component API. Recommended against: it adds dependency without reducing work.

---

## Decision

Start with **Chainlit for Point 1** now. When Point 2 development begins, build the **TypeScript frontend from scratch** with the security checklist baked in from day one. The GRAIL Python API layer will be shared between both surfaces.
