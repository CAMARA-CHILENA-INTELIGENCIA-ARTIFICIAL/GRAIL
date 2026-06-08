"""
Unit tests for the grail.viz module.

These tests use synthetic in-memory DataFrames so they run fast and don't
require any indexed project.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from grail.viz.colors import (
    DEFAULT_TYPE_PALETTE,
    build_community_palette,
    build_type_palette,
    hash_color,
)
from grail.viz.exporter import build_sigma_graph
from grail.viz.template import render_html


# ── Fixtures ───────────────────────────────────────────────────────────


def _entities() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "id": "e1", "name": "ALICE", "type": "PERSON",
            "description": "An entity.", "degree": 3,
            "description_embedding": [0.1, 0.2],
            "text_unit_ids": ["t1"], "document_ids": ["d1"],
        },
        {
            "id": "e2", "name": "ACME CORP", "type": "ORGANIZATION",
            "description": "A company.", "degree": 2,
            "description_embedding": [0.3, 0.4],
            "text_unit_ids": ["t1"], "document_ids": ["d1"],
        },
        {
            "id": "e3", "name": "ASPIRIN", "type": "DRUG",
            "description": "A medication.", "degree": 1,
            "description_embedding": [0.5, 0.6],
            "text_unit_ids": ["t2"], "document_ids": ["d2"],
        },
        # Unknown type — should fall through to FALLBACK_PALETTE.
        {
            "id": "e4", "name": "FOO", "type": "WIDGET",
            "description": "Mystery.", "degree": 0,
            "description_embedding": [0.7, 0.8],
            "text_unit_ids": [], "document_ids": [],
        },
    ])


def _relationships() -> pd.DataFrame:
    return pd.DataFrame([
        {"id": "r1", "source": "ALICE", "target": "ACME CORP",
         "description": "works at", "weight": 5.0, "rank": 4,
         "text_unit_ids": ["t1"], "document_ids": ["d1"]},
        {"id": "r2", "source": "ALICE", "target": "ASPIRIN",
         "description": "takes", "weight": 2.0, "rank": 2,
         "text_unit_ids": ["t2"], "document_ids": ["d2"]},
        # Self-loop should be skipped.
        {"id": "r3", "source": "ALICE", "target": "ALICE",
         "description": "self", "weight": 1.0, "rank": 1,
         "text_unit_ids": [], "document_ids": []},
    ])


def _nodes() -> pd.DataFrame:
    return pd.DataFrame([
        {"title": "ALICE",     "community": "0", "level": 0, "degree": 3},
        {"title": "ACME CORP", "community": "0", "level": 0, "degree": 2},
        {"title": "ASPIRIN",   "community": "1", "level": 0, "degree": 1},
    ])


def _documents() -> pd.DataFrame:
    return pd.DataFrame([
        {"id": "d1", "title": "report.pdf", "raw_content": "...", "path": "x", "text_unit_ids": ["t1"]},
        {"id": "d2", "title": "memo.txt",   "raw_content": "...", "path": "y", "text_unit_ids": ["t2"]},
    ])


def _text_units() -> pd.DataFrame:
    return pd.DataFrame([
        {"id": "t1", "text": "Alice works at ACME.", "n_tokens": 8, "document_id": "d1",
         "document_ids": ["d1"], "entity_ids": ["e1", "e2"], "relationship_ids": ["r1"]},
        {"id": "t2", "text": "Alice takes aspirin.", "n_tokens": 7, "document_id": "d2",
         "document_ids": ["d2"], "entity_ids": ["e1", "e3"], "relationship_ids": ["r2"]},
    ])


def _communities() -> pd.DataFrame:
    return pd.DataFrame([
        {"id": "0-0", "level": 0, "community": "0", "title": "Community 0",
         "entity_ids": ["ALICE", "ACME CORP"], "size": 2},
        {"id": "1-0", "level": 0, "community": "1", "title": "Community 1",
         "entity_ids": ["ASPIRIN"], "size": 1},
    ])


def _reports() -> pd.DataFrame:
    return pd.DataFrame([
        {"id": "0-0", "community": "0", "level": 0, "title": "People at companies",
         "summary": "Alice works at ACME.", "full_content": "{}", "rank": 5.0,
         "rank_explanation": "central characters",
         "findings": [
             {"summary": "Employment relationship", "explanation": "Alice is at ACME [Data: Entities (0,1)]."},
             {"summary": "Active researcher", "explanation": "Alice publishes."},
         ]},
        {"id": "1-0", "community": "1", "level": 0, "title": "Medications",
         "summary": "Aspirin is a drug.", "full_content": "{}", "rank": 4.0,
         "rank_explanation": "minor topic",
         "findings": [
             {"summary": "Common medication", "explanation": "Aspirin is widely used."},
         ]},
    ])


# ── colors.py ──────────────────────────────────────────────────────────


class TestColors:
    def test_default_types_have_stable_colors(self):
        palette = build_type_palette(["PERSON", "DISEASE", "DRUG"])
        assert palette["PERSON"] == DEFAULT_TYPE_PALETTE["PERSON"]
        assert palette["DISEASE"] == DEFAULT_TYPE_PALETTE["DISEASE"]
        assert palette["DRUG"] == DEFAULT_TYPE_PALETTE["DRUG"]

    def test_unknown_types_get_fallback(self):
        palette = build_type_palette(["PERSON", "WIDGET", "GIZMO"])
        assert palette["WIDGET"] != palette["GIZMO"], "Unknown types should get distinct colors"
        for color in palette.values():
            assert re.match(r"^#[0-9a-f]{6}$", color, re.I)

    def test_unknown_types_are_deterministic(self):
        a = build_type_palette(["WIDGET", "GIZMO"])
        b = build_type_palette(["GIZMO", "WIDGET"])
        assert a == b, "Ordering of input shouldn't matter"

    def test_community_palette(self):
        palette = build_community_palette(["0", "1", "2"])
        assert len(palette) == 3
        assert len({v for v in palette.values()}) == 3, "Each community gets a unique color"

    def test_hash_color_deterministic(self):
        assert hash_color("abc") == hash_color("abc")
        assert hash_color("abc") != hash_color("xyz")


# ── exporter.py ────────────────────────────────────────────────────────


class TestExporter:
    def _full(self):
        return build_sigma_graph(
            entities_df=_entities(),
            relationships_df=_relationships(),
            nodes_df=_nodes(),
            documents_df=_documents(),
            text_units_df=_text_units(),
            communities_df=_communities(),
            reports_df=_reports(),
        )

    def test_emits_all_five_kinds(self):
        sigma = self._full()
        kinds = {n["attributes"]["_kind"] for n in sigma.nodes}
        assert kinds == {"document", "chunk", "entity", "community", "finding"}

    def test_kind_counts_match_inputs(self):
        sigma = self._full()
        kc = sigma.meta["kind_counts"]
        assert kc["document"] == 2
        assert kc["chunk"] == 2
        assert kc["entity"] == 4
        assert kc["community"] == 2
        assert kc["finding"] == 3  # 2 + 1

    def test_edge_kinds_present(self):
        sigma = self._full()
        ek = sigma.meta["edge_kind_counts"]
        # Self-loop dropped → 2 RELATED, not 3.
        assert ek.get("RELATED") == 2
        assert ek.get("PART_OF") == 2  # one per chunk
        assert ek.get("HAS_ENTITY") >= 1
        assert ek.get("IN_COMMUNITY") == 3  # ALICE+ACME→0, ASPIRIN→1 (FOO has no community)
        assert ek.get("HAS_FINDING") == 3
        assert ek.get("MENTIONS") >= 1

    def test_default_visible_kinds(self):
        sigma = self._full()
        # Entities-only by default — the rest of the Neo4j data model is one
        # toggle away in the sidebar, but the default render is the clean
        # community-coloured entity galaxy.
        assert sigma.meta["default_visible_kinds"] == ["entity"]
        assert sigma.meta["default_visible_edge_kinds"] == ["RELATED"]

    def test_entity_attribute_completeness(self):
        sigma = self._full()
        # No x/y — the D3 force simulation computes positions in the browser.
        required = {
            "label", "size", "color",
            "typeColor", "communityColor",
            "_kind", "_type", "_community", "_degree", "_description", "_documents",
        }
        for node in sigma.nodes:
            if node["attributes"]["_kind"] != "entity":
                continue
            missing = required - set(node["attributes"].keys())
            assert not missing, f"Entity {node['key']} missing: {missing}"

    def test_document_attributes(self):
        sigma = self._full()
        doc = next(n for n in sigma.nodes if n["attributes"]["_kind"] == "document")
        a = doc["attributes"]
        for key in ("_title", "_path", "_n_text_units", "_doc_id"):
            assert key in a, f"Document missing {key}"

    def test_community_attributes(self):
        sigma = self._full()
        comm = next(n for n in sigma.nodes if n["attributes"]["_kind"] == "community")
        a = comm["attributes"]
        for key in ("_community_id", "_size", "_rank", "_summary", "_n_findings"):
            assert key in a, f"Community missing {key}"

    def test_finding_attributes(self):
        sigma = self._full()
        find = next(n for n in sigma.nodes if n["attributes"]["_kind"] == "finding")
        a = find["attributes"]
        for key in ("_summary", "_explanation", "_community_id"):
            assert key in a, f"Finding missing {key}"

    def test_self_loops_dropped(self):
        sigma = self._full()
        for edge in sigma.edges:
            assert edge["source"] != edge["target"]

    def test_unknown_type_gets_fallback_color(self):
        sigma = self._full()
        widget_node = next(n for n in sigma.nodes if n["attributes"].get("_type") == "WIDGET")
        assert re.match(r"^#[0-9a-f]{6}$", widget_node["attributes"]["typeColor"], re.I)

    def test_documents_resolved_on_entity(self):
        sigma = self._full()
        alice = next(n for n in sigma.nodes
                     if n["attributes"]["_kind"] == "entity" and n["attributes"]["label"] == "ALICE")
        assert "report.pdf" in alice["attributes"]["_documents"]

    def test_meta_counts(self):
        sigma = self._full()
        assert sigma.meta["n_entities"] == 4
        assert sigma.meta["n_relationships"] == 2
        assert sigma.meta["n_communities"] == 2
        assert sigma.meta["n_documents"] == 2
        assert sigma.meta["n_chunks"] == 2
        assert sigma.meta["n_findings"] == 3

    def test_minimal_inputs_still_work(self):
        """Without docs/chunks/reports, we still emit entities + community nodes
        (community ids come from nodes_df.community)."""
        sigma = build_sigma_graph(
            entities_df=_entities(),
            relationships_df=_relationships(),
            nodes_df=_nodes(),
        )
        kinds = {n["attributes"]["_kind"] for n in sigma.nodes}
        assert kinds == {"entity", "community"}
        assert sigma.meta["n_entities"] == 4
        assert sigma.meta["n_documents"] == 0
        assert sigma.meta["n_chunks"] == 0
        assert sigma.meta["n_findings"] == 0

    def test_empty_inputs(self):
        sigma = build_sigma_graph(
            entities_df=pd.DataFrame(columns=["id", "name", "type"]),
            relationships_df=pd.DataFrame(),
            nodes_df=pd.DataFrame(),
        )
        assert sigma.nodes == []
        assert sigma.edges == []
        assert sigma.meta["n_entities"] == 0


# ── template.py ────────────────────────────────────────────────────────


class TestTemplate:
    def test_renders_html(self):
        sigma = build_sigma_graph(
            entities_df=_entities(), relationships_df=_relationships(),
            nodes_df=_nodes(), documents_df=_documents(),
            text_units_df=_text_units(), communities_df=_communities(),
            reports_df=_reports(),
        )
        html = render_html(
            sigma.to_dict(),
            title="Test",
            project_name="proj",
            run_id="2026-05-20-abc",
        )
        # Sanity-check the structural pieces of the D3 viewer.
        assert html.startswith("<!doctype html>")
        assert "</html>" in html
        # The renderer is mounted from the inlined UMD bundle.
        assert "GrailViz" in html
        assert "__GRAIL_VIZ_PAYLOAD__" in html
        assert 'id="grail-viz-payload"' in html

    def test_data_embedded_and_parseable(self):
        sigma = build_sigma_graph(
            entities_df=_entities(), relationships_df=_relationships(),
            nodes_df=_nodes(), documents_df=_documents(),
            text_units_df=_text_units(), communities_df=_communities(),
            reports_df=_reports(),
        )
        html = render_html(sigma.to_dict(), title="Test", project_name="proj", run_id="run-1")
        m = re.search(
            r'<script id="grail-viz-payload" type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        assert m, "Embedded grail-viz-payload block not found"
        data = json.loads(m.group(1))
        # 4 entities + 2 docs + 2 chunks + 2 communities + 3 findings.
        assert len(data["nodes"]) == 13
        # 2 RELATED + 2 PART_OF + HAS_ENTITY edges + IN_COMMUNITY + HAS_FINDING + MENTIONS.
        assert len(data["edges"]) > 5
        assert data["meta"]["n_entities"] == 4

    def test_html_escapes_title(self):
        sigma = build_sigma_graph(
            entities_df=_entities(), relationships_df=_relationships(),
            nodes_df=_nodes(), documents_df=_documents(),
            text_units_df=_text_units(), communities_df=_communities(),
            reports_df=_reports(),
        )
        html = render_html(sigma.to_dict(), title="<script>alert(1)</script>", project_name="x", run_id="y")
        assert "<script>alert(1)</script>" not in html, "Title should be HTML-escaped"
        assert "&lt;script&gt;" in html

    def test_numpy_arrays_serialise(self):
        """description_embedding can be a numpy array — must not break json.dumps."""
        ents = _entities()
        ents["description_embedding"] = ents["description_embedding"].apply(np.array)
        sigma = build_sigma_graph(ents, _relationships(), _nodes(), _documents())
        html = render_html(sigma.to_dict(), title="t", project_name="p", run_id="r")
        # Just ensure render succeeds without raising.
        assert "__GRAIL_VIZ_PAYLOAD__" in html
