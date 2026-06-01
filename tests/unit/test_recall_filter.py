"""RecallFilter unit tests — masks per dimension + relative-time parsing."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from grail.query.recall_filter import RecallFilter, normalize_time


# ---------------------------------------------------------------- normalize_time


def test_normalize_time_passes_iso_through():
    iso = "2026-05-30T10:00:00Z"
    assert normalize_time(iso) == iso


def test_normalize_time_handles_relative():
    ref = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    out = normalize_time("1h", now=ref)
    assert out == "2026-06-01T11:00:00Z"


def test_normalize_time_handles_days_with_ago():
    ref = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    out = normalize_time("7 days ago", now=ref)
    assert out == "2026-05-25T12:00:00Z"


def test_normalize_time_now_token():
    ref = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert normalize_time("now", now=ref) == "2026-06-01T12:00:00Z"


def test_normalize_time_none_passes_through():
    assert normalize_time(None) is None


# ---------------------------------------------------------------- masks


def test_empty_filter_is_empty():
    assert RecallFilter().is_empty()
    assert not RecallFilter(since="1h").is_empty()


def test_entity_mask_filters_by_type():
    df = pd.DataFrame(
        [
            {"name": "ALICE", "type": "PERSON"},
            {"name": "ACME", "type": "ORGANIZATION"},
            {"name": "BERLIN", "type": "LOCATION"},
        ]
    )
    f = RecallFilter(entity_types=["PERSON"])
    mask = f.applies_to_entities(df)
    assert mask.tolist() == [True, False, False]


def test_entity_mask_filters_by_name():
    df = pd.DataFrame(
        [
            {"name": "ALICE", "type": "PERSON"},
            {"name": "BOB", "type": "PERSON"},
        ]
    )
    f = RecallFilter(entity_names=["alice"])  # case-insensitive
    mask = f.applies_to_entities(df)
    assert mask.tolist() == [True, False]


def test_entity_mask_temporal():
    df = pd.DataFrame(
        [
            {"name": "A", "type": "PERSON", "observed_at": "2026-05-30T10:00:00Z"},
            {"name": "B", "type": "PERSON", "observed_at": "2026-05-29T10:00:00Z"},
        ]
    )
    f = RecallFilter(since="2026-05-30T00:00:00Z")
    mask = f.applies_to_entities(df)
    assert mask.tolist() == [True, False]


def test_entity_mask_min_confidence():
    df = pd.DataFrame(
        [
            {"name": "A", "type": "PERSON", "confidence": 0.95},
            {"name": "B", "type": "PERSON", "confidence": 0.6},
        ]
    )
    f = RecallFilter(min_confidence=0.8)
    mask = f.applies_to_entities(df)
    assert mask.tolist() == [True, False]


def test_entity_mask_category_via_community_ids():
    df = pd.DataFrame(
        [
            {"name": "A", "type": "PERSON", "community_ids": ["work/clients/acme"]},
            {"name": "B", "type": "PERSON", "community_ids": ["personal/family"]},
            {"name": "C", "type": "PERSON", "community_ids": []},
        ]
    )
    f = RecallFilter(category="work/**")
    mask = f.applies_to_entities(df)
    assert mask.tolist() == [True, False, False]


def test_document_mask_tags_any_match():
    df = pd.DataFrame(
        [
            {"id": "1", "tags": ["pricing", "meeting"]},
            {"id": "2", "tags": ["birthday"]},
            {"id": "3", "tags": []},
        ]
    )
    f = RecallFilter(tags=["pricing"])
    mask = f.applies_to_documents(df)
    assert mask.tolist() == [True, False, False]


def test_document_mask_combines_category_and_tags():
    df = pd.DataFrame(
        [
            {"id": "1", "category": "work/clients/acme", "tags": ["pricing"]},
            {"id": "2", "category": "personal/family", "tags": ["pricing"]},
            {"id": "3", "category": "work/clients/acme", "tags": ["meeting"]},
        ]
    )
    f = RecallFilter(category="work/**", tags=["pricing"])
    mask = f.applies_to_documents(df)
    assert mask.tolist() == [True, False, False]


def test_text_unit_mask_temporal_and_confidence():
    df = pd.DataFrame(
        [
            {"id": "tu1", "observed_at": "2026-05-30T10:00:00Z", "confidence": 0.95},
            {"id": "tu2", "observed_at": "2026-05-29T10:00:00Z", "confidence": 0.6},
        ]
    )
    f = RecallFilter(since="2026-05-30T00:00:00Z", min_confidence=0.8)
    mask = f.applies_to_text_units(df)
    assert mask.tolist() == [True, False]


def test_candidate_text_unit_ids_returns_none_when_empty_filter():
    tus = pd.DataFrame([{"id": "tu1"}])
    docs = pd.DataFrame([{"id": "d1"}])
    assert RecallFilter().candidate_text_unit_ids(tus, docs) is None


def test_candidate_text_unit_ids_intersects_doc_filter():
    tus = pd.DataFrame(
        [
            {"id": "tu1", "document_id": "d1", "observed_at": "2026-05-30T10:00:00Z", "confidence": 1.0},
            {"id": "tu2", "document_id": "d2", "observed_at": "2026-05-30T10:00:00Z", "confidence": 1.0},
        ]
    )
    docs = pd.DataFrame(
        [
            {"id": "d1", "category": "work/clients/acme", "tags": ["pricing"]},
            {"id": "d2", "category": "personal/family", "tags": []},
        ]
    )
    f = RecallFilter(category="work/**")
    ids = f.candidate_text_unit_ids(tus, docs)
    assert ids == {"tu1"}
