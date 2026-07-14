"""
GRAIL MCP server — typed tools over GRAIL's knowledge-base and memory modes.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

One package, profile-selected toolset (the parity decision with the skill):

    grail-mcp --profile memory   # agentic-memory write + recall tools
    grail-mcp --profile kb        # knowledge-base index + query tools
    grail-mcp --profile all       # everything (default)

Optional ``--project <ref>`` binds the server to one project: every tool's
``project`` argument then defaults to it, and (unless ``--profile`` is given)
the profile is auto-selected from that project's mode.

Every tool returns the same ``{ok, data, warnings, next_steps, error}`` envelope
the skill and SDK use, so MCP clients read identical keys. Tool *descriptions*
carry a condensed form of GRAIL's routing guidance so the MCP surface keeps the
judgement layer the skill teaches in prose.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from grail._version import __version__
from grail.mcp._shared import (
    discover_projects,
    load_grail,
    open_memory_project,
    project_envelope,
    project_mode,
    reply,
    reply_from_core,
    resolve_project_ref,
    search_result_data,
)

_HOME_PROJECTS = Path.home() / ".grail" / "projects"


def _project_dir_for_new(ref: str) -> Path:
    """Bare names land in ``~/.grail/projects/<name>``; paths resolve as given."""
    s = ref.strip()
    if not s:
        raise ValueError("project name/path cannot be empty.")
    looks_like_path = "/" in s or "\\" in s or s.startswith(".") or s.startswith("~")
    return Path(s).expanduser().resolve() if looks_like_path else (_HOME_PROJECTS / s).resolve()


def build_server(*, profile: str = "all", default_project: str | None = None):
    """Construct a FastMCP server with the tools for ``profile`` registered."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SystemExit(
            "The MCP extra is not installed. Install it with:\n"
            '    pip install "graphgrail[mcp]"\n'
            "or run zero-install with:\n"
            '    uvx --from "graphgrail[mcp]" grail-mcp'
        ) from exc

    mcp = FastMCP("grail")

    def _resolve(project: str) -> Path:
        ref = project or default_project or ""
        return resolve_project_ref(ref)

    # ------------------------------------------------------------------ shared

    @mcp.tool()
    def grail_list_projects(include_stale: bool = False) -> dict[str, Any]:
        """List every GRAIL project on this machine (name, id, mode, path).

        Call this first to discover what's available. ``mode`` is
        ``knowledge_base`` or ``memory`` — route subsequent tools on it.
        """
        return reply(True, data={"projects": discover_projects(include_stale=include_stale)})

    @mcp.tool()
    def grail_status(project: str = "") -> dict[str, Any]:
        """Inspect a project: mode, artefact counts, observation count, active run.

        ``project`` is a path, registered name, or ULID prefix (omit if the
        server was launched bound to a project).
        """
        path = _resolve(project)
        mode = project_mode(path)
        import contextlib
        import json as _json

        output = path / "output"
        active = output
        current = output / "current.json"
        if current.exists():
            with contextlib.suppress(Exception):
                active = path / _json.loads(current.read_text(encoding="utf-8")).get("run_dir", "output")

        def _count(name: str) -> int:
            p = active / name
            if not p.exists():
                return 0
            try:
                import pandas as pd

                return int(len(pd.read_parquet(p)))
            except Exception:
                return -1

        artefacts = {
            "documents": _count("final_docs.parquet"),
            "text_units": _count("final_text_units.parquet"),
            "entities": _count("final_entities.parquet"),
            "relationships": _count("final_relationships.parquet"),
            "communities": _count("final_communities.parquet"),
            "community_reports": _count("final_community_reports.parquet"),
        }
        memories = path / "memories"
        n_obs = sum(1 for _ in memories.rglob("*.md") if not _.name.startswith(".")) if memories.exists() else 0
        return reply(
            True,
            mode=mode,
            project=project_envelope(path),
            data={"artefacts": artefacts, "observations": n_obs},
        )

    # ------------------------------------------------------------------ memory profile

    if profile in ("memory", "all"):
        _register_memory_tools(mcp, _resolve)

    # ------------------------------------------------------------------ kb profile

    if profile in ("kb", "all"):
        _register_kb_tools(mcp, _resolve)

    return mcp


