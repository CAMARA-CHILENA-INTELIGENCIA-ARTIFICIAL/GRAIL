"""meta.json + ULID + registry tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from grail import MemoryProject
from grail.memory.identity import (
    ProjectMeta,
    list_projects,
    new_ulid,
    read_meta,
    register_project,
    unregister_project,
    write_meta,
)


def test_ulid_format_and_sortability():
    a = new_ulid()
    assert len(a) == 26
    # ULIDs minted just-after should sort >= just-before.
    import time
    time.sleep(0.002)
    b = new_ulid()
    assert b > a or b == a


def test_ulid_uniqueness_in_a_burst():
    ids = {new_ulid() for _ in range(500)}
    assert len(ids) == 500


def test_project_init_writes_meta_and_registers(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "my-mem"
    mp = MemoryProject(project, registry_home=home, name="my-mem")
    assert mp.meta.mode == "memory"
    assert mp.meta.name == "my-mem"
    assert len(mp.meta.id) == 26
    # meta.json on disk
    meta_path = project / "meta.json"
    assert meta_path.exists()
    on_disk = json.loads(meta_path.read_text())
    assert on_disk["mode"] == "memory"
    assert on_disk["id"] == mp.meta.id
    # registry knows about the project
    entries = list_projects(home=home)
    assert any(e["id"] == mp.meta.id for e in entries)
    assert any(e["path"] == str(project.resolve()) for e in entries)


def test_reopen_existing_project_keeps_id(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "p"
    first = MemoryProject(project, registry_home=home, name="p")
    first_id = first.meta.id
    # New instance opens the same dir.
    second = MemoryProject(project, registry_home=home)
    assert second.meta.id == first_id
    assert second.meta.name == "p"


def test_unregister_removes_entry(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "p"
    mp = MemoryProject(project, registry_home=home, name="p")
    assert unregister_project(mp.meta.id, home=home)
    assert not any(e["id"] == mp.meta.id for e in list_projects(home=home))
    # Idempotent second remove returns False.
    assert not unregister_project(mp.meta.id, home=home)


def test_scaffolding_creates_expected_folders(tmp_path: Path):
    project = tmp_path / "scaffold"
    MemoryProject(project, registry_home=tmp_path / "home")
    assert (project / "memories").is_dir()
    assert (project / "output").is_dir()
