"""
FastAPI server for the GRAIL chat application.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from grail._version import __version__
from grail.apps.chat.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from grail.apps.chat.database import (
    configure_db_path,
    create_message,
    create_session,
    create_user,
    delete_session,
    get_messages,
    get_recent_messages,
    get_session,
    get_user_by_username,
    get_user_count,
    init_db,
    list_sessions,
    update_session,
)
from grail.apps.chat.schemas import (
    AuthRequest,
    AuthResponse,
    ChatRequest,
    ConfigResponse,
    MessageResponse,
    SessionCreate,
    SessionDetailResponse,
    SessionResponse,
    SessionUpdate,
    UserResponse,
)

log = logging.getLogger("grail.apps.chat")

FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"


def create_app(
    project_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    dev: bool = False,
    db_path: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="GRAIL Chat API", version=__version__)

    app.state.project_dir = project_dir
    app.state.grail_instance = None
    app.state.host = host
    app.state.port = port

    if db_path:
        configure_db_path(db_path)

    # -- CORS
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"] if dev else []
    origins += [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Startup
    @app.on_event("startup")
    async def on_startup() -> None:
        await init_db()
        log.info("Database initialized")

    # -- Helpers

    def _get_grail():
        """Lazily create the GRAIL instance on first use."""
        if app.state.grail_instance is not None:
            return app.state.grail_instance
        if app.state.project_dir is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No GRAIL project configured. Start the server with a project directory.",
            )
        from grail.config import load_config
        from grail.core import GRAIL

        config = load_config(app.state.project_dir)
        app.state.grail_instance = GRAIL.from_config(config)
        log.info("GRAIL instance created for project: %s", config.project_name)
        return app.state.grail_instance

    # ================================================================ Auth

    @app.get("/api/auth/status")
    async def auth_status() -> dict[str, bool]:
        count = await get_user_count()
        return {"needs_setup": count == 0}

    @app.post("/api/auth/setup", response_model=AuthResponse)
    async def auth_setup(req: AuthRequest) -> AuthResponse:
        count = await get_user_count()
        if count > 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup already completed")
        hashed = hash_password(req.password)
        user = await create_user(req.username, hashed)
        token = create_access_token(user["id"], user["username"])
        return AuthResponse(
            access_token=token,
            user=UserResponse(id=user["id"], username=user["username"]),
        )

    @app.post("/api/auth/login", response_model=AuthResponse)
    async def auth_login(req: AuthRequest) -> AuthResponse:
        user = await get_user_by_username(req.username)
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = create_access_token(user["id"], user["username"])
        return AuthResponse(
            access_token=token,
            user=UserResponse(id=user["id"], username=user["username"]),
        )

    @app.get("/api/auth/me", response_model=UserResponse)
    async def auth_me(current_user: dict = Depends(get_current_user)) -> UserResponse:
        return UserResponse(id=current_user["id"], username=current_user["username"])

    # ================================================================ Sessions

    @app.get("/api/sessions", response_model=list[SessionResponse])
    async def sessions_list(current_user: dict = Depends(get_current_user)) -> list[SessionResponse]:
        rows = await list_sessions(current_user["id"])
        return [SessionResponse(**r) for r in rows]

    @app.post("/api/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
    async def sessions_create(
        body: SessionCreate, current_user: dict = Depends(get_current_user),
    ) -> SessionResponse:
        session = await create_session(current_user["id"], title=body.title, mode=body.mode)
        return SessionResponse(**session)

    @app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
    async def sessions_get(
        session_id: str, current_user: dict = Depends(get_current_user),
    ) -> SessionDetailResponse:
        session = await get_session(session_id, current_user["id"])
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        messages = await get_messages(session_id)
        return SessionDetailResponse(
            id=session["id"], title=session["title"], mode=session["mode"],
            created_at=session["created_at"], updated_at=session["updated_at"],
            messages=[MessageResponse(**m) for m in messages],
        )

    @app.patch("/api/sessions/{session_id}", response_model=SessionResponse)
    async def sessions_update(
        session_id: str, body: SessionUpdate, current_user: dict = Depends(get_current_user),
    ) -> SessionResponse:
        session = await update_session(
            session_id, current_user["id"],
            title=body.title, mode=body.mode,
        )
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return SessionResponse(**session)

    @app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def sessions_delete(
        session_id: str, current_user: dict = Depends(get_current_user),
    ) -> None:
        deleted = await delete_session(session_id, current_user["id"])
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # ================================================================ Chat

    @app.post("/api/chat")
    async def chat(body: ChatRequest, current_user: dict = Depends(get_current_user)):
        session = await get_session(body.session_id, current_user["id"])
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        grail = _get_grail()
        mode = body.mode or session["mode"]

        async def event_stream() -> AsyncIterator[dict[str, Any]]:
            user_msg = await create_message(body.session_id, "user", body.message)
            yield {"event": "user_message", "data": json.dumps(user_msg)}
            yield {"event": "status", "data": json.dumps({"status": "searching", "mode": mode})}

            chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
            result_holder: list[Any] = [None]
            error_holder: list[Exception | None] = [None]

            async def on_chunk(text: str) -> None:
                await chunk_queue.put(text)

            async def run_search() -> None:
                from grail.llm.wrapper import set_stream_callback
                try:
                    set_stream_callback(on_chunk)
                    recent = await get_recent_messages(body.session_id, limit=20)
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in recent
                        if m["id"] != user_msg["id"]
                    ][-10:]

                    if mode == "agent":
                        result_holder[0] = await grail.agent_search(
                            query=body.message,
                            conversation_history=history,
                        )
                    else:
                        result_holder[0] = await grail.search(
                            query=body.message,
                            mode=mode,
                            conversation_history=history,
                            document=body.document,
                            use_reranker=body.use_reranker,
                        )
                except Exception as exc:
                    error_holder[0] = exc
                finally:
                    set_stream_callback(None)
                    await chunk_queue.put(None)

            task = asyncio.create_task(run_search())

            while True:
                chunk = await chunk_queue.get()
                if chunk is None:
                    break
                yield {"event": "assistant_chunk", "data": json.dumps({"content": chunk})}

            await task

            if error_holder[0]:
                log.exception("Error during GRAIL search", exc_info=error_holder[0])
                yield {"event": "error", "data": json.dumps({"detail": str(error_holder[0])})}
            else:
                result = result_holder[0]
                response_text = result.response if isinstance(result.response, str) else json.dumps(result.response)
                metadata = {
                    "completion_time": result.completion_time,
                    "llm_calls": result.llm_calls,
                    "mode": mode,
                }

                new_title = None
                if session["title"] == "New Chat":
                    new_title = body.message[:50].strip()
                    if len(body.message) > 50:
                        new_title += "..."
                    await update_session(body.session_id, current_user["id"], title=new_title)

                assistant_msg = await create_message(
                    body.session_id, "assistant", response_text, metadata=metadata,
                )
                if new_title:
                    assistant_msg["session_title"] = new_title
                yield {"event": "assistant_message", "data": json.dumps(assistant_msg)}

            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(event_stream())

    # ================================================================ Config

    @app.get("/api/config", response_model=ConfigResponse)
    async def config_get(current_user: dict = Depends(get_current_user)) -> ConfigResponse:
        grail = _get_grail()
        return ConfigResponse(
            project_name=grail.config.project_name,
            project_path=str(grail.config.resolved_root()),
            modes=["local", "global", "document", "agent"],
            has_reranker=grail.config.reranker.enabled,
            version=__version__,
        )

    # ================================================================ Documents

    @app.get("/api/documents")
    async def documents_list(current_user: dict = Depends(get_current_user)) -> list[dict[str, str]]:
        grail = _get_grail()
        from grail.query.retrieval import load_artifacts_for_search
        artifacts = load_artifacts_for_search(grail.storage, grail._output_folder())
        docs = artifacts.documents
        if docs.empty:
            return []
        result = []
        for _, row in docs.iterrows():
            result.append({
                "id": str(row.get("id", "")),
                "title": str(row.get("title", "")),
                "path": str(row.get("path", "")),
            })
        return result

    # ================================================================ Static files / SPA

    if FRONTEND_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def spa_catch_all(full_path: str) -> FileResponse:
            file_path = FRONTEND_DIR / full_path
            if file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(FRONTEND_DIR / "index.html"))

    return app


def run_server(
    project_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    dev: bool = False,
    db_path: Path | None = None,
) -> None:
    import uvicorn

    app = create_app(project_dir=project_dir, host=host, port=port, dev=dev, db_path=db_path)
    uvicorn.run(app, host=host, port=port, log_level="info")
