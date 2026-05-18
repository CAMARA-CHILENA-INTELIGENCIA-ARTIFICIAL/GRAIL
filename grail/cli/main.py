"""
GRAIL command-line interface.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Subcommands:

    grail init <project_dir>                # scaffold an empty project
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
import json
import os
import shutil
from pathlib import Path
from typing import Optional

import typer
import yaml
from dotenv import load_dotenv
from rich import print as rprint

from grail.config import Config, dump_config, load_config
from grail.core import GRAIL
from grail.reporting import RichProgressReporter


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


app = typer.Typer(help="GRAIL — Graph RAG with Advanced Integration and Learning.")


def _load(path: Path) -> Config:
    _autoload_env(path)
    return load_config(path)


def _build(path: Path) -> GRAIL:
    config = _load(path)
    reporter = RichProgressReporter(prefix=f"GRAIL[{config.project_name}]")
    return GRAIL.from_config(config, reporter=reporter)


# ----------------------------------------------------------------------- init


_INIT_TEMPLATE = """\
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

storage:
  backend: local
  root: {root}
"""


@app.command("init")
def init(
    project_dir: Path = typer.Argument(..., help="Directory to scaffold."),
    name: Optional[str] = typer.Option(None, help="Project name."),
    overwrite: bool = typer.Option(False, help="Overwrite an existing config."),
) -> None:
    """Create a new GRAIL project: input/, output/, grail.yaml, sample .env."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "input").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)

    cfg_path = project_dir / "grail.yaml"
    if cfg_path.exists() and not overwrite:
        rprint(f"[yellow]Refusing to overwrite {cfg_path} (use --overwrite).[/yellow]")
        raise typer.Exit(code=1)

    root_abs = str(project_dir.resolve())
    cfg_path.write_text(
        _INIT_TEMPLATE.format(name=name or project_dir.name, root=root_abs)
    )
    env_path = project_dir / ".env.example"
    if not env_path.exists():
        template = Path(__file__).resolve().parents[2] / ".env.example"
        if template.exists():
            shutil.copy(template, env_path)
    rprint(f"[green]✓ Scaffolded project at {project_dir}[/green]")
    rprint(f"  Config: {cfg_path}")
    rprint("  Drop input files into ./input and run `grail index <project>`.")


# ----------------------------------------------------------------------- index


@app.command("index")
def index(project_dir: Path = typer.Argument(...)) -> None:
    """Run the full indexing pipeline."""
    grail = _build(project_dir)
    result = asyncio.run(grail.index())
    rprint(result)


# ----------------------------------------------------------------------- query


@app.command("query")
def query(
    project_dir: Path = typer.Argument(...),
    question: str = typer.Argument(...),
    mode: str = typer.Option("local", "--mode", "-m", help="local | global"),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Answer a question against an indexed project."""
    grail = _build(project_dir)
    result = asyncio.run(grail.search(question, mode=mode))
    if output == "json":
        rprint(
            json.dumps(
                {
                    "response": result.response,
                    "completion_time": result.completion_time,
                    "llm_calls": result.llm_calls,
                },
                indent=2,
            )
        )
    else:
        rprint(result.response)


# ----------------------------------------------------------------------- append / edit / delete


@app.command("append")
def append(
    project_dir: Path = typer.Argument(...),
    files: list[Path] = typer.Argument(..., help="Files to add to the input folder."),
) -> None:
    grail = _build(project_dir)
    result = asyncio.run(grail.append([str(f) for f in files]))
    rprint(result)


@app.command("delete")
def delete(
    project_dir: Path = typer.Argument(...),
    files: list[str] = typer.Argument(..., help="Input-folder filenames to remove."),
) -> None:
    grail = _build(project_dir)
    result = asyncio.run(grail.delete(files))
    rprint(result)


@app.command("edit")
def edit(
    project_dir: Path = typer.Argument(...),
    name: str = typer.Option(..., help="Existing filename in the input folder."),
    src: Path = typer.Option(..., help="Local path with replacement content."),
) -> None:
    grail = _build(project_dir)
    result = asyncio.run(grail.edit({name: str(src)}))
    rprint(result)


# ----------------------------------------------------------------------- entity types


@app.command("create-entities")
def create_entities(
    project_dir: Path = typer.Argument(...),
    write: bool = typer.Option(False, help="Persist the proposed entity types into the project config."),
) -> None:
    grail = _build(project_dir)
    types = asyncio.run(grail.create_entity_types())
    rprint({"entity_types": types})
    if write:
        cfg_path = project_dir / "grail.yaml"
        config = _load(project_dir)
        config.indexing.entity_types = types
        dump_config(config, cfg_path)
        rprint(f"[green]✓ Wrote new entity types to {cfg_path}[/green]")


# ----------------------------------------------------------------------- config / status


config_app = typer.Typer(help="Inspect and edit configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(project_dir: Path = typer.Argument(...)) -> None:
    cfg = _load(project_dir)
    rprint(yaml.safe_dump(cfg.model_dump(mode="python"), sort_keys=False))


@app.command("status")
def status(project_dir: Path = typer.Argument(...)) -> None:
    grail = _build(project_dir)
    rprint(grail.status())


if __name__ == "__main__":  # pragma: no cover
    app()
