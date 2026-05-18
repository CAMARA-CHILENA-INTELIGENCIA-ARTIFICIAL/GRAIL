"""FileLoader tests (no LLM required)."""
from pathlib import Path

from grail.indexing.loader import FileLoader
from grail.storage import LocalStorage


def test_build_text_units_creates_docs_and_chunks(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/a.txt", "Alice is a researcher who works on quantum biology.")
    storage.write_text("input/b.txt", "Bob is a software engineer specialising in graph databases.")

    loader = FileLoader(storage=storage, chunk_size=500, chunk_overlap=20)
    docs_df, units_df, mapping = loader.build_text_units()
    loader.write_artifacts(docs_df, units_df, mapping)

    assert len(docs_df) == 2
    assert "a.txt" in docs_df["title"].tolist()
    assert len(units_df) >= 1
    # Every text unit should record the contributing document(s).
    for _, row in units_df.iterrows():
        assert isinstance(row["document_ids"], list)
        assert all(isinstance(d, str) for d in row["document_ids"])
    # Mapping should be keyed by doc id and carry the original path.
    for doc_id, info in mapping.items():
        assert "original_path" in info


def test_load_artifacts_returns_empty_when_missing(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    loader = FileLoader(storage=storage)
    docs_df, units_df, mapping = loader.load_artifacts()
    assert docs_df.empty
    assert units_df.empty
    assert mapping == {}


def test_unsupported_extensions_are_ignored(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/keep.md", "hello")
    storage.write_text("input/skip.bin", "binary content placeholder")
    storage.write_bytes("input/img.png", b"\x89PNG\r\n\x1a\n")
    loader = FileLoader(storage=storage)
    keys = loader.find()
    assert any(k.endswith("keep.md") for k in keys)
    assert all(not k.endswith("img.png") for k in keys)
