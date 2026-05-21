"""Run manifest / cost tracking tests."""
import json
from pathlib import Path

from grail.indexing.run_manifest import (
    RunContext,
    generate_run_id,
    read_current_run,
    resolve_active_run_folder,
    run_folder,
    write_current_run,
    write_llm_calls_log,
    write_manifest,
    write_summary,
)
from grail.llm.cost import UNDEFINED_COST_REASON, CostTracker
from grail.storage import LocalStorage


def test_generate_run_id_shape():
    import re

    rid = generate_run_id()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-[a-f0-9]{5}$", rid), (
        f"Expected YYYY-MM-DDTHH-MM-SS-<5hex>, got {rid}"
    )


def test_generate_run_id_unique_within_a_second():
    seen = {generate_run_id() for _ in range(20)}
    assert len(seen) == 20


def test_resolve_active_run_falls_back_to_legacy(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    # Drop a legacy artefact at output/.
    storage.write_text("output/final_entities.parquet", "fake")
    assert resolve_active_run_folder(storage, "output") == "output"


def test_resolve_active_run_uses_pointer(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    # Create a run dir and a pointer.
    storage.ensure_prefix("output/runs/2026-05-19T10-00-00-aaaaa")
    write_current_run(storage, "output", run_id="2026-05-19T10-00-00-aaaaa", operation="index")
    assert resolve_active_run_folder(storage, "output") == "output/runs/2026-05-19T10-00-00-aaaaa"


def test_run_folder_path():
    assert run_folder("output", "2026-05-19T10-00-00-abcde") == "output/runs/2026-05-19T10-00-00-abcde"


def test_manifest_round_trip(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    ctx = RunContext(
        run_id="r1",
        run_dir="output/runs/r1",
        base_output_folder="output",
        config_snapshot={"project_name": "test"},
        grail_version="0.1.0",
    )
    storage.ensure_prefix(ctx.run_dir)
    op = ctx.begin_operation("index")
    cost = CostTracker()
    cost.record(model="openai|gpt-4o-mini", prompt_tokens=100, completion_tokens=50, duration_s=0.5, tag="x")
    ctx.finish_operation(op, ok=True, stats={"entities": 3})

    manifest_key = write_manifest(storage, ctx, cost)
    summary_key = write_summary(storage, ctx, cost, counts={"entities": 3})
    calls_key = write_llm_calls_log(storage, ctx, cost)

    manifest = json.loads(storage.read_text(manifest_key))
    summary = json.loads(storage.read_text(summary_key))
    calls = [json.loads(l) for l in storage.read_text(calls_key).splitlines() if l]

    assert manifest["run_id"] == "r1"
    assert manifest["operations"][0]["name"] == "index"
    assert manifest["operations"][0]["ok"]
    assert manifest["llm"]["pricing_status"] == "complete"
    assert manifest["llm"]["total_cost_usd"] is not None
    assert summary["counts"]["entities"] == 3
    assert len(calls) == 1
    assert calls[0]["model"] == "openai|gpt-4o-mini"


def test_manifest_marks_undefined_when_no_pricing(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    ctx = RunContext(
        run_id="r2",
        run_dir="output/runs/r2",
        base_output_folder="output",
        config_snapshot={},
        grail_version="0.1.0",
    )
    storage.ensure_prefix(ctx.run_dir)
    op = ctx.begin_operation("index")
    cost = CostTracker()  # default pricing has no DeepInfra models
    cost.record(
        model="deepinfra|google/gemma-4-26B-A4B-it",
        prompt_tokens=1000,
        completion_tokens=500,
        duration_s=1.0,
        tag="entity_extraction",
    )
    ctx.finish_operation(op, ok=True)

    manifest_key = write_manifest(storage, ctx, cost)
    manifest = json.loads(storage.read_text(manifest_key))
    assert manifest["llm"]["pricing_status"] == "undefined"
    assert manifest["llm"]["total_cost_usd"] is None
    assert manifest["llm"]["total_cost_display"] == UNDEFINED_COST_REASON
    assert "deepinfra|google/gemma-4-26B-A4B-it" in manifest["llm"]["unresolved_models"]


def test_pointer_file_round_trip(tmp_path: Path):
    storage = LocalStorage(root=tmp_path)
    write_current_run(storage, "output", run_id="r3", operation="index")
    pointer = read_current_run(storage, "output")
    assert pointer is not None
    assert pointer["run_id"] == "r3"
    assert pointer["operation"] == "index"
