"""GRAIL — memory-mode SDK quickstart.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

End-to-end demo of using GRAIL's memory mode as a library. No LLM, no
embeddings — every step is purely structural so the script runs offline.

What this covers (Phases A–E of the memory-mode build):

  * Phase A — markdown frontmatter loader, new schema columns
  * Phase B — MemoryProject tool surface (add_observation / add_entity /
    add_relationship / add_community / list_*)
  * Phase C — RecallFilter + the ``recall`` peer search mode
  * Phase D — consolidate() proposal generator + accept/reject
  * Phase E — meta.json + workspace registry maintenance

Prereqs:

  * ``uv pip install -e .`` from the repo root.
  * No API key needed — the script passes ``embeddings=None`` so no network
    calls happen. (You can plug in real embeddings later by deleting the
    ``embeddings=None`` argument.)

Run:

  uv run python examples/memory_quickstart/quickstart.py
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from grail import MemoryProject, RecallFilter


async def main() -> None:
    # 1. Open (or create) a memory project. ``meta.json`` is written on first
    #    open; the workspace registry (``~/.grail/registry.json``) is updated.
    #    We use a temp dir so the demo is self-contained and re-runnable.
    project_dir = Path(tempfile.mkdtemp(prefix="grail-memory-demo-"))
    print(f"Project: {project_dir}")

    mp = MemoryProject(project_dir, embeddings=None)
    # Tune the consolidate threshold down for the demo (default 30).
    mp.config.memory.min_entities_for_consolidate = 5
    mp.config.memory.confidence_threshold_discover_community = 0.5

    print(f"  mode={mp.meta.mode}  id={mp.meta.id}  name={mp.meta.name}")

    # 2. Write observations under different folder communities. Each
    #    observation is a markdown file under memories/<category>/ with YAML
    #    frontmatter. Entities + relationships supplied by the caller go
    #    straight into the parquets — no LLM extraction.
    print("\n=== Phase B: add observations ===")

    work_obs = await mp.add_observation(
        title="Meeting with Acme on Q2 pricing",
        content="John pushed for 15% reduction. Sarah pushed back, citing margin.",
        category="work/clients/acme",
        tags=["meeting", "pricing", "Q2"],
        observed_at="2026-05-27T15:30:00Z",
        entities=[
            {"name": "JOHN_SMITH", "type": "PERSON",
             "description": "Acme procurement lead."},
            {"name": "SARAH_LIN", "type": "PERSON",
             "description": "Our account manager."},
            {"name": "ACME", "type": "ORGANIZATION",
             "description": "Client — manufacturing sector."},
            {"name": "PRICING_Q2", "type": "CONCEPT",
             "description": "Q2 pricing negotiation."},
        ],
        relationships=[
            {"source": "JOHN_SMITH", "target": "ACME",
             "relationship_type": "WORKS_AT", "description": "John works at Acme."},
            {"source": "SARAH_LIN", "target": "PRICING_Q2",
             "relationship_type": "ASSOCIATED_WITH",
             "description": "Sarah leads the pricing discussion."},
            {"source": "JOHN_SMITH", "target": "SARAH_LIN",
             "relationship_type": "MENTIONS", "description": "Negotiating with."},
        ],
    )
    print(f"  → {work_obs.data['slug']}")
    for warning in work_obs.warnings:
        print(f"    warning: {warning[:80]}...")

    followup = await mp.add_observation(
        title="Acme follow-up email",
        content="John replied with revised terms. Mentioned Sarah's earlier proposal.",
        category="work/clients/acme",
        tags=["email", "pricing"],
        observed_at="2026-05-28T09:15:00Z",
        entities=[
            {"name": "JOHN_SMITH", "type": "PERSON",
             "description": "Acme procurement lead."},
            {"name": "ACME", "type": "ORGANIZATION", "description": "Same client."},
            {"name": "PRICING_Q2", "type": "CONCEPT", "description": "Continued."},
        ],
        relationships=[
            {"source": "JOHN_SMITH", "target": "PRICING_Q2",
             "relationship_type": "MENTIONS", "description": "Sent counter-proposal."},
        ],
    )
    print(f"  → {followup.data['slug']}")

    # Drop ALICE into a different category to exercise multi-membership +
    # cross-folder discovery later.
    personal = await mp.add_observation(
        title="Dinner with friends",
        content="Saw Alice Smith and John (yes, same Acme John).",
        category="personal/friends",
        tags=["dinner"],
        observed_at="2026-05-29T20:00:00Z",
        entities=[
            {"name": "ALICE_SMITH", "type": "PERSON",
             "description": "Friend from college."},
            {"name": "JOHN_SMITH", "type": "PERSON",
             "description": "Also a personal friend."},
        ],
        relationships=[
            {"source": "ALICE_SMITH", "target": "JOHN_SMITH",
             "relationship_type": "MENTIONS",
             "description": "Hung out at dinner."},
        ],
    )
    print(f"  → {personal.data['slug']}")

    # 3. Inventory helpers.
    print("\n=== Phase B: list_* read-side helpers ===")
    print("  categories:", mp.list_categories().data["categories"])
    ents_reply = mp.list_entities(limit=10)
    print(f"  entities ({ents_reply.data['total']} total):")
    for e in ents_reply.data["entities"]:
        cids = e["community_ids"] or []
        print(f"    {e['name']:<14} type={e['type']:<14} communities={cids}")

    # 4. Phase C — recall: structural-only search with no LLM.
    print("\n=== Phase C: recall mode (no LLM) ===")
    last_week = await mp.recall(since="7d", category="work/clients/**")
    print(f"  since=7d category=work/clients/** → "
          f"{len(last_week.data['observations'])} observations, "
          f"{len(last_week.data['entities'])} entities")
    for obs in last_week.data["observations"]:
        print(f"    {obs['observed_at']}  {obs['title']}  tags={obs['tags']}")

    pricing_tag = await mp.recall(tag="pricing")
    print(f"  tag=pricing → {len(pricing_tag.data['observations'])} observations")

    # 5. Phase B — find_similar_entity (edit-distance fallback when no embeddings).
    print("\n=== Phase B: find_similar_entity (edit distance) ===")
    similar = await mp.find_similar_entity("john smyth")
    for c in similar.data["candidates"]:
        print(f"  {c['name']:<14} sim={c['similarity']:.3f} method={c['method']}")

    # 6. Phase D — consolidate generates proposals (read pass, no mutation).
    print("\n=== Phase D: consolidate → proposals ===")
    cons = mp.consolidate()
    if not cons.ok:
        print(f"  refused: {cons.error}")
    else:
        print(f"  generated {cons.data['total']} proposal(s); by kind:")
        for kind, n in cons.data["by_kind"].items():
            print(f"    {kind:<22} {n}")
        print(f"  yaml: {cons.data['proposal_set_path']}")

    # 7. Phase D — accept one proposal, watch the parquets mutate.
    proposals = mp.list_proposals().data["proposals"]
    if proposals:
        target = proposals[0]
        print(f"\n  accepting first: {target['id'][:8]} ({target['kind']})")
        print(f"    rationale: {target['rationale'][:80]}...")
        applied = mp.accept_proposal(target["id"])
        if applied.ok:
            print(f"    → status={applied.data['status']}; "
                  f"outcome={applied.data['outcome']}")

    # 8. Phase E surface: show the meta.json + history audit log.
    print("\n=== Phase E: meta.json + audit log ===")
    print(f"  meta.json: {(project_dir / 'meta.json').exists()}")
    history = project_dir / "_history.jsonl"
    if history.exists():
        print(f"  _history.jsonl operations: {sum(1 for _ in history.open())} entries")

    print(f"\nDone. Project preserved at: {project_dir}")
    print("Delete it when you're done exploring:")
    print(f"  rm -rf {project_dir}")


if __name__ == "__main__":
    asyncio.run(main())
