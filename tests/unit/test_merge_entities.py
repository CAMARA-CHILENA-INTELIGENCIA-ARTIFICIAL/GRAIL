"""Targeted, user-directed entity fusion — MemoryProject.merge_entities().

The direct sibling of the merge_aliases consolidation proposal, but merged on command.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from grail import MemoryProject
from grail.config import load_config

_QUICKSTART = Path(__file__).resolve().parents[2] / "examples" / "quickstart"


def _active_kb_run() -> Optional[Path]:
    """Resolve the quickstart knowledge-base's active run folder (skip if the sample is absent)."""
    cur = _QUICKSTART / "output" / "current.json"
    if not cur.exists():
        return None
    try:
        run_dir = _QUICKSTART / json.loads(cur.read_text())["run_dir"]
    except Exception:
        return None
    return run_dir if (run_dir / "final_entities.parquet").exists() else None


async def _project_with_dupes(tmp_path: Path) -> MemoryProject:
    mp = MemoryProject(tmp_path / "p", registry_home=tmp_path / "home", embeddings=None)
    await mp.add_observation(
        title="w",
        content="Acme renewal in March; Ana is the CSM.",
        category="clients",
        entities=[
            {"name": "ACME CORP", "type": "ORG", "description": "mid-market client"},
            {"name": "ANA", "type": "PERSON", "description": "CSM for the account"},
        ],
        relationships=[{"source": "ANA", "target": "ACME CORP", "description": "CSM of"}],
    )
    await mp.add_observation(
        title="w2",
        content="Acme signed the annual plan.",
        category="clients",
        entities=[
            # Duplicate of "ACME CORP" under a different surface form.
            {"name": "ACME", "type": "ORG", "description": "the Acme account"},
            {"name": "ANA", "type": "PERSON", "description": "account owner"},
        ],
        relationships=[{"source": "ANA", "target": "ACME", "description": "owns"}],
    )
    return mp


def _entities(mp: MemoryProject) -> pd.DataFrame:
    return pd.read_parquet(mp.path / "output" / "final_entities.parquet")


def _rels(mp: MemoryProject) -> pd.DataFrame:
    return pd.read_parquet(mp.path / "output" / "final_relationships.parquet")


@pytest.mark.asyncio
async def test_merge_entities_fuses_alias_into_canonical(tmp_path: Path):
    mp = await _project_with_dupes(tmp_path)
    before = _entities(mp)
    assert {"ACME", "ACME CORP"} <= set(before["name"].astype(str))

    reply = mp.merge_entities("ACME CORP", ["ACME"])
    assert reply.ok, reply.error
    assert reply.data["canonical"] == "ACME CORP"
    assert reply.data["merged_aliases"] == ["ACME"]

    ents = _entities(mp)
    names = set(ents["name"].astype(str))
    assert "ACME" not in names, "alias should be removed"
    assert "ACME CORP" in names, "canonical should survive"

    # Relationships that pointed at the alias now point at the canonical (deduped, no self-loops).
    # GRAIL normalizes endpoint order, so compare the unordered pair.
    rels = _rels(mp)
    assert "ACME" not in set(rels["source"].astype(str)) | set(rels["target"].astype(str))
    pairs = [frozenset((s, t)) for s, t in zip(rels["source"].astype(str), rels["target"].astype(str))]
    assert pairs.count(frozenset({"ANA", "ACME CORP"})) == 1, "the ANA↔ACME CORP edge should dedup to one"

    # The survivor's embedding is invalidated so recall re-embeds the fused entity.
    canon = ents[ents["name"] == "ACME CORP"].iloc[0]
    assert canon["description_embedding"] is None


@pytest.mark.asyncio
async def test_merge_entities_description_override(tmp_path: Path):
    mp = await _project_with_dupes(tmp_path)
    reply = mp.merge_entities("ACME CORP", ["ACME"], description="Acme Corporation — annual client")
    assert reply.ok
    canon = _entities(mp).query("name == 'ACME CORP'").iloc[0]
    assert canon["description"] == "Acme Corporation — annual client"


