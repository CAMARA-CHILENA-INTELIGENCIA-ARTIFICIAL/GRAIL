"""
Custom file-handler tests — registry, policy, describe path, emit merge.

No LLM required: handlers are exercised directly and the emit-merge builders are
pure functions.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from grail.indexing.emit_merge import (
    build_emit_frames,
    entity_embedding_text,
    recompute_degrees,
    renumber_human_readable_ids,
)
from grail.indexing.handlers import (
    EmitEntity,
    EmitRelationship,
    EmitResult,
    FileHandler,
    FunctionHandler,
    HandlerContext,
    HandlerRegistry,
    UnhandledFileError,
)
from grail.indexing.loader import FileLoader
from grail.storage import LocalStorage


# --------------------------------------------------------------------------- #
# Handlers used across tests
# --------------------------------------------------------------------------- #


class _DescribeHandler(FileHandler):
    NAME = "xyz_describe"
    EXTENSIONS = frozenset({".xyz"})

    async def describe(self, source: Path, ctx: HandlerContext) -> str:
        return f"described:{source.name}"


class _EmitHandler(FileHandler):
    NAME = "rec_emit"
    EXTENSIONS = frozenset({".rec"})

    async def emit(self, source: Path, ctx: HandlerContext) -> EmitResult:
        return EmitResult(
            entities=[EmitEntity(name="ACME", type="ORG", description="a company")],
            relationships=[],
            text="one record",
        )


class _BothHandler(FileHandler):
    NAME = "broken_both"
    EXTENSIONS = frozenset({".both"})

    async def describe(self, source, ctx):  # pragma: no cover - never called
        return ""

    async def emit(self, source, ctx):  # pragma: no cover - never called
        return EmitResult()


class _NeitherHandler(FileHandler):
    NAME = "broken_neither"
    EXTENSIONS = frozenset({".none"})


# --------------------------------------------------------------------------- #
# Mode detection
# --------------------------------------------------------------------------- #


def test_mode_detection():
    assert _DescribeHandler().mode == "describe"
    assert _EmitHandler().mode == "emit"


def test_mode_ambiguous_raises():
    with pytest.raises(TypeError):
        _ = _BothHandler().mode


def test_mode_missing_raises():
    with pytest.raises(TypeError):
        _ = _NeitherHandler().mode


def test_extension_normalisation():
    class H(FileHandler):
        NAME = "h"
        EXTENSIONS = frozenset({"XYZ", ".AbC"})

        async def describe(self, source, ctx):
            return ""

    assert H().normalised_extensions() == frozenset({".xyz", ".abc"})


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_register_and_resolve():
    reg = HandlerRegistry()
    reg.register(_DescribeHandler())
    reg.register(_EmitHandler())
    assert reg.resolve(".xyz").NAME == "xyz_describe"
    assert reg.resolve("rec").NAME == "rec_emit"  # missing dot tolerated
    assert reg.resolve(".missing") is None
    assert reg.is_handled(".xyz")
    assert not reg.is_handled(".missing")
    assert reg.extensions() == frozenset({".xyz", ".rec"})


def test_collision_raises():
    class Other(FileHandler):
        NAME = "other"
        EXTENSIONS = frozenset({".xyz"})

        async def describe(self, source, ctx):
            return ""

    reg = HandlerRegistry()
    reg.register(_DescribeHandler())
    with pytest.raises(ValueError, match="claimed by both"):
        reg.register(Other())


def test_list_handlers():
    reg = HandlerRegistry()
    reg.register(_DescribeHandler())
    reg.register(_EmitHandler())
    rows = reg.list_handlers()
    by_name = {r["name"]: r for r in rows}
    assert by_name["xyz_describe"]["mode"] == "describe"
    assert by_name["rec_emit"]["extensions"] == [".rec"]


def test_load_from_custom_paths_HANDLER(tmp_path: Path):
    module = tmp_path / "h_single.py"
    module.write_text(
        "from grail.indexing.handlers import FileHandler\n"
        "class H(FileHandler):\n"
        "    NAME='single'\n"
        "    EXTENSIONS=frozenset({'.aaa'})\n"
        "    async def describe(self, source, ctx):\n"
        "        return 'x'\n"
        "HANDLER = H()\n"
    )
    reg = HandlerRegistry(custom_paths=[tmp_path])
    assert reg.resolve(".aaa").NAME == "single"


def test_load_from_custom_paths_HANDLERS_list(tmp_path: Path):
    module = tmp_path / "h_many.py"
    module.write_text(
        "from grail.indexing.handlers import FileHandler\n"
        "class A(FileHandler):\n"
        "    NAME='a'\n"
        "    EXTENSIONS=frozenset({'.a1'})\n"
        "    async def describe(self, source, ctx):\n"
        "        return 'x'\n"
        "class B(FileHandler):\n"
        "    NAME='b'\n"
        "    EXTENSIONS=frozenset({'.b1'})\n"
        "    async def describe(self, source, ctx):\n"
        "        return 'y'\n"
        "HANDLERS = [A(), B()]\n"
    )
    reg = HandlerRegistry(custom_paths=[tmp_path])
    assert reg.resolve(".a1").NAME == "a"
    assert reg.resolve(".b1").NAME == "b"


def test_module_without_handler_raises(tmp_path: Path):
    (tmp_path / "bad.py").write_text("X = 1\n")
    with pytest.raises(AttributeError, match="HANDLER"):
        HandlerRegistry(custom_paths=[tmp_path])


def test_missing_custom_dir_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        HandlerRegistry(custom_paths=[tmp_path / "nope"])


def test_function_handler():
    h = FunctionHandler(name="fn", extensions={".fn"}, fn=lambda p: f"got:{p.name}")
    assert h.mode == "describe"
    assert h.NAME == "fn"


# --------------------------------------------------------------------------- #
# Loader: classification + policy + describe read
# --------------------------------------------------------------------------- #


def _registry_describe_emit() -> HandlerRegistry:
    reg = HandlerRegistry()
    reg.register(_DescribeHandler())
    reg.register(_EmitHandler())
    return reg


def test_classify_inputs(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/a.txt", "builtin text")
    storage.write_text("input/b.xyz", "describe me")
    storage.write_text("input/c.rec", "emit me")
    storage.write_text("input/d.weird", "no handler")

    loader = FileLoader(storage=storage, handler_registry=_registry_describe_emit())
    c = loader.classify_inputs()
    assert [Path(k).name for k in c["builtin"]] == ["a.txt"]
    assert [Path(k).name for k in c["describe"]] == ["b.xyz"]
    assert [Path(k).name for k in c["emit"]] == ["c.rec"]
    assert [Path(k).name for k in c["unhandled"]] == ["d.weird"]


def test_policy_error(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/keep.txt", "ok")
    storage.write_text("input/mystery.weird", "???")
    loader = FileLoader(
        storage=storage,
        handler_registry=HandlerRegistry(),
        on_unhandled="error",
    )
    with pytest.raises(UnhandledFileError, match="mystery.weird"):
        loader.find()


def test_policy_skip_default(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/keep.txt", "ok")
    storage.write_text("input/mystery.weird", "???")
    # Default on_unhandled="skip" — unhandled silently dropped.
    loader = FileLoader(storage=storage)
    keys = loader.find()
    assert [Path(k).name for k in keys] == ["keep.txt"]


def test_policy_dotfiles_never_error(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/keep.txt", "ok")
    storage.write_bytes("input/.DS_Store", b"\x00\x01")
    loader = FileLoader(storage=storage, on_unhandled="error")
    # Hidden file is filtered before the policy — no raise.
    assert [Path(k).name for k in loader.find()] == ["keep.txt"]


def test_describe_read_from_processed(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/b.xyz", "raw")
    # Simulate the pre-pass having materialised the handler output.
    storage.write_text("input/_processed/b.md", "# Title\n\nprocessed body")

    loader = FileLoader(storage=storage, handler_registry=_registry_describe_emit())
    docs_df, units_df, mapping = loader.build_text_units()
    assert len(docs_df) == 1
    assert "processed body" in docs_df.iloc[0]["raw_content"]
    # Emit files are excluded from chunking entirely.
    assert all(not k.endswith(".rec") for k in loader.find())


def test_describe_read_missing_processed_skips(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    storage.write_text("input/b.xyz", "raw")  # no _processed/b.md
    loader = FileLoader(storage=storage, handler_registry=_registry_describe_emit())
    # build_text_units catches the per-file error and skips, yielding no docs.
    docs_df, units_df, mapping = loader.build_text_units()
    assert docs_df.empty


# --------------------------------------------------------------------------- #
# Emit merge math
# --------------------------------------------------------------------------- #

# The exact column sets the extractor produces (entities_relationships.py).
_ENTITY_COLS = {
    "id", "name", "title", "type", "description", "retrieval_queries",
    "human_readable_id", "graph_embedding", "text_unit_ids", "document_ids",
    "description_embedding", "degree", "community_ids", "observed_at",
    "confidence", "source",
}
_REL_COLS = {
    "id", "source", "target", "source_id", "target_id", "relationship_type",
    "description", "weight", "text_unit_ids", "document_ids",
    "human_readable_id", "rank", "observed_at", "confidence",
    "source_attribution", "source_degree", "target_degree",
}
_TU_COLS = {
    "id", "text", "n_tokens", "document_id", "document_ids", "observed_at",
    "confidence", "source", "entity_ids", "relationship_ids",
}


def test_build_emit_frames_shapes_and_embeddings():
    result = EmitResult(
        entities=[
            EmitEntity(name="ACME", type="ORG", description="a company"),
            EmitEntity(name="JANE", type="PERSON", description="an employee"),
        ],
        relationships=[
            EmitRelationship(source="ACME", target="JANE", type="EMPLOYS", description="hires"),
        ],
        text="summary text",
    )
    emb = {"ACME": [0.1, 0.2], "JANE": [0.3, 0.4]}
    frames = build_emit_frames(
        results=[("input/x.rec", result)],
        embeddings_by_name=emb,
    )

    assert set(frames.entities.columns) == _ENTITY_COLS
    assert set(frames.relationships.columns) == _REL_COLS
    assert set(frames.text_units.columns) == _TU_COLS
    assert len(frames.docs) == 1

    # Every emitted entity carries a (non-None) description embedding.
    assert all(e is not None for e in frames.entities["description_embedding"])

    # Provenance: entities point at the synthetic TU + doc.
    tu_id = frames.text_units.iloc[0]["id"]
    doc_id = frames.docs.iloc[0]["id"]
    for _, ent in frames.entities.iterrows():
        assert ent["text_unit_ids"] == [tu_id]
        assert ent["document_ids"] == [doc_id]

    # Relationship endpoints resolve to per-file entity ids.
    name_to_id = dict(zip(frames.entities["name"], frames.entities["id"]))
    rel = frames.relationships.iloc[0]
    assert rel["source_id"] == name_to_id["ACME"]
    assert rel["target_id"] == name_to_id["JANE"]
    assert rel["relationship_type"] == "EMPLOYS"

    # Mapping is keyed by the synthetic doc id.
    assert doc_id in frames.mapping
    assert frames.mapping[doc_id]["original_path"] == "input/x.rec"


def test_build_emit_frames_text_fallback():
    result = EmitResult(entities=[EmitEntity(name="A", description="d")], relationships=[])
    frames = build_emit_frames(
        results=[("input/y.rec", result)],
        embeddings_by_name={"A": [0.0]},
    )
    # No text supplied → a non-empty stub is generated for the citation anchor.
    assert frames.text_units.iloc[0]["text"]


def test_recompute_degrees():
    entities = pd.DataFrame({"name": ["A", "B", "C"], "degree": [0, 0, 0]})
    rels = pd.DataFrame(
        {
            "source": ["A", "A"],
            "target": ["B", "C"],
            "source_degree": [0, 0],
            "target_degree": [0, 0],
            "rank": [0, 0],
        }
    )
    ent2, rel2 = recompute_degrees(entities, rels)
    deg = dict(zip(ent2["name"], ent2["degree"]))
    assert deg == {"A": 2, "B": 1, "C": 1}
    assert rel2.iloc[0]["rank"] == deg["A"] + deg["B"]


def test_renumber_human_readable_ids():
    df = pd.DataFrame({"human_readable_id": [5, 9, 2]})
    out = renumber_human_readable_ids(df)
    assert out["human_readable_id"].tolist() == [0, 1, 2]


def test_entity_embedding_text_matches_extractor_format():
    assert entity_embedding_text("ACME", "a company", ["q1", "q2"]) == "ACME: a company q1 q2"
    assert entity_embedding_text("ACME", "a company", []) == "ACME: a company"


# --------------------------------------------------------------------------- #
# Core helper wiring (offline — fake embeddings, no LLM)
# --------------------------------------------------------------------------- #


class _FakeEmbeddings:
    """Minimal stand-in: deterministic 2-d vectors, records call count."""

    def __init__(self):
        self.calls = 0

    async def embed_safe(self, texts, tag=None):
        self.calls += 1
        return [[float(len(t)), 0.5] for t in texts]


def _make_grail(tmp_path: Path, registry: HandlerRegistry):
    from grail.config import Config
    from grail.core import GRAIL
    from grail.prompts import PromptRegistry

    return GRAIL(
        config=Config(root_dir=str(tmp_path)),
        storage=LocalStorage(root=tmp_path),
        llm=None,
        embeddings=_FakeEmbeddings(),
        prompts=PromptRegistry(),
        handlers=registry,
    )


@pytest.mark.asyncio
async def test_describe_prepass_materialises_markdown(tmp_path: Path):
    reg = HandlerRegistry()
    reg.register(_DescribeHandler())
    g = _make_grail(tmp_path, reg)
    g.storage.write_text("input/b.xyz", "raw bytes")

    loader = g._make_loader()
    await g._run_describe_prepass(loader, ["input/b.xyz"])

    processed = tmp_path / "input" / "_processed" / "b.md"
    assert processed.exists()
    assert processed.read_text() == "described:b.xyz"


@pytest.mark.asyncio
async def test_describe_prepass_is_mtime_cached(tmp_path: Path):
    reg = HandlerRegistry()

    class Counting(_DescribeHandler):
        runs = 0

        async def describe(self, source, ctx):
            type(self).runs += 1
            return "out"

    reg.register(Counting())
    g = _make_grail(tmp_path, reg)
    g.storage.write_text("input/b.xyz", "raw")

    loader = g._make_loader()
    await g._run_describe_prepass(loader, ["input/b.xyz"])
    await g._run_describe_prepass(loader, ["input/b.xyz"])  # cached, no re-run
    assert Counting.runs == 1


@pytest.mark.asyncio
async def test_emit_handler_embeds_descriptions(tmp_path: Path):
    reg = HandlerRegistry()
    reg.register(_EmitHandler())
    g = _make_grail(tmp_path, reg)
    g.storage.write_text("input/c.rec", "record")

    loader = g._make_loader()
    frames = await g._run_emit_handlers(loader, ["input/c.rec"])

    assert frames is not None
    assert frames.entities.iloc[0]["name"] == "ACME"
    # Embedding was computed and attached.
    assert frames.entities.iloc[0]["description_embedding"] is not None
    assert g.embeddings.calls == 1
