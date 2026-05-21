"""
Lightweight token + cost tracking.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Replaces the proprietary ``AsyncCallbackManager`` cost-accounting surface. Every LLM
call goes through :meth:`CostTracker.record`; users can pull summaries grouped by
``tag`` (logical operation, e.g. ``"entity_extraction"``) and by ``session_id``
(one user-facing request).

## Pricing policy

The OpenAI Python SDK does **not** expose model pricing — ``/v1/models`` only
returns ``{id, object, created, owned_by}``. Any provider that does ship rates
does it through their own extension (e.g. DeepInfra returns ``metadata.pricing``,
which is not part of the OpenAI shape).

For that reason GRAIL takes the conservative position:

* The built-in ``DEFAULT_PRICING`` lists only canonical OpenAI / Anthropic
  models that GRAIL maintainers verify by hand.
* For any other model, the cost is reported as **Undefined** unless the user
  supplies a rate via :class:`grail.config.LLMConfig.extra_pricing`.
* :meth:`CostTracker.pricing_status` exposes whether the ledger is ``complete``,
  ``partial``, or ``undefined`` so the index summary can surface an accurate
  message instead of pretending zero == free.

Cost rates are USD-per-1M-tokens, mirroring how the major providers publish them.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any, Optional


# Public string returned in summaries / manifests when no model in the ledger has a
# pricing match. Kept as a constant so callers can use it for display + tests.
UNDEFINED_COST_REASON: str = (
    "Undefined, provider does not follow the proper OpenAI Python package output format"
)


@dataclass
class UsageRecord:
    """One LLM call's accounting line."""

    model: str
    tag: Optional[str]
    session_id: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float           # 0.0 when not resolved; check ``cost_resolved`` to disambiguate.
    cost_resolved: bool       # True when a pricing entry matched the model.
    duration_s: float
    cache_hit: bool = False


# Best-effort default price book — only includes rates that the GRAIL maintainers
# verify by hand. Anything missing here surfaces as "Undefined" in summaries.
# Values are USD per 1M tokens (prompt, completion).
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "claude-3-5-sonnet-latest": (3.0, 15.0),
    "claude-3-5-haiku-latest": (0.80, 4.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _resolve_pricing_key(
    model: str, pricing: dict[str, tuple[float, float]]
) -> Optional[str]:
    """Resolve a model identifier to a key in ``pricing``, or ``None`` if no match.

    Resolution order:
        1. Exact match.
        2. Strip ``"endpoint|"`` prefix, retry exact match.
        3. Substring fallback (key ends-with or appears in the model id).
    """
    if model in pricing:
        return model
    bare = model.split("|", 1)[1] if "|" in model else model
    if bare in pricing:
        return bare
    return next((m for m in pricing if bare.endswith(m) or m in bare), None)


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    pricing: dict[str, tuple[float, float]],
) -> Optional[float]:
    """Return USD cost given token counts and a price book, or ``None`` if the model
    has no matching pricing entry.

    The previous version returned ``0.0`` for both "free call" and "unknown model"
    cases, which made the ledger lie about cost. ``None`` lets the caller signal
    "we have no rate for this provider/model" honestly.
    """
    key = _resolve_pricing_key(model, pricing)
    if key is None:
        return None
    in_rate, out_rate = pricing[key]
    return (prompt_tokens / 1_000_000.0) * in_rate + (completion_tokens / 1_000_000.0) * out_rate


@dataclass
class CostTracker:
    """Thread-safe ledger of LLM usage."""

    pricing: dict[str, tuple[float, float]] = field(default_factory=lambda: dict(DEFAULT_PRICING))
    records: list[UsageRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    # ------------------------------------------------------------------ recording

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_s: float,
        tag: Optional[str] = None,
        session_id: Optional[str] = None,
        cache_hit: bool = False,
    ) -> UsageRecord:
        cost = estimate_cost(model, prompt_tokens, completion_tokens, self.pricing)
        rec = UsageRecord(
            model=model,
            tag=tag,
            session_id=session_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost if cost is not None else 0.0,
            cost_resolved=cost is not None,
            duration_s=duration_s,
            cache_hit=cache_hit,
        )
        with self._lock:
            self.records.append(rec)
        return rec

    # ------------------------------------------------------------------ aggregation

    def summary(self, *, by: str = "tag") -> dict[str, dict[str, Any]]:
        """Aggregate records by ``"tag" | "model" | "session_id"``.

        Each bucket includes a ``cost_resolved`` count so callers can tell how
        much of the aggregated ``cost_usd`` was actually priced versus filled
        with zeros from unresolved models.
        """
        key_fn = {"tag": lambda r: r.tag or "<none>",
                  "model": lambda r: r.model,
                  "session_id": lambda r: r.session_id or "<none>"}.get(by)
        if key_fn is None:
            raise ValueError(f"Unsupported group key: {by}")
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            for r in self.records:
                key = key_fn(r)
                bucket = out.setdefault(
                    key,
                    {
                        "calls": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": 0.0,
                        "duration_s": 0.0,
                        "cache_hits": 0,
                        "calls_resolved": 0,
                        "calls_unresolved": 0,
                    },
                )
                bucket["calls"] += 1
                bucket["prompt_tokens"] += r.prompt_tokens
                bucket["completion_tokens"] += r.completion_tokens
                bucket["total_tokens"] += r.total_tokens
                bucket["cost_usd"] += r.cost_usd
                bucket["duration_s"] += r.duration_s
                bucket["cache_hits"] += int(r.cache_hit)
                if r.cost_resolved:
                    bucket["calls_resolved"] += 1
                else:
                    bucket["calls_unresolved"] += 1
        return out

    def total_cost_usd(self) -> float:
        """Sum of resolved costs in USD. May be 0.0 even with many calls — check
        :meth:`pricing_status` to know whether that means "free" or "unpriced"."""
        with self._lock:
            return sum(r.cost_usd for r in self.records)

    def pricing_status(self) -> str:
        """Return ``"complete"``, ``"partial"``, or ``"undefined"`` describing
        whether every record in the ledger had a pricing match.

        * ``complete`` — every record was priced (or the ledger is empty).
        * ``partial`` — at least one record priced, at least one not.
        * ``undefined`` — no record was priced (typical for self-hosted /
          third-party providers without manual rate entries).
        """
        with self._lock:
            if not self.records:
                return "complete"
            resolved_count = sum(1 for r in self.records if r.cost_resolved)
        if resolved_count == len(self.records):
            return "complete"
        if resolved_count == 0:
            return "undefined"
        return "partial"

    def unresolved_models(self) -> list[str]:
        """List the distinct model ids that lacked pricing — useful for prompting
        the user to supply ``extra_pricing`` entries.
        """
        with self._lock:
            return sorted({r.model for r in self.records if not r.cost_resolved})

    # ------------------------------------------------------------------ serialization

    def to_dicts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(r) for r in self.records]

    def render_total_cost(self) -> str:
        """Human-readable total. Returns the ``UNDEFINED_COST_REASON`` string when
        every record is unresolved, a partial-resolution warning when some are
        unresolved, or a dollar amount otherwise.
        """
        status = self.pricing_status()
        if status == "undefined":
            return UNDEFINED_COST_REASON
        if status == "partial":
            unresolved = self.unresolved_models()
            return (
                f"${self.total_cost_usd():.4f} (partial — {len(unresolved)} model(s) had no pricing: "
                f"{', '.join(unresolved)})"
            )
        return f"${self.total_cost_usd():.4f}"


def now() -> float:
    return time.perf_counter()
