"""Mode-mismatch warnings on CLI commands."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from grail.cli.main import _project_mode, app


runner = CliRunner()


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


def test_project_mode_resolves_from_meta_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    assert _project_mode(project) == "memory"


def test_project_mode_defaults_to_knowledge_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_home(monkeypatch, tmp_path)
    # Empty project dir → no meta, no config → defaults.
    assert _project_mode(tmp_path) == "knowledge_base"


def test_index_on_memory_project_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    # Index should still attempt to run (and probably fail because no LLM is
    # actually configured to call), but the warning must be emitted.
    result = runner.invoke(app, ["index", str(project)])
    assert "designed for knowledge base" in result.output


def test_consolidate_on_kb_project_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project)])  # KB by default
    result = runner.invoke(app, ["consolidate", str(project)])
    # Either we see the warning or the consolidate refusal — both are
    # acceptable evidence that the mode check is wired.
    assert "designed for memory" in result.output or "refuses below" in result.output


def test_consolidate_on_memory_project_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    result = runner.invoke(app, ["consolidate", str(project)])
    assert "designed for memory" not in result.output


def test_index_on_kb_project_no_mode_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project)])
    result = runner.invoke(app, ["index", str(project)])
    # ``grail index`` may fail later because no input files exist, but the
    # mode-mismatch warning specifically must not appear on a KB project.
    assert "designed for knowledge base" not in result.output
