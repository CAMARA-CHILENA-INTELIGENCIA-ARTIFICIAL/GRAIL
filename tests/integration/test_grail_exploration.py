"""
Integration tests that exercise GRAIL library modules against the quickstart
project and validate output structures.

These tests require:
  - A DEEPINFRA_API_KEY in the environment (or .env at the quickstart root).
  - The quickstart project to have been indexed at least once
    (``grail index examples/quickstart``).

Run with:
    uv run pytest tests/integration/test_grail_exploration.py -v -s

The ``-s`` flag lets you see the printed output tables inline — useful for
reviewing the shapes of every artefact.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd
import pytest

# ── GRAIL public API ────────────────────────────────────────────────────
from grail import GRAIL, Config, SearchResult, load_config
from grail.config import MANDATORY_ENTITY_TYPES
from grail.indexing import (
    CommunityExtractor,
    CommunityReportGenerator,
    EntityRelationshipExtractor,
    FileLoader,
    IncrementalCommunityExtractor,
)
from grail.query import (
    AgentSearch,
    DocumentSearch,
    GlobalSearch,
    LocalSearch,
    load_artifacts_for_search,
    map_query_to_entities,
)
from grail.query.retrieval import (
    SearchArtifacts,
    build_community_context,
    build_entity_context,
    build_relationship_context,
    build_text_unit_context,
)
from grail.storage import LocalStorage

# ── Paths ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
QUICKSTART = REPO_ROOT / "examples" / "quickstart"
QUICKSTART_YAML = QUICKSTART / "grail.yaml"


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def config() -> Config:
    assert QUICKSTART_YAML.exists(), f"Missing {QUICKSTART_YAML}"
    return load_config(QUICKSTART_YAML)


@pytest.fixture(scope="module")
def grail_instance(config: Config) -> GRAIL:
    return GRAIL.from_config(config)


@pytest.fixture(scope="module")
def storage(config: Config) -> LocalStorage:
    return LocalStorage(root=config.storage.root)


@pytest.fixture(scope="module")
def artifacts(grail_instance: GRAIL) -> SearchArtifacts:
    return load_artifacts_for_search(
        grail_instance.storage, grail_instance._output_folder()
    )


# =====================================================================
#  1. CONFIG LAYER
# =====================================================================


class TestConfig:
    def test_load_config(self, config: Config):
        assert config.project_name == "quickstart"
        assert config.llm.endpoint == "deepinfra"
        assert config.llm.model == "google/gemma-4-26B-A4B-it"
        assert config.embeddings.model == "Qwen/Qwen3-Embedding-0.6B"

    def test_mandatory_entity_types_injected(self, config: Config):
        for t in MANDATORY_ENTITY_TYPES:
            assert t in config.indexing.entity_types, (
                f"{t} should be force-injected"
            )

    def test_entity_types_upper_snake(self, config: Config):
        for t in config.indexing.entity_types:
            assert t == t.upper(), f"Entity type {t!r} should be UPPER_SNAKE_CASE"

    def test_extra_pricing(self, config: Config):
        key = "deepinfra|google/gemma-4-26B-A4B-it"
        assert key in config.llm.extra_pricing
        prompt, completion = config.llm.extra_pricing[key]
        assert prompt > 0 and completion > 0

    def test_endpoints_populated(self, config: Config):
        assert "deepinfra" in config.endpoints
        ep = config.endpoints["deepinfra"]
        assert "deepinfra" in ep.base_url.lower() or "api" in ep.base_url.lower()


# =====================================================================
#  2. STORAGE LAYER
# =====================================================================


class TestStorage:
    def test_storage_root_exists(self, storage: LocalStorage):
        assert Path(storage.root).exists()

    def test_mapping_json_exists(self, storage: LocalStorage):
        assert storage.exists("mapping.json")

    def test_mapping_json_schema(self, storage: LocalStorage):
        raw = storage.read_text("mapping.json")
        mapping = json.loads(raw)
        assert isinstance(mapping, dict), "mapping.json should be a dict"
        for doc_id, info in mapping.items():
            assert isinstance(doc_id, str)
            assert "original_path" in info or "path" in info, (
                f"Document {doc_id} must have a path/original_path"
            )
        print(f"\n  mapping.json: {len(mapping)} documents")
        for doc_id, info in mapping.items():
            print(f"    {doc_id}: {info}")


# =====================================================================
#  3. ARTEFACT SCHEMAS — parquet column & type validation
# =====================================================================


class TestArtifactSchemas:
    """Validate that every parquet has the expected columns and non-zero rows."""

    def test_documents(self, artifacts: SearchArtifacts):
        df = artifacts.documents
        assert not df.empty, "final_docs.parquet should not be empty"
        required = {"id", "title", "raw_content", "path", "text_unit_ids"}
        assert required.issubset(set(df.columns)), f"Missing cols: {required - set(df.columns)}"
        print(f"\n  Documents: {len(df)} rows")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Titles: {df['title'].tolist()}")

    def test_text_units(self, artifacts: SearchArtifacts):
        df = artifacts.text_units
        assert not df.empty
        required = {"id", "text", "n_tokens", "document_ids", "entity_ids", "relationship_ids"}
        assert required.issubset(set(df.columns)), f"Missing: {required - set(df.columns)}"
        print(f"\n  Text units: {len(df)} rows")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Token range: {df['n_tokens'].min()} – {df['n_tokens'].max()}")

    def test_entities(self, artifacts: SearchArtifacts):
        df = artifacts.entities
        assert not df.empty
        required = {"id", "name", "type", "description", "description_embedding",
                     "text_unit_ids", "degree"}
        assert required.issubset(set(df.columns)), f"Missing: {required - set(df.columns)}"
        print(f"\n  Entities: {len(df)} rows")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Types: {sorted(df['type'].dropna().unique())}")
        print(f"  Top 10 by degree:")
        top = df.nlargest(10, "degree")[["name", "type", "degree"]]
        print(top.to_string(index=False))

    def test_entity_embeddings_exist(self, artifacts: SearchArtifacts):
        df = artifacts.entities
        has_emb = df["description_embedding"].apply(
            lambda x: x is not None and hasattr(x, '__len__') and len(x) > 0
        )
        pct = has_emb.mean() * 100
        print(f"\n  Entities with embeddings: {pct:.1f}%")
        assert pct > 50, "At least half the entities should have embeddings"

    def test_relationships(self, artifacts: SearchArtifacts):
        df = artifacts.relationships
        assert not df.empty
        required = {"id", "source", "target", "description", "weight", "text_unit_ids", "rank"}
        assert required.issubset(set(df.columns)), f"Missing: {required - set(df.columns)}"
        print(f"\n  Relationships: {len(df)} rows")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Weight range: {df['weight'].min():.2f} – {df['weight'].max():.2f}")
        print(f"  Top 10 by rank:")
        top = df.nlargest(10, "rank")[["source", "target", "weight", "rank"]]
        print(top.to_string(index=False))

    def test_nodes(self, artifacts: SearchArtifacts):
        df = artifacts.nodes
        assert not df.empty
        required = {"title", "community", "level", "degree"}
        assert required.issubset(set(df.columns)), f"Missing: {required - set(df.columns)}"
        print(f"\n  Nodes: {len(df)} rows")
        print(f"  Community levels: {sorted(df['level'].unique())}")
        print(f"  Communities per level:")
        for lvl in sorted(df["level"].unique()):
            n = df[df["level"] == lvl]["community"].nunique()
            print(f"    Level {lvl}: {n} communities")

    def test_communities(self, artifacts: SearchArtifacts):
        df = artifacts.communities
        assert not df.empty
        print(f"\n  Communities: {len(df)} rows")
        print(f"  Columns: {list(df.columns)}")

    def test_community_reports(self, artifacts: SearchArtifacts):
        df = artifacts.community_reports
        assert not df.empty
        print(f"\n  Community reports: {len(df)} rows")
        print(f"  Columns: {list(df.columns)}")
        if "full_content" in df.columns:
            sample = df.iloc[0]
            print(f"  Sample report (community={sample.get('community', '?')}):")
            content = str(sample.get("full_content", ""))[:500]
            print(f"    {content}...")


# =====================================================================
#  4. GRAPH STRUCTURE
# =====================================================================


class TestGraph:
    def test_graphml_loads(self, grail_instance: GRAIL):
        out = grail_instance._output_folder()
        key = f"{out}/entity_relationship_graph.graphml"
        with grail_instance.storage.open_for_read(key) as path:
            G = nx.read_graphml(path)
        assert G.number_of_nodes() > 0
        assert G.number_of_edges() > 0
        print(f"\n  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        print(f"  Density: {nx.density(G):.4f}")
        print(f"  Connected components: {nx.number_connected_components(G.to_undirected())}")

    def test_entities_match_graph(self, artifacts: SearchArtifacts, grail_instance: GRAIL):
        out = grail_instance._output_folder()
        key = f"{out}/entity_relationship_graph.graphml"
        with grail_instance.storage.open_for_read(key) as path:
            G = nx.read_graphml(path)
        parquet_names = set(artifacts.entities["name"].str.upper())
        graph_names = set(n.upper() for n in G.nodes())
        overlap = parquet_names & graph_names
        print(f"\n  Parquet entities: {len(parquet_names)}")
        print(f"  Graph nodes: {len(graph_names)}")
        print(f"  Overlap: {len(overlap)}")
        assert len(overlap) > 0


# =====================================================================
#  5. RETRIEVAL PRIMITIVES
# =====================================================================


class TestRetrievalPrimitives:
    def test_build_entity_context(self, artifacts: SearchArtifacts):
        text, rows = build_entity_context(
            artifacts.entities.head(20), max_tokens=2000
        )
        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(rows, pd.DataFrame)
        print(f"\n  Entity context: {len(text)} chars, {len(rows)} entities selected")

    def test_build_relationship_context(self, artifacts: SearchArtifacts):
        names = artifacts.entities.head(5)["name"].tolist()
        text, rows = build_relationship_context(
            artifacts.relationships, names, max_tokens=2000
        )
        assert isinstance(text, str)
        assert isinstance(rows, pd.DataFrame)
        print(f"\n  Relationship context: {len(text)} chars, {len(rows)} rels selected")

    def test_build_community_context(self, artifacts: SearchArtifacts):
        result, rows = build_community_context(
            artifacts.community_reports, max_tokens=4000
        )
        assert result  # string or list of strings
        assert isinstance(rows, pd.DataFrame)
        text = result if isinstance(result, str) else "\n".join(result)
        print(f"\n  Community context: {len(text)} chars, {len(rows)} reports used")

    def test_build_text_unit_context(self, artifacts: SearchArtifacts):
        names = artifacts.entities.head(5)["name"].tolist()
        text, rows = build_text_unit_context(
            artifacts.text_units, names, max_tokens=3000,
            documents=artifacts.documents, mapping=artifacts.mapping,
        )
        assert isinstance(text, str)
        assert isinstance(rows, pd.DataFrame)
        print(f"\n  Text unit context: {len(text)} chars, {len(rows)} units selected")

    def test_map_query_to_entities(self, artifacts: SearchArtifacts, grail_instance: GRAIL):
        emb = asyncio.get_event_loop().run_until_complete(
            grail_instance.embeddings.embed_one("cancer treatment guidelines")
        )
        ranked = map_query_to_entities(
            query_embedding=emb,
            entities_df=artifacts.entities,
            top_k=10,
        )
        assert isinstance(ranked, pd.DataFrame)
        assert len(ranked) <= 10
        print(f"\n  Mapped entities for 'cancer treatment guidelines':")
        for _, row in ranked.iterrows():
            print(f"    {row['name']} ({row['type']})")


# =====================================================================
#  6. GRAIL HIGH-LEVEL API
# =====================================================================


class TestGRAILHighLevel:
    def test_status(self, grail_instance: GRAIL):
        status = grail_instance.status()
        assert status["project_name"] == "quickstart"
        print(f"\n  Status:")
        for k, v in status["artefacts"].items():
            mark = "OK" if v else "MISSING"
            print(f"    {k}: {mark}")
        assert status["artefacts"]["entities"], "Entities must exist"
        assert status["artefacts"]["reports"], "Reports must exist"

    def test_local_search(self, grail_instance: GRAIL):
        result = asyncio.get_event_loop().run_until_complete(
            grail_instance.search(
                "What are the main treatments for cancer cachexia?",
                mode="local",
            )
        )
        _validate_search_result(result, "local_search")

    def test_global_search(self, grail_instance: GRAIL):
        result = asyncio.get_event_loop().run_until_complete(
            grail_instance.search(
                "What are the main themes covered in the indexed documents?",
                mode="global",
            )
        )
        _validate_search_result(result, "global_search")

    def test_document_search(self, grail_instance: GRAIL):
        result = asyncio.get_event_loop().run_until_complete(
            grail_instance.search(
                "What does this document cover?",
                mode="document",
                document="cachexia",
            )
        )
        _validate_search_result(result, "document_search")

    def test_local_search_with_conversation_history(self, grail_instance: GRAIL):
        history = [
            {"role": "user", "content": "Tell me about gliomas."},
            {"role": "assistant", "content": "Gliomas are brain tumors..."},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            grail_instance.search(
                "What treatments are recommended?",
                mode="local",
                conversation_history=history,
            )
        )
        _validate_search_result(result, "local_search_with_history")

    def test_local_search_with_entity_filter(self, grail_instance: GRAIL):
        result = asyncio.get_event_loop().run_until_complete(
            grail_instance.search(
                "What are the guidelines?",
                mode="local",
                include_entity_names=["SEOM"],
            )
        )
        _validate_search_result(result, "local_search_filtered")


# =====================================================================
#  7. PROVENANCE TRACING (source → document chain)
# =====================================================================


class TestProvenance:
    """Reproduce the legacy script's source-tracing logic through the GRAIL API."""

    def test_source_document_chain(self, artifacts: SearchArtifacts, grail_instance: GRAIL):
        result = asyncio.get_event_loop().run_until_complete(
            grail_instance.search("cancer cachexia treatment", mode="local")
        )
        ctx = result.context_data
        assert isinstance(ctx, dict)
        if "sources" not in ctx or ctx["sources"].empty:
            pytest.skip("No source rows in context (small index)")

        sources_df = ctx["sources"]
        docs_df = artifacts.documents
        mapping = artifacts.mapping

        cited_doc_ids: set[str] = set()
        if "document_ids" in sources_df.columns:
            for _, row in sources_df.iterrows():
                dids = row["document_ids"]
                if isinstance(dids, list):
                    cited_doc_ids.update(dids)
                elif isinstance(dids, str):
                    cited_doc_ids.add(dids)

        cited_files: list[str] = []
        for doc_id in cited_doc_ids:
            match = docs_df[docs_df["id"] == doc_id]
            if not match.empty:
                cited_files.append(match.iloc[0]["title"])
            elif doc_id in mapping:
                cited_files.append(mapping[doc_id].get("original_path", doc_id))

        print(f"\n  Cited document IDs: {cited_doc_ids}")
        print(f"  Resolved files: {cited_files}")
        assert len(cited_doc_ids) > 0, "Search should cite at least one document"


