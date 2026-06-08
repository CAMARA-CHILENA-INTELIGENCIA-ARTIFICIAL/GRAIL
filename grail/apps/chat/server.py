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
    create_messages_batch,
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
    debug: bool = False,
) -> FastAPI:
    app = FastAPI(title="GRAIL Chat API", version=__version__)

    app.state.project_dir = project_dir
    app.state.grail_instance = None
    app.state.host = host
    app.state.port = port
    app.state.debug = debug

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
        rows = await list_sessions(current_user["id"], source="web")
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
            user_meta: dict[str, Any] = {}
            if body.document:
                user_meta["document_scope"] = body.document
            user_msg = await create_message(
                body.session_id, "user", body.message, metadata=user_meta or None
            )
            yield {"event": "user_message", "data": json.dumps(user_msg)}
            yield {"event": "status", "data": json.dumps({"status": "searching", "mode": mode})}

            chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
            # Buffer the full streamed payload (final answer text + any
            # <tool_call> XML the agent emits) so we can persist exactly
            # what the user saw.
            streamed_buffer: list[str] = []
            result_holder: list[Any] = [None]
            error_holder: list[Exception | None] = [None]

            async def on_chunk(text: str) -> None:
                streamed_buffer.append(text)
                await chunk_queue.put(text)

            async def run_search() -> None:
                from grail.llm.wrapper import set_debug_mode, set_stream_callback
                try:
                    # Stream for every mode. In agent mode the LLM wrapper
                    # already separates content from tool-call fragments, so
                    # only assistant text reaches the callback — tool-call
                    # arguments are accumulated and surfaced via the agent's
                    # own <tool_call> emissions.
                    set_stream_callback(on_chunk)
                    if app.state.debug:
                        set_debug_mode(True)
                    recent = await get_recent_messages(body.session_id, limit=40)
                    history = []
                    for m in recent:
                        if m["id"] == user_msg["id"]:
                            continue
                        entry: dict[str, Any] = {"role": m["role"], "content": m["content"]}
                        if m.get("tool_calls"):
                            entry["tool_calls"] = m["tool_calls"]
                        if m.get("tool_call_id"):
                            entry["tool_call_id"] = m["tool_call_id"]
                        history.append(entry)
                    history = history[-20:]

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
                    set_debug_mode(False)
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
                # Prefer what we actually streamed (text + tool_call tags)
                # so reloads show the same content the user saw. Fall back
                # to result.response if the stream was empty (e.g. a mode
                # that doesn't stream yet).
                streamed_text = "".join(streamed_buffer).strip()
                if streamed_text:
                    response_text = streamed_text
                else:
                    response_text = (
                        result.response if isinstance(result.response, str)
                        else json.dumps(result.response)
                    )

                source_refs: list[dict[str, str]] = []
                if isinstance(result.context_data, dict):
                    from grail.query.retrieval import extract_source_references, load_artifacts_for_search
                    artifacts = load_artifacts_for_search(grail.storage, grail._output_folder())
                    source_refs = extract_source_references(
                        result.context_data,
                        documents=artifacts.documents,
                        mapping=artifacts.mapping,
                    )

                metadata: dict[str, Any] = {
                    "completion_time": result.completion_time,
                    "llm_calls": result.llm_calls,
                    "mode": mode,
                    "sources": source_refs,
                }

                agent_msgs = (result.context_data or {}).get("agent_messages")
                if agent_msgs:
                    await create_messages_batch(body.session_id, agent_msgs)

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
            modes=["local", "cascade", "global", "document", "agent"],
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

    # ================================================================ Document download

    @app.get("/api/documents/{doc_id}/download")
    async def document_download(
        doc_id: str,
        request: Request,
        token: Optional[str] = None,
    ) -> FileResponse:
        from grail.apps.chat.auth import decode_token
        auth_header = request.headers.get("authorization") or ""
        bearer_token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer") else ""
        actual_token = bearer_token or token or ""
        if not actual_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        try:
            decode_token(actual_token)
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
        grail = _get_grail()
        from grail.query.retrieval import load_artifacts_for_search
        artifacts = load_artifacts_for_search(grail.storage, grail._output_folder())
        docs = artifacts.documents
        if docs.empty:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No documents indexed")
        match = docs[docs["id"] == doc_id]
        if match.empty:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        row = match.iloc[0]
        storage_key = str(row.get("path", ""))
        if not storage_key or not grail.storage.exists(storage_key):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found on disk")
        with grail.storage.open_for_read(storage_key) as file_path:
            return FileResponse(
                path=str(file_path),
                filename=Path(storage_key).name,
                media_type="application/octet-stream",
            )

    # ================================================================ Knowledge graph viz

    # Soft cap on how many entities the chat UI loads by default. Past this
    # the SVG renderer slows down noticeably and memory climbs into the
    # hundreds of MB. The user can lift the cap explicitly.
    DEFAULT_VIZ_ENTITY_CAP = 5000

    @app.get("/api/viz/graph")
    async def viz_graph(
        max_entities: int = DEFAULT_VIZ_ENTITY_CAP,
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        """Return the D3 force-graph payload for the current project.

        ``max_entities`` enforces a soft cap (default 5000): when the indexed
        corpus exceeds it, the response carries only the top-N highest-degree
        entities and the relationships induced over them, with a
        ``meta.truncation`` block explaining what was dropped.

        Pass ``max_entities=0`` (or any non-positive value) to disable the
        cap and load everything.
        """
        grail = _get_grail()
        from grail.query.retrieval import load_artifacts_for_search
        from grail.viz.exporter import build_sigma_graph
        from grail.viz.sampling import top_n_by_degree

        artifacts = load_artifacts_for_search(grail.storage, grail._output_folder())
        if artifacts.entities.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No entities indexed yet — run `grail index` first.",
            )

        cap = max_entities if max_entities > 0 else None
        sampled = top_n_by_degree(
            entities=artifacts.entities,
            relationships=artifacts.relationships,
            text_units=artifacts.text_units,
            nodes=artifacts.nodes,
            communities=artifacts.communities,
            community_reports=artifacts.community_reports,
            documents=artifacts.documents,
            max_entities=cap,
        )

        truncation_meta: Optional[dict] = (
            {
                "truncated": True,
                "total_entities": sampled.total_entities,
                "total_relationships": sampled.total_relationships,
                "kept_entities": sampled.kept_entities,
                "kept_relationships": sampled.kept_relationships,
                "policy": sampled.policy,
                "cap": cap or 0,
            }
            if sampled.truncated
            else None
        )

        sigma = build_sigma_graph(
            entities_df=sampled.entities,
            relationships_df=sampled.relationships,
            nodes_df=sampled.nodes,
            documents_df=sampled.documents,
            text_units_df=sampled.text_units,
            communities_df=sampled.communities,
            reports_df=sampled.community_reports,
            truncation=truncation_meta,
        )
        return sigma.to_dict()

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
    debug: bool = False,
) -> None:
    import uvicorn

    app = create_app(project_dir=project_dir, host=host, port=port, dev=dev, db_path=db_path, debug=debug)
    uvicorn.run(app, host=host, port=port, log_level="info")
