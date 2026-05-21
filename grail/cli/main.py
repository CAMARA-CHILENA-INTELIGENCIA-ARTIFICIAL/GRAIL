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


# ----------------------------------------------------------------------- init


_INIT_TEMPLATE = """
# GRAIL project config.
# Endpoints (base_url + api_key_env per name) come from configs/endpoints.yaml in
# the repo by default — every built-in (openai, anthropic, deepinfra, together,
# groq, openrouter, ollama, vllm, sglang, lmstudio, local) is available out of
# the box. To override or add your own, drop an `endpoints.yaml` next to this
# file with just the entries you need:
#
#   endpoints:
#     my-vllm:
#       base_url: http://my-vllm:8000/v1
#       api_key_env: MY_VLLM_KEY
#       requires_key: false

project_name: {name}
root_dir: {root}

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
  # Let the LLM propose additional entity types from the corpus before extraction.
  # discover_entity_types: false
  # max_entity_types: 15
  # Extraction delimiters — the parser is bound to these tokens.
  # Uncomment only if you customise the entity_relation prompt.
  # tuple_delimiter: "<|>"
  # record_delimiter: "##"
  # completion_delimiter: "<|COMPLETE|>"
  # start_delimiter: "<|START_OUTPUT|>"
  # Token budgets per LLM call:
  # extraction_max_tokens: 8192
  # entity_discovery_max_tokens: 2048
  # max_summarization_tokens: 756

storage:
  backend: local
  root: {root}
"""


@app.command("init")
def init(
    project_dir: Optional[Path] = typer.Argument(None, help="Directory to scaffold."),
    name: Optional[str] = typer.Option(None, help="Project name."),
    overwrite: bool = typer.Option(False, help="Overwrite existing files."),
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
    """Create a new GRAIL project: input/, output/, grail.yaml, sample .env."""
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

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "input").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)

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
        cfg_path.write_text(
            _INIT_TEMPLATE.format(name=project_name, root=str(project_dir.resolve()))
        )
        files_written = ["grail.yaml"]

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
) -> None:
    """Run the full indexing pipeline."""
    console = Console()
    config = _load(project_dir)

    if discover_entities is not None:
        config.indexing.discover_entity_types = discover_entities

    print_banner(console)
    print_config_panel(console, config, command="index")

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter)
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
    question: str = typer.Argument(...),
    mode: str = typer.Option("local", "--mode", "-m", help="local | global | document | agent"),
    document: Optional[str] = typer.Option(
        None, "--document", "-d",
        help="Document name/path for --mode document.",
    ),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Answer a question against an indexed project."""
    if mode == "document" and not document:
        rprint("[red]--mode document requires --document <name>.[/red]")
        raise typer.Exit(code=1)

    console = Console()
    config = _load(project_dir)

    if output != "json":
        print_banner(console)
        print_query_panel(console, config, question=question, mode=mode, document=document)

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter)

    if mode == "agent":
        result = asyncio.run(grail.agent_search(question))
    else:
        result = asyncio.run(grail.search(question, mode=mode, document=document))

    # Extract context stats from the result for display.
    context_stats: dict[str, int] = {}
    entities_used: list[str] = []
    if isinstance(result.context_data, dict):
        for key in ("entities", "relationships", "reports", "sources"):
            df = result.context_data.get(key)
            if df is not None and hasattr(df, "__len__"):
                context_stats[key] = len(df)
        ent_df = result.context_data.get("entities")
        if ent_df is not None and hasattr(ent_df, "empty") and not ent_df.empty and "name" in ent_df.columns:
            entities_used = ent_df["name"].tolist()

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
                    "cost": cost_display,
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
) -> None:
    """Add new files to an existing index (incremental update)."""
    console = Console()
    config = _load(project_dir)
    file_names = [f.name for f in files]

    print_banner(console)
    print_append_panel(console, config, files=file_names)

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter)
    result = asyncio.run(grail.append([str(f) for f in files]))

    print_append_summary(console, result)


@app.command("delete")
def delete(
    project_dir: Path = typer.Argument(...),
    files: list[str] = typer.Argument(..., help="Input-folder filenames to remove."),
) -> None:
    """Remove files from the index and prune orphaned entities."""
    console = Console()
    config = _load(project_dir)

    print_banner(console)
    print_delete_panel(console, config, files=files)

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter)
    result = asyncio.run(grail.delete(files))

    print_delete_summary(console, result)


@app.command("edit")
def edit(
    project_dir: Path = typer.Argument(...),
    name: str = typer.Option(..., help="Existing filename in the input folder."),
    src: Path = typer.Option(..., help="Local path with replacement content."),
) -> None:
    """Replace an existing file and re-extract affected entities."""
    console = Console()
    config = _load(project_dir)

    print_banner(console)
    print_edit_panel(console, config, name=name, src=str(src))

    reporter = _StyledReporter(console)
    grail = GRAIL.from_config(config, reporter=reporter)
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


if __name__ == "__main__":  # pragma: no cover
    app()