# =====================================================================
#  8. COST TRACKER
# =====================================================================


class TestCostTracker:
    def test_cost_tracker_after_search(self, grail_instance: GRAIL):
        tracker = grail_instance.cost_tracker
        summary = tracker.summary(by="tag")
        print(f"\n  Cost summary by tag:")
        for tag, info in summary.items():
            print(f"    {tag}: {info}")
        total = tracker.total_cost_usd()
        print(f"  Total cost: ${total:.6f}")
        print(f"  Display: {tracker.render_total_cost()}")
        print(f"  Pricing status: {tracker.pricing_status()}")


# =====================================================================
#  Helpers
# =====================================================================


def _validate_search_result(result: SearchResult, label: str):
    """Common assertions for any SearchResult."""
    assert isinstance(result, SearchResult), f"{label}: expected SearchResult"
    assert isinstance(result.response, str), f"{label}: response should be str"
    assert len(result.response) > 0, f"{label}: response should not be empty"
    assert result.completion_time > 0, f"{label}: should have a positive completion time"
    assert result.llm_calls >= 1, f"{label}: should have made at least 1 LLM call"

    print(f"\n  [{label}]")
    print(f"  Response ({len(result.response)} chars): {result.response[:300]}...")
    print(f"  Completion time: {result.completion_time:.2f}s")
    print(f"  LLM calls: {result.llm_calls}")

    if isinstance(result.context_data, dict):
        print(f"  Context data keys: {list(result.context_data.keys())}")
        for k, v in result.context_data.items():
            if isinstance(v, pd.DataFrame):
                print(f"    {k}: DataFrame with {len(v)} rows, cols={list(v.columns)}")
            else:
                print(f"    {k}: {type(v).__name__}")
