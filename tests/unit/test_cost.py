"""CostTracker pricing-resolution tests."""
from grail.llm.cost import (
    DEFAULT_PRICING,
    UNDEFINED_COST_REASON,
    CostTracker,
    estimate_cost,
)


def test_estimate_cost_known_model_returns_float():
    cost = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000, DEFAULT_PRICING)
    assert cost is not None
    # Known rates: (0.15, 0.60) per 1M → 0.15 + 0.60 = 0.75
    assert abs(cost - 0.75) < 1e-6


def test_estimate_cost_unknown_model_returns_none():
    assert estimate_cost("does-not-exist|wat", 100, 100, DEFAULT_PRICING) is None


def test_estimate_cost_strips_endpoint_prefix():
    cost = estimate_cost("openai|gpt-4o-mini", 1_000_000, 0, DEFAULT_PRICING)
    assert cost is not None
    assert abs(cost - 0.15) < 1e-6


def test_record_marks_resolved_for_priced_models():
    t = CostTracker()
    rec = t.record(model="openai|gpt-4o-mini", prompt_tokens=100, completion_tokens=50, duration_s=0.1)
    assert rec.cost_resolved is True
    assert rec.cost_usd > 0


def test_record_marks_unresolved_for_unknown_models():
    t = CostTracker()
    rec = t.record(model="deepinfra|whatever", prompt_tokens=100, completion_tokens=50, duration_s=0.1)
    assert rec.cost_resolved is False
    assert rec.cost_usd == 0.0


def test_pricing_status_complete():
    t = CostTracker()
    t.record(model="gpt-4o-mini", prompt_tokens=10, completion_tokens=10, duration_s=0.01)
    assert t.pricing_status() == "complete"


def test_pricing_status_undefined():
    t = CostTracker()
    t.record(model="deepinfra|unknown-model", prompt_tokens=10, completion_tokens=10, duration_s=0.01)
    assert t.pricing_status() == "undefined"
    assert t.render_total_cost() == UNDEFINED_COST_REASON


def test_pricing_status_partial():
    t = CostTracker()
    t.record(model="gpt-4o-mini", prompt_tokens=10, completion_tokens=10, duration_s=0.01)
    t.record(model="deepinfra|unknown-model", prompt_tokens=10, completion_tokens=10, duration_s=0.01)
    assert t.pricing_status() == "partial"
    assert "partial" in t.render_total_cost()


def test_user_pricing_overrides_defaults():
    t = CostTracker()
    # Inject pricing for a model that wouldn't otherwise resolve.
    t.pricing["deepinfra|google/gemma-4-26B-A4B-it"] = (0.07, 0.34)
    rec = t.record(
        model="deepinfra|google/gemma-4-26B-A4B-it",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        duration_s=1.0,
    )
    assert rec.cost_resolved
    assert abs(rec.cost_usd - 0.41) < 1e-6


def test_unresolved_models_list_is_distinct():
    t = CostTracker()
    t.record(model="deepinfra|a", prompt_tokens=1, completion_tokens=1, duration_s=0.01)
    t.record(model="deepinfra|a", prompt_tokens=1, completion_tokens=1, duration_s=0.01)
    t.record(model="deepinfra|b", prompt_tokens=1, completion_tokens=1, duration_s=0.01)
    assert sorted(t.unresolved_models()) == ["deepinfra|a", "deepinfra|b"]


# ----------------------------------------------------------------- embedding client

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from grail.llm import EmbeddingClient


class _FakeEmbeddingResponse:
    def __init__(self, n_inputs: int, n_dims: int = 4, prompt_tokens: int = 42) -> None:
        self.data = [SimpleNamespace(embedding=[0.0] * n_dims) for _ in range(n_inputs)]
        self.usage = SimpleNamespace(prompt_tokens=prompt_tokens, total_tokens=prompt_tokens)


class _FakeEmbeddingsAPI:
    def __init__(self, prompt_tokens_per_call: int = 42) -> None:
        self._tokens = prompt_tokens_per_call
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeEmbeddingResponse:
        self.calls.append(kwargs)
        return _FakeEmbeddingResponse(n_inputs=len(kwargs["input"]), prompt_tokens=self._tokens)


class _FakeEmbeddingClient:
    def __init__(self, prompt_tokens_per_call: int = 42) -> None:
        self.embeddings = _FakeEmbeddingsAPI(prompt_tokens_per_call=prompt_tokens_per_call)


@pytest.fixture
def fake_embedding_client(monkeypatch: pytest.MonkeyPatch) -> tuple[EmbeddingClient, CostTracker]:
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test")
    tracker = CostTracker()
    # User-supplied pricing so the calls resolve.
    tracker.pricing["deepinfra|fake-embed"] = (0.005, 0.0)
    client = EmbeddingClient(
        default_endpoint="deepinfra",
        default_model="fake-embed",
        cost_tracker=tracker,
        max_batch_size=2,
    )
    client._clients["deepinfra"] = SimpleNamespace(
        client=_FakeEmbeddingClient(prompt_tokens_per_call=42), base_url="x"
    )
    return client, tracker


async def test_embed_records_into_cost_tracker(fake_embedding_client):
    client, tracker = fake_embedding_client
    out = await client.embed(["a", "b", "c"], tag="entity_embedding")
    assert len(out) == 3
    # max_batch_size=2 → 2 batches → 2 cost records.
    assert len(tracker.records) == 2
    for rec in tracker.records:
        assert rec.tag == "entity_embedding"
        assert rec.completion_tokens == 0           # embeddings have no completion side
        assert rec.prompt_tokens == 42
        assert rec.cost_resolved
        assert rec.cost_usd > 0


async def test_embed_unresolved_pricing_marks_undefined(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test")
    tracker = CostTracker()
    # No pricing entry → records should land with cost_resolved=False.
    client = EmbeddingClient(
        default_endpoint="deepinfra", default_model="mystery-embed",
        cost_tracker=tracker, max_batch_size=2,
    )
    client._clients["deepinfra"] = SimpleNamespace(
        client=_FakeEmbeddingClient(), base_url="x"
    )
    await client.embed_one("hello", tag="query_embedding")
    assert len(tracker.records) == 1
    assert tracker.records[0].cost_resolved is False
    assert tracker.records[0].tag == "query_embedding"
    assert tracker.pricing_status() == "undefined"


async def test_embed_session_id_passes_through(fake_embedding_client):
    client, tracker = fake_embedding_client
    await client.embed_one("x", session_id="bench-001")
    assert tracker.records[0].session_id == "bench-001"


def test_embedding_client_without_tracker_is_a_noop(monkeypatch: pytest.MonkeyPatch):
    """When cost_tracker is not supplied, the embedding path still works."""
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test")
    client = EmbeddingClient(default_endpoint="deepinfra", default_model="m")
    client._clients["deepinfra"] = SimpleNamespace(
        client=_FakeEmbeddingClient(), base_url="x"
    )
    out = asyncio.run(client.embed_one("x"))
    assert isinstance(out, list)
