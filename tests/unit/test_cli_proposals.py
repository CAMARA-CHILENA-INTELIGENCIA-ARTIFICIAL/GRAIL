"""``grail consolidate`` / ``grail proposals`` CLI tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from grail import MemoryProject
from grail.cli.main import app


runner = CliRunner()


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


async def _populate(project: Path) -> MemoryProject:
    mp = MemoryProject(project, embeddings=None)
    mp.config.memory.min_entities_for_consolidate = 3
    # Persist the threshold override into grail.yaml so the fresh CLI process
    # sees it. Just mutate the file directly — quick + reliable.
    cfg = yaml.safe_load((project / "grail.yaml").read_text())
    cfg.setdefault("memory", {})["min_entities_for_consolidate"] = 3
    (project / "grail.yaml").write_text(yaml.safe_dump(cfg))
    # Build a discoverable cross-folder pattern.
    await mp.add_observation(
        title="w",
        content="...",
        category="work",
        entities=[
            {"name": "ALICE", "type": "PERSON", "description": "rep"},
            {"name": "BOB", "type": "PERSON", "description": "eng"},
            {"name": "CARLOS", "type": "PERSON", "description": "pm"},
            {"name": "ACME", "type": "ORG", "description": "client"},
        ],
        relationships=[
            {"source": "ALICE", "target": "BOB", "description": "x"},
            {"source": "ALICE", "target": "CARLOS", "description": "x"},
            {"source": "BOB", "target": "CARLOS", "description": "x"},
            {"source": "ALICE", "target": "ACME", "description": "x"},
            {"source": "BOB", "target": "ACME", "description": "x"},
            {"source": "CARLOS", "target": "ACME", "description": "x"},
        ],
    )
    await mp.add_observation(
        title="p",
        content="...",
        category="personal",
        entities=[
            {"name": "ALICE", "type": "PERSON", "description": "friend"},
            {"name": "BOB", "type": "PERSON", "description": "friend"},
        ],
        relationships=[{"source": "ALICE", "target": "BOB", "description": "x"}],
    )
    return mp


@pytest.mark.asyncio
async def test_cli_consolidate_writes_proposal_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    init = runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    assert init.exit_code == 0, init.output
    await _populate(project)
    result = runner.invoke(app, ["consolidate", str(project)])
    assert result.exit_code == 0, result.output
    assert "proposal" in result.output.lower()
    # File exists on disk.
    proposals_dir = project / "output" / "proposals"
    yamls = [p for p in proposals_dir.glob("*.yaml") if p.name != "latest.yaml"]
    assert yamls
    assert (proposals_dir / "latest.yaml").exists()


@pytest.mark.asyncio
async def test_cli_proposals_list_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    result = runner.invoke(app, ["proposals", "list", str(project)])
    assert result.exit_code == 0
    assert "No proposals" in result.output


@pytest.mark.asyncio
async def test_cli_proposals_list_after_consolidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    await _populate(project)
    runner.invoke(app, ["consolidate", str(project)])
    result = runner.invoke(app, ["proposals", "list", str(project)])
    assert result.exit_code == 0
    assert "discover_community" in result.output


@pytest.mark.asyncio
async def test_cli_proposals_apply_accept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    await _populate(project)
    consolidate = runner.invoke(app, ["consolidate", str(project), "--output", "json"])
    payload = json.loads(consolidate.output)
    # Pick the first discover_community proposal.
    target = next(
        p for p in payload["data"]["proposals"] if p["kind"] == "discover_community"
    )
    accept = runner.invoke(
        app,
        ["proposals", "apply", str(project), target["id"], "--accept"],
    )
    assert accept.exit_code == 0, accept.output
    assert "Accepted" in accept.output


@pytest.mark.asyncio
async def test_cli_proposals_apply_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    await _populate(project)
    consolidate = runner.invoke(app, ["consolidate", str(project), "--output", "json"])
    payload = json.loads(consolidate.output)
    target = payload["data"]["proposals"][0]
    result = runner.invoke(
        app,
        ["proposals", "apply", str(project), target["id"], "--reject", "--reason", "no"],
    )
    assert result.exit_code == 0, result.output
    assert "Rejected" in result.output


def test_cli_proposals_apply_requires_one_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    # Neither --accept nor --reject.
    result = runner.invoke(app, ["proposals", "apply", str(project), "abc"])
    assert result.exit_code != 0
    assert "exactly one" in result.output


def test_cli_proposals_apply_both_flags_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_home(monkeypatch, tmp_path)
    project = tmp_path / "p"
    runner.invoke(app, ["init", str(project), "--memory", "--no-git"])
    result = runner.invoke(
        app, ["proposals", "apply", str(project), "abc", "--accept", "--reject"]
    )
    assert result.exit_code != 0