@pytest.mark.asyncio
async def test_merge_entities_unknown_alias_is_ok_false(tmp_path: Path):
    mp = await _project_with_dupes(tmp_path)
    reply = mp.merge_entities("ACME CORP", ["DOES_NOT_EXIST"])
    assert not reply.ok
    assert "none of the given aliases" in (reply.error or "").lower()


@pytest.mark.asyncio
async def test_merge_entities_requires_inputs(tmp_path: Path):
    mp = await _project_with_dupes(tmp_path)
    assert not mp.merge_entities("", ["ACME"]).ok
    assert not mp.merge_entities("ACME CORP", []).ok


@pytest.mark.asyncio
async def test_merge_entities_promotes_alias_when_canonical_absent(tmp_path: Path):
    """If the named canonical doesn't exist but an alias does, the alias is promoted."""
    mp = await _project_with_dupes(tmp_path)
    reply = mp.merge_entities("ACME INC", ["ACME", "ACME CORP"])
    assert reply.ok, reply.error
    names = set(_entities(mp)["name"].astype(str))
    # One surviving Acme entity; the other alias folded in.
    assert len(names & {"ACME", "ACME CORP", "ACME INC"}) == 1


@pytest.mark.asyncio
async def test_merge_entities_knowledge_mode_on_sample_kb(tmp_path: Path):
    """KNOWLEDGE-BASE mode on the real quickstart KB: the merge must also rewrite the Leiden
    artefacts (final_nodes.title + final_communities.entity_ids), and must NOT assume the
    memory-mode-only columns (retrieval_queries / community_ids on entities)."""
    run = _active_kb_run()
    if run is None:
        pytest.skip("quickstart knowledge-base sample not available")

    kb = tmp_path / "kb"
    (kb / "output").mkdir(parents=True)
    for f in run.glob("final_*.parquet"):
        shutil.copy(f, kb / "output" / f.name)

    cfg = load_config(None)
    cfg.mode = "knowledge_base"
    cfg.root_dir = str(kb)
    mp = MemoryProject(kb, config=cfg, registry_home=tmp_path / "home", embeddings=None)
    assert mp.config.mode == "knowledge_base"

    out = kb / "output"
    ents = pd.read_parquet(out / "final_entities.parquet")
    nodes = pd.read_parquet(out / "final_nodes.parquet")
    comms = pd.read_parquet(out / "final_communities.parquet")
    node_names = set(nodes["title"].astype(str))

    def _in_comm(name: str) -> bool:
        return any(str(x) == name for ids in comms["entity_ids"] for x in list(ids))

    ranked = ents.sort_values("degree", ascending=False)["name"].astype(str).tolist()
    canonical = ranked[0]
    # Pick an alias present in BOTH the node map and a community, so the KB-specific rewrite runs.
    alias = next(n for n in ranked[1:] if n != canonical and n in node_names and _in_comm(n))

    reply = mp.merge_entities(canonical, [alias])
    assert reply.ok, reply.error
    assert reply.data["merged_aliases"] == [alias]

    e2 = pd.read_parquet(out / "final_entities.parquet")
    n2 = pd.read_parquet(out / "final_nodes.parquet")
    r2 = pd.read_parquet(out / "final_relationships.parquet")
    c2 = pd.read_parquet(out / "final_communities.parquet")

    assert alias not in set(e2["name"].astype(str)) and canonical in set(e2["name"].astype(str))
    assert (n2["title"].astype(str) == alias).sum() == 0, "final_nodes must be rewritten"
    assert not any(str(x) == alias for ids in c2["entity_ids"] for x in list(ids)), "communities must be rewritten"
    assert ((r2["source"].astype(str) == alias) | (r2["target"].astype(str) == alias)).sum() == 0
    # Community sizes stay consistent with their (deduped) member lists.
    assert all(int(c2.iloc[i]["size"]) == len(list(c2.iloc[i]["entity_ids"])) for i in range(len(c2)))
