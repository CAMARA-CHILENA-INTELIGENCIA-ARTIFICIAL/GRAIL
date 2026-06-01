"""Special-case apply tests: merge_aliases (auto) and split_folder (manual)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from grail import MemoryProject


@pytest.mark.asyncio
async def test_accept_merge_aliases(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    mp.config.memory.min_entities_for_consolidate = 2

    # Two close-name entities with a relationship to the same neighbour so we
    # can prove the merge rewrites endpoints correctly.
    await mp.add_observation(
        title="o",
        content="...",
        category="work",
        entities=[
            {"name": "DR_SMITH", "type": "PERSON", "description": "cardiologist"},
            {"name": "BERLIN", "type": "LOCATION", "description": "city"},
        ],
        relationships=[
            {"source": "DR_SMITH", "target": "BERLIN", "description": "lives in"},
        ],
    )
    await mp.add_observation(
        title="o2",
        content="...",
        category="work",
        entities=[
            {"name": "DR_SMTH", "type": "PERSON", "description": "another spelling"},
        ],
        relationships=[],
    )
    await mp.add_relationship(
        source="DR_SMTH", target="BERLIN", description="lives in"
    )

    mp.consolidate()
    proposals = mp.list_proposals().data["proposals"]
    alias_props = [p for p in proposals if p["kind"] == "merge_aliases"]
    assert alias_props, "expected an alias-merge proposal"
    target = alias_props[0]
    reply = mp.accept_proposal(target["id"])
    assert reply.ok
    outcome = reply.data["outcome"]
    assert outcome["canonical"] == "DR_SMITH"
    assert outcome["merged_aliases"] == ["DR_SMTH"]
    # DR_SMTH gone, DR_SMITH still here.
    ents = pd.read_parquet(mp.path / "output" / "final_entities.parquet")
    assert "DR_SMTH" not in set(ents["name"])
    assert "DR_SMITH" in set(ents["name"])
    # All rels rewrite to the canonical.
    rels = pd.read_parquet(mp.path / "output" / "final_relationships.parquet")
    assert all(s != "DR_SMTH" and t != "DR_SMTH" for s, t in zip(rels["source"], rels["target"]))
    # The duplicate rel collapsed.
    smith_to_berlin = rels[(rels["source"] == "DR_SMITH") & (rels["target"] == "BERLIN")]
    smith_to_berlin = pd.concat(
        [smith_to_berlin, rels[(rels["source"] == "BERLIN") & (rels["target"] == "DR_SMITH")]]
    )
    assert len(smith_to_berlin) == 1


@pytest.mark.asyncio
async def test_accept_split_folder_generates_script(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    mp.config.memory.min_entities_for_consolidate = 3
    mp.config.memory.folder_split_min_entities = 6

    # Build a bimodal subgraph inside one folder.
    entities_a = [
        {"name": f"A{i}", "type": "PERSON", "description": f"a{i}"} for i in range(4)
    ]
    entities_b = [
        {"name": f"B{i}", "type": "PERSON", "description": f"b{i}"} for i in range(4)
    ]
    rels = []
    for i in range(4):
        for j in range(i + 1, 4):
            rels.append({"source": f"A{i}", "target": f"A{j}", "description": "a"})
            rels.append({"source": f"B{i}", "target": f"B{j}", "description": "b"})
    rels.append({"source": "A0", "target": "B0", "description": "bridge"})
    await mp.add_observation(
        title="big",
        content="...",
        category="big-folder",
        entities=entities_a + entities_b,
        relationships=rels,
    )

    mp.consolidate()
    proposals = mp.list_proposals().data["proposals"]
    split_props = [p for p in proposals if p["kind"] == "split_folder"]
    assert split_props, "expected a split_folder proposal"
    target = split_props[0]
    reply = mp.accept_proposal(target["id"])
    assert reply.ok
    assert reply.data["status"] == "accepted-pending-manual"
    script_path = Path(reply.data["outcome"]["apply_script"])
    assert script_path.exists()
    body = script_path.read_text()
    assert "#!/usr/bin/env bash" in body
    assert "mkdir -p" in body
    # Files are NOT moved automatically.
    assert (mp.path / "memories" / "big-folder").exists()
    assert any((mp.path / "memories" / "big-folder").glob("*.md"))
