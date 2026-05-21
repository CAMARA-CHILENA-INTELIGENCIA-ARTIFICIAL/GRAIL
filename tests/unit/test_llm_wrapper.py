"""LLMClient tests (mocked — no network)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from grail.llm import LLMClient
from grail.llm.cache import LLMCache
from grail.llm.cost import CostTracker
from grail.llm.providers import (
    Endpoint,
    EndpointRegistry,
    parse_model_id,
    resolve_endpoint_and_model,
)


def test_parse_model_id_legacy_shorthand_defaults_to_openai():
    endpoint, model = parse_model_id("gpt-4o-mini")
    assert endpoint == "openai"
    assert model == "gpt-4o-mini"


def test_parse_model_id_splits_explicit_pipe():
    assert parse_model_id("deepinfra|Qwen/Qwen3-32B") == ("deepinfra", "Qwen/Qwen3-32B")


def test_resolve_uses_explicit_endpoint_when_given():
    ep, mod = resolve_endpoint_and_model("Qwen/Qwen3-32B", endpoint="vllm", default_endpoint="openai")
    assert ep == "vllm"
    assert mod == "Qwen/Qwen3-32B"


def test_resolve_falls_back_to_default_endpoint_for_bare_models():
    ep, mod = resolve_endpoint_and_model("gpt-4o-mini", default_endpoint="anthropic")
    assert ep == "anthropic"
    assert mod == "gpt-4o-mini"


def test_resolve_honors_pipe_shorthand_when_no_endpoint_override():
    ep, mod = resolve_endpoint_and_model(
        "vllm|my-llama", default_endpoint="openai", default_model="gpt-4o-mini"
    )
    assert ep == "vllm"
    assert mod == "my-llama"


def test_resolve_endpoint_override_strips_pipe_in_model():
    ep, mod = resolve_endpoint_and_model(
        "deepinfra|Qwen/Qwen3-32B", endpoint="vllm", default_endpoint="openai"
    )
    assert ep == "vllm"
    assert mod == "Qwen/Qwen3-32B"


def test_endpoint_registry_register_and_override():
    reg = EndpointRegistry()
    reg.register(Endpoint(name="custom", base_url="https://x", api_key_env="X_KEY"))
    assert reg.get("custom").base_url == "https://x"
    reg.override("custom", base_url="https://y")
    assert reg.get("custom").base_url == "https://y"


class _FakeStreamChunk:
    def __init__(self, content: str | None = None, usage: Any = None) -> None:
        if content is not None:
            self.choices = [SimpleNamespace(delta=SimpleNamespace(content=content))]
        else:
            self.choices = []
        self.usage = usage


class _FakeStream:
    """Async iterator that yields one content chunk then a usage-only chunk."""

    def __init__(self, content: str, prompt_tokens: int = 12, completion_tokens: int = 7) -> None:
        self._chunks = [
            _FakeStreamChunk(content=content),
            _FakeStreamChunk(
                usage=SimpleNamespace(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            ),
        ]

    def __aiter__(self) -> "_FakeStream":
        self._idx = 0
        return self

    async def __anext__(self) -> _FakeStreamChunk:
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


class _FakeChatCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(kwargs)
        return _FakeStream(self._content)


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(content))


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> tuple[LLMClient, _FakeClient]:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = LLMClient(
        default_endpoint="openai", default_model="gpt-test", cost_tracker=CostTracker()
    )
    fake = _FakeClient("hello world")
    client._clients["openai"] = SimpleNamespace(client=fake, base_url="https://api.openai.com/v1")
    return client, fake


async def test_execute_uses_defaults(fake_llm):
    client, fake = fake_llm
    out = await client.execute(messages=[{"role": "user", "content": "hi"}])
    assert out == "hello world"
    assert fake.chat.completions.calls[0]["model"] == "gpt-test"


async def test_execute_endpoint_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k1")
    monkeypatch.setenv("VLLM_API_KEY", "k2")
    client = LLMClient(default_endpoint="openai", default_model="gpt-test")
    fake_openai = _FakeClient("from-openai")
    fake_vllm = _FakeClient("from-vllm")
    client._clients["openai"] = SimpleNamespace(client=fake_openai, base_url="x")
    client._clients["vllm"] = SimpleNamespace(client=fake_vllm, base_url="y")
    out = await client.execute(
        messages=[{"role": "user", "content": "hi"}], endpoint="vllm", model="my-llama"
    )
    assert out == "from-vllm"
    assert fake_vllm.chat.completions.calls[0]["model"] == "my-llama"
    assert fake_openai.chat.completions.calls == []  # openai client wasn't touched


async def test_execute_records_cost(fake_llm):
    client, _ = fake_llm
    await client.execute(messages=[{"role": "user", "content": "hi"}], tag="t")
    assert client.cost_tracker is not None
    assert len(client.cost_tracker.records) == 1
    rec = client.cost_tracker.records[0]
    assert rec.tag == "t"
    assert rec.model == "openai|gpt-test"  # canonical endpoint|model in the ledger
    assert rec.prompt_tokens == 12
    assert rec.completion_tokens == 7


async def test_cache_hits_skip_the_network(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cache = LLMCache(directory=tmp_path / "cache", enabled=True)
    client = LLMClient(
        default_endpoint="openai",
        default_model="gpt-test",
        cache=cache,
        cost_tracker=CostTracker(),
    )
    fake = _FakeClient("first")
    client._clients["openai"] = SimpleNamespace(client=fake, base_url="x")
    msgs = [{"role": "user", "content": "same"}]
    assert await client.execute(messages=msgs) == "first"

    fake2 = _FakeClient("second")
    client._clients["openai"] = SimpleNamespace(client=fake2, base_url="x")
    assert await client.execute(messages=msgs) == "first"
    assert len(fake2.chat.completions.calls) == 0


async def test_safe_returns_none_on_failure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    client = LLMClient(
        default_endpoint="openai", default_model="x", max_retries=1, max_retry_wait=0
    )

    class _Boom:
        async def create(self, **_: Any):
            raise RuntimeError("boom")

    client._clients["openai"] = SimpleNamespace(
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Boom())),
        base_url="x",
    )
    out = await client.execute_safe(messages=[{"role": "user", "content": "hi"}])
    assert out is None
