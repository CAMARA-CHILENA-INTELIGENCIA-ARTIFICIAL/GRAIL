"""``grail handlers list`` / ``grail handlers check`` smoke tests."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from grail.cli.main import app

runner = CliRunner()


def _init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "kb"
    result = runner.invoke(app, ["init", str(project)])
    assert result.exit_code == 0, result.output
    return project


def _add_handler(project: Path) -> None:
    handlers_dir = project / "handlers"
    handlers_dir.mkdir()
    (handlers_dir / "h.py").write_text(
        "from grail.indexing.handlers import FileHandler\n"
        "class H(FileHandler):\n"
        "    NAME='xyz'\n"
        "    EXTENSIONS=frozenset({'.xyz'})\n"
        "    async def describe(self, source, ctx):\n"
        "        return 'x'\n"
        "HANDLER = H()\n"
    )
    cfg = project / "grail.yaml"
    cfg.write_text(cfg.read_text() + "\nhandlers:\n  custom_paths: [\"handlers\"]\n")


def test_handlers_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = _init(tmp_path, monkeypatch)
    result = runner.invoke(app, ["handlers", "list", str(project)])
    assert result.exit_code == 0, result.output
    assert "No custom handlers" in result.output


def test_handlers_list_and_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = _init(tmp_path, monkeypatch)
    _add_handler(project)
    (project / "input" / "data.xyz").write_text("hello")
    (project / "input" / "mystery.weird").write_text("???")

    out = runner.invoke(app, ["handlers", "list", str(project)])
    assert out.exit_code == 0, out.output
    assert "xyz" in out.output

    chk = runner.invoke(app, ["handlers", "check", str(project)])
    assert chk.exit_code == 0, chk.output
    assert "describe" in chk.output
    assert "unhandled" in chk.output
