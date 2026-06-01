"""``RecallSearch`` peer mode + ``MemoryProject.recall`` integration tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from grail import MemoryProject, RecallFilter
from grail.query.recall_search import RecallSearch
from grail.storage import LocalStorage


# ---------------------------------------------------------------- direct asearch


@pytest.mark.asyncio
async def test_recall_search_returns_zero_llm_calls(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await mp.add_observation(
        title="One",
        content="content one",
        category="work",
        entities=[{"name": "ALICE", "type": "PERSON", "description": "..."}],
    )
    rs = RecallSearch(storage=LocalStorage(root=mp.path))
    result = await rs.asearch(RecallFilter(category="work"))
    assert result.llm_calls == 0


@pytest.mark.asyncio
async def test_recall_search_returns_matching_entities_and_docs(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await mp.add_observation(
        title="Work meeting",
        content="acme pricing",
        category="work/clients/acme",
        tags=["pricing"],
        entities=[{"name": "ALICE", "type": "PERSON", "description": "..."}],
    )
    await mp.add_observation(
        title="Dinner",
        content="...",
        category="personal/family",
        entities=[{"name": "BOB", "type": "PERSON", "description": "..."}],
    )
    rs = RecallSearch(storage=LocalStorage(root=mp.path))
    result = await rs.asearch(RecallFilter(category="work/**"))
    ents = result.context_data["entities"]
    docs = result.context_data["documents"]
    assert set(ents["name"]) == {"ALICE"}
    assert set(docs["title"]) == {"Work meeting"}


@pytest.mark.asyncio
async def test_recall_search_empty_filter_returns_everything(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await mp.add_observation(
        title="A",
        content="...",
        category="c1",
        entities=[{"name": "X", "type": "PERSON", "description": "x"}],
    )
    await mp.add_observation(
        title="B",
        content="...",
        category="c2",
        entities=[{"name": "Y", "type": "PERSON", "description": "y"}],
    )
    rs = RecallSearch(storage=LocalStorage(root=mp.path))
    result = await rs.asearch(RecallFilter())
    assert len(result.context_data["entities"]) == 2
    assert len(result.context_data["documents"]) == 2


# ---------------------------------------------------------------- MemoryProject.recall


@pytest.mark.asyncio
async def test_memory_project_recall_mode_recall(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await mp.add_observation(
        title="Recent",
        content="...",
        category="work",
        observed_at="2026-06-01T10:00:00Z",
        entities=[{"name": "RECENT_E", "type": "CONCEPT", "description": "r"}],
    )
    await mp.add_observation(
        title="Old",
        content="...",
        category="work",
        observed_at="2026-04-01T10:00:00Z",
        entities=[{"name": "OLD_E", "type": "CONCEPT", "description": "o"}],
    )
    reply = await mp.recall(since="2026-05-01T00:00:00Z")
    assert reply.ok
    # Only the recent observation matches.
    titles = [o["title"] for o in reply.data["observations"]]
    assert titles == ["Recent"]
    names = [e["name"] for e in reply.data["entities"]]
    assert "RECENT_E" in names
    assert "OLD_E" not in names


@pytest.mark.asyncio
async def test_memory_project_recall_with_tag_and_category(tmp_path: Path):
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await mp.add_observation(
        title="pricing-meeting",
        content="...",
        category="work/clients/acme",
        tags=["pricing"],
        entities=[{"name": "A1", "type": "PERSON", "description": "..."}],
    )
    await mp.add_observation(
        title="status-meeting",
        content="...",
        category="work/clients/acme",
        tags=["status"],
        entities=[{"name": "A2", "type": "PERSON", "description": "..."}],
    )
    reply = await mp.recall(category="work/clients/acme", tag="pricing")
    assert reply.ok
    titles = [o["title"] for o in reply.data["observations"]]
    assert titles == ["pricing-meeting"]


@pytest.mark.asyncio
async def test_memory_project_recall_unsupported_mode_without_llm(tmp_path: Path):
    """Modes that need an LLM should error gracefully when LLM is unconfigured."""
    from grail.config import load_config

    cfg = load_config(None)
    cfg.llm = None
    mp = MemoryProject(
        tmp_path / "p",
        registry_home=tmp_path / "home",
        embeddings=None,
        config=cfg,
    )
    reply = await mp.recall("acme pricing", mode="cascade")
    assert not reply.ok
    assert "llm" in (reply.error or "").lower()


# ---------------------------------------------------------------- modifier composition


@pytest.mark.asyncio
async def test_filter_applied_to_local_search_artifacts(tmp_path: Path):
    """Filter as modifier — verify the artefact pool shrinks correctly."""
    from grail.query.retrieval import load_artifacts_for_search

    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await mp.add_observation(
        title="Work",
        content="acme pricing",
        category="work/clients/acme",
        entities=[
            {"name": "ACME", "type": "ORGANIZATION", "description": "acme corp"},
            {"name": "ALICE", "type": "PERSON", "description": "acme rep"},
        ],
    )
    await mp.add_observation(
        title="Home",
        content="grocery list",
        category="personal/home",
        entities=[{"name": "GROCERIES", "type": "CONCEPT", "description": "..."}],
    )
    artifacts = load_artifacts_for_search(mp.storage)
    f = RecallFilter(category="work/**")
    filtered = f.apply_to_artifacts(artifacts)
    names = set(filtered.entities["name"])
    assert names == {"ACME", "ALICE"}
    titles = set(filtered.documents["title"])
    assert titles == {"Work"}
