"""accept_proposal / reject_proposal end-to-end tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from grail import MemoryProject


async def _build_project_with_proposals(tmp_path: Path) -> MemoryProject:
    """Construct a project with a known set of proposals after consolidate()."""
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    mp.config.memory.min_entities_for_consolidate = 3
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
        relationships=[{"source": "ALICE", "target": "BOB", "description": "friends"}],
    )
    mp.consolidate()
    return mp


@pytest.mark.asyncio
async def test_accept_discover_community(tmp_path: Path):
    mp = await _build_project_with_proposals(tmp_path)
    proposals = mp.list_proposals().data["proposals"]
    target = next(p for p in proposals if p["kind"] == "discover_community")
    reply = mp.accept_proposal(target["id"])
    assert reply.ok
    assert reply.data["kind"] == "discover_community"
    cid = reply.data["outcome"]["community_id"]
    comms = pd.read_parquet(mp.path / "output" / "final_communities.parquet")
    assert cid in set(comms["community"].astype(str))
    # Member entities have the new community appended.
    ents = pd.read_parquet(mp.path / "output" / "final_entities.parquet")
    members = set(reply.data["outcome"]["members"])
    for _, row in ents.iterrows():
        if row["name"] in members:
            assert cid in list(row["community_ids"])


@pytest.mark.asyncio
async def test_reject_proposal_marks_status(tmp_path: Path):
    mp = await _build_project_with_proposals(tmp_path)
    proposals = mp.list_proposals().data["proposals"]
    target = proposals[0]
    reply = mp.reject_proposal(target["id"], reason="not interesting")
    assert reply.ok
    assert reply.data["status"] == "rejected"
    after = mp.list_proposals().data["proposals"]
    if after:
        matched = [p for p in after if p["id"] == target["id"]]
        if matched:
            assert matched[0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_accept_proposal_twice_fails(tmp_path: Path):
    mp = await _build_project_with_proposals(tmp_path)
    proposals = mp.list_proposals().data["proposals"]
    target = next(p for p in proposals if p["kind"] == "discover_community")
    first = mp.accept_proposal(target["id"])
    assert first.ok
    second = mp.accept_proposal(target["id"])
    assert not second.ok


@pytest.mark.asyncio
async def test_accept_proposal_unknown_id(tmp_path: Path):
    mp = await _build_project_with_proposals(tmp_path)
    reply = mp.accept_proposal("nonexistent-id")
    assert not reply.ok
    assert "no proposal" in (reply.error or "").lower()


@pytest.mark.asyncio
async def test_no_proposal_set_yet(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home")
    reply = mp.list_proposals()
    assert reply.ok
    assert reply.data["proposals"] == []
    assert any("consolidate" in s for s in reply.next_steps)


@pytest.mark.asyncio
async def test_accept_move_entity(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    mp.config.memory.min_entities_for_consolidate = 3
    # Construct: ALICE in work but most edges go to personal/friends.
    await mp.add_observation(
        title="w",
        content="...",
        category="work",
        entities=[
            {"name": "ALICE", "type": "PERSON", "description": "x"},
            {"name": "C1", "type": "PERSON", "description": "x"},
        ],
        relationships=[
            {"source": "ALICE", "target": "C1", "description": "x"},
        ],
    )
    await mp.add_observation(
        title="p",
        content="...",
        category="personal/friends",
        entities=[
            {"name": "F1", "type": "PERSON", "description": "x"},
            {"name": "F2", "type": "PERSON", "description": "x"},
            {"name": "F3", "type": "PERSON", "description": "x"},
        ],
        relationships=[],
    )
    await mp.add_relationship(source="ALICE", target="F1", description="x")
    await mp.add_relationship(source="ALICE", target="F2", description="x")
    await mp.add_relationship(source="ALICE", target="F3", description="x")

    mp.consolidate()
    proposals = mp.list_proposals().data["proposals"]
    # Multiple move_entity proposals may fire (one per dominant-outside
    # entity); pick the one that names ALICE.
    move_props = [
        p
        for p in proposals
        if p["kind"] == "move_entity" and p["payload"]["entity"] == "ALICE"
    ]
    assert move_props, "expected a move_entity proposal for ALICE"
    target = move_props[0]
    reply = mp.accept_proposal(target["id"])
    assert reply.ok
    assert reply.data["outcome"]["entity"] == "ALICE"
    ents = pd.read_parquet(mp.path / "output" / "final_entities.parquet")
    alice = ents[ents["name"] == "ALICE"].iloc[0]
    assert "personal/friends" in list(alice["community_ids"])
