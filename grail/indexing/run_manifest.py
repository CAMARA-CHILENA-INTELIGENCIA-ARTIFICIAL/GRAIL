"""
Per-run bookkeeping: run IDs, manifests, LLM call logs, summaries, current-pointer.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Every full :meth:`GRAIL.index` writes its artefacts under ``output/runs/<run_id>/``.
Incremental operations (:meth:`append` / :meth:`edit` / :meth:`delete`) modify
the **current** run in place and append a new entry to the operations log inside
its manifest.

Three files always land alongside the parquet artefacts:

* ``manifest.json`` — config snapshot, inputs processed, operation history,
  pricing status.
* ``llm_calls.jsonl`` — one line per LLM call (``CostTracker`` flushed).
* ``summary.json`` — compact, human-readable summary of the run.

A top-level ``output/current.json`` pointer marks which run is "active" for
search and incremental operations. Old runs remain on disk so users can
inspect / diff / roll back.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from grail.llm.cost import UNDEFINED_COST_REASON, CostTracker
from grail.storage import StorageBackend


# --- Path constants -----------------------------------------------------------------


def runs_root(output_folder: str) -> str:
    """Path (storage key) where per-run folders live, e.g. ``output/runs``."""
    return f"{output_folder.rstrip('/')}/runs"


def run_folder(output_folder: str, run_id: str) -> str:
    """Path (storage key) to one run, e.g. ``output/runs/2026-05-19T17-30-12-a3b4f``."""
    return f"{runs_root(output_folder)}/{run_id}"


def current_pointer_key(output_folder: str) -> str:
    """Path to the ``current.json`` pointer file at the output root."""
    return f"{output_folder.rstrip('/')}/current.json"


# --- ID generation ------------------------------------------------------------------


def generate_run_id(slug: Optional[str] = None) -> str:
    """Generate a filesystem-safe run id.

    Format: ``YYYY-MM-DDTHH-MM-SS-<5char>``. Colons in ISO datetimes are replaced
    with hyphens so the id works as a directory name on every platform. The
    5-char suffix is a hex slug — guards against collisions when two runs start
    within the same second.

    Pass ``slug`` to override the random suffix (e.g. from a CI build number).
    """
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H-%M-%S")
    suffix = slug if slug else secrets.token_hex(3)[:5]
    return f"{ts}-{suffix}"


# --- Run context --------------------------------------------------------------------


@dataclass
class RunOperation:
    """One operation in a run's history (``index`` / ``append`` / ``edit`` / ``delete``)."""

    name: str
    started_at: str          # ISO 8601 UTC
    finished_at: Optional[str] = None
    duration_s: Optional[float] = None
    ok: bool = False
    reason: Optional[str] = None
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunContext:
    """Holds the metadata GRAIL needs to write a complete run record."""

    run_id: str
    run_dir: str                                     # storage key (e.g. "output/runs/<id>")
    base_output_folder: str                          # storage key (e.g. "output")
    config_snapshot: dict[str, Any]
    grail_version: str
    operations: list[RunOperation] = field(default_factory=list)

    def begin_operation(self, name: str) -> RunOperation:
        op = RunOperation(name=name, started_at=_utcnow_iso())
        self.operations.append(op)
        return op

    def finish_operation(
        self,
        op: RunOperation,
        *,
        ok: bool,
        stats: Optional[dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> None:
        op.finished_at = _utcnow_iso()
        if op.started_at:
            try:
                op.duration_s = (
                    datetime.fromisoformat(op.finished_at) - datetime.fromisoformat(op.started_at)
                ).total_seconds()
            except ValueError:
                op.duration_s = None
        op.ok = ok
        op.reason = reason
        if stats is not None:
            op.stats = stats


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Pointer file -------------------------------------------------------------------


def read_current_run(storage: StorageBackend, output_folder: str) -> Optional[dict[str, Any]]:
    """Return the parsed ``current.json`` pointer, or ``None`` if absent / corrupt."""
    key = current_pointer_key(output_folder)
    if not storage.exists(key):
        return None
    try:
        return json.loads(storage.read_text(key))
    except (json.JSONDecodeError, OSError):
        return None


def write_current_run(
    storage: StorageBackend,
    output_folder: str,
    *,
    run_id: str,
    operation: str,
) -> None:
    """Update ``output/current.json`` to point at ``run_id``."""
    payload = {
        "run_id": run_id,
        "operation": operation,
        "updated_at": _utcnow_iso(),
        "run_dir": run_folder(output_folder, run_id),
    }
    storage.write_text(current_pointer_key(output_folder), json.dumps(payload, indent=2))


def resolve_active_run_folder(
    storage: StorageBackend, output_folder: str
) -> str:
    """Return the path GRAIL should read artefacts from.

    Resolution:
        1. If ``output/current.json`` exists and points at an existing run dir → use it.
        2. Else if the legacy flat ``output/final_entities.parquet`` exists → use ``output/``.
        3. Else fall back to ``output/`` (empty; first run will populate).
    """
    pointer = read_current_run(storage, output_folder)
    if pointer and pointer.get("run_dir") and storage.exists(pointer["run_dir"]):
        return pointer["run_dir"]
    if storage.exists(f"{output_folder.rstrip('/')}/final_entities.parquet"):
        return output_folder
    return output_folder


# --- Manifest / summary / call log --------------------------------------------------


def _manifest_payload(
    ctx: RunContext, cost: CostTracker, *, files_processed: Optional[list[dict[str, Any]]] = None
) -> dict[str, Any]:
    pricing_status = cost.pricing_status()
    total_cost_str = cost.render_total_cost()
    return {
        "run_id": ctx.run_id,
        "run_dir": ctx.run_dir,
        "grail_version": ctx.grail_version,
        "created_at": ctx.operations[0].started_at if ctx.operations else _utcnow_iso(),
        "updated_at": _utcnow_iso(),
        "operations": [_serialize_op(op) for op in ctx.operations],
        "files_processed": files_processed or [],
        "config": ctx.config_snapshot,
        "llm": {
            "total_calls": len(cost.records),
            "total_tokens": sum(r.total_tokens for r in cost.records),
            "by_tag": cost.summary(by="tag"),
            "by_model": cost.summary(by="model"),
            "pricing_status": pricing_status,
            "total_cost_usd": cost.total_cost_usd() if pricing_status != "undefined" else None,
            "total_cost_display": total_cost_str,
            "unresolved_models": cost.unresolved_models(),
            "undefined_reason": UNDEFINED_COST_REASON if pricing_status == "undefined" else None,
        },
    }


def _serialize_op(op: RunOperation) -> dict[str, Any]:
    return {
        "name": op.name,
        "started_at": op.started_at,
        "finished_at": op.finished_at,
        "duration_s": op.duration_s,
        "ok": op.ok,
        "reason": op.reason,
        "stats": op.stats,
    }


def write_manifest(
    storage: StorageBackend,
    ctx: RunContext,
    cost: CostTracker,
    *,
    files_processed: Optional[list[dict[str, Any]]] = None,
) -> str:
    """Persist ``manifest.json`` inside the run folder. Returns the key."""
    payload = _manifest_payload(ctx, cost, files_processed=files_processed)
    key = f"{ctx.run_dir}/manifest.json"
    storage.write_text(key, json.dumps(payload, indent=2, default=str))
    return key


def write_llm_calls_log(
    storage: StorageBackend,
    ctx: RunContext,
    cost: CostTracker,
) -> str:
    """Persist ``llm_calls.jsonl`` — one record per call, JSON-lines format."""
    key = f"{ctx.run_dir}/llm_calls.jsonl"
    lines = "\n".join(json.dumps(rec, default=str) for rec in cost.to_dicts())
    storage.write_text(key, lines + ("\n" if lines else ""))
    return key


def write_summary(
    storage: StorageBackend,
    ctx: RunContext,
    cost: CostTracker,
    *,
    counts: dict[str, Any],
) -> str:
    """Persist a compact ``summary.json`` suitable for printing to stdout."""
    last_op = ctx.operations[-1] if ctx.operations else None
    pricing_status = cost.pricing_status()
    payload = {
        "run_id": ctx.run_id,
        "run_dir": ctx.run_dir,
        "operation": last_op.name if last_op else "unknown",
        "ok": last_op.ok if last_op else False,
        "duration_s": last_op.duration_s if last_op else None,
        "counts": counts,
        "llm": {
            "calls": len(cost.records),
            "total_tokens": sum(r.total_tokens for r in cost.records),
            "by_tag": cost.summary(by="tag"),
            "pricing_status": pricing_status,
            "total_cost_display": cost.render_total_cost(),
        },
    }
    key = f"{ctx.run_dir}/summary.json"
    storage.write_text(key, json.dumps(payload, indent=2, default=str))
    return key
