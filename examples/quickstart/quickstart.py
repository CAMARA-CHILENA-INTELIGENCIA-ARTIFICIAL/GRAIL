"""GRAIL — Python SDK quickstart.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

End-to-end demo of using GRAIL as a library (no CLI involved). Mirrors what
``grail index`` + ``grail query`` do, but from Python so you can embed the same
calls inside your own app.

Prereqs:

* ``uv pip install -e .`` from the repo root.
* A ``.env`` next to ``grail.yaml`` (or exported env vars) with the API key
  referenced by your endpoint — for the shipped config that is
  ``DEEPINFRA_API_KEY``.
* Source files in ``examples/quickstart/input/`` (the corpus that ships with
  the repo already satisfies this).

Run:

    uv run python examples/quickstart/quickstart.py
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from grail import GRAIL, load_config

HERE = Path(__file__).resolve().parent


async def main() -> None:
    # 1. Load the YAML config that lives next to this script. ``load_config``
    #    also accepts a directory (it will pick up ``grail.yaml`` + any
    #    per-module YAMLs) or you can build a ``Config`` object in Python — see
    #    docs/python_api.md for the no-YAML path.
    config = load_config(HERE / "grail.yaml")

    # 2. Build the orchestrator. ``from_config`` wires storage, LLM client,
    #    embedding client, prompt registry, cost tracker, and reranker.
    grail = GRAIL.from_config(config)

    # 3. Index the corpus. Skips work if you've already indexed — the run is
    #    idempotent at the project level (it writes a new run folder each call,
    #    so re-running re-extracts). Comment this out after the first run.
    print("Indexing…")
    index_result = await grail.index()
    if not index_result["ok"]:
        raise SystemExit(f"Indexing failed: {index_result.get('reason')}")
    print(
        f"  entities={index_result['entities']} "
        f"relationships={index_result['relationships']} "
        f"communities={index_result['communities']} "
        f"reports={index_result['reports']}"
    )

    # 4. Run searches. Every mode returns the same ``SearchResult`` shape:
    #    ``response`` (the answer string), ``context_data`` / ``context_text``
    #    (what the LLM saw), ``completion_time``, ``llm_calls``.
    print("\nLocal search (entity-anchored)…")
    local = await grail.search(
        "What are the main treatments mentioned in the corpus?",
        mode="local",
    )
    print(local.response)

    print("\nCascade search (entity + text rescue)…")
    cascade = await grail.search(
        "Which biomarkers does the guideline cite for treatment selection?",
        mode="cascade",
    )
    print(cascade.response)

    print("\nGlobal search (community-level synthesis)…")
    global_ = await grail.search(
        "What are the key themes across the corpus?",
        mode="global",
    )
    print(global_.response)

    print("\nAgent search (LLM picks tools)…")
    agent = await grail.agent_search(
        "Compare how the guidelines treat early-stage vs advanced disease."
    )
    print(agent.response)

    # 5. Inspect cost. The CostTracker is shared between LLM + embedding +
    #    reranker clients, so this is the single source of truth.
    print("\nCost ledger:")
    print(f"  total: {grail.cost_tracker.render_total_cost()}")
    print(f"  pricing status: {grail.cost_tracker.pricing_status()}")
    for tag, row in grail.cost_tracker.summary(by="tag").items():
        print(f"  {tag}: {row}")


if __name__ == "__main__":
    asyncio.run(main())
