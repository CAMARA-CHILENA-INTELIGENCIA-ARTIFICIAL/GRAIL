"""Local-storage backend tests."""
from pathlib import Path

import pytest

from grail.storage import LocalStorage


def test_write_and_read_roundtrip(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("docs/hello.txt", "world")
    assert storage.exists("docs/hello.txt")
    assert storage.read_text("docs/hello.txt") == "world"


def test_list_filters_to_files(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("a/one.txt", "1")
    storage.write_text("a/two.txt", "2")
    storage.write_text("b/three.txt", "3")
    keys = storage.list("a")
    assert keys == ["a/one.txt", "a/two.txt"]


def test_delete_removes_file(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("doomed.txt", "x")
    storage.delete("doomed.txt")
    assert not storage.exists("doomed.txt")


def test_traversal_is_blocked(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    with pytest.raises(PermissionError):
        storage.read_text("../escape.txt")


def test_open_for_write_yields_atomic_path(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    with storage.open_for_write("nested/file.txt") as path:
        path.write_text("ok")
    assert storage.read_text("nested/file.txt") == "ok"
