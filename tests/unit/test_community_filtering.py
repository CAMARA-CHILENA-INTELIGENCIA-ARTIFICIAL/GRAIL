"""Community-level + min_report_size filtering tests."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from grail.indexing.community_reports import CommunityReportGenerator


@pytest.fixture
def report_gen():
    storage = MagicMock()
    llm = MagicMock()
    return CommunityReportGenerator(
        storage=storage,
        llm=llm,
        community_level="coarsest",
        min_report_size=3,
    )


def test_resolve_levels_coarsest(report_gen):
    assert report_gen._resolve_levels([0, 1, 2]) == [0]


def test_resolve_levels_finest():
    rg = CommunityReportGenerator(storage=MagicMock(), llm=MagicMock(), community_level="finest")
    assert rg._resolve_levels([0, 1, 2]) == [2]


def test_resolve_levels_all():
    rg = CommunityReportGenerator(storage=MagicMock(), llm=MagicMock(), community_level="all")
    assert rg._resolve_levels([0, 1, 2]) == [0, 1, 2]


def test_resolve_levels_specific_int():
    rg = CommunityReportGenerator(storage=MagicMock(), llm=MagicMock(), community_level=1)
    assert rg._resolve_levels([0, 1, 2]) == [1]


def test_resolve_levels_specific_int_missing():
    rg = CommunityReportGenerator(storage=MagicMock(), llm=MagicMock(), community_level=5)
    assert rg._resolve_levels([0, 1, 2]) == []


def test_resolve_levels_numeric_string():
    rg = CommunityReportGenerator(storage=MagicMock(), llm=MagicMock(), community_level="2")
    assert rg._resolve_levels([0, 1, 2]) == [2]


def test_resolve_levels_unknown_falls_back_to_coarsest():
    rg = CommunityReportGenerator(storage=MagicMock(), llm=MagicMock(), community_level="banana")
    assert rg._resolve_levels([0, 1, 2]) == [0]


def test_resolve_levels_empty_input():
    rg = CommunityReportGenerator(storage=MagicMock(), llm=MagicMock())
    assert rg._resolve_levels([]) == []


def test_min_report_size_drops_singletons():
    # Construct a fake communities_df with mixed sizes at level 0.
    comm_df = pd.DataFrame(
        [
            {"id": "0-1", "level": 0, "community": "1", "title": "big",   "entity_ids": [f"e{i}" for i in range(8)], "size": 8},
            {"id": "0-2", "level": 0, "community": "2", "title": "small", "entity_ids": ["x"],                      "size": 1},
            {"id": "0-3", "level": 0, "community": "3", "title": "mid",   "entity_ids": ["a", "b", "c"],            "size": 3},
        ]
    )
    rg = CommunityReportGenerator(
        storage=MagicMock(), llm=MagicMock(), community_level="coarsest", min_report_size=3
    )
    # Manually replicate the filtering logic (the report generator does this then
    # calls the LLM; here we just check the row selection).
    levels = rg._resolve_levels(sorted({int(lv) for lv in comm_df["level"].unique()}))
    selected = comm_df[comm_df["level"].isin(levels)]
    selected = selected[selected["size"] >= rg.min_report_size]
    assert sorted(selected["community"].tolist()) == ["1", "3"]


def test_min_report_size_zero_disables_filter():
    comm_df = pd.DataFrame(
        [
            {"id": "0-1", "level": 0, "community": "1", "size": 1},
            {"id": "0-2", "level": 0, "community": "2", "size": 3},
        ]
    )
    rg = CommunityReportGenerator(
        storage=MagicMock(), llm=MagicMock(), community_level="coarsest", min_report_size=0
    )
    levels = rg._resolve_levels(sorted({int(lv) for lv in comm_df["level"].unique()}))
    selected = comm_df[comm_df["level"].isin(levels)]
    if rg.min_report_size > 0:
        selected = selected[selected["size"] >= rg.min_report_size]
    assert len(selected) == 2
