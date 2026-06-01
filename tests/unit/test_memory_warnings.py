"""Warning surfaces — the agent should be nudged toward good behaviour."""
from __future__ import annotations

from pathlib import Path

import pytest

from grail import MemoryProject
from grail.config import IndexingConfig, load_config


@pytest.mark.asyncio
async def test_find_similar_entity_flags_near_duplicates(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home")
    await mp.add_entity(name="DR_SMITH", type="PERSON", description="cardiologist")
    # Slightly different spelling — agent should be warned via the
    # find_similar_entity result before they call add_entity.
    reply = await mp.find_similar_entity("DR_SMTH")
    assert reply.ok
    candidates = reply.data["candidates"]
    assert any(c["name"] == "DR_SMITH" for c in candidates)


@pytest.mark.asyncio
async def test_relationship_type_warning_when_outside_vocab(tmp_path: Path):
    cfg = load_config(None)
    cfg.mode = "memory"
    cfg.indexing.relationship_types = ["WORKS_AT", "OWNS"]
    mp = MemoryProject(
        tmp_path / "p", registry_home=tmp_path / "home", config=cfg
    )
    await mp.add_entity(name="A", type="PERSON", description="a")
    await mp.add_entity(name="B", type="PERSON", description="b")
    reply = await mp.add_relationship(
        source="A",
        target="B",
        relationship_type="MARRIED_TO",  # not in the configured vocab
        description="...",
    )
    assert reply.ok  # still succeeds, just warns
    assert any("not in indexing.relationship_types" in w for w in reply.warnings)


@pytest.mark.asyncio
async def test_folder_threshold_next_step(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home")
    cat = "work/clients/acme"
    # Add 5 separate observations so the folder crosses the threshold.
    for i in range(5):
        await mp.add_observation(
            title=f"meeting {i}",
            content="...",
            category=cat,
            entities=[
                {"name": f"ENT_{i}", "type": "CONCEPT", "description": f"e{i}"},
            ],
        )
    # The 5th add_observation reply should suggest the meta.md write-up.
    last = await mp.add_observation(
        title="trigger",
        content="...",
        category=cat,
        entities=[{"name": "TRIGGER", "type": "CONCEPT", "description": "t"}],
    )
    assert any("meta.md" in s for s in last.next_steps)


@pytest.mark.asyncio
async def test_small_community_warns(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home")
    await mp.add_entity(name="A", type="PERSON", description="a")
    await mp.add_entity(name="B", type="PERSON", description="b")
    reply = mp.add_community(
        community_id="tiny",
        title="Tiny",
        member_entity_names=["A", "B"],
    )
    assert reply.ok
    assert any("only 2 members" in w for w in reply.warnings)


@pytest.mark.asyncio
async def test_entity_empty_description_warns(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home")
    reply = await mp.add_observation(
        title="t",
        content="content",
        category="c",
        entities=[
            {"name": "GHOST", "type": "PERSON", "description": ""},
        ],
    )
    assert reply.ok
    assert any("empty description" in w for w in reply.warnings)
