"""
Consolidate proposals — the structured suggestions ``consolidate()`` emits.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The contract:
1. ``consolidate()`` produces a ``ProposalSet`` — a yaml file at
   ``output/proposals/<ULID>.yaml`` and a ``latest.yaml`` pointing to it.
2. Each proposal carries ``status="pending"`` until the agent (or a human)
   calls ``accept_proposal()`` / ``reject_proposal()``.
3. Apply semantics live in ``MemoryProject``: most proposal kinds mutate the
   parquets directly; ``split_folder`` generates a shell script the agent can
   review and run because moving files on disk is destructive.

A proposal file is self-documenting — status transitions are written back in
place so anyone can `cat` it and understand what's pending vs. resolved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import yaml

from grail.memory.identity import new_ulid


ProposalKind = Literal[
    "discover_community",
    "move_entity",
    "merge_aliases",
    "split_folder",
]
ProposalStatus = Literal[
    "pending",
    "accepted",
    "rejected",
    "accepted-pending-manual",
]


def _iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Proposal:
    """One actionable suggestion emitted by an analysis."""

    id: str
    kind: ProposalKind
    rationale: str
    confidence: float
    status: ProposalStatus = "pending"
    # kind-specific payload — kept as a free-form dict to avoid an exploding
    # set of subclasses. Each analysis documents the shape it produces and
    # the apply path reads only the fields it needs.
    payload: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_iso)
    resolved_at: Optional[str] = None
    resolved_reason: Optional[str] = None
    applied_outcome: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def fresh(
        cls,
        *,
        kind: ProposalKind,
        rationale: str,
        confidence: float,
        payload: dict[str, Any],
        evidence: Optional[dict[str, Any]] = None,
    ) -> "Proposal":
        return cls(
            id=new_ulid(),
            kind=kind,
            rationale=rationale,
            confidence=float(confidence),
            payload=dict(payload),
            evidence=dict(evidence or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "confidence": float(self.confidence),
            "rationale": self.rationale,
            "payload": dict(self.payload),
            "evidence": dict(self.evidence),
            "created_at": self.created_at,
        }
        if self.resolved_at is not None:
            out["resolved_at"] = self.resolved_at
        if self.resolved_reason is not None:
            out["resolved_reason"] = self.resolved_reason
        if self.applied_outcome:
            out["applied_outcome"] = dict(self.applied_outcome)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Proposal":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),  # type: ignore[arg-type]
            status=str(data.get("status", "pending")),  # type: ignore[arg-type]
            rationale=str(data.get("rationale", "")),
            confidence=float(data.get("confidence", 0.0)),
            payload=dict(data.get("payload") or {}),
            evidence=dict(data.get("evidence") or {}),
            created_at=str(data.get("created_at") or _iso()),
            resolved_at=data.get("resolved_at"),
            resolved_reason=data.get("resolved_reason"),
            applied_outcome=dict(data.get("applied_outcome") or {}),
        )


@dataclass
class ProposalSet:
    """One ``consolidate()`` run's worth of proposals, persisted as a yaml file."""

    schema_version: int = 1
    generated_at: str = field(default_factory=_iso)
    graph_snapshot: dict[str, Any] = field(default_factory=dict)
    proposals: list[Proposal] = field(default_factory=list)
    # Where this set lives on disk (set on save/load).
    path: Optional[Path] = None

    def by_kind(self, kind: ProposalKind) -> list[Proposal]:
        return [p for p in self.proposals if p.kind == kind]

    def pending(self) -> list[Proposal]:
        return [p for p in self.proposals if p.status == "pending"]

    def find(self, proposal_id: str) -> Optional[Proposal]:
        for p in self.proposals:
            if p.id == proposal_id or p.id.startswith(proposal_id):
                return p
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "graph_snapshot": dict(self.graph_snapshot),
            "proposals": [p.to_dict() for p in self.proposals],
        }

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(self.to_dict(), sort_keys=False, default_flow_style=False)
        p.write_text(text, encoding="utf-8")
        self.path = p
        # Maintain ``latest.yaml`` next to the file so consumers always have
        # a stable entry point. Cross-platform symlinks are flaky, so we just
        # write a copy.
        latest = p.parent / "latest.yaml"
        latest.write_text(text, encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "ProposalSet":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(
            schema_version=int(raw.get("schema_version", 1)),
            generated_at=str(raw.get("generated_at") or _iso()),
            graph_snapshot=dict(raw.get("graph_snapshot") or {}),
            proposals=[Proposal.from_dict(d) for d in (raw.get("proposals") or [])],
            path=p,
        )


def proposals_root(project_path: str | Path, output_folder: str = "output") -> Path:
    return Path(project_path) / output_folder / "proposals"


def archive_dir(project_path: str | Path, output_folder: str = "output") -> Path:
    return proposals_root(project_path, output_folder) / "archive"


def latest_proposal_set(
    project_path: str | Path, output_folder: str = "output"
) -> Optional[ProposalSet]:
    """Return the most-recent ProposalSet, resolved to its canonical file.

    ``latest.yaml`` is treated as a pointer-copy: when present, we still
    return the timestamped ``<ULID>.yaml`` as ``ps.path`` so callers always
    write to the canonical file (and ``save`` re-mirrors to ``latest.yaml``).
    """
    root = proposals_root(project_path, output_folder)
    candidates = sorted(
        p for p in root.glob("*.yaml") if p.name != "latest.yaml"
    )
    if candidates:
        return ProposalSet.load(candidates[-1])
    # If only latest.yaml exists (shouldn't happen in practice, but defensive),
    # fall back to it.
    latest = root / "latest.yaml"
    if latest.exists():
        return ProposalSet.load(latest)
    return None


def maybe_archive(set_path: Path, ps: ProposalSet) -> Optional[Path]:
    """If every proposal in ``ps`` is resolved, move the file to archive/."""
    if any(p.status == "pending" for p in ps.proposals):
        return None
    if not ps.proposals:
        return None
    arch = set_path.parent / "archive"
    arch.mkdir(parents=True, exist_ok=True)
    dest = arch / set_path.name
    set_path.rename(dest)
    ps.path = dest
    # If latest.yaml points at the same content, drop it so the next consolidate
    # run rebuilds it cleanly.
    latest = (set_path.parent / "latest.yaml")
    if latest.exists():
        latest.unlink()
    return dest


__all__ = [
    "Proposal",
    "ProposalKind",
    "ProposalSet",
    "ProposalStatus",
    "archive_dir",
    "latest_proposal_set",
    "maybe_archive",
    "proposals_root",
]
