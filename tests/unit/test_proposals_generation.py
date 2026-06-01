"""``consolidate()`` proposal-generation tests.

Use synthetic graph snapshots so each analysis's signal is isolated.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from grail import MemoryProject
from grail.memory.analyses import (
    AliasDetect,
    EdgeDensity,
    FolderSplit,
    GraphSnapshot,
    Membership,
)


def _snapshot(entities, relationships):
    """Build a snapshot from list-of-dicts for the bits the analyses care about."""
    ents = pd.DataFrame(entities)
    rels = pd.DataFrame(relationships)
    return GraphSnapshot(
        entities=ents,
        relationships=rels,
        text_units=pd.DataFrame(),
        documents=pd.DataFrame(),
        communities=pd.DataFrame(),
        community_reports=pd.DataFrame(),
    )


# ---------------------------------------------------------------- edge density


def test_edge_density_fires_on_cross_folder_clique():
    """Triangle ACME/ALICE/BOB span work AND personal — should be flagged."""
    from grail.config import MemoryConfig

    cfg = MemoryConfig()
    snapshot = _snapshot(
        entities=[
            {"name": "ALICE", "type": "PERSON", "community_ids": ["work", "personal"]},
            {"name": "BOB", "type": "PERSON", "community_ids": ["work", "personal"]},
            {"name": "ACME", "type": "ORG", "community_ids": ["work"]},
            {"name": "CARLOS", "type": "PERSON", "community_ids": ["work"]},
        ],
        relationships=[
            {"source": "ALICE", "target": "BOB", "weight": 1.0},
            {"source": "ALICE", "target": "ACME", "weight": 1.0},
            {"source": "BOB", "target": "ACME", "weight": 1.0},
            {"source": "ALICE", "target": "CARLOS", "weight": 1.0},
            {"source": "BOB", "target": "CARLOS", "weight": 1.0},
            {"source": "ACME", "target": "CARLOS", "weight": 1.0},
        ],
    )
    proposals = EdgeDensity().propose(snapshot, cfg)
    assert proposals, "expected at least one discover_community proposal"
    p = proposals[0]
    assert p.kind == "discover_community"
    members = set(p.payload["members"])
    assert {"ALICE", "BOB", "ACME"} <= members
    assert p.confidence >= cfg.confidence_threshold_discover_community


def test_edge_density_does_not_fire_when_density_too_low():
    """Sparse chain inside a single folder — no proposal."""
    from grail.config import MemoryConfig

    cfg = MemoryConfig()
    snapshot = _snapshot(
        entities=[
            {"name": f"E{i}", "type": "CONCEPT", "community_ids": ["only-here"]}
            for i in range(5)
        ],
        relationships=[
            {"source": f"E{i}", "target": f"E{i+1}", "weight": 1.0} for i in range(4)
        ],
    )
    proposals = EdgeDensity().propose(snapshot, cfg)
    assert proposals == []


def test_edge_density_skips_when_all_share_one_folder():
    from grail.config import MemoryConfig

    cfg = MemoryConfig()
    snapshot = _snapshot(
        entities=[
            {"name": "A", "type": "PERSON", "community_ids": ["work"]},
            {"name": "B", "type": "PERSON", "community_ids": ["work"]},
            {"name": "C", "type": "PERSON", "community_ids": ["work"]},
        ],
        relationships=[
            {"source": "A", "target": "B", "weight": 1.0},
            {"source": "B", "target": "C", "weight": 1.0},
            {"source": "A", "target": "C", "weight": 1.0},
        ],
    )
    assert EdgeDensity().propose(snapshot, cfg) == []


# ---------------------------------------------------------------- alias detect


def test_alias_detect_fires_on_close_jaro_winkler():
    from grail.config import MemoryConfig

    cfg = MemoryConfig()
    snapshot = _snapshot(
        entities=[
            {"name": "DR_SMITH", "type": "PERSON", "text_unit_ids": ["tu1", "tu2"]},
            {"name": "DR_SMTH", "type": "PERSON", "text_unit_ids": ["tu3"]},
        ],
        relationships=[],
    )
    proposals = AliasDetect().propose(snapshot, cfg)
    assert proposals
    p = proposals[0]
    assert p.kind == "merge_aliases"
    # Canonical should be DR_SMITH (more text_units + longer name).
    assert p.payload["canonical"] == "DR_SMITH"
    assert p.payload["aliases"] == ["DR_SMTH"]


def test_alias_detect_ignores_different_types():
    from grail.config import MemoryConfig

    cfg = MemoryConfig()
    snapshot = _snapshot(
        entities=[
            {"name": "ACME", "type": "PERSON", "text_unit_ids": []},
            {"name": "ACME", "type": "ORGANIZATION", "text_unit_ids": []},
        ],
        relationships=[],
    )
    # Same name, different types — alias detect should not flag a self-merge.
    proposals = AliasDetect().propose(snapshot, cfg)
    # We deliberately allow the case-insensitive match across same-named rows
    # in *different* types to drop out.
    assert all(
        p.payload["canonical"].upper() != p.payload["aliases"][0].upper()
        for p in proposals
    )


# ---------------------------------------------------------------- membership


def test_membership_fires_when_outside_community_dominates():
    from grail.config import MemoryConfig

    cfg = MemoryConfig()
    # ALICE is declared only in work, but most of her edges go to personal/friends.
    snapshot = _snapshot(
        entities=[
            {"name": "ALICE", "type": "PERSON", "community_ids": ["work"]},
            {"name": "F1", "type": "PERSON", "community_ids": ["personal/friends"]},
            {"name": "F2", "type": "PERSON", "community_ids": ["personal/friends"]},
            {"name": "F3", "type": "PERSON", "community_ids": ["personal/friends"]},
            {"name": "C1", "type": "PERSON", "community_ids": ["work"]},
        ],
        relationships=[
            {"source": "ALICE", "target": "F1", "weight": 1.0},
            {"source": "ALICE", "target": "F2", "weight": 1.0},
            {"source": "ALICE", "target": "F3", "weight": 1.0},
            {"source": "ALICE", "target": "C1", "weight": 1.0},
        ],
    )
    proposals = Membership().propose(snapshot, cfg)
    alice_props = [p for p in proposals if p.payload.get("entity") == "ALICE"]
    assert alice_props
    p = alice_props[0]
    assert p.kind == "move_entity"
    assert p.payload["add_community_ids"] == ["personal/friends"]


# ---------------------------------------------------------------- folder split


def test_folder_split_fires_on_bimodal_subgraph():
    from grail.config import MemoryConfig

    cfg = MemoryConfig()
    cfg.folder_split_min_entities = 6  # lower for the test
    # Two dense cliques inside the same folder.
    entities = [
        {"name": f"A{i}", "type": "PERSON", "community_ids": ["big-folder"]}
        for i in range(4)
    ] + [
        {"name": f"B{i}", "type": "PERSON", "community_ids": ["big-folder"]}
        for i in range(4)
    ]
    relationships = []
    # Clique A.
    for i in range(4):
        for j in range(i + 1, 4):
            relationships.append({"source": f"A{i}", "target": f"A{j}", "weight": 1.0})
    # Clique B.
    for i in range(4):
        for j in range(i + 1, 4):
            relationships.append({"source": f"B{i}", "target": f"B{j}", "weight": 1.0})
    # One bridge edge.
    relationships.append({"source": "A0", "target": "B0", "weight": 1.0})

    snapshot = _snapshot(entities=entities, relationships=relationships)
    proposals = FolderSplit().propose(snapshot, cfg)
    assert proposals
    p = proposals[0]
    assert p.kind == "split_folder"
    assert p.payload["folder"] == "big-folder"
    assert len(p.payload["suggested_split"]) == 2


# ---------------------------------------------------------------- orchestrator


@pytest.mark.asyncio
async def test_consolidate_refuses_below_threshold(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    reply = mp.consolidate()
    assert not reply.ok
    assert "min_entities_for_consolidate" in (reply.error or "")


@pytest.mark.asyncio
async def test_consolidate_writes_proposal_file(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    mp.config.memory.min_entities_for_consolidate = 3
    # Set up a rich cross-folder scenario.
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
            {"source": "ALICE", "target": "BOB", "description": "team"},
            {"source": "ALICE", "target": "CARLOS", "description": "team"},
            {"source": "BOB", "target": "CARLOS", "description": "team"},
            {"source": "ALICE", "target": "ACME", "description": "rep"},
            {"source": "BOB", "target": "ACME", "description": "eng"},
            {"source": "CARLOS", "target": "ACME", "description": "pm"},
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
        relationships=[
            {"source": "ALICE", "target": "BOB", "description": "friends"},
        ],
    )

    reply = mp.consolidate()
    assert reply.ok
    set_path = Path(reply.data["proposal_set_path"])
    assert set_path.exists()
    assert (set_path.parent / "latest.yaml").exists()
    # Should have generated at least one discover_community proposal.
    kinds = reply.data["by_kind"]
    assert "discover_community" in kinds and kinds["discover_community"] >= 1


@pytest.mark.asyncio
async def test_consolidate_idempotent(tmp_path: Path):
    """Running consolidate twice doesn't change the world."""
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    mp.config.memory.min_entities_for_consolidate = 3
    await mp.add_observation(
        title="w",
        content="...",
        category="work",
        entities=[
            {"name": f"E{i}", "type": "PERSON", "description": "x"} for i in range(4)
        ],
        relationships=[
            {"source": "E0", "target": "E1", "description": "x"},
            {"source": "E1", "target": "E2", "description": "x"},
        ],
    )
    first = mp.consolidate()
    second = mp.consolidate()
    assert first.ok and second.ok
    # Same scenario should produce the same kinds + counts.
    assert first.data["by_kind"] == second.data["by_kind"]
