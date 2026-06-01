"""Tests for YAML frontmatter parsing in the loader."""
from __future__ import annotations

import json
from pathlib import Path

from grail.indexing.loader import FileLoader, parse_frontmatter
from grail.storage import LocalStorage


def test_parse_frontmatter_extracts_yaml_block():
    text = (
        "---\n"
        "title: Meeting notes\n"
        "category: work/clients/acme\n"
        "tags: [meeting, pricing]\n"
        "confidence: 0.9\n"
        "---\n"
        "# Meeting notes\n\nAlice said pricing should drop 15%.\n"
    )
    fm, body = parse_frontmatter(text)
    assert fm["title"] == "Meeting notes"
    assert fm["category"] == "work/clients/acme"
    assert fm["tags"] == ["meeting", "pricing"]
    assert fm["confidence"] == 0.9
    assert body.startswith("# Meeting notes")
    assert "Alice said pricing" in body


def test_parse_frontmatter_no_block():
    text = "# Just a normal markdown file\n\nNothing fancy here.\n"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == text


def test_parse_frontmatter_malformed_yaml_returns_empty():
    # Truly malformed YAML — tab indentation in a flow mapping confuses PyYAML.
    text = "---\nfoo: {bar: 1,\n\tbaz: 2}\n---\n\nBody.\n"
    fm, body = parse_frontmatter(text)
    # Lenient by design — malformed YAML should not drop the file content.
    assert fm == {}
    # Body is returned untouched when YAML parsing fails.
    assert "Body." in body


def test_parse_frontmatter_yaml_list_returns_empty():
    # A YAML block that parses to a non-dict (e.g. a list) should also be
    # ignored — only dict frontmatter is meaningful.
    text = "---\n- item1\n- item2\n---\n\nBody.\n"
    fm, body = parse_frontmatter(text)
    assert fm == {}


def test_loader_lifts_known_keys_to_doc_columns(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text(
        "input/obs.md",
        "---\n"
        "title: Acme meeting\n"
        "category: work/clients/acme\n"
        "tags: [meeting, Q2]\n"
        "observed_at: '2026-05-27T15:30:00Z'\n"
        "confidence: 0.9\n"
        "source: agent-claude\n"
        "custom_field: hello\n"
        "---\n"
        "# Acme meeting\n\nBody content here.\n",
    )
    loader = FileLoader(storage=storage, chunk_size=500, chunk_overlap=20)
    docs_df, units_df, _ = loader.build_text_units()

    assert len(docs_df) == 1
    row = docs_df.iloc[0]
    assert row["title"] == "Acme meeting"
    assert row["category"] == "work/clients/acme"
    assert row["tags"] == ["meeting", "Q2"]

    # Unknown keys land in the attributes JSON blob.
    attrs = json.loads(row["attributes"])
    assert attrs == {"custom_field": "hello"}

    # Text units inherit provenance from the document.
    tu = units_df.iloc[0]
    assert tu["observed_at"] == "2026-05-27T15:30:00Z"
    assert tu["confidence"] == 0.9
    assert tu["source"] == "agent-claude"

    # Body content was chunked; frontmatter was stripped.
    assert "Body content here" in tu["text"]
    assert "title:" not in tu["text"]


def test_loader_disabled_frontmatter_keeps_yaml_in_text(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text(
        "input/obs.md",
        "---\ntitle: Won't be parsed\n---\nBody.\n",
    )
    loader = FileLoader(storage=storage, parse_frontmatter=False)
    docs_df, units_df, _ = loader.build_text_units()

    assert len(docs_df) == 1
    # With parsing off, the YAML block stays in raw_content and the chunk text.
    assert "title: Won't be parsed" in docs_df.iloc[0]["raw_content"]
    assert any("title:" in t for t in units_df["text"])
    # Title falls back to the filename.
    assert docs_df.iloc[0]["title"] == "obs.md"


def test_loader_non_markdown_does_not_parse_frontmatter(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    # .txt file with a leading --- block — shouldn't be parsed as frontmatter
    # because frontmatter only applies to markdown.
    storage.write_text(
        "input/a.txt",
        "---\ntitle: Looks like frontmatter\n---\nBody.\n",
    )
    loader = FileLoader(storage=storage)
    docs_df, units_df, _ = loader.build_text_units()
    assert docs_df.iloc[0]["category"] is None
    assert "title: Looks like frontmatter" in units_df.iloc[0]["text"]
