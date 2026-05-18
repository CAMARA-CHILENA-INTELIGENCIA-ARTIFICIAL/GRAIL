"""
Lightweight token + cost tracking.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Replaces the proprietary ``AsyncCallbackManager`` cost-accounting surface. Every LLM
call goes through :meth:`CostTracker.record`; users can pull summaries grouped by
``tag`` (logical operation, e.g. ``"entity_extraction"``) and by ``session_id``
(one user-facing request). Pricing lookups are best-effort; if a model is unknown
we just track tokens.

Cost rates are USD-per-1M-tokens, mirroring how the major providers publish them.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any, Optional


@dataclass
class UsageRecord:
    """One LLM call's accounting line."""

    model: str
    tag: Optional[str]
    session_id: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    duration_s: float
    cache_hit: bool = False


# Best-effort default price book — extend or override in config.
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


def estimate_cost(
    model: str, prompt_tokens: int, completion_tokens: int, pricing: dict[str, tuple[float, float]]
) -> float:
    """Return USD cost given token counts and a price book. Falls back to 0 if unknown."""
    key = model
    if key not in pricing:
        # Strip provider prefix and try again.
        if "|" in key:
            key = key.split("|", 1)[1]
        if key not in pricing:
            # Match by suffix (e.g. "meta-llama/Llama-3.3-70B-Instruct-Turbo" against partial keys).
            match = next((m for m in pricing if key.endswith(m) or m in key), None)
            if match is None:
                return 0.0
            key = match
    in_rate, out_rate = pricing[key]
    return (prompt_tokens / 1_000_000.0) * in_rate + (completion_tokens / 1_000_000.0) * out_rate


@dataclass
class CostTracker:
    """Thread-safe ledger of LLM usage."""

    pricing: dict[str, tuple[float, float]] = field(default_factory=lambda: dict(DEFAULT_PRICING))
    records: list[UsageRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

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
            cost_usd=cost,
            duration_s=duration_s,
            cache_hit=cache_hit,
        )
        with self._lock:
            self.records.append(rec)
        return rec

    def summary(self, *, by: str = "tag") -> dict[str, dict[str, Any]]:
        """Aggregate records by ``"tag" | "model" | "session_id"``."""
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
                    {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                     "total_tokens": 0, "cost_usd": 0.0, "duration_s": 0.0, "cache_hits": 0},
                )
                bucket["calls"] += 1
                bucket["prompt_tokens"] += r.prompt_tokens
                bucket["completion_tokens"] += r.completion_tokens
                bucket["total_tokens"] += r.total_tokens
                bucket["cost_usd"] += r.cost_usd
                bucket["duration_s"] += r.duration_s
                bucket["cache_hits"] += int(r.cache_hit)
        return out

    def total_cost_usd(self) -> float:
        with self._lock:
            return sum(r.cost_usd for r in self.records)

    def to_dicts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(r) for r in self.records]


def now() -> float:
    return time.perf_counter()
