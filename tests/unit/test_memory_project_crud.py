"""CRUD tests for MemoryProject — verify parquet shapes and lifecycle."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from grail import MemoryProject


@pytest.fixture
def project(tmp_path: Path) -> MemoryProject:
    return MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", name="p")


@pytest.mark.asyncio
async def test_add_observation_writes_file_and_parquets(project: MemoryProject):
    reply = await project.add_observation(
        title="Meeting with Acme",
        content="John said pricing should drop 15% for Q2. Sarah pushed back.",
        category="work/clients/acme",
        tags=["meeting", "pricing"],
        entities=[
            {"name": "JOHN_SMITH", "type": "PERSON", "description": "Acme negotiator."},
            {"name": "SARAH_LIN", "type": "PERSON", "description": "Internal lead."},
            {"name": "ACME", "type": "ORGANIZATION", "description": "Client."},
        ],
        relationships=[
            {
                "source": "JOHN_SMITH",
                "target": "ACME",
                "relationship_type": "WORKS_AT",
                "description": "John works at Acme.",
            },
            {
                "source": "JOHN_SMITH",
                "target": "SARAH_LIN",
                "relationship_type": "MENTIONS",
                "description": "Conversation in the meeting.",
            },
        ],
    )
    assert reply.ok
    assert sorted(reply.data["new_entities"]) == ["ACME", "JOHN_SMITH", "SARAH_LIN"]
    file_path = Path(reply.data["file_path"])
    assert file_path.exists()
    assert "John said pricing" in file_path.read_text()

    # Parquets exist and carry the new columns.
    out = project.path / "output"
    ents = pd.read_parquet(out / "final_entities.parquet")
    assert {"community_ids", "observed_at", "confidence", "source"} <= set(ents.columns)
    # Folder-as-community: all three entities are tagged with the category.
    for cids in ents["community_ids"]:
        assert "work/clients/acme" in (cids or [])

    rels = pd.read_parquet(out / "final_relationships.parquet")
    assert {"relationship_type", "observed_at", "confidence"} <= set(rels.columns)
    assert set(rels["relationship_type"]) == {"WORKS_AT", "MENTIONS"}

    docs = pd.read_parquet(out / "final_docs.parquet")
    assert docs.iloc[0]["category"] == "work/clients/acme"
    assert list(docs.iloc[0]["tags"]) == ["meeting", "pricing"]


@pytest.mark.asyncio
async def test_typed_edges_between_same_pair_are_distinct(project: MemoryProject):
    await project.add_observation(
        title="t",
        content="content",
        category="t",
        entities=[
            {"name": "ALICE", "type": "PERSON", "description": "x"},
            {"name": "ACME", "type": "ORGANIZATION", "description": "y"},
        ],
        relationships=[
            {"source": "ALICE", "target": "ACME", "relationship_type": "WORKS_AT", "description": "a"},
            {"source": "ALICE", "target": "ACME", "relationship_type": "OWNS", "description": "b"},
        ],
    )
    rels = pd.read_parquet(project.path / "output" / "final_relationships.parquet")
    assert len(rels) == 2
    assert set(rels["relationship_type"]) == {"WORKS_AT", "OWNS"}


@pytest.mark.asyncio
async def test_add_entity_without_observation_warns(project: MemoryProject):
    reply = await project.add_entity(
        name="ZEKE",
        type="PERSON",
        description="A stand-alone declared entity.",
    )
    assert reply.ok
    assert any("no underlying observation" in w for w in reply.warnings)


@pytest.mark.asyncio
async def test_add_relationship_blocks_missing_endpoints(project: MemoryProject):
    reply = await project.add_relationship(
        source="MISSING",
        target="ALSO_MISSING",
        description="...",
    )
    assert not reply.ok
    assert "not found" in (reply.error or "")


@pytest.mark.asyncio
async def test_add_relationship_self_loop_blocked(project: MemoryProject):
    await project.add_entity(name="X", type="CONCEPT", description="x")
    reply = await project.add_relationship(
        source="X", target="X", description="self?"
    )
    assert not reply.ok
    assert "self-loop" in (reply.error or "").lower()


@pytest.mark.asyncio
async def test_add_community_appends_to_member_community_ids(project: MemoryProject):
    await project.add_entity(name="A", type="PERSON", description="a")
    await project.add_entity(name="B", type="PERSON", description="b")
    reply = project.add_community(
        community_id="my-group",
        title="My Group",
        member_entity_names=["A", "B"],
        kind="folder",
        report_content="# My Group\n\nDetails about the group.",
    )
    assert reply.ok
    ents = pd.read_parquet(project.path / "output" / "final_entities.parquet")
    for _, row in ents.iterrows():
        assert "my-group" in (row["community_ids"] or [])
    reports = pd.read_parquet(
        project.path / "output" / "final_community_reports.parquet"
    )
    assert reports.iloc[0]["source"] == "agent"
    assert reports.iloc[0]["full_content"].startswith("# My Group")


@pytest.mark.asyncio
async def test_update_community_report_replaces_content(project: MemoryProject):
    await project.add_entity(name="A", type="PERSON", description="a")
    await project.add_entity(name="B", type="PERSON", description="b")
    project.add_community(
        community_id="g",
        title="Old",
        member_entity_names=["A", "B"],
        report_content="old",
    )
    reply = project.update_community_report(
        community_id="g", title="New", content="new content"
    )
    assert reply.ok
    reports = pd.read_parquet(
        project.path / "output" / "final_community_reports.parquet"
    )
    assert reports.iloc[0]["title"] == "New"
    assert reports.iloc[0]["full_content"] == "new content"


@pytest.mark.asyncio
async def test_delete_observation_removes_file_and_prunes(project: MemoryProject):
    reply = await project.add_observation(
        title="Doomed",
        content="will be deleted",
        category="trash",
        entities=[
            {"name": "DOOMED_ENT", "type": "PERSON", "description": "dies w/ the file"},
        ],
    )
    slug = reply.data["slug"]
    file_path = Path(reply.data["file_path"])
    assert file_path.exists()

    del_reply = project.delete_observation(slug, reason="testing")
    assert del_reply.ok
    assert not file_path.exists()
    # Entity that was only attached to the deleted observation is pruned.
    ents_path = project.path / "output" / "final_entities.parquet"
    ents = pd.read_parquet(ents_path)
    assert "DOOMED_ENT" not in set(ents["name"])


@pytest.mark.asyncio
async def test_update_observation_round_trip(project: MemoryProject):
    reply = await project.add_observation(
        title="To edit",
        content="initial body",
        category="cat",
        entities=[{"name": "E", "type": "CONCEPT", "description": "first"}],
    )
    slug = reply.data["slug"]
    upd = await project.update_observation(
        slug,
        content="updated body",
        entities=[{"name": "E", "type": "CONCEPT", "description": "second"}],
    )
    assert upd.ok
    ents = pd.read_parquet(project.path / "output" / "final_entities.parquet")
    row = ents[ents["name"] == "E"].iloc[0]
    assert row["description"] == "second"


def test_list_categories_includes_folders_on_disk(tmp_path: Path):
    proj = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home")
    # Create an empty folder; should be picked up.
    (proj.path / "memories" / "work" / "clients" / "acme").mkdir(parents=True)
    cats = proj.list_categories().data["categories"]
    assert "work" in cats
    assert "work/clients" in cats
    assert "work/clients/acme" in cats


@pytest.mark.asyncio
async def test_history_jsonl_appends_each_op(project: MemoryProject):
    await project.add_observation(
        title="h",
        content="...",
        category="c",
        entities=[{"name": "X", "type": "CONCEPT", "description": "x"}],
    )
    await project.add_entity(name="Y", type="CONCEPT", description="y")
    hp = project.path / "_history.jsonl"
    lines = hp.read_text().splitlines()
    assert len(lines) == 2
    ops = [json.loads(l)["op"] for l in lines]
    assert ops == ["add_observation", "add_entity"]


@pytest.mark.asyncio
async def test_recall_filters_by_category_and_tag(tmp_path: Path):
    proj = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home")
    await proj.add_observation(
        title="a",
        content="...",
        category="work/clients/acme",
        tags=["pricing"],
        entities=[{"name": "A", "type": "PERSON", "description": "x"}],
    )
    await proj.add_observation(
        title="b",
        content="...",
        category="personal/family",
        tags=["birthday"],
        entities=[{"name": "B", "type": "PERSON", "description": "x"}],
    )
    work = (await proj.recall(category="work/clients/acme")).data
    assert len(work["observations"]) == 1
    assert work["observations"][0]["title"] == "a"
    tagged = (await proj.recall(tag="birthday")).data
    assert len(tagged["observations"]) == 1
    assert tagged["observations"][0]["title"] == "b"
