"""``grail init`` with and without ``--memory``."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from grail.cli.main import app


runner = CliRunner()


def _isolate_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect ``~/.grail/registry.json`` into ``tmp_path/home``.

    Both the CLI's ``register_project`` call and tests using ``list_projects``
    pick up the override via the ``HOME`` env var, since identity.registry_path
    uses ``Path.home()``.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_init_kb_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_registry(monkeypatch, tmp_path)
    project = tmp_path / "kb-proj"
    result = runner.invoke(app, ["init", str(project)])
    assert result.exit_code == 0, result.output
    # Scaffolding.
    assert (project / "input").is_dir()
    assert (project / "output").is_dir()
    assert (project / "grail.yaml").exists()
    assert (project / "meta.json").exists()
    # meta.json carries mode=knowledge_base.
    meta = json.loads((project / "meta.json").read_text())
    assert meta["mode"] == "knowledge_base"
    # grail.yaml carries mode field.
    cfg = yaml.safe_load((project / "grail.yaml").read_text())
    assert cfg.get("mode") == "knowledge_base"
    # No memories/ in KB mode.
    assert not (project / "memories").exists()
    # No git by default in KB mode.
    assert not (project / ".git").exists()


def test_init_memory_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_registry(monkeypatch, tmp_path)
    project = tmp_path / "mem-proj"
    result = runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    assert result.exit_code == 0, result.output
    assert (project / "memories").is_dir()
    assert (project / "memories" / ".template.md").exists()
    assert not (project / "input").exists()
    assert (project / "meta.json").exists()
    meta = json.loads((project / "meta.json").read_text())
    assert meta["mode"] == "memory"
    cfg = yaml.safe_load((project / "grail.yaml").read_text())
    assert cfg.get("mode") == "memory"
    # Default-on git would have created .git/; with --no-git, no .git.
    assert not (project / ".git").exists()


def test_init_memory_with_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_registry(monkeypatch, tmp_path)
    project = tmp_path / "mem-git"
    # Explicit --git; defaults aside.
    result = runner.invoke(app, ["init", str(project), "--memory", "--git"])
    # If git isn't on PATH the command should still succeed but print a warning.
    assert result.exit_code == 0, result.output
    # Either .git was created OR a warning was printed (depending on env).
    assert (project / ".git").exists() or "git init skipped" in result.output


def test_init_meta_contains_ulid_and_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_registry(monkeypatch, tmp_path)
    project = tmp_path / "p"
    result = runner.invoke(app, ["init", str(project), "--memory", "--no-git", "--name", "custom"])
    assert result.exit_code == 0, result.output
    meta = json.loads((project / "meta.json").read_text())
    assert meta["name"] == "custom"
    # ULID = 26 Crockford-Base32 chars.
    assert len(meta["id"]) == 26


def test_init_refuses_to_overwrite_without_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_registry(monkeypatch, tmp_path)
    project = tmp_path / "p"
    project.mkdir()
    (project / "grail.yaml").write_text("project_name: existing\n")
    result = runner.invoke(app, ["init", str(project)])
    assert result.exit_code != 0
    assert "Refusing to overwrite" in result.output


def test_init_memory_and_template_mutually_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_registry(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        ["init", str(tmp_path / "p"), "--memory", "--template", "low_cost_setup"],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output
