"""Tests for the lazy in-memory schema migration."""
from __future__ import annotations

import pandas as pd

from grail.indexing.schema_migration import migrate_dataframe, needs_migration


def test_entities_get_phase_a_columns():
    # Pre-Phase-A entities had no community_ids / observed_at / confidence / source.
    df = pd.DataFrame([
        {"id": "e1", "name": "ALICE", "type": "PERSON", "description": "..."}
    ])
    assert needs_migration(df, "final_entities")
    out = migrate_dataframe(df, "final_entities")
    assert "community_ids" in out.columns
    assert "observed_at" in out.columns
    assert "confidence" in out.columns
    assert "source" in out.columns
    # Defaults are sensible.
    row = out.iloc[0]
    assert row["community_ids"] == []
    assert row["observed_at"] is None
    assert row["confidence"] == 1.0
    assert row["source"] is None


def test_relationships_legacy_type_carries_to_relationship_type():
    # Pre-rename parquets used ``type``; the migration carries them forward.
    df = pd.DataFrame([
        {"id": "r1", "source": "ALICE", "target": "BOB", "type": "WORKS_AT"},
        {"id": "r2", "source": "BOB", "target": "CARLOS", "type": None},
    ])
    out = migrate_dataframe(df, "final_relationships")
    assert "relationship_type" in out.columns
    assert out.iloc[0]["relationship_type"] == "WORKS_AT"
    # Null legacy types should default to RELATED.
    assert out.iloc[1]["relationship_type"] == "RELATED"


def test_relationships_no_legacy_type_gets_default():
    df = pd.DataFrame([
        {"id": "r1", "source": "ALICE", "target": "BOB", "description": "..."},
    ])
    out = migrate_dataframe(df, "final_relationships")
    assert out.iloc[0]["relationship_type"] == "RELATED"


def test_communities_gain_kind_column():
    df = pd.DataFrame([
        {"id": "0-1", "level": 0, "community": "1", "size": 5},
    ])
    out = migrate_dataframe(df, "final_communities")
    assert out.iloc[0]["kind"] == "leiden"


def test_reports_gain_source_and_source_path():
    df = pd.DataFrame([
        {"community": "1", "title": "T", "summary": "s", "rank": 5.0},
    ])
    out = migrate_dataframe(df, "final_community_reports")
    assert out.iloc[0]["source"] == "llm"
    assert out.iloc[0]["source_path"] is None


def test_docs_gain_category_tags_attributes():
    df = pd.DataFrame([
        {"id": "d1", "title": "doc.md", "path": "input/doc.md"},
    ])
    out = migrate_dataframe(df, "final_docs")
    row = out.iloc[0]
    assert row["category"] is None
    assert row["tags"] == []
    assert row["attributes"] is None


def test_migrate_empty_dataframe_still_adds_columns():
    df = pd.DataFrame()
    out = migrate_dataframe(df, "final_entities")
    for col in ("community_ids", "observed_at", "confidence", "source"):
        assert col in out.columns


def test_migrate_unknown_table_passes_through():
    df = pd.DataFrame([{"id": 1}])
    out = migrate_dataframe(df, "not_a_real_table")
    # Same shape, same values.
    assert out.equals(df)


def test_migration_does_not_mutate_input():
    df = pd.DataFrame([{"id": "e1", "name": "ALICE"}])
    cols_before = set(df.columns)
    migrate_dataframe(df, "final_entities")
    assert set(df.columns) == cols_before


def test_migration_idempotent():
    df = pd.DataFrame([{"id": "e1", "name": "ALICE"}])
    once = migrate_dataframe(df, "final_entities")
    twice = migrate_dataframe(once, "final_entities")
    assert list(once.columns) == list(twice.columns)
    assert needs_migration(once, "final_entities") is False
