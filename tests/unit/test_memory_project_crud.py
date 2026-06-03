"""CRUD tests for MemoryProject — verify parquet shapes and lifecycle."""
from __future__ import annotations

import asyncio
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


# --------------------------------------------------------------- regression tests


@pytest.mark.asyncio
async def test_add_observation_with_entity_already_in_multiple_communities(
    project: MemoryProject,
):
    """Regression for the nudge lambda crashing on parquet-round-tripped lists.

    The bug: ``lambda cids: category in (cids or [])`` raised
    ``ValueError: The truth value of an array with more than one element is
    ambiguous`` when ``cids`` was a numpy array (which is what pandas hands
    back for list columns after a parquet round-trip). The fix uses
    ``_aslist`` to normalise first.
    """
    # Put SHARED_ENT into two folder communities first.
    for cat in ("work/clients/acme", "personal/friends"):
        reply = await project.add_observation(
            title=f"seed-{cat.replace('/', '-')}",
            content="seed",
            category=cat,
            entities=[
                {"name": "SHARED_ENT", "type": "PERSON", "description": "shared"}
            ],
        )
        assert reply.ok, reply.error
    # Verify SHARED_ENT is multi-community on disk.
    ents = pd.read_parquet(project.path / "output" / "final_entities.parquet")
    cids = list(ents[ents["name"] == "SHARED_ENT"].iloc[0]["community_ids"])
    assert "work/clients/acme" in cids and "personal/friends" in cids

    # Now add another observation in one of the same folders that ALSO
    # references SHARED_ENT. The nudge lambda walks every entity's
    # community_ids — including SHARED_ENT's, which is now a multi-element
    # numpy array on read. Pre-fix this raised on .apply().
    reply = await project.add_observation(
        title="meeting-3",
        content="follow-up",
        category="work/clients/acme",
        entities=[
            {"name": "SHARED_ENT", "type": "PERSON", "description": "still shared"},
            {"name": "NEW_ENT", "type": "PERSON", "description": "new"},
        ],
    )
    assert reply.ok, reply.error


@pytest.mark.asyncio
async def test_grail_delete_works_on_memory_project(tmp_path: Path):
    """Regression for ``GRAIL.delete(file_names=...)`` raising KeyError on
    memory projects because they lacked ``partial_text_units.parquet``.

    Fix: ``MemoryProject._sync_partial_text_units`` mirrors the final
    text-units parquet into the partial-text-units parquet so the
    KB-pipeline loader path (used by ``GRAIL.delete`` / ``GRAIL.edit``)
    works on memory projects too.
    """
    from grail import GRAIL, load_config

    mp = MemoryProject(
        tmp_path / "p", registry_home=tmp_path / "home", embeddings=None
    )
    reply = await mp.add_observation(
        title="To be deleted",
        content="some body content",
        category="work",
        entities=[
            {"name": "DELETE_ME", "type": "CONCEPT", "description": "will go"}
        ],
    )
    assert reply.ok
    file_path = Path(reply.data["file_path"])
    assert file_path.exists()

    # The partial-text-units mirror must now exist.
    partial = mp.path / "output" / "partial_text_units.parquet"
    assert partial.exists(), "partial_text_units.parquet was not synced"
    partial_df = pd.read_parquet(partial)
    assert "id" in partial_df.columns
    assert len(partial_df) >= 1

    # Now route through ``GRAIL.delete`` — this is the path the CLI /
    # skill uses and is what was previously broken. The library matches
    # filenames by basename. Need to pin the config's storage root at
    # the project path explicitly (CLI ``grail init --memory`` would
    # write grail.yaml with this set; MemoryProject's ad-hoc opens skip
    # the yaml write).
    cfg = load_config(mp.path)
    cfg.root_dir = str(mp.path)
    cfg.storage.root = str(mp.path)
    grail = GRAIL.from_config(cfg)
    result = await grail.delete(file_names=[file_path.name])
    assert result.get("ok"), f"GRAIL.delete failed: {result.get('reason')}"
    # Final docs parquet should no longer reference the deleted file.
    docs_after = pd.read_parquet(mp.path / "output" / "final_docs.parquet")
    assert not docs_after["path"].apply(
        lambda p: Path(p).name == file_path.name
    ).any()


@pytest.mark.asyncio
async def test_delete_observation_syncs_partial_text_units(
    project: MemoryProject,
):
    """After a delete, partial_text_units should also lose the deleted TU."""
    r1 = await project.add_observation(
        title="keep",
        content="content one",
        category="cat",
        entities=[{"name": "K", "type": "CONCEPT", "description": "x"}],
    )
    r2 = await project.add_observation(
        title="trash",
        content="content two",
        category="cat",
        entities=[{"name": "T", "type": "CONCEPT", "description": "x"}],
    )
    project.delete_observation(r2.data["slug"])
    partial = project.path / "output" / "partial_text_units.parquet"
    assert partial.exists()
    final = pd.read_parquet(project.path / "output" / "final_text_units.parquet")
    pdf = pd.read_parquet(partial)
    # Same ids in both after sync.
    assert set(final["id"].astype(str)) == set(pdf["id"].astype(str))


def test_runtime_version_matches_installed_metadata():
    """``import grail; grail.__version__`` must match the installed
    package metadata for ``graphgrail`` — not the hardcoded fallback."""
    import grail
    from importlib.metadata import version

    try:
        installed = version("graphgrail")
    except Exception:
        pytest.skip("graphgrail not installed via metadata; editable mode")
    assert grail.__version__ == installed
