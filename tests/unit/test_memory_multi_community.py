"""Regression tests for the multi-community + atomicity bugs found by a Claude Code agent on 2026-06-02.

The agent observed:
  1. ``add_observation`` crashed with a numpy "ambiguous truth value" once
     any entity reached 2+ community memberships, because the nudge code at
     project.py:374 did ``(cids or [])``.
  2. ``list_entities(category=...)`` crashed on the same numpy pattern at
     project.py:1028.
  3. The crash happened AFTER the markdown file was written, so retries
     produced ``<slug>-2.md`` collisions.

These tests exercise each path explicitly and would have caught all three.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from grail import MemoryProject


async def _seed_multi_community_entity(mp: MemoryProject) -> None:
    """Put ALICE into two folder communities so her community_ids becomes a 2-element ndarray after parquet round-trip."""
    await mp.add_observation(
        title="acme meeting",
        content="content",
        category="work/clients/acme",
        entities=[
            {"name": "ALICE", "type": "PERSON", "description": "rep"},
        ],
    )
    await mp.add_observation(
        title="dinner",
        content="content",
        category="personal/friends",
        entities=[
            {"name": "ALICE", "type": "PERSON", "description": "friend"},
        ],
    )
    # Verify ALICE truly has 2 community memberships before continuing.
    ents = pd.read_parquet(mp.path / "output" / "final_entities.parquet")
    cids = list(ents.loc[ents["name"] == "ALICE", "community_ids"].iloc[0])
    assert set(cids) == {"work/clients/acme", "personal/friends"}, cids


# ---------------------------------------------------------------- Bug 1a — add_observation:374


@pytest.mark.asyncio
async def test_add_observation_with_multi_community_entity_does_not_crash(tmp_path: Path):
    """A 3rd add_observation that references the multi-community entity must succeed."""
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await _seed_multi_community_entity(mp)

    # 3rd observation under a 3rd folder — would crash at line 374 before the fix.
    reply = await mp.add_observation(
        title="coffee",
        content="content",
        category="work/clients/acme",
        entities=[
            {"name": "ALICE", "type": "PERSON", "description": "rep"},
            {"name": "BOB", "type": "PERSON", "description": "colleague"},
        ],
    )
    assert reply.ok, reply.error


@pytest.mark.asyncio
async def test_add_observation_nudge_fires_for_multi_community_folder(tmp_path: Path):
    """The folder-threshold nudge counts entities correctly even with multi-membership."""
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    cat = "work/clients/acme"
    # 5 entities all sharing the same category — should fire the nudge.
    for i in range(5):
        reply = await mp.add_observation(
            title=f"meeting {i}",
            content="content",
            category=cat,
            entities=[
                {"name": "ALICE", "type": "PERSON", "description": "x"},
                {"name": f"OTHER_{i}", "type": "PERSON", "description": "x"},
            ],
        )
        assert reply.ok
    # Last reply should carry the nudge.
    nudges = [s for s in (reply.next_steps or []) if "meta.md" in s]
    assert nudges, f"expected nudge with meta.md in next_steps, got {reply.next_steps!r}"


# ---------------------------------------------------------------- Bug 1a — list_entities:1028


@pytest.mark.asyncio
async def test_list_entities_by_category_with_multi_community_entity(tmp_path: Path):
    """``list_entities(category=...)`` must work after multi-community membership."""
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await _seed_multi_community_entity(mp)

    reply = mp.list_entities(category="work/clients/acme")
    assert reply.ok
    names = [e["name"] for e in reply.data["entities"]]
    assert "ALICE" in names

    reply = mp.list_entities(category="personal/friends")
    assert reply.ok
    names = [e["name"] for e in reply.data["entities"]]
    assert "ALICE" in names


# ---------------------------------------------------------------- Bug 1b — atomicity / file cleanup


@pytest.mark.asyncio
async def test_add_observation_cleans_up_file_on_post_persist_failure(tmp_path: Path):
    """If anything after the markdown write fails, the file must be removed.

    Simulates the original 2026-06-02 crash by injecting a failure into the
    nudge code path. Verifies the rollback so retries don't collide.
    """
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)

    # Force a failure deep inside the post-persist logic. We patch the
    # _append_history method which runs in step 7, after the parquet writes.
    boom = RuntimeError("synthetic crash deep in add_observation")
    with patch.object(mp, "_append_history", side_effect=boom):
        with pytest.raises(RuntimeError, match="synthetic crash"):
            await mp.add_observation(
                title="doomed",
                content="content",
                category="misc",
                entities=[{"name": "X", "type": "PERSON", "description": "x"}],
            )

    # No ``-2.md`` collision should exist; the doomed file should be cleaned up.
    md_files = list((mp.path / "memories" / "misc").glob("*.md"))
    assert md_files == [], f"expected no leftover files, found {md_files}"

    # Retrying succeeds with the original slug (not -2).
    reply = await mp.add_observation(
        title="doomed",
        content="content",
        category="misc",
        entities=[{"name": "X", "type": "PERSON", "description": "x"}],
    )
    assert reply.ok
    assert reply.data["slug"].endswith("_doomed"), reply.data["slug"]


# ---------------------------------------------------------------- Bonus — recall composition


@pytest.mark.asyncio
async def test_recall_by_category_with_multi_community_entity(tmp_path: Path):
    """Recall must surface the multi-membership entity under either folder."""
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await _seed_multi_community_entity(mp)

    work = (await mp.recall(category="work/clients/acme")).data
    names = [e["name"] for e in work["entities"]]
    assert "ALICE" in names

    personal = (await mp.recall(category="personal/friends")).data
    names = [e["name"] for e in personal["entities"]]
    assert "ALICE" in names
