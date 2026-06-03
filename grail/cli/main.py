"""
GRAIL command-line interface.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Subcommands:

    grail init <project_dir>                # scaffold an empty project
    grail init --list-templates             # show available built-in templates
    grail index <project_dir>               # full pipeline
    grail append <project_dir> <file...>    # add files + re-index
    grail edit <project_dir> --name X --src Y
    grail delete <project_dir> <file...>
    grail query <project_dir> "<question>"  # --mode local|global
    grail create-entities <project_dir>     # propose entity types
    grail config show <project_dir>
    grail status <project_dir>
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import typer
import yaml
from dotenv import load_dotenv
from rich import print as rprint
from rich.console import Console
from rich.logging import RichHandler

from grail.cli.banner import (
    print_append_panel,
    print_append_summary,
    print_banner,
    print_config_panel,
    print_delete_panel,
    print_delete_summary,
    print_edit_panel,
    print_edit_summary,
    print_entities_result,
    print_explore_overview,
    print_index_preview,
    print_init_result,
    print_prompt_list,
    print_prompt_messages,
    print_query_panel,
    print_query_result,
    print_status_panel,
    print_summary,
)
from grail.config import Config, dump_config, load_config
from grail.core import GRAIL


def _setup_logging(level: str) -> None:
    """Route every ``grail.*`` logger through a Rich handler.

    Resolution: explicit ``--log-level`` > ``GRAIL_LOG_LEVEL`` env var > WARNING.
    Logs from ``openai``, ``httpx``, ``urllib3`` stay at WARNING regardless — the
    OpenAI SDK is chatty at DEBUG and would drown out the actual pipeline output.
    """
    resolved = (level or os.environ.get("GRAIL_LOG_LEVEL") or "WARNING").upper()
    numeric = getattr(logging, resolved, logging.WARNING)

    handler = RichHandler(rich_tracebacks=True, show_time=True, show_path=False, markup=True)
    handler.setLevel(numeric)

    root = logging.getLogger("grail")
    root.setLevel(numeric)
    # Avoid stacking handlers when the CLI is invoked repeatedly in one process.
    if not any(isinstance(h, RichHandler) for h in root.handlers):
        root.addHandler(handler)
    root.propagate = False

    # Keep third-party noise quiet even when we crank GRAIL to DEBUG.
    for noisy in ("openai", "httpx", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

# Built-in templates ship at configs/templates/ in the repo. When the package is
# installed editable, that path is reachable; for a wheel install they'd need to
# be moved under grail/ and referenced via importlib.resources — handle that
# when we cut a non-editable release.
_BUILTIN_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "configs" / "templates"

_TEMPLATE_PLACEHOLDERS = ("name", "root", "date")
_TEMPLATE_FILES = (
    "grail.yaml",
    "endpoints.yaml",
    "llm.yaml",
    "embeddings.yaml",
    "indexing.yaml",
    "community.yaml",
    "search.yaml",
    "storage.yaml",
    "prompts.yaml",
    "vectorstore.yaml",
)


def _discover_templates(extra_dirs: list[Path] | None = None) -> dict[str, Path]:
    """Return {template_name: directory} across built-ins + user dirs.

    User entries override built-ins with the same name (let people patch a
    bundled template without editing the repo).
    """
    out: dict[str, Path] = {}
    if _BUILTIN_TEMPLATES_DIR.exists():
        for p in sorted(_BUILTIN_TEMPLATES_DIR.iterdir()):
            if p.is_dir() and not p.name.startswith("_"):
                out[p.name] = p
    for extra in extra_dirs or []:
        if not extra.exists() or not extra.is_dir():
            continue
        for p in sorted(extra.iterdir()):
            if p.is_dir() and not p.name.startswith("_"):
                out[p.name] = p
    return out


def _render_template(text: str, *, name: str, root: str) -> str:
    """Substitute ``{name}``, ``{root}``, ``{date}`` placeholders. Other ``{…}``
    sequences are left alone (so we don't break unrelated brace usage).
    """
    today = datetime.date.today().isoformat()
    return (
        text.replace("{name}", name)
        .replace("{root}", root)
        .replace("{date}", today)
    )


def _apply_template(
    template_dir: Path, project_dir: Path, *, name: str, overwrite: bool
) -> list[Path]:
    """Copy every recognised YAML in ``template_dir`` into ``project_dir`` with
    placeholder substitution. Returns the list of files written.
    """
    root_abs = str(project_dir.resolve())
    written: list[Path] = []
    for filename in _TEMPLATE_FILES:
        src = template_dir / filename
        if not src.exists():
            continue
        dst = project_dir / filename
        if dst.exists() and not overwrite:
            rprint(f"[yellow]Skipping {dst} (exists; pass --overwrite to replace).[/yellow]")
            continue
        dst.write_text(_render_template(src.read_text(), name=name, root=root_abs))
        written.append(dst)
    return written


def _autoload_env(project_dir: Optional[Path] = None) -> None:
    """Load .env files so users don't have to ``export`` keys manually.

    Resolution order (later wins):
    1. ``<cwd>/.env`` (typically the repo root with all provider keys).
    2. ``<project_dir>/.env`` (project-specific overrides).

    Variables already in the environment are NOT overwritten — explicit shell
    exports take precedence over file values.
    """
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        load_dotenv(cwd_env, override=False)
    if project_dir is not None:
        project_env = project_dir / ".env"
        if project_env.exists() and project_env.resolve() != cwd_env.resolve():
            load_dotenv(project_env, override=False)


class _StyledReporter:
    """CLI reporter that prints styled step messages without a Live display."""

    def __init__(self, console: Console) -> None:
        self._console = console

    def info(self, message: str) -> None:
        self._console.print(f"  [bold #14b8a6]◆[/bold #14b8a6]  {message}")

    def success(self, message: str) -> None:
        self._console.print(f"     [green]✓[/green] {message}")

    def warning(self, message: str) -> None:
        self._console.print(f"     [yellow]⚠[/yellow]  {message}")

    def error(self, message: str) -> None:
        self._console.print(f"     [red]✗[/red] {message}")

    def debug(self, message: str) -> None:
        self._console.print(f"       [dim]{message}[/dim]")

    async def async_info(self, message: str) -> None:
        self.info(message)

    async def async_success(self, message: str) -> None:
        self.success(message)

    async def async_warning(self, message: str) -> None:
        self.warning(message)

    async def async_error(self, message: str) -> None:
        self.error(message)

    def child(self, prefix: str, transient: bool = True) -> "_StyledReporter":
        return self

    def dispose(self) -> None:
        pass


app = typer.Typer(help="GRAIL — Graph RAG with Advanced Integration and Learning.")


@app.callback()
def _global_options(
    log_level: str = typer.Option(
        "",
        "--log-level",
        help="Logging level for grail.* loggers (DEBUG / INFO / WARNING / ERROR). "
        "Defaults to $GRAIL_LOG_LEVEL or WARNING.",
        envvar="GRAIL_LOG_LEVEL",
    ),
) -> None:
    _setup_logging(log_level)


def _load(path: Path) -> Config:
    _autoload_env(path)
    return load_config(path)


def _project_mode(project_dir: Path) -> str:
    """Resolve the project's declared mode.

    Prefers ``meta.json`` (written by ``grail init`` since Phase E) and falls
    back to the ``mode`` field in ``grail.yaml``. Defaults to
    ``knowledge_base`` when nothing declares one — that matches the legacy
    behaviour for pre-Phase-E projects.
    """
    try:
        from grail.memory.identity import read_meta

        meta = read_meta(project_dir)
        if meta is not None and meta.mode:
            return str(meta.mode)
    except Exception:
        pass
    try:
        cfg = load_config(project_dir)
        return str(cfg.mode or "knowledge_base")
    except Exception:
        return "knowledge_base"


def _warn_mode_mismatch(
    project_dir: Path,
    command: str,
    *,
    expects: str,
    alternative: str,
) -> None:
    """Print a yellow warning when a command targets the wrong project mode.

    Never raises — the user can proceed if they know what they're doing.
    """
    actual = _project_mode(project_dir)
    if actual == expects:
        return
    rprint(
        f"[yellow]Note:[/yellow] [bold]{command}[/bold] is designed for "
        f"{expects.replace('_', ' ')} projects; this one is "
        f"[bold]{actual.replace('_', ' ')}[/bold]. {alternative}"
    )


# ----------------------------------------------------------------------- init


_INIT_TEMPLATE = """
# GRAIL project config (knowledge_base mode).
# Drop source files into ./input/ and run `grail index <project>`.

project_name: {name}
root_dir: {root}
mode: knowledge_base

llm:
  endpoint: openai
  model: gpt-4o-mini

embeddings:
  endpoint: deepinfra
  model: intfloat/multilingual-e5-large

indexing:
  entity_types:
    - person
    - organization
    - location
    - event
    - concept

storage:
  backend: local
  root: {root}
"""


_INIT_MEMORY_TEMPLATE = """
# GRAIL project config (memory mode).
# Observations are tool-managed under ./memories/. The agent calls
# MemoryProject.add_observation(...) / add_entity(...) / consolidate() etc.
# Search modes (local, cascade, global, document, recall) work just like KB
# projects — the only difference is the write path.

project_name: {name}
root_dir: {root}
mode: memory

# LLM is OPTIONAL in memory mode. Leave the endpoint/model in place for
# search modes that need it (local/cascade/global/document/agent); set
# ``llm: null`` for a fully zero-LLM project (recall mode + tool writes only).
llm:
  endpoint: openai
  model: gpt-4o-mini

embeddings:
  endpoint: deepinfra
  model: intfloat/multilingual-e5-large

indexing:
  parse_frontmatter: true
  # Memory mode benefits from a bounded vocabulary the agent picks from;
  # leave empty to let the LLM/agent choose freely.
  relationship_types:
    - RELATED
    - MENTIONS
    - WORKS_AT
    - OWNS
    - LOCATED_IN
    - CAUSES
    - PART_OF
    - CONTRADICTS
    - SUPERSEDES
    - OBSERVED_AT
    - ASSOCIATED_WITH
    - DEPENDS_ON
  entity_types:
    - person
    - organization
    - location
    - event
    - concept

memory:
  # consolidate() refuses below this threshold — communities only become
  # useful at scale.
  min_entities_for_consolidate: 30
  # Set true to ``git commit -am`` after every tool write.
  auto_commit: false

storage:
  backend: local
  root: {root}
"""


# Observation file template — copied into ``memories/.template.md`` so the
# agent has a frontmatter scaffold to copy when authoring new observations
# by hand. The MemoryProject SDK doesn't read this file; it exists for humans.
_OBSERVATION_TEMPLATE = """---
title: Untitled observation
category: misc
tags: []
observed_at: 2026-06-01T00:00:00Z
confidence: 1.0
source: human
---

# Observation body

Free-form markdown goes here. The body is what gets chunked and indexed.
"""


@app.command("init")
def init(
    project_dir: Optional[Path] = typer.Argument(None, help="Directory to scaffold."),
    name: Optional[str] = typer.Option(None, help="Project name."),
    overwrite: bool = typer.Option(False, help="Overwrite existing files."),
    memory: bool = typer.Option(
        False, "--memory", help="Scaffold a memory-mode project (memories/, agent tools)."
    ),
    git: Optional[bool] = typer.Option(
        None, "--git/--no-git",
        help="Initialise a git repo. Default: on for memory mode, off for KB mode.",
    ),
    template: Optional[str] = typer.Option(
        None,
        "--template",
        "-t",
        help="Template name from configs/templates/ (built-in) or from --templates-dir.",
    ),
    templates_dir: Optional[Path] = typer.Option(
        None,
        "--templates-dir",
        help="Extra directory to search for user-provided templates.",
    ),
    list_templates: bool = typer.Option(
        False, "--list-templates", help="Print available templates and exit."
    ),
) -> None:
    """Create a new GRAIL project.

    Default mode is ``knowledge_base`` — scaffolds ``input/`` for batch
    indexing. Add ``--memory`` to scaffold ``memories/`` for an agent-driven
    memory project (tool writes via the ``MemoryProject`` SDK).
    """
    extra_dirs = [templates_dir] if templates_dir else []
    discovered = _discover_templates(extra_dirs)

    if list_templates:
        if not discovered:
            rprint("[yellow]No templates found.[/yellow]")
            return
        rprint("[bold]Available templates:[/bold]")
        for tname, tpath in discovered.items():
            origin = "built-in" if tpath.is_relative_to(_BUILTIN_TEMPLATES_DIR) else "user"
            rprint(f"  • {tname:<25}  [dim]({origin}: {tpath})[/dim]")
        rprint(
            "\nUse with: [cyan]grail init <project> --template <name>[/cyan]"
            + (f" --templates-dir {templates_dir}" if templates_dir else "")
        )
        return

    if project_dir is None:
        rprint("[red]Pass a project directory, or use --list-templates.[/red]")
        raise typer.Exit(code=1)

    if memory and template:
        rprint(
            "[red]--memory and --template are mutually exclusive. Templates "
            "ship a specific mode; pick one or the other.[/red]"
        )
        raise typer.Exit(code=1)

    mode = "memory" if memory else "knowledge_base"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)
    if memory:
        (project_dir / "memories").mkdir(exist_ok=True)
    else:
        (project_dir / "input").mkdir(exist_ok=True)

    project_name = name or project_dir.name

    console = Console()
    print_banner(console)

    if template:
        if template not in discovered:
            rprint(f"[red]Template '{template}' not found.[/red]")
            rprint("[dim]Run `grail init --list-templates` to see what's available.[/dim]")
            raise typer.Exit(code=1)
        written = _apply_template(
            discovered[template], project_dir, name=project_name, overwrite=overwrite
        )
        if not written:
            rprint(f"[yellow]Nothing written from template '{template}'.[/yellow]")
            raise typer.Exit(code=1)
        files_written = [str(p.name) for p in written]
    else:
        cfg_path = project_dir / "grail.yaml"
        if cfg_path.exists() and not overwrite:
            rprint(f"[yellow]Refusing to overwrite {cfg_path} (use --overwrite).[/yellow]")
            raise typer.Exit(code=1)
        tpl = _INIT_MEMORY_TEMPLATE if memory else _INIT_TEMPLATE
        cfg_path.write_text(tpl.format(name=project_name, root=str(project_dir.resolve())))
        files_written = ["grail.yaml"]

    # meta.json + workspace registry — always written, regardless of template.
    from grail.memory.identity import (
        ProjectMeta,
        read_meta,
        register_project,
        write_meta,
    )

    existing_meta = read_meta(project_dir)
    if existing_meta is None or overwrite:
        meta = ProjectMeta.fresh(name=project_name, mode=mode)
        write_meta(project_dir, meta)
        register_project(project_dir, meta)
        files_written.append("meta.json")

    if memory:
        # Observation template for humans who hand-author markdown.
        tpl_path = project_dir / "memories" / ".template.md"
        if not tpl_path.exists() or overwrite:
            tpl_path.write_text(_OBSERVATION_TEMPLATE, encoding="utf-8")
            files_written.append("memories/.template.md")

    # Git: opt-in via --git/--no-git. Default ON for memory, OFF for KB.
    do_git = memory if git is None else bool(git)
    if do_git and not (project_dir / ".git").exists():
        import subprocess

        try:
            subprocess.run(
                ["git", "init", "-q"],
                cwd=project_dir,
                check=True,
                capture_output=True,
            )
            files_written.append(".git/")
            # Default .gitignore: skip the output directory; observations
            # live in git but derived artefacts don't need to.
            gi_path = project_dir / ".gitignore"
            if not gi_path.exists():
                gi_path.write_text("output/\n.env\n*.faiss\nfaiss/\n")
                files_written.append(".gitignore")
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            console.print(f"[yellow]git init skipped: {exc}[/yellow]")

    env_path = project_dir / ".env.example"
    if not env_path.exists():
        candidate = Path(__file__).resolve().parents[2] / ".env.example"
        if candidate.exists():
            shutil.copy(candidate, env_path)
            files_written.append(".env.example")

    print_init_result(
        console,
        project_dir=str(project_dir.resolve()),
        project_name=project_name,
        template=template,
        files_written=files_written,
    )
    if memory:
        console.print(
            "  [dim]Add observations via the SDK:[/dim] "
            "[cyan]from grail import MemoryProject[/cyan]"
        )
        console.print(
            "  [dim]Or hand-author markdown under[/dim] [cyan]./memories/[/cyan] "
            "[dim](see .template.md for frontmatter shape)[/dim]"
        )
        console.print(
            "  [dim]Search:[/dim] [cyan]grail query <project> --mode recall --since 1h[/cyan]"
        )
    else:
        console.print(
            "  [dim]Drop input files into ./input and run[/dim] [cyan]grail index <project>[/cyan]"
        )


# ----------------------------------------------------------------------- index


@app.command("index")
def index(
    project_dir: Path = typer.Argument(...),
    discover_entities: Optional[bool] = typer.Option(
        None,
        "--discover-entities/--no-discover-entities",
        help="Use the LLM to discover entity types from the corpus before extraction. "
        "Overrides indexing.discover_entity_types in the config.",
    ),
    vectorstore: Optional[str] = typer.Option(
        None, "--vectorstore", "--vs",
        help="Vector store backend: lancedb (default) | faiss | chromadb.",
    ),
) -> None:
    """Run the full indexing pipeline."""
    console = Console()
    _warn_mode_mismatch(
        project_dir,
        "grail index",
        expects="knowledge_base",
        alternative=(
            "Observations in memory mode are tool-managed via "
            "MemoryProject.add_observation(). Run anyway only if you have "
            "files under ./input/ you want batch-indexed alongside."
        ),
    )
    config = _load(project_dir)

    if discover_entities is not None:
        config.indexing.discover_entity_types = discover_entities

    print_banner(console)
    print_config_panel(console, config, command="index")

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter, vectorstore=vectorstore)
    result = asyncio.run(grail.index())

    print_summary(console, result, root_dir=config.resolved_root())

    if result.get("ok"):
        from grail.query.retrieval import load_artifacts_for_search

        arts = load_artifacts_for_search(grail.storage, grail._output_folder())
        print_index_preview(
            console, arts.entities, arts.relationships,
            arts.community_reports, arts.documents,
        )


# ----------------------------------------------------------------------- query


@app.command("query")
def query(
    project_dir: Path = typer.Argument(...),
    question: str = typer.Argument(""),
    mode: str = typer.Option(
        "local", "--mode", "-m",
        help="local | global | document | cascade | agent | recall",
    ),
    document: Optional[str] = typer.Option(
        None, "--document", "-d",
        help="Document name/path for --mode document.",
    ),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
    rerank: Optional[bool] = typer.Option(
        None, "--rerank/--no-rerank",
        help="Override reranker config for this query. Default: use config setting.",
    ),
    trace: Optional[Path] = typer.Option(
        None, "--trace", "-t",
        help="Directory to write full query trace (prompts, responses, context).",
    ),
    vectorstore: Optional[str] = typer.Option(
        None, "--vectorstore", "--vs",
        help="Vector store backend: lancedb (default) | faiss | chromadb.",
    ),
    # ----------------------------------------------------------- recall filter
    since: Optional[str] = typer.Option(
        None, "--since",
        help="Restrict to observations newer than this. ISO-8601 or relative (1h, 7d).",
    ),
    before: Optional[str] = typer.Option(
        None, "--before",
        help="Restrict to observations older than this. ISO-8601 or relative.",
    ),
    category: Optional[str] = typer.Option(
        None, "--category",
        help="Folder-glob filter (e.g. 'work/clients/**').",
    ),
    tag: list[str] = typer.Option(
        [], "--tag",
        help="Tag filter; repeat for multiple (any-match).",
    ),
    entity_filter: list[str] = typer.Option(
        [], "--entity-name",
        help="Restrict to specific entity name(s); repeat for multiple.",
    ),
    entity_type: list[str] = typer.Option(
        [], "--type",
        help="Restrict to entities of this type (PERSON, ORGANIZATION, ...).",
    ),
    min_confidence: Optional[float] = typer.Option(
        None, "--min-confidence",
        help="Drop entities / TUs whose confidence is below this threshold.",
    ),
) -> None:
    """Answer a question against an indexed project.

    With ``--mode recall`` (or any of the other modes plus filter flags), the
    candidate pool is pre-filtered before scoring. ``recall`` mode itself
    runs no LLM and returns the matching rows directly.
    """
    if mode == "document" and not document:
        rprint("[red]--mode document requires --document <name>.[/red]")
        raise typer.Exit(code=1)
    if mode != "recall" and not question:
        rprint("[red]A question is required for every mode except --mode recall.[/red]")
        raise typer.Exit(code=1)

    console = Console()
    config = _load(project_dir)

    # Build the recall filter (no-op when all flags are unset).
    from grail.query.recall_filter import RecallFilter

    rfilter = RecallFilter(
        since=since,
        before=before,
        category=category,
        tags=list(tag),
        entity_names=list(entity_filter),
        entity_types=list(entity_type),
        min_confidence=min_confidence,
    )

    if output != "json":
        print_banner(console)
        print_query_panel(console, config, question=question or "(no query)", mode=mode, document=document, rerank=rerank)
        if not rfilter.is_empty():
            from rich import print as rprint
            rprint(f"[dim]Recall filter active: {rfilter}[/dim]")

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter, vectorstore=vectorstore)

    # Attach tracer if --trace is given.
    tracer = None
    if trace is not None:
        from grail.query.trace import QueryTracer

        tracer = QueryTracer()
        grail.llm.tracer = tracer

    if mode == "agent":
        result = asyncio.run(grail.agent_search(question))
    else:
        result = asyncio.run(
            grail.search(
                question,
                mode=mode,
                document=document,
                use_reranker=rerank,
                filter=rfilter if not rfilter.is_empty() else None,
            )
        )

    # Write trace if requested.
    trace_path = None
    if tracer is not None and trace is not None:
        context_text = result.context_text if isinstance(result.context_text, str) else "\n\n".join(result.context_text)
        trace_path = tracer.dump(
            trace,
            query=question,
            mode=mode,
            result_response=result.response if isinstance(result.response, str) else json.dumps(result.response, default=str),
            context_text=context_text,
            completion_time=result.completion_time,
            llm_calls=result.llm_calls,
        )
        if output != "json":
            reporter.success(f"Trace written to {trace_path}")

    # Extract context stats from the result for display.
    context_stats: dict[str, int] = {}
    entities_used: list[str] = []
    sources_used: list[dict[str, str]] = []
    if isinstance(result.context_data, dict):
        for key in ("entities", "relationships", "reports", "sources"):
            df = result.context_data.get(key)
            if df is not None and hasattr(df, "__len__"):
                context_stats[key] = len(df)
        ent_df = result.context_data.get("entities")
        if ent_df is not None and hasattr(ent_df, "empty") and not ent_df.empty and "name" in ent_df.columns:
            entities_used = ent_df["name"].tolist()

        from grail.query.retrieval import extract_source_references, load_artifacts_for_search
        artifacts = load_artifacts_for_search(grail.storage, grail._output_folder())
        sources_used = extract_source_references(
            result.context_data,
            documents=artifacts.documents,
            mapping=artifacts.mapping,
        )

    cost_display = grail.cost_tracker.render_total_cost() if grail.cost_tracker.records else None

    if output == "json":
        rprint(
            json.dumps(
                {
                    "response": result.response,
                    "completion_time": result.completion_time,
                    "llm_calls": result.llm_calls,
                    "context_stats": context_stats,
                    "entities_used": entities_used,
                    "sources": sources_used,
                    "cost": cost_display,
                    "trace_path": str(trace_path) if trace_path is not None else None,
                },
                indent=2,
                default=str,
            )
        )
    else:
        raw = result.response if isinstance(result.response, str) else json.dumps(result.response, indent=2)
        response_text = raw.strip()
        print_query_result(
            console,
            response_text,
            completion_time=result.completion_time,
            llm_calls=result.llm_calls,
            context_stats=context_stats,
            cost_display=cost_display,
            entities_used=entities_used,
        )


# ----------------------------------------------------------------------- append / edit / delete


@app.command("append")
def append(
    project_dir: Path = typer.Argument(...),
    files: list[Path] = typer.Argument(..., help="Files to add to the input folder."),
    vectorstore: Optional[str] = typer.Option(
        None, "--vectorstore", "--vs",
        help="Vector store backend: lancedb (default) | faiss | chromadb.",
    ),
) -> None:
    """Add new files to an existing index (incremental update)."""
    console = Console()
    config = _load(project_dir)
    file_names = [f.name for f in files]

    print_banner(console)
    print_append_panel(console, config, files=file_names)

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter, vectorstore=vectorstore)
    result = asyncio.run(grail.append([str(f) for f in files]))

    print_append_summary(console, result)


@app.command("delete")
def delete(
    project_dir: Path = typer.Argument(...),
    files: list[str] = typer.Argument(..., help="Input-folder filenames to remove."),
    vectorstore: Optional[str] = typer.Option(
        None, "--vectorstore", "--vs",
        help="Vector store backend: lancedb (default) | faiss | chromadb.",
    ),
) -> None:
    """Remove files from the index and prune orphaned entities."""
    console = Console()
    config = _load(project_dir)

    print_banner(console)
    print_delete_panel(console, config, files=files)

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter, vectorstore=vectorstore)
    result = asyncio.run(grail.delete(files))

    print_delete_summary(console, result)


@app.command("edit")
def edit(
    project_dir: Path = typer.Argument(...),
    name: str = typer.Option(..., help="Existing filename in the input folder."),
    src: Path = typer.Option(..., help="Local path with replacement content."),
    vectorstore: Optional[str] = typer.Option(
        None, "--vectorstore", "--vs",
        help="Vector store backend: lancedb (default) | faiss | chromadb.",
    ),
) -> None:
    """Replace an existing file and re-extract affected entities."""
    console = Console()
    config = _load(project_dir)

    print_banner(console)
    print_edit_panel(console, config, name=name, src=str(src))

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter, vectorstore=vectorstore)
    result = asyncio.run(grail.edit({name: str(src)}))

    print_edit_summary(console, result)


# ----------------------------------------------------------------------- entity types


@app.command("create-entities")
def create_entities(
    project_dir: Path = typer.Argument(...),
    write: bool = typer.Option(False, help="Persist the proposed entity types into the project config."),
) -> None:
    """Use the LLM to discover entity types from the corpus."""
    console = Console()
    config = _load(project_dir)

    print_banner(console)
    print_config_panel(console, config, command="create-entities")

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter)
    types = asyncio.run(grail.create_entity_types())

    cfg_path: str | None = None
    if write:
        cfg_path_obj = project_dir / "grail.yaml"
        config.indexing.entity_types = types
        dump_config(config, cfg_path_obj)
        cfg_path = str(cfg_path_obj)

    print_entities_result(
        console, types=types, written=write, config_path=cfg_path
    )


# ----------------------------------------------------------------------- config / status


config_app = typer.Typer(help="Inspect and edit configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(project_dir: Path = typer.Argument(...)) -> None:
    """Dump the effective merged configuration."""
    console = Console()
    cfg = _load(project_dir)

    print_banner(console)
    print_config_panel(console, cfg, command="config")
    console.print(yaml.safe_dump(cfg.model_dump(mode="python"), sort_keys=False))


@app.command("status")
def status(project_dir: Path = typer.Argument(...)) -> None:
    """Show which artefacts exist for an indexed project."""
    console = Console()
    config = _load(project_dir)

    print_banner(console)

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter)
    result = grail.status()

    print_status_panel(console, result)


# ----------------------------------------------------------------------- prompts


prompt_app = typer.Typer(help="List and preview prompt templates.")
app.add_typer(prompt_app, name="prompt")


@prompt_app.command("list")
def prompt_list(
    project_dir: Optional[Path] = typer.Argument(
        None, help="Project folder (to pick up custom prompt overrides). Optional."
    ),
) -> None:
    """List all available prompts (built-in + custom overrides)."""
    console = Console()
    print_banner(console)

    from grail.prompts import PromptRegistry

    if project_dir:
        config = _load(project_dir)
        registry = PromptRegistry(
            custom_paths=[Path(p) for p in config.prompts.custom_paths],
            strict=config.prompts.strict,
        )
    else:
        registry = PromptRegistry()

    prompts = registry.discover()
    params: dict[str, list[str]] = {}
    for name in prompts:
        mod = registry.get(name)
        params[name] = list(mod.REQUIRED_PARAMS)

    print_prompt_list(console, prompts, params=params)


@prompt_app.command("show")
def prompt_show(
    name: str = typer.Argument(..., help="Prompt name (e.g. entity_relation, local_search)."),
    project_dir: Optional[Path] = typer.Argument(
        None, help="Project folder — when given, renders the prompt with sample data from the index."
    ),
) -> None:
    """Render a prompt template with sample or placeholder data."""
    console = Console()
    print_banner(console)

    from grail.prompts import PromptRegistry

    if project_dir:
        config = _load(project_dir)
        registry = PromptRegistry(
            custom_paths=[Path(p) for p in config.prompts.custom_paths],
            strict=config.prompts.strict,
        )
    else:
        registry = PromptRegistry()
        config = None

    try:
        mod = registry.get(name)
    except (ImportError, ValueError, KeyError) as exc:
        rprint(f"[red]Prompt '{name}' not found:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"  [dim bold]Prompt:[/dim bold]  [bold cyan]{mod.NAME}[/bold cyan]")
    console.print(f"  [dim bold]Required:[/dim bold] {', '.join(mod.REQUIRED_PARAMS) or '—'}")
    console.print()

    sample_params = _build_sample_params(name, config, project_dir)
    messages = mod.build_messages(**sample_params)
    print_prompt_messages(console, name, messages)


def _build_sample_params(
    name: str, config: Optional[Config], project_dir: Optional[Path]
) -> dict[str, Any]:
    """Build sample kwargs for rendering a prompt.

    When a project_dir is given and already indexed, pulls real snippets from
    the parquet files. Otherwise falls back to readable placeholder strings.
    """
    sample_text = (
        "The World Health Organization (WHO) classifies gliomas into grades I-IV. "
        "Low-grade gliomas (WHO grade II) include diffuse astrocytomas and oligodendrogliomas. "
        "Temozolomide is a standard chemotherapy agent used in glioma treatment."
    )

    # Try to load real data from an indexed project.
    real_text: Optional[str] = None
    real_entity_types: Optional[list[str]] = None
    real_context: Optional[str] = None
    real_entity_name: Optional[str] = None

    if project_dir and config:
        try:
            from grail.query.retrieval import load_artifacts_for_search
            from grail.storage import LocalStorage
            from grail.indexing.run_manifest import resolve_active_run_folder

            storage = LocalStorage(root=config.storage.root)
            out = resolve_active_run_folder(storage, config.indexing.output_folder)
            arts = load_artifacts_for_search(storage, out)

            if not arts.text_units.empty:
                real_text = str(arts.text_units.iloc[0]["text"])[:2000]
            if not arts.entities.empty:
                real_entity_name = str(arts.entities.iloc[0]["name"])
                # Build a small context snippet from entities
                top = arts.entities.nlargest(5, "degree")
                lines = [f"- {r['name']} ({r['type']}): {str(r.get('description', ''))[:100]}" for _, r in top.iterrows()]
                real_context = "\n".join(lines)
            real_entity_types = config.indexing.entity_types
        except Exception:
            pass

    entity_types = real_entity_types or ["PERSON", "ORGANIZATION", "DISEASE", "TREATMENT"]
    input_text = real_text or sample_text
    context = real_context or f"Entities:\n- LOW-GRADE GLIOMA (DISEASE): A type of brain tumor\n- TEMOZOLOMIDE (DRUG): Standard chemotherapy\n- WHO (ORGANIZATION): World Health Organization"

    defaults: dict[str, dict[str, Any]] = {
        "entity_relation": {
            "entity_types": entity_types,
            "input_text": input_text,
        },
        "summarize_description": {
            "entity_name": real_entity_name or "LOW-GRADE GLIOMA",
            "description_list": [
                "A type of brain tumor classified as WHO grade II.",
                "Low-grade gliomas include diffuse astrocytomas and oligodendrogliomas.",
                "These tumors grow slowly but can transform into higher-grade gliomas.",
            ],
        },
        "community_report": {
            "input_text": context,
        },
        "json_correction": {
            "json_string": '{"title": "Sample", "summary": "A test", "findings": [}',
            "exception": "JSONDecodeError: Expecting value: line 1 column 52 (char 51)",
        },
        "create_custom_entities": {
            "texts": [input_text],
            "existing_types": [t for t in entity_types if t not in ("PERSON", "ORGANIZATION")],
            "max_types": 13,
        },
        "local_search": {
            "context_data": context,
            "user_query": "What are the main treatments for gliomas?",
        },
        "global_map": {
            "context_data": context,
            "user_query": "What are the main themes in the indexed documents?",
        },
        "global_reduce": {
            "context_data": context,
            "user_query": "What are the main themes in the indexed documents?",
        },
        "claim_extraction": {
            "entity_specs": "LOW-GRADE GLIOMA, TEMOZOLOMIDE",
            "claim_description": "clinical claims about treatment efficacy",
            "input_text": input_text,
        },
    }
    return defaults.get(name, {})


# ----------------------------------------------------------------------- explore


@app.command("explore")
def explore(
    project_dir: Path = typer.Argument(..., help="Project folder (contains grail.yaml)."),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Inspect the indexed knowledge graph: entities, relationships, communities."""
    console = Console()
    config = _load(project_dir)

    from grail.query.retrieval import SearchArtifacts, load_artifacts_for_search
    from grail.storage import LocalStorage, get_backend

    s_cfg = config.storage
    if s_cfg.backend == "local":
        storage = LocalStorage(root=s_cfg.root)
    else:
        storage = get_backend(
            s_cfg.backend, bucket=s_cfg.s3_bucket, prefix=s_cfg.s3_prefix,
            region_name=s_cfg.s3_region, endpoint_url=s_cfg.s3_endpoint_url,
        )

    from grail.indexing.run_manifest import resolve_active_run_folder

    out = resolve_active_run_folder(storage, config.indexing.output_folder)
    arts = load_artifacts_for_search(storage, out)

    if output == "json":
        data: dict[str, Any] = {
            "project": config.project_name,
            "documents": len(arts.documents),
            "text_units": len(arts.text_units),
            "entities": len(arts.entities),
            "relationships": len(arts.relationships),
            "communities": len(arts.community_reports),
        }
        if not arts.entities.empty:
            data["entity_types"] = arts.entities["type"].value_counts().to_dict()
            data["top_entities"] = (
                arts.entities.nlargest(10, "degree")[["name", "type", "degree"]]
                .to_dict(orient="records")
            )
        if not arts.relationships.empty:
            data["top_relationships"] = (
                arts.relationships.nlargest(10, "rank")[["source", "target", "weight", "rank"]]
                .to_dict(orient="records")
            )
        if not arts.community_reports.empty and "title" in arts.community_reports.columns:
            data["community_titles"] = arts.community_reports["title"].tolist()
        rprint(json.dumps(data, indent=2, default=str))
        return

    print_banner(console)
    print_explore_overview(
        console,
        documents=arts.documents,
        text_units=arts.text_units,
        entities=arts.entities,
        relationships=arts.relationships,
        communities=arts.communities,
        community_reports=arts.community_reports,
        nodes=arts.nodes,
        mapping=arts.mapping,
    )


@app.command("viz")
def viz(
    project_dir: Path = typer.Argument(..., help="Project folder (contains grail.yaml)."),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Where to write the HTML file. Defaults to <project>/graph.html.",
    ),
    open_browser: bool = typer.Option(
        True, "--open/--no-open",
        help="Open the generated file in the default browser.",
    ),
    layout_seed: int = typer.Option(
        42, "--seed", help="Layout seed — same value produces the same layout.",
    ),
    layout_iterations: int = typer.Option(
        200, "--iterations", help="Spring-layout iterations (more = tighter clusters, slower).",
    ),
) -> None:
    """Render a standalone HTML graph viewer powered by Sigma.js.

    The result is a single self-contained .html file you can share by email —
    Sigma.js + Graphology load from CDN, all graph data is embedded inline.
    """
    console = Console()
    _autoload_env(project_dir)

    print_banner(console)

    try:
        from grail.viz import build_visualization
    except ImportError as exc:  # pragma: no cover — defensive; viz has no extra deps today
        rprint(f"[red]Visualization module unavailable:[/red] {exc}")
        raise typer.Exit(1)

    config = _load(project_dir)
    try:
        out_path = build_visualization(
            project_dir=project_dir,
            output_path=output,
            config=config,
            layout_seed=layout_seed,
            layout_iterations=layout_iterations,
        )
    except RuntimeError as exc:
        rprint(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    size_kb = out_path.stat().st_size // 1024
    rprint(f"[green]✓[/green] Wrote [bold]{out_path}[/bold] ([dim]{size_kb} KB[/dim])")

    if open_browser:
        import webbrowser
        webbrowser.open(out_path.resolve().as_uri())
        rprint("[dim]Opened in your default browser.[/dim]")
    else:
        rprint(f"[dim]Open in a browser:[/dim] file://{out_path.resolve()}")


# ================================================================ export-neo4j


@app.command("export-neo4j")
def export_neo4j(
    project_dir: Path = typer.Argument(
        ...,
        help="Path to an indexed GRAIL project.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    uri: Optional[str] = typer.Option(
        None, "--uri",
        help="Neo4j Bolt URI (e.g. neo4j+s://xxx.databases.neo4j.io). Falls back to NEO4J_URI env var.",
    ),
    username: Optional[str] = typer.Option(
        None, "--username", "-u",
        help="Neo4j username. Falls back to NEO4J_USERNAME env var. Default: 'neo4j'.",
    ),
    password: Optional[str] = typer.Option(
        None, "--password", "-p",
        help="Neo4j password. Falls back to NEO4J_PASSWORD env var.",
    ),
    database: str = typer.Option(
        "", "--database", "-d",
        help="Target Neo4j database name. Leave empty for Aura Free (uses server default).",
    ),
    clear: bool = typer.Option(
        False, "--clear",
        help="Wipe the target database before importing (DETACH DELETE all nodes).",
    ),
    no_apoc: bool = typer.Option(
        False, "--no-apoc",
        help="Skip APOC procedures (dynamic entity type labels won't be created).",
    ),
    batch_size: int = typer.Option(
        500, "--batch-size",
        help="Rows per Cypher transaction.",
    ),
) -> None:
    """Export the knowledge graph to a Neo4j database for visualization.

    Pushes entities, relationships, text units, documents, communities, and
    community reports into Neo4j using MERGE statements.  Use the free Neo4j
    Aura tier to get a cloud-hosted instance with the Neo4j Browser for
    interactive graph exploration.

    \b
    Required credentials (via flags or environment variables):
      NEO4J_URI        Bolt URI (e.g. neo4j+s://xxx.databases.neo4j.io)
      NEO4J_USERNAME   Username (default: neo4j)
      NEO4J_PASSWORD   Password

    \b
    Setup guide:
      1. Create a free Neo4j Aura instance at https://neo4j.com/cloud/aura-free/
      2. Copy the connection URI and password from the dashboard
      3. Add to your project's .env file:
           NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
           NEO4J_USERNAME=neo4j
           NEO4J_PASSWORD=your-password
      4. Run: grail export-neo4j <project>
      5. Open the Neo4j Browser from your Aura dashboard to explore the graph
    """
    console = Console()
    _autoload_env(project_dir)

    print_banner(console)

    resolved_uri = uri or os.environ.get("NEO4J_URI", "")
    resolved_username = username or os.environ.get("NEO4J_USERNAME", "neo4j")
    resolved_password = password or os.environ.get("NEO4J_PASSWORD", "")

    if not resolved_uri:
        rprint()
        rprint("[bold red]✗ Neo4j URI not configured[/bold red]")
        rprint()
        rprint("To export your graph to Neo4j you need connection credentials.")
        rprint()
        rprint("[bold]Quick setup:[/bold]")
        rprint()
        rprint("  [dim]1.[/dim] Create a free Neo4j Aura instance at [cyan]https://neo4j.com/cloud/aura-free/[/cyan]")
        rprint("  [dim]2.[/dim] Copy the connection URI and password from the dashboard")
        rprint("  [dim]3.[/dim] Add them to your project's [bold].env[/bold] file:")
        rprint()
        rprint("     [green]NEO4J_URI[/green]=neo4j+s://xxxxxxxx.databases.neo4j.io")
        rprint("     [green]NEO4J_USERNAME[/green]=neo4j")
        rprint("     [green]NEO4J_PASSWORD[/green]=your-password")
        rprint()
        rprint(f"  [dim]4.[/dim] Run again: [bold]grail export-neo4j <project>[/bold]")
        rprint()
        rprint("[dim]Or pass credentials directly:[/dim]")
        rprint(f"  grail export-neo4j <project> --uri neo4j+s://xxx.databases.neo4j.io --password YOUR_PASSWORD")
        rprint()
        raise typer.Exit(1)

    if not resolved_password:
        rprint()
        rprint("[bold red]✗ Neo4j password not configured[/bold red]")
        rprint()
        rprint("Set [green]NEO4J_PASSWORD[/green] in your .env file or pass [bold]--password[/bold].")
        rprint()
        raise typer.Exit(1)

    try:
        from grail.export.neo4j import export_to_neo4j
    except ImportError:
        rprint()
        rprint("[bold red]✗ Missing dependency: neo4j[/bold red]")
        rprint()
        rprint("Install the Neo4j Python driver:")
        rprint("  [bold]pip install neo4j[/bold]")
        rprint()
        raise typer.Exit(1)

    from grail.query.retrieval import load_artifacts_for_search
    from grail.storage import LocalStorage
    from grail.indexing.run_manifest import resolve_active_run_folder

    storage = LocalStorage(project_dir)
    base_output = "output"
    output_folder = resolve_active_run_folder(storage, base_output)
    artifacts = load_artifacts_for_search(storage, output_folder)

    reporter = _StyledReporter(console)

    rprint()
    console.print(f"  [dim]URI:[/dim]       {resolved_uri}")
    console.print(f"  [dim]User:[/dim]      {resolved_username}")
    console.print(f"  [dim]Database:[/dim]  {database or '(server default)'}")
    console.print(f"  [dim]Clear:[/dim]     {'yes' if clear else 'no'}")
    console.print(f"  [dim]APOC:[/dim]      {'disabled' if no_apoc else 'enabled'}")
    rprint()

    try:
        result = export_to_neo4j(
            uri=resolved_uri,
            username=resolved_username,
            password=resolved_password,
            database=database,
            entities=artifacts.entities,
            relationships=artifacts.relationships,
            text_units=artifacts.text_units,
            documents=artifacts.documents,
            communities=artifacts.communities,
            community_reports=artifacts.community_reports,
            batch_size=batch_size,
            clear_graph=clear,
            use_apoc=not no_apoc,
            reporter=reporter,
        )
    except ConnectionError as exc:
        rprint()
        rprint(f"[bold red]✗ Connection failed[/bold red]")
        rprint(f"  {exc}")
        rprint()
        raise typer.Exit(1)
    except ImportError as exc:
        rprint(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1)

    rprint()
    console.print("[bold green]Export summary[/bold green]")
    console.print(f"  Documents:         {result.documents}")
    console.print(f"  Text units:        {result.text_units}")
    console.print(f"  Entities:          {result.entities}")
    console.print(f"  Relationships:     {result.relationships}")
    console.print(f"  Communities:        {result.communities}")
    console.print(f"  Community reports:  {result.community_reports}")
    console.print(f"  Time:              {result.elapsed:.1f}s")
    rprint()
    rprint("[dim]Open the Neo4j Browser from your Aura dashboard to explore the graph.[/dim]")
    rprint()


# ================================================================ ui


@app.command()
def ui(
    project_dir: Path = typer.Argument(
        ...,
        help="Path to an indexed GRAIL project (must contain output/ with artifacts).",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Bind address."
    ),
    port: int = typer.Option(
        8765, "--port", "-p", help="Port to serve on."
    ),
    dev: bool = typer.Option(
        False, "--dev", help="Enable dev mode (CORS for Vite dev server on :5173)."
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Print every LLM prompt and response with colored output."
    ),
) -> None:
    """Launch the GRAIL chat web interface."""
    _autoload_env(project_dir)

    console = Console()
    print_banner(console)

    try:
        from grail.apps.chat.server import run_server
    except ImportError as exc:
        rprint(
            f"[red]Missing dependencies for the chat UI.[/red] "
            f"Install with: [bold]pip install graphgrail\\[ui][/bold]\n{exc}"
        )
        raise typer.Exit(1)

    console.print(
        f"  [dim bold]{'Project':>10}[/dim bold]  [bold white]{project_dir.name}[/bold white]"
    )
    console.print(
        f"  [dim bold]{'URL':>10}[/dim bold]  [cyan]http://{host}:{port}[/cyan]"
    )
    if dev:
        console.print(
            f"  [dim bold]{'Dev mode':>10}[/dim bold]  [yellow]ON[/yellow] — CORS enabled for localhost:5173"
        )
    if debug:
        console.print(
            f"  [dim bold]{'Debug':>10}[/dim bold]  [magenta]ON[/magenta] — LLM prompts and responses will be printed below"
        )
    console.print()

    run_server(project_dir=project_dir, host=host, port=port, dev=dev, debug=debug)


# ================================================================ chat


@app.command()
def chat(
    project_dir: Path = typer.Argument(
        ...,
        help="Path to an indexed GRAIL project (must contain output/ with artifacts).",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    mode: str = typer.Option(
        "agent", "--mode", "-m",
        help="Initial search mode: agent | local | cascade | global | document.",
    ),
    session: Optional[str] = typer.Option(
        None, "--session", "-s",
        help="Resume a specific session by id prefix (or use /resume inside).",
    ),
    db: Optional[Path] = typer.Option(
        None, "--db",
        help="Override SQLite path (default: <project>/.grail/chat.db).",
    ),
) -> None:
    """Interactive terminal chat with the GRAIL agent.

    Streams responses, renders tool calls, supports slash commands, and
    persists sessions to SQLite.  Each launch starts a NEW session by default;
    use /resume inside to list past chats and pick one (or pass --session).
    Type /help inside the chat for a full list of slash commands.
    """
    _autoload_env(project_dir)

    valid_modes = {"agent", "local", "cascade", "global", "document"}
    if mode not in valid_modes:
        rprint(f"[red]Invalid mode '{mode}'.[/red] Valid: {', '.join(sorted(valid_modes))}")
        raise typer.Exit(1)

    try:
        from grail.apps.cli_chat import run_chat
    except ImportError as exc:
        rprint(
            f"[red]Missing dependencies for the chat TUI.[/red] "
            f"Install with: [bold]pip install textual[/bold]\n{exc}"
        )
        raise typer.Exit(1)

    run_chat(project_dir=project_dir, mode=mode, session_id=session, db_path=db)


# ----------------------------------------------------------------------- memory tools


def _open_memory_project(project_dir: Path):
    """Open ``project_dir`` as a MemoryProject. Lazy import — keeps top-level fast."""
    from grail.memory import MemoryProject

    return MemoryProject(project_dir)


@app.command("consolidate")
def consolidate_cmd(
    project_dir: Path = typer.Argument(..., help="Project to consolidate."),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Run the proposal analyses and write the result to output/proposals/.

    Pure read pass — no parquet mutation. Use ``grail proposals list`` to
    browse the result and ``grail proposals apply --accept`` / ``--reject``
    to act on individual proposals.
    """
    console = Console()
    if output != "json":
        print_banner(console)
        _warn_mode_mismatch(
            project_dir,
            "grail consolidate",
            expects="memory",
            alternative=(
                "KB-mode communities are computed at index time. Run "
                "`grail index` to refresh them. ``consolidate`` will still "
                "run here as a proposal pass over the existing graph."
            ),
        )

    mp = _open_memory_project(project_dir)
    reply = mp.consolidate()
    if output == "json":
        # Use plain print: rich's rprint soft-wraps long lines and produces
        # un-parseable JSON.
        print(json.dumps(reply.to_dict(), indent=2, default=str))
        return
    if not reply.ok:
        rprint(f"[yellow]{reply.error}[/yellow]")
        raise typer.Exit(code=1)
    rprint(
        f"\n[bold]Consolidate produced {reply.data['total']} proposal(s)[/bold] "
        f"at [cyan]{reply.data['proposal_set_path']}[/cyan]"
    )
    if reply.data["by_kind"]:
        for kind, count in sorted(reply.data["by_kind"].items()):
            rprint(f"  • {kind:<22} [dim]{count}[/dim]")
    if reply.data["total"]:
        rprint(
            "\n[dim]Review with:[/dim] "
            f"[cyan]grail proposals list {project_dir}[/cyan]"
        )


proposals_app = typer.Typer(help="Browse and apply proposals from ``consolidate``.")
app.add_typer(proposals_app, name="proposals")


@proposals_app.command("list")
def proposals_list(
    project_dir: Path = typer.Argument(...),
    status: Optional[str] = typer.Option(
        None, "--status",
        help="Filter by status: pending | accepted | rejected | accepted-pending-manual",
    ),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """List proposals from the most-recent consolidate run."""
    mp = _open_memory_project(project_dir)
    reply = mp.list_proposals(status=status)
    if output == "json":
        # Use plain print: rich's rprint soft-wraps long lines and produces
        # un-parseable JSON.
        print(json.dumps(reply.to_dict(), indent=2, default=str))
        return
    if not reply.data["proposals"]:
        rprint("[yellow]No proposals found.[/yellow]")
        for hint in reply.next_steps:
            rprint(f"  [dim]→[/dim] {hint}")
        return
    rprint(f"[bold]Proposal set:[/bold] [cyan]{reply.data.get('set_path')}[/cyan]\n")
    for p in reply.data["proposals"]:
        short_id = p["id"][:8]
        rprint(
            f"[bold]{short_id}[/bold]  "
            f"[magenta]{p['kind']:<22}[/magenta]  "
            f"[dim]conf={p['confidence']:.2f}[/dim]  "
            f"[yellow]{p['status']}[/yellow]"
        )
        rprint(f"  {p['rationale']}")
        rprint()


@proposals_app.command("apply")
def proposals_apply(
    project_dir: Path = typer.Argument(...),
    proposal_id: str = typer.Argument(..., help="Proposal id (or unambiguous prefix)."),
    accept: bool = typer.Option(False, "--accept", help="Accept the proposal."),
    reject: bool = typer.Option(False, "--reject", help="Reject the proposal."),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason (for --reject)."),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Accept or reject a single proposal by id."""
    if accept == reject:
        rprint("[red]Pick exactly one of --accept or --reject.[/red]")
        raise typer.Exit(code=1)
    mp = _open_memory_project(project_dir)
    if accept:
        reply = mp.accept_proposal(proposal_id)
    else:
        reply = mp.reject_proposal(proposal_id, reason=reason)
    if output == "json":
        # Use plain print: rich's rprint soft-wraps long lines and produces
        # un-parseable JSON.
        print(json.dumps(reply.to_dict(), indent=2, default=str))
        return
    if not reply.ok:
        rprint(f"[red]{reply.error}[/red]")
        raise typer.Exit(code=1)
    if accept:
        rprint(
            f"[green]Accepted[/green] [bold]{reply.data['proposal_id'][:8]}[/bold] "
            f"({reply.data['kind']}) → status=[yellow]{reply.data['status']}[/yellow]"
        )
        outcome = reply.data.get("outcome") or {}
        if outcome:
            for k, v in outcome.items():
                rprint(f"  [dim]{k}:[/dim] {v}")
    else:
        rprint(f"[yellow]Rejected[/yellow] {reply.data['proposal_id'][:8]}")


# ================================================================ user-add


@app.command("user-add")
def user_add(
    username: str = typer.Argument(..., help="Username to create."),
    db: Path = typer.Option(
        None,
        "--db",
        help="Override chat DB path (default: ~/.grail/chat.db, matches the web UI).",
    ),
) -> None:
    """Create a chat-UI user (works as the first-user bootstrap or to add more)."""
    try:
        from grail.apps.chat.auth import hash_password
        from grail.apps.chat.database import (
            configure_db_path,
            create_user,
            get_user_by_username,
            init_db,
        )
    except ImportError as exc:
        rprint(
            f"[red]Missing dependencies for the chat UI.[/red] "
            f"Install with: pip install graphgrail[ui]\n[dim]{exc}[/dim]"
        )
        raise typer.Exit(code=1)

    if db:
        configure_db_path(db)

    password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    if len(password) < 4:
        rprint("[red]Password must be at least 4 characters.[/red]")
        raise typer.Exit(code=1)

    async def _run() -> None:
        await init_db()
        existing = await get_user_by_username(username)
        if existing:
            rprint(f"[red]User '{username}' already exists.[/red]")
            raise typer.Exit(code=1)
        hashed = hash_password(password)
        user = await create_user(username, hashed)
        rprint(
            f"[green]Created user[/green] [bold]{user['username']}[/bold] "
            f"[dim]({user['id'][:8]})[/dim]"
        )

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    app()
