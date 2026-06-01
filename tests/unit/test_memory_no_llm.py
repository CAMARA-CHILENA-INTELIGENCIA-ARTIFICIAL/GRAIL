"""
Prove memory mode writes work with zero LLM calls.

The contract: ``MemoryProject(embeddings=None)`` accepts ``add_observation`` /
``add_entity`` / etc. and writes parquets without invoking *any* LLM endpoint.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from grail import MemoryProject


@pytest.mark.asyncio
async def test_zero_llm_bulk_writes(tmp_path: Path):
    """100 observations + 300 entities + 200 relationships, zero LLM."""
    mp = MemoryProject(
        tmp_path / "p",
        registry_home=tmp_path / "home",
        embeddings=None,  # explicit — no embeddings client
    )
    # Sanity: there is no embeddings client we could even call.
    assert mp.embeddings is None

    for i in range(100):
        reply = await mp.add_observation(
            title=f"Observation {i}",
            content=f"# Obs {i}\n\nBody for observation {i}.",
            category=f"bucket-{i % 5}",
            tags=[f"tag-{i % 3}"],
            entities=[
                {
                    "name": f"ENTITY_{i}_A",
                    "type": "CONCEPT",
                    "description": f"entity A for obs {i}",
                },
                {
                    "name": f"ENTITY_{i}_B",
                    "type": "CONCEPT",
                    "description": f"entity B for obs {i}",
                },
                {
                    "name": "SHARED_ANCHOR",  # accumulates across observations
                    "type": "CONCEPT",
                    "description": "shared anchor entity",
                },
            ],
            relationships=[
                {
                    "source": f"ENTITY_{i}_A",
                    "target": f"ENTITY_{i}_B",
                    "relationship_type": "RELATED",
                    "description": "siblings",
                },
                {
                    "source": f"ENTITY_{i}_A",
                    "target": "SHARED_ANCHOR",
                    "relationship_type": "ASSOCIATED_WITH",
                    "description": "anchored",
                },
            ],
        )
        assert reply.ok
        # First-pass warning about missing embeddings expected.
        if i == 0:
            assert any("No embeddings" in w for w in reply.warnings)

    ents = pd.read_parquet(mp.path / "output" / "final_entities.parquet")
    rels = pd.read_parquet(mp.path / "output" / "final_relationships.parquet")
    # 200 unique per-obs entities + 1 SHARED_ANCHOR = 201.
    assert len(ents) == 201
    # SHARED_ANCHOR's text_unit_ids span all 100 observations.
    anchor = ents[ents["name"] == "SHARED_ANCHOR"].iloc[0]
    assert len(anchor["text_unit_ids"]) >= 100
    # 100 RELATED edges (one per obs, A_i↔B_i) + 100 ASSOCIATED_WITH edges
    # (one per obs, A_i↔SHARED_ANCHOR) = 200.
    assert len(rels) == 200
    assert set(rels["relationship_type"]) == {"RELATED", "ASSOCIATED_WITH"}
    # Degree sanity: SHARED_ANCHOR should have degree 100 (one edge per obs).
    anchor_after = ents[ents["name"] == "SHARED_ANCHOR"].iloc[0]
    assert int(anchor_after["degree"]) == 100


@pytest.mark.asyncio
async def test_recall_works_without_embeddings(tmp_path: Path):
    mp = MemoryProject(
        tmp_path / "p", registry_home=tmp_path / "home", embeddings=None
    )
    await mp.add_observation(
        title="Meeting",
        content="...",
        category="work",
        tags=["meeting"],
        observed_at="2026-05-30T10:00:00Z",
        entities=[{"name": "X", "type": "PERSON", "description": "x"}],
    )
    await mp.add_observation(
        title="Dinner",
        content="...",
        category="personal",
        tags=["food"],
        observed_at="2026-05-29T20:00:00Z",
        entities=[{"name": "Y", "type": "PERSON", "description": "y"}],
    )
    # Temporal filter.
    after = (await mp.recall(since="2026-05-30T00:00:00Z")).data
    titles = [o["title"] for o in after["observations"]]
    assert titles == ["Meeting"]
    # Category filter.
    work = (await mp.recall(category="work")).data
    assert [o["title"] for o in work["observations"]] == ["Meeting"]


@pytest.mark.asyncio
async def test_find_similar_entity_falls_back_to_edit_distance(tmp_path: Path):
    """Without embeddings, ``find_similar_entity`` still works via edit distance."""
    mp = MemoryProject(
        tmp_path / "p", registry_home=tmp_path / "home", embeddings=None
    )
    await mp.add_entity(name="DR_SMITH", type="PERSON", description="...")
    reply = await mp.find_similar_entity("dr smith")
    assert reply.ok
    candidates = reply.data["candidates"]
    methods = {c["method"] for c in candidates}
    # No embedding path because no embeddings client.
    assert "embedding" not in methods
    # Should still surface DR_SMITH via exact/edit_distance match.
    assert any(c["name"] == "DR_SMITH" for c in candidates)
