"""
CLI banner and styled output helpers.

Provided by Nirvai (Nirvana). Author: Benjamin Gonzalez Guerrero.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from grail._version import __version__
from grail.config import Config

GRAIL_BANNER = r"""
 ██████╗ ██████╗  █████╗ ██╗██╗
██╔════╝ ██╔══██╗██╔══██╗██║██║
██║  ███╗██████╔╝███████║██║██║
██║   ██║██╔══██╗██╔══██║██║██║
╚██████╔╝██║  ██║██║  ██║██║███████╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝""".lstrip(
    "\n"
)

_GRADIENT = [
    "#5eead4",  # teal-300
    "#2dd4bf",  # teal-400
    "#14b8a6",  # teal-500
    "#0d9488",  # teal-600
    "#2dd4bf",  # teal-400
    "#5eead4",  # teal-300
]


def _styled_banner() -> Text:
    """Build the ASCII banner as a Rich Text with per-row gradient."""
    lines = GRAIL_BANNER.splitlines()
    text = Text()
    for i, line in enumerate(lines):
        text.append(line, style=f"bold {_GRADIENT[i % len(_GRADIENT)]}")
        if i < len(lines) - 1:
            text.append("\n")
    return text


def print_banner(console: Console) -> None:
    console.print()
    console.print(_styled_banner(), highlight=False)
    console.print(
        f"  Graph RAG with Advanced Integration and Learning  [dim]v{__version__}[/dim]",
    )
    console.print()


def print_config_panel(
    console: Console, config: Config, *, command: str = "index"
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=12)
    table.add_column("value")

    table.add_row("Project", f"[bold white]{config.project_name}[/bold white]")
    table.add_row(
        "LLM",
        f"[cyan]{config.llm.endpoint}[/cyan] [dim]·[/dim] {config.llm.model}",
    )
    table.add_row(
        "Embeddings",
        f"[cyan]{config.embeddings.endpoint}[/cyan] [dim]·[/dim] {config.embeddings.model}",
    )

    root = _display_path(config.resolved_root())
    table.add_row(
        "Storage",
        f"{config.storage.backend} [dim]·[/dim] {root}",
    )

    types = config.indexing.entity_types
    if len(types) > 4:
        types_str = ", ".join(types[:4]) + f" [dim]+{len(types) - 4} more[/dim]"
    else:
        types_str = ", ".join(types)
    table.add_row("Entities", types_str)

    console.print(
        Panel(
            table,
            title=f"[bold]{command.upper()}[/bold]",
            title_align="left",
            border_style="#14b8a6",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )
    console.print()



def _format_duration(seconds: float) -> str:
    if seconds >= 60:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.1f}s"
    return f"{seconds:.1f}s"


def _add_cost_row(table: Table, result: dict[str, Any]) -> None:
    pricing_status = result.get("pricing_status")
    # Per-stage cost breakdown. Stages whose pricing resolved show the dollar
    # amount; stages with no pricing match show "Undefined" (per the canonical
    # message — provider isn't returning prices in the OpenAI Python shape).
    llm_summary = result.get("llm_summary") or {}
    if llm_summary:
        table.add_row("", "")  # spacer
        # Sort by human-pleasing pipeline order, then alphabetically for unknowns.
        order = [
            "entity_extraction",
            "entity_embedding",
            "summarize_description",
            "community_report",
            "json_correction",
            "create_custom_entities",
            "local_search",
            "global_map",
            "global_reduce",
            "query_embedding",
        ]
        ordered = [t for t in order if t in llm_summary] + sorted(
            t for t in llm_summary if t not in order
        )
        for tag in ordered:
            stats = llm_summary[tag]
            total_tokens = stats.get("total_tokens", 0)
            resolved = stats.get("calls_resolved", 0)
            unresolved = stats.get("calls_unresolved", 0)
            calls = stats.get("calls", resolved + unresolved)
            if unresolved == 0:
                # All calls for this stage had pricing → real dollar amount.
                cell = f"[green]${stats.get('cost_usd', 0.0):.4f}[/green]"
            elif resolved == 0:
                # Nothing priced → honest "Undefined" instead of $0.
                cell = "[red]Undefined[/red]"
            else:
                # Mixed: show what we have + flag the unresolved tail.
                cell = (
                    f"[yellow]${stats.get('cost_usd', 0.0):.4f} "
                    f"(partial · {unresolved}/{calls} unpriced)[/yellow]"
                )
            label = tag.replace("_", " ").capitalize()
            table.add_row(f"  {label}", f"{calls:>3} calls · {total_tokens:>7,} tok · {cell}")

    cost_display = result.get("total_cost_display")
    if cost_display:
        colour = "green" if pricing_status == "complete" else "yellow"
        table.add_row("Est. total cost", f"[{colour}]{cost_display}[/{colour}]")
    else:
        cost = result.get("total_cost_usd")
        if cost is not None:
            table.add_row("Est. total cost", f"[green]${cost:.4f}[/green]")


def _display_path(absolute: Path) -> str:
    """Show ``./relative`` when the path is under cwd, otherwise absolute."""
    try:
        return "./" + str(absolute.relative_to(Path.cwd()))
    except ValueError:
        return str(absolute)


def _print_artefact_paths(
    console: Console, result: dict[str, Any], *, root_dir: Path | None = None
) -> None:
    artefacts = result.get("artefacts")
    if not artefacts:
        return
    console.print()
    for label, key in [
        ("Manifest", "manifest"),
        ("Calls log", "llm_calls"),
        ("Summary", "summary"),
    ]:
        rel = artefacts.get(key)
        if not rel:
            continue
        if root_dir is not None:
            path = _display_path((root_dir / rel).resolve())
        else:
            path = rel
        console.print(
            f"  [dim bold]{label:>10}[/dim bold]  [dim]{path}[/dim]",
            soft_wrap=True,
        )


def _result_panel(
    console: Console,
    table: Table,
    *,
    title: str = "COMPLETE",
    border: str = "green",
) -> None:
    console.print()
    console.print(
        Panel(
            table,
            title=f"[bold {border}]{title}[/bold {border}]",
            title_align="left",
            border_style=border,
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )


def _fail_panel(console: Console, result: dict[str, Any]) -> None:
    console.print()
    console.print(
        Panel(
            f"[bold red]Failed:[/bold red] {result.get('reason', 'unknown')}",
            border_style="red",
            box=box.ROUNDED,
        )
    )


def _summary_table() -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=14)
    table.add_column("value", style="bold white")
    return table


# ------------------------------------------------------------------ index

def print_summary(
    console: Console, result: dict[str, Any], *, root_dir: Path | None = None
) -> None:
    if not result.get("ok"):
        _fail_panel(console, result)
        return

    table = _summary_table()
    table.add_row("Duration", _format_duration(result.get("duration_s", 0)))

    if result.get("run_id"):
        table.add_row("Run ID", f"[cyan]{result['run_id']}[/cyan]")

    table.add_row("Documents", str(result.get("documents", 0)))
    table.add_row("Text units", str(result.get("text_units", 0)))
    table.add_row("Entities", str(result.get("entities", 0)))
    table.add_row("Relationships", str(result.get("relationships", 0)))
    table.add_row("Communities", str(result.get("communities", 0)))
    table.add_row("Reports", str(result.get("reports", 0)))

    _add_cost_row(table, result)
    _result_panel(console, table)

    _print_artefact_paths(console, result, root_dir=root_dir)


# ------------------------------------------------------------------ query

def print_query_panel(
    console: Console,
    config: Config,
    *,
    question: str,
    mode: str,
    document: str | None = None,
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=12)
    table.add_column("value")

    table.add_row("Project", f"[bold white]{config.project_name}[/bold white]")

    mode_styles = {
        "local": "[bold cyan]LOCAL[/bold cyan]",
        "global": "[bold magenta]GLOBAL[/bold magenta]",
        "document": "[bold yellow]DOCUMENT[/bold yellow]",
        "agent": "[bold green]AGENT[/bold green]",
    }
    table.add_row("Mode", mode_styles.get(mode, f"[bold]{mode.upper()}[/bold]"))

    lookup_mode = mode if mode in ("local", "global") else "local"
    ep = getattr(config.search, f"{lookup_mode}_search_endpoint", None) or config.llm.endpoint
    model = getattr(config.search, f"{lookup_mode}_search_model", None) or config.llm.model
    table.add_row("LLM", f"[cyan]{ep}[/cyan] [dim]·[/dim] {model}")

    if document:
        table.add_row("Document", f"[bold]{document}[/bold]")

    q_display = question if len(question) <= 60 else question[:57] + "..."
    table.add_row("Question", f"[italic]{q_display}[/italic]")

    console.print(
        Panel(
            table,
            title="[bold]QUERY[/bold]",
            title_align="left",
            border_style="#14b8a6",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )
    console.print()


def print_query_result(
    console: Console,
    response: str,
    *,
    completion_time: float,
    llm_calls: int,
    context_stats: dict[str, int] | None = None,
    cost_display: str | None = None,
    entities_used: list[str] | None = None,
) -> None:
    console.print(
        Panel(
            response,
            title="[bold green]RESPONSE[/bold green]",
            title_align="left",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )
    parts: list[str] = [
        _format_duration(completion_time),
        f"{llm_calls} LLM call{'s' if llm_calls != 1 else ''}",
    ]
    if cost_display:
        parts.append(cost_display)
    console.print(f"  [dim]{'  ·  '.join(parts)}[/dim]")

    if context_stats:
        items = []
        for label, key in [
            ("entities", "entities"),
            ("relationships", "relationships"),
            ("communities", "communities"),
            ("sources", "sources"),
            ("reports", "reports"),
        ]:
            val = context_stats.get(key)
            if val is not None and val > 0:
                items.append(f"{val} {label}")
        if items:
            console.print(f"  [dim]Context: {', '.join(items)}[/dim]")

    if entities_used:
        display = entities_used[:8]
        suffix = f" +{len(entities_used) - 8} more" if len(entities_used) > 8 else ""
        names = ", ".join(display) + suffix
        console.print(f"  [dim]Entities: {names}[/dim]")


# ------------------------------------------------------------------ append

def print_append_panel(
    console: Console,
    config: Config,
    *,
    files: list[str],
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=12)
    table.add_column("value")

    table.add_row("Project", f"[bold white]{config.project_name}[/bold white]")
    table.add_row(
        "LLM",
        f"[cyan]{config.llm.endpoint}[/cyan] [dim]·[/dim] {config.llm.model}",
    )

    if len(files) <= 3:
        files_str = ", ".join(files)
    else:
        files_str = ", ".join(files[:3]) + f" [dim]+{len(files) - 3} more[/dim]"
    table.add_row("Files", files_str)

    console.print(
        Panel(
            table,
            title="[bold]APPEND[/bold]",
            title_align="left",
            border_style="#14b8a6",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )
    console.print()


def print_append_summary(console: Console, result: dict[str, Any]) -> None:
    if not result.get("ok"):
        _fail_panel(console, result)
        return

    table = _summary_table()
    table.add_row("Duration", _format_duration(result.get("duration_s", 0)))
    table.add_row("New files", str(result.get("new_files", 0)))
    table.add_row("New text units", str(result.get("new_text_units", 0)))
    table.add_row("New entities", str(result.get("new_entities", 0)))
    table.add_row("Updated entities", str(result.get("updated_entities", 0)))
    table.add_row("Total entities", str(result.get("total_entities", 0)))
    table.add_row("Total rels", str(result.get("total_relationships", 0)))
    table.add_row("Communities", str(result.get("communities", 0)))
    table.add_row("Reports", str(result.get("reports", 0)))

    _add_cost_row(table, result)
    _result_panel(console, table)


# ------------------------------------------------------------------ edit

def print_edit_panel(
    console: Console,
    config: Config,
    *,
    name: str,
    src: str,
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=12)
    table.add_column("value")

    table.add_row("Project", f"[bold white]{config.project_name}[/bold white]")
    table.add_row(
        "LLM",
        f"[cyan]{config.llm.endpoint}[/cyan] [dim]·[/dim] {config.llm.model}",
    )
    table.add_row("Target", f"[bold]{name}[/bold]")
    table.add_row("Source", _display_path(Path(src).resolve()))

    console.print(
        Panel(
            table,
            title="[bold]EDIT[/bold]",
            title_align="left",
            border_style="#14b8a6",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )
    console.print()


def print_edit_summary(console: Console, result: dict[str, Any]) -> None:
    if not result.get("ok"):
        _fail_panel(console, result)
        return

    table = _summary_table()
    table.add_row("Duration", _format_duration(result.get("duration_s", 0)))
    table.add_row("Edited files", str(result.get("edited_files", 0)))
    table.add_row("Edited TUs", str(result.get("edited_text_units", 0)))
    table.add_row("New entities", str(result.get("new_entities", 0)))
    table.add_row("Updated entities", str(result.get("updated_entities", 0)))
    table.add_row("Deleted entities", str(result.get("deleted_entities", 0)))
    table.add_row("Total entities", str(result.get("total_entities", 0)))
    table.add_row("Total rels", str(result.get("total_relationships", 0)))
    table.add_row("Communities", str(result.get("communities", 0)))

    _add_cost_row(table, result)
    _result_panel(console, table)


# ------------------------------------------------------------------ delete

def print_delete_panel(
    console: Console,
    config: Config,
    *,
    files: list[str],
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=12)
    table.add_column("value")

    table.add_row("Project", f"[bold white]{config.project_name}[/bold white]")

    if len(files) <= 3:
        files_str = ", ".join(files)
    else:
        files_str = ", ".join(files[:3]) + f" [dim]+{len(files) - 3} more[/dim]"
    table.add_row("Removing", f"[bold red]{files_str}[/bold red]")

    console.print(
        Panel(
            table,
            title="[bold]DELETE[/bold]",
            title_align="left",
            border_style="#14b8a6",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )
    console.print()


def print_delete_summary(console: Console, result: dict[str, Any]) -> None:
    if not result.get("ok"):
        _fail_panel(console, result)
        return

    table = _summary_table()
    table.add_row("Duration", _format_duration(result.get("duration_s", 0)))
    table.add_row("Deleted files", str(result.get("deleted_files", 0)))
    table.add_row("Deleted TUs", str(result.get("deleted_text_units", 0)))
    table.add_row("Updated entities", str(result.get("updated_entities", 0)))
    table.add_row("Pruned entities", str(result.get("deleted_entities", 0)))
    table.add_row("Total entities", str(result.get("total_entities", 0)))
    table.add_row("Total rels", str(result.get("total_relationships", 0)))
    table.add_row("Communities", str(result.get("communities", 0)))

    _add_cost_row(table, result)
    _result_panel(console, table)


# ------------------------------------------------------------------ status

def print_status_panel(console: Console, result: dict[str, Any]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=14)
    table.add_column("value")

    table.add_row("Project", f"[bold white]{result.get('project_name', '?')}[/bold white]")
    table.add_row("Storage", f"[dim]{result.get('storage', '?')}[/dim]")

    console.print(
        Panel(
            table,
            title="[bold]STATUS[/bold]",
            title_align="left",
            border_style="#14b8a6",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )

    artefacts = result.get("artefacts", {})
    if artefacts:
        art_table = Table(
            show_header=True, box=box.SIMPLE_HEAVY, padding=(0, 2), expand=False
        )
        art_table.add_column("Artefact", style="bold")
        art_table.add_column("Status")
        for name, exists in artefacts.items():
            icon = "[green]✓[/green]" if exists else "[dim]—[/dim]"
            art_table.add_row(name, icon)
        console.print()
        console.print(art_table)


# ------------------------------------------------------------------ init

def print_init_result(
    console: Console,
    *,
    project_dir: str,
    project_name: str,
    template: str | None = None,
    files_written: list[str] | None = None,
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("key", style="dim bold", min_width=12)
    table.add_column("value")

    table.add_row("Project", f"[bold white]{project_name}[/bold white]")
    table.add_row("Directory", _display_path(Path(project_dir).resolve()))
    if template:
        table.add_row("Template", f"[cyan]{template}[/cyan]")

    if files_written:
        for f in files_written[:5]:
            table.add_row("", f"[dim]  {f}[/dim]")
        if len(files_written) > 5:
            table.add_row("", f"[dim]  +{len(files_written) - 5} more[/dim]")

    _result_panel(console, table, title="SCAFFOLDED")


# ------------------------------------------------------------------ create-entities

def print_entities_result(
    console: Console,
    *,
    types: list[str],
    written: bool = False,
    config_path: str | None = None,
) -> None:
    formatted = ", ".join(f"[bold]{t}[/bold]" for t in types)
    content = f"  {formatted}"
    if written and config_path:
        display = _display_path(Path(config_path).resolve())
        content += f"\n\n  [green]✓[/green] Written to [dim]{display}[/dim]"

    console.print()
    console.print(
        Panel(
            content,
            title="[bold green]ENTITY TYPES[/bold green]",
            title_align="left",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )


# ------------------------------------------------------------------ prompts

def print_prompt_list(
    console: Console,
    prompts: dict[str, str],
    *,
    params: dict[str, list[str]],
) -> None:
    t = Table(
        title="[bold]Available Prompts[/bold]",
        title_style="#14b8a6",
        box=box.SIMPLE_HEAVY,
        padding=(0, 1),
        expand=False,
    )
    t.add_column("Name", style="bold cyan")
    t.add_column("Source", style="dim")
    t.add_column("Required params")
    for name, source in sorted(prompts.items()):
        src_display = _display_path(Path(source).resolve()) if Path(source).exists() else source
        required = ", ".join(params.get(name, []))
        t.add_row(name, src_display, required or "[dim]—[/dim]")
    console.print()
    console.print(t)
    console.print()
    console.print(
        "  [dim]View a prompt:[/dim] [cyan]grail prompt show <name>[/cyan]"
    )
    console.print(
        "  [dim]With sample data:[/dim] [cyan]grail prompt show <name> <project>[/cyan]"
    )


def print_prompt_messages(
    console: Console,
    name: str,
    messages: list[dict[str, Any]],
) -> None:
    console.print()
    role_styles = {
        "system": ("bold magenta", "SYSTEM"),
        "user": ("bold cyan", "USER"),
        "assistant": ("bold green", "ASSISTANT"),
    }
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        style, label = role_styles.get(role, ("bold", role.upper()))
        content = msg.get("content", "")
        console.print(
            Panel(
                content,
                title=f"[{style}]{label}[/{style}] [dim]({i + 1}/{len(messages)})[/dim]",
                title_align="left",
                border_style=style.split()[-1],
                box=box.ROUNDED,
                padding=(1, 1),
            )
        )


# ------------------------------------------------------------------ explore / preview

def print_index_preview(
    console: Console,
    entities: pd.DataFrame,
    relationships: pd.DataFrame,
    community_reports: pd.DataFrame,
    documents: pd.DataFrame,
) -> None:
    """Print a short sample of the indexed data after index or as standalone explore."""
    console.print()

    # --- Top entities by degree ---
    if not entities.empty and "degree" in entities.columns:
        t = Table(
            title="[bold]Top Entities[/bold]",
            title_style="#14b8a6",
            box=box.SIMPLE_HEAVY,
            padding=(0, 1),
            expand=False,
        )
        t.add_column("Entity", style="bold")
        t.add_column("Type", style="cyan")
        t.add_column("Degree", justify="right")
        for _, r in entities.nlargest(8, "degree").iterrows():
            t.add_row(str(r["name"]), str(r.get("type", "")), str(int(r["degree"])))
        console.print(t)

    # --- Top relationships by rank ---
    if not relationships.empty and "rank" in relationships.columns:
        console.print()
        t = Table(
            title="[bold]Top Relationships[/bold]",
            title_style="#14b8a6",
            box=box.SIMPLE_HEAVY,
            padding=(0, 1),
            expand=False,
        )
        t.add_column("Source", style="bold")
        t.add_column("Target", style="bold")
        t.add_column("Weight", justify="right")
        t.add_column("Rank", justify="right")
        for _, r in relationships.nlargest(8, "rank").iterrows():
            t.add_row(
                str(r["source"]), str(r["target"]),
                f"{float(r['weight']):.1f}", str(int(r["rank"])),
            )
        console.print(t)

    # --- Community report titles ---
    if not community_reports.empty and "title" in community_reports.columns:
        console.print()
        t = Table(
            title="[bold]Communities[/bold]",
            title_style="#14b8a6",
            box=box.SIMPLE_HEAVY,
            padding=(0, 1),
            expand=False,
        )
        t.add_column("#", style="dim", justify="right")
        t.add_column("Title", style="bold")
        t.add_column("Rank", justify="right")
        for i, (_, r) in enumerate(
            community_reports.sort_values("rank", ascending=False).iterrows(), 1
        ):
            title = str(r["title"])
            if len(title) > 70:
                title = title[:67] + "..."
            t.add_row(str(i), title, f"{float(r.get('rank', 0)):.1f}")
        console.print(t)

    # --- Entity type distribution ---
    if not entities.empty and "type" in entities.columns:
        console.print()
        type_counts = entities["type"].value_counts()
        t = Table(
            title="[bold]Entity Types[/bold]",
            title_style="#14b8a6",
            box=box.SIMPLE_HEAVY,
            padding=(0, 1),
            expand=False,
        )
        t.add_column("Type", style="cyan bold")
        t.add_column("Count", justify="right")
        for etype, count in type_counts.head(12).items():
            t.add_row(str(etype), str(count))
        if len(type_counts) > 12:
            t.add_row(f"[dim]+{len(type_counts) - 12} more[/dim]", "")
        console.print(t)


def print_explore_overview(
    console: Console,
    *,
    documents: pd.DataFrame,
    text_units: pd.DataFrame,
    entities: pd.DataFrame,
    relationships: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
    nodes: pd.DataFrame,
    mapping: dict[str, Any],
) -> None:
    """Full explore panel: overview counts + detailed tables."""
    # --- Overview ---
    table = _summary_table()
    table.add_row("Documents", str(len(documents)))
    if not documents.empty and "title" in documents.columns:
        titles = ", ".join(documents["title"].tolist())
        if len(titles) > 60:
            titles = titles[:57] + "..."
        table.add_row("", f"[dim]{titles}[/dim]")
    table.add_row("Text units", str(len(text_units)))
    if not text_units.empty and "n_tokens" in text_units.columns:
        table.add_row(
            "",
            f"[dim]{int(text_units['n_tokens'].sum()):,} tokens "
            f"({int(text_units['n_tokens'].min())}–{int(text_units['n_tokens'].max())} per unit)[/dim]",
        )
    table.add_row("Entities", str(len(entities)))
    if not entities.empty and "type" in entities.columns:
        n_types = entities["type"].nunique()
        table.add_row("", f"[dim]{n_types} distinct types[/dim]")
    table.add_row("Relationships", str(len(relationships)))
    table.add_row("Communities", str(len(community_reports)))
    if not nodes.empty and "level" in nodes.columns:
        levels = sorted(nodes["level"].unique())
        table.add_row("", f"[dim]Leiden levels: {levels}[/dim]")

    _result_panel(console, table, title="OVERVIEW", border="#14b8a6")

    # --- Detailed tables ---
    print_index_preview(console, entities, relationships, community_reports, documents)