def _register_memory_tools(mcp, _resolve):
    @mcp.tool()
    def memory_create_project(name: str) -> dict[str, Any]:
        """Create a new memory-mode project. Bare names land in ~/.grail/projects/<name>.

        Memory mode runs with zero LLM for ``memory_recall``; add an embeddings
        stanza to its grail.yaml later if you want semantic recall.
        """
        path = _project_dir_for_new(name)
        mp = open_memory_project(path)  # constructor scaffolds meta.json + memories/
        return reply(
            True,
            mode="memory",
            project=project_envelope(mp.path),
            data={"location": str(mp.path)},
            next_steps=["Add an observation with memory_add_observation"],
        )

    @mcp.tool()
    async def memory_add_observation(
        title: str,
        content: str,
        project: str = "",
        category: str = "",
        tags: list[str] | None = None,
        entities: list[dict[str, Any]] | None = None,
        relationships: list[dict[str, Any]] | None = None,
        observed_at: str = "",
        confidence: float = 1.0,
        source: str = "",
    ) -> dict[str, Any]:
        """Write one memory observation (a markdown note) and merge its graph.

        This is the primary memory write path. ``entities`` is a list of
        ``{"name","type","description?"}`` (type UPPER_SNAKE_CASE, e.g.
        PERSON/ORGANIZATION). ``relationships`` is a list of
        ``{"source","target","relationship_type?","description?"}``. ``category``
        is a folder-style path like ``work/clients/acme`` — it becomes a community.
        """
        path = _resolve(project)
        mp = open_memory_project(path)
        r = await mp.add_observation(
            title=title,
            content=content,
            category=category or None,
            tags=tags,
            entities=entities,
            relationships=relationships,
            observed_at=observed_at or None,
            confidence=confidence,
            source=source or None,
        )
        return reply_from_core(r, path)

    @mcp.tool()
    async def memory_add_entity(
        name: str,
        type: str,
        description: str,
        project: str = "",
        retrieval_queries: list[str] | None = None,
        community_ids: list[str] | None = None,
        confidence: float = 1.0,
        source: str = "",
    ) -> dict[str, Any]:
        """Declare a standalone entity (no source observation).

        Prefer attaching entities to an observation via memory_add_observation —
        this tool warns because the entity gets no provenance. ``retrieval_queries``
        are 2-3 anticipated user questions that sharpen the entity's embedding.
        """
        path = _resolve(project)
        mp = open_memory_project(path)
        r = await mp.add_entity(
            name=name,
            type=type,
            description=description,
            retrieval_queries=retrieval_queries,
            community_ids=community_ids,
            confidence=confidence,
            source=source or None,
        )
        return reply_from_core(r, path)

    @mcp.tool()
    async def memory_add_relationship(
        source: str,
        target: str,
        description: str,
        project: str = "",
        relationship_type: str = "RELATED",
        weight: float = 1.0,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Add a typed relationship between two existing entities.

        ``relationship_type`` is UPPER_SNAKE_CASE (REGULATES, FUNDS, CHOSE, ...).
        Both endpoints should already exist (add them via observations first).
        """
        path = _resolve(project)
        mp = open_memory_project(path)
        r = await mp.add_relationship(
            source=source,
            target=target,
            description=description,
            relationship_type=relationship_type,
            weight=weight,
            confidence=confidence,
        )
        return reply_from_core(r, path)

    @mcp.tool()
    def memory_add_community(
        community_id: str,
        title: str,
        member_entity_names: list[str],
        project: str = "",
        kind: str = "folder",
        report_content: str = "",
        rank: float = 5.0,
        level: int = 0,
    ) -> dict[str, Any]:
        """Declare a community (a named group of entities) with an optional report."""
        path = _resolve(project)
        mp = open_memory_project(path)
        r = mp.add_community(
            community_id=community_id,
            title=title,
            member_entity_names=member_entity_names,
            kind=kind,
            report_content=report_content or None,
            rank=rank,
            level=level,
        )
        return reply_from_core(r, path)

    @mcp.tool()
    async def memory_find_similar_entity(name: str, project: str = "", top_k: int = 5) -> dict[str, Any]:
        """Check for near-duplicate entities before adding one (dedup helper).

        Returns ranked candidates by exact match → embedding cosine → edit
        distance. Use the canonical existing name instead of creating a duplicate.
        """
        path = _resolve(project)
        mp = open_memory_project(path)
        r = await mp.find_similar_entity(name, top_k=top_k)
        return reply_from_core(r, path)

    @mcp.tool()
    async def memory_recall(
        project: str = "",
        query: str = "",
        mode: str = "recall",
        since: str = "",
        before: str = "",
        category: str = "",
        tags: list[str] | None = None,
        entity_names: list[str] | None = None,
        entity_types: list[str] | None = None,
        min_confidence: float | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Recall memories. ``mode=recall`` is a zero-LLM structural filter (default).

        Other modes (``cascade``/``local``/``global``/``document``) synthesize an
        answer with the LLM and require a configured model + a ``query``. Filters
        compose with any mode: ``since``/``before`` accept ISO-8601 or relative
        ("1h", "7d", "2 weeks ago"); ``category`` is a folder glob; ``tags`` /
        ``entity_names`` / ``entity_types`` narrow further.
        """
        path = _resolve(project)
        mp = open_memory_project(path)
        r = await mp.recall(
            query=query or None,
            mode=mode,
            since=since or None,
            before=before or None,
            category=category or None,
            tags=tags,
            entity_names=entity_names,
            entity_types=entity_types,
            min_confidence=min_confidence,
            limit=limit,
        )
        return reply_from_core(r, path)

    @mcp.tool()
    def memory_list_observations(
        project: str = "",
        category: str = "",
        since: str = "",
        before: str = "",
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List observations (id, title, category, tags, observed_at) with filters."""
        path = _resolve(project)
        mp = open_memory_project(path)
        r = mp.list_observations(
            category=category or None, since=since or None, before=before or None, limit=limit
        )
        return reply_from_core(r, path)

    @mcp.tool()
    def memory_list_entities(
        project: str = "", category: str = "", type: str = "", limit: int | None = None
    ) -> dict[str, Any]:
        """List entities (name, type, description, degree) with optional filters."""
        path = _resolve(project)
        mp = open_memory_project(path)
        r = mp.list_entities(category=category or None, type=type or None, limit=limit)
        return reply_from_core(r, path)

    @mcp.tool()
    def memory_list_categories(project: str = "") -> dict[str, Any]:
        """List the distinct memory categories (folder paths) in the project."""
        path = _resolve(project)
        mp = open_memory_project(path)
        return reply_from_core(mp.list_categories(), path)

    @mcp.tool()
    def memory_list_communities(project: str = "") -> dict[str, Any]:
        """List communities (id, title, level, size, kind) in the project."""
        path = _resolve(project)
        mp = open_memory_project(path)
        return reply_from_core(mp.list_communities(), path)

    @mcp.tool()
    def memory_consolidate(project: str = "") -> dict[str, Any]:
        """Run consolidation analyses and surface merge/split/community proposals.

        Writes a proposal set and returns proposals by kind. Review with
        memory_list_proposals, then apply with memory_apply_proposal. Worth
        running once the graph has ~30+ entities.
        """
        path = _resolve(project)
        mp = open_memory_project(path)
        return reply_from_core(mp.consolidate(), path)

    @mcp.tool()
    def memory_list_proposals(project: str = "", status: str = "") -> dict[str, Any]:
        """List consolidation proposals, optionally filtered by status.

        Status is one of pending / accepted / rejected / accepted-pending-manual.
        """
        path = _resolve(project)
        mp = open_memory_project(path)
        return reply_from_core(mp.list_proposals(status=status or None), path)

    @mcp.tool()
    def memory_apply_proposal(
        proposal_id: str, project: str = "", accept: bool = True, reason: str = ""
    ) -> dict[str, Any]:
        """Accept (apply) or reject a consolidation proposal by id prefix."""
        path = _resolve(project)
        mp = open_memory_project(path)
        r = mp.accept_proposal(proposal_id) if accept else mp.reject_proposal(proposal_id, reason=reason or None)
        return reply_from_core(r, path)


def _register_kb_tools(mcp, _resolve):
    @mcp.tool()
    def kb_create_project(name: str) -> dict[str, Any]:
        """Create a knowledge-base project (scaffolds grail.yaml + input/).

        Delegates to ``grail init``. Bare names land in ~/.grail/projects/<name>;
        then drop files into its input/ folder and call kb_index.
        """
        path = _project_dir_for_new(name)
        path.mkdir(parents=True, exist_ok=True)
        display = path.name
        cli = ["grail", "init", str(path), "--name", display]
        if shutil.which("grail") is None:
            cli = [sys.executable, "-m", "grail.cli.main"] + cli[1:]
        proc = subprocess.run(cli, capture_output=True, text=True)
        if proc.returncode != 0:
            return reply(False, error=f"grail init failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return reply(
            True,
            mode="knowledge_base",
            project=project_envelope(path),
            data={"location": str(path)},
            next_steps=[f"Drop files into {path / 'input'}", "Then call kb_index"],
        )

    @mcp.tool()
    async def kb_index(project: str = "", discover_entities: bool = False) -> dict[str, Any]:
        """Build the knowledge graph from the project's input/ files (full pipeline).

        Chunks → extracts entities+relationships → detects communities → writes
        reports. Returns artefact counts and cost. Run after dropping files in.
        """
        from grail.indexing.handlers import UnhandledFileError

        path = _resolve(project)
        grail = load_grail(path)
        if discover_entities:
            try:
                types = await grail.create_entity_types()
                grail.config.indexing.entity_types = types
            except Exception:
                pass
        try:
            result = await grail.index()
        except UnhandledFileError as exc:
            return reply(
                False,
                mode="knowledge_base",
                project=project_envelope(path),
                error=str(exc),
                next_steps=[
                    "Call kb_handlers to see how each input file is classified.",
                    "Register a handler (handlers.custom_paths in grail.yaml) for the "
                    "unknown extension(s), or set handlers.on_unhandled to 'skip'.",
                ],
            )
        return reply(True, mode="knowledge_base", project=project_envelope(path), data=result)

    @mcp.tool()
    def kb_handlers(project: str = "") -> dict[str, Any]:
        """List custom file handlers and classify the project's input/ files.

        Shows which extensions are claimed by custom handlers (and whether each
        describes the file to text or emits entities directly), plus how every
        file currently in input/ will be ingested (builtin / describe / emit /
        unhandled). Use before kb_index to spot files that need a handler.
        """
        path = _resolve(project)
        grail = load_grail(path)
        loader = grail._make_loader()
        return reply(
            True,
            mode="knowledge_base",
            project=project_envelope(path),
            data={
                "handlers": grail.handlers.list_handlers(),
                "on_unhandled": grail.config.handlers.on_unhandled,
                "classification": loader.classify_inputs(),
            },
        )

    @mcp.tool()
    async def kb_append(files: list[str], project: str = "") -> dict[str, Any]:
        """Incrementally add new files to an existing index (no full rebuild)."""
        path = _resolve(project)
        grail = load_grail(path)
        result = await grail.append(files)
        return reply(True, mode="knowledge_base", project=project_envelope(path), data=result)

    @mcp.tool()
    async def kb_edit(replacements: dict[str, str], project: str = "") -> dict[str, Any]:
        """Replace indexed documents incrementally. ``replacements`` maps the
        existing filename to the path of its replacement."""
        path = _resolve(project)
        grail = load_grail(path)
        result = await grail.edit(replacements)
        return reply(True, mode="knowledge_base", project=project_envelope(path), data=result)

    @mcp.tool()
    async def kb_delete(files: list[str], project: str = "") -> dict[str, Any]:
        """Remove documents from the index incrementally (prunes orphan entities)."""
        path = _resolve(project)
        grail = load_grail(path)
        result = await grail.delete(files)
        return reply(True, mode="knowledge_base", project=project_envelope(path), data=result)

    @mcp.tool()
    async def kb_query(
        query: str,
        project: str = "",
        mode: str = "cascade",
        document: str = "",
        since: str = "",
        before: str = "",
        category: str = "",
        tags: list[str] | None = None,
        entity_names: list[str] | None = None,
        entity_types: list[str] | None = None,
        min_confidence: float | None = None,
        rerank: bool | None = None,
    ) -> dict[str, Any]:
        """Query the knowledge base. Pick ``mode`` by question shape:

        - ``cascade`` (default): factual questions / specific details — entity
          gate + BM25 text rescue; most robust.
        - ``local``: named concepts and entities.
        - ``global``: broad / thematic questions (community-report synthesis).
        - ``document``: scope to one file (requires ``document``).
        - ``agent``: complex questions; the LLM picks tools across the above.

        Query tip for local/cascade: phrase as [WHO does it] + [WHAT process] +
        [SPECIFIC TERMS] — it matches entity embeddings far better than keywords.
        Filters (``since``/``before``/``category``/``tags``/...) compose with any mode.
        """
        path = _resolve(project)
        if mode == "document" and not document:
            return reply(False, project=project_envelope(path), error="mode 'document' requires a document filename.")
        from grail.query.recall_filter import RecallFilter

        rfilter = RecallFilter(
            since=since or None,
            before=before or None,
            category=category or None,
            tags=list(tags or []),
            entity_names=list(entity_names or []),
            entity_types=list(entity_types or []),
            min_confidence=min_confidence,
        )
        grail = load_grail(path)
        try:
            if mode == "agent":
                result = await grail.agent_search(query)
            else:
                result = await grail.search(
                    query,
                    mode=mode,
                    document=document or None,
                    use_reranker=rerank,
                    filter=rfilter if not rfilter.is_empty() else None,
                )
        except ValueError as exc:
            return reply(False, project=project_envelope(path), error=f"search failed: {exc}")
        data = search_result_data(
            result,
            search_mode=mode,
            cost=grail.cost_tracker.render_total_cost(),
            filter_active=not rfilter.is_empty(),
        )
        return reply(True, mode="knowledge_base", project=project_envelope(path), data=data)


def main(argv: list[str] | None = None) -> None:
    """Console entry point for ``grail-mcp``."""
    ap = argparse.ArgumentParser(
        prog="grail-mcp",
        description="GRAIL MCP server — knowledge-base and agentic-memory tools.",
    )
    ap.add_argument(
        "--profile",
        choices=["kb", "memory", "all"],
        default=None,
        help="Which toolset to expose. Default: auto from --project, else 'all'.",
    )
    ap.add_argument(
        "--project",
        default=None,
        help="Bind the server to one project (path/name/id). Tools default to it.",
    )
    ap.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport. Default stdio (local). Use streamable-http for remote.",
    )
    ap.add_argument("--port", type=int, default=8000, help="Port for streamable-http transport.")
    ap.add_argument("--version", action="version", version=f"grail-mcp (graphgrail {__version__})")
    args = ap.parse_args(argv)

    # Auto-select profile from the bound project's mode when not given.
    profile = args.profile
    if profile is None:
        if args.project:
            try:
                profile = "memory" if project_mode(resolve_project_ref(args.project)) == "memory" else "kb"
            except Exception:
                profile = "all"
        else:
            profile = "all"

    mcp = build_server(profile=profile, default_project=args.project)
    if args.transport == "streamable-http":
        import contextlib

        with contextlib.suppress(Exception):
            mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
