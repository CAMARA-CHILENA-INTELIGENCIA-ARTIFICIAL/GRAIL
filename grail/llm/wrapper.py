"""
LLMClient — the OpenAI-protocol async wrapper that replaces ``achain_nirvana``.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Public surface:

    client = LLMClient(default_endpoint="openai", default_model="gpt-4o-mini")

    response: str = await client.execute(
        messages=[{"role": "system", "content": ...}, {"role": "user", "content": ...}],
        endpoint="deepinfra",         # overrides default_endpoint
        model="Qwen/Qwen3-32B",       # overrides default_model
        max_tokens=2048,
        temperature=0.0,
        response_format={"type": "json_object"},
        tag="entity_extraction",      # logical-operation label, used by CostTracker
        session_id="bench-2024-05-17",
        prefix_answer="<think>\\n\\n</think>\\n",
    )

Endpoint and model are **separate fields**. GRAIL only speaks the OpenAI protocol,
so adding a new deployment is just a matter of registering one more endpoint with
its ``base_url`` + ``api_key_env``. The ``"endpoint|model"`` pipe shorthand still
works in any string argument (e.g. ``model="vllm|my-llama"``) for power users who
prefer to type one field.

Preserved from the legacy ``LLMAPIWrapper``:

* Semaphore-bounded concurrency (default 15).
* tenacity retry on transient OpenAI / network errors.
* 30-second sleep on HTTP 429 before propagating the rate-limit error.
* Qwen3-style ``<think>...</think>`` prefix injection (configurable per call).
* Per-call timeout (default 180s).

Added in the port:

* Disk caching (off by default).
* CostTracker integration keyed by ``tag``.
* Pluggable endpoint registry.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

from openai import (
    APIConnectionError,
    APIError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from grail.llm.cache import LLMCache
from grail.llm.cost import CostTracker, now
from grail.llm.providers import (
    EndpointRegistry,
    resolve_endpoint_and_model,
)
from grail.reporting import NullReporter, Reporter

log = logging.getLogger("grail.llm")

StreamCallback = Callable[[str], Coroutine[Any, Any, None]]
_stream_callback_var: contextvars.ContextVar[StreamCallback | None] = contextvars.ContextVar(
    "grail_stream_callback", default=None,
)


def set_stream_callback(cb: StreamCallback | None) -> None:
    _stream_callback_var.set(cb)


_THINKING_RE = re.compile(r"<think>.*?</think>\s*", flags=re.S)


def _strip_thinking(text: str) -> str:
    """Remove ``<think>…</think>`` blocks emitted by reasoning models (Qwen3, etc.)."""
    return _THINKING_RE.sub("", text)


@dataclass
class _ClientHandle:
    client: AsyncOpenAI
    base_url: str


class LLMClient(BaseModel):
    """Async LLM client speaking the OpenAI Chat Completions protocol."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    default_endpoint: str = Field(
        default="openai",
        description="Endpoint name to use when callers don't override. Must exist in endpoint_registry.",
    )
    default_model: str = Field(
        default="gpt-4o-mini",
        description="Model name (no endpoint prefix) to use when callers don't override.",
    )
    request_timeout: float = Field(default=360.0, description="Per-call timeout in seconds.")
    max_retries: int = Field(default=10, description="tenacity attempt count for transient errors.")
    max_retry_wait: float = Field(default=10.0, description="Seconds to wait between retries.")
    sleep_on_rate_limit: float = Field(default=30.0, description="Sleep before propagating a 429.")
    concurrent_requests: int = Field(default=15, description="Semaphore size.")
    endpoint_registry: EndpointRegistry = Field(default_factory=EndpointRegistry)
    cache: Optional[Any] = None  # LLMCache; Any avoids pydantic introspecting asyncio.Lock.
    cost_tracker: Optional[Any] = None  # CostTracker; Any avoids pydantic introspecting threading.Lock.
    reporter: Any = Field(default_factory=NullReporter)
    default_session_id: str = Field(default="default")
    debug: bool = Field(default=False)
    tracer: Optional[Any] = None  # QueryTracer; Optional to avoid circular import.

    _semaphore: Optional[asyncio.Semaphore] = None
    _clients: dict[str, _ClientHandle] = {}

    def model_post_init(self, __context: Any) -> None:
        self._semaphore = asyncio.Semaphore(self.concurrent_requests)
        self._clients = {}

    # ------------------------------------------------------------------ endpoints

    def _client_for(self, endpoint_name: str) -> _ClientHandle:
        if endpoint_name in self._clients:
            return self._clients[endpoint_name]
        ep = self.endpoint_registry.get(endpoint_name)
        api_key = ep.resolve_api_key()
        if ep.requires_key and not api_key:
            raise RuntimeError(
                f"Endpoint '{endpoint_name}' requires {ep.api_key_env}, but it is not set. "
                f"Export it or pick a different endpoint."
            )
        handle = _ClientHandle(
            client=AsyncOpenAI(api_key=api_key or "no-key", base_url=ep.base_url),
            base_url=ep.base_url,
        )
        self._clients[endpoint_name] = handle
        return handle

    # ------------------------------------------------------------------ retries

    def _retry(self):
        return retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_fixed(self.max_retry_wait),
            retry=retry_if_exception_type(
                (asyncio.TimeoutError, APIError, APIConnectionError, RateLimitError)
            ),
            reraise=True,
        )

    # ------------------------------------------------------------------ core API

    async def execute(
        self,
        messages: list[dict[str, Any]],
        *,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        top_p: Optional[float] = None,
        response_format: Optional[dict[str, Any]] = None,
        stop: Optional[list[str]] = None,
        tag: Optional[str] = None,
        session_id: Optional[str] = None,
        prefix_answer: str = "",
        extra_body: Optional[dict[str, Any]] = None,
    ) -> str:
        """Send ``messages`` to the chat-completions endpoint and return the content string.

        ``endpoint`` and ``model`` are independent overrides — pass either, both, or
        neither. The pipe shorthand (``model="deepinfra|Qwen/Qwen3-32B"``) is still
        recognized for convenience.

        ``prefix_answer`` is appended as a final assistant message (the legacy Qwen3
        reasoning-prefix trick). The prefix is *not* prepended to the returned content.
        """
        endpoint_name, model_name = resolve_endpoint_and_model(
            model,
            endpoint=endpoint,
            default_endpoint=self.default_endpoint,
            default_model=self.default_model,
        )
        sid = session_id or self.default_session_id

        adapted_messages = list(messages)
        if prefix_answer:
            adapted_messages = adapted_messages + [{"role": "assistant", "content": prefix_answer}]

        # Cache key — built from the canonical (endpoint, model) pair plus params.
        cache_key: Optional[str] = None
        canonical_model_id = f"{endpoint_name}|{model_name}"
        if self.cache is not None and self.cache.enabled:
            cache_key = self.cache.make_key(
                model=canonical_model_id,
                messages=adapted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                top_p=top_p,
                stop=stop,
            )
            cached = await self.cache.get(sid, cache_key)
            if cached is not None:
                if self.cost_tracker is not None:
                    self.cost_tracker.record(
                        model=canonical_model_id,
                        prompt_tokens=0,
                        completion_tokens=0,
                        duration_s=0.0,
                        tag=tag,
                        session_id=sid,
                        cache_hit=True,
                    )
                return cached

        handle = self._client_for(endpoint_name)
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": adapted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if top_p is not None:
            kwargs["top_p"] = top_p
        if response_format is not None:
            kwargs["response_format"] = response_format
        if stop is not None:
            kwargs["stop"] = stop
        if extra_body is not None:
            kwargs["extra_body"] = extra_body

        start = now()
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}

        async def _call() -> str:
            assert self._semaphore is not None
            chunks: list[str] = []
            usage_prompt = 0
            usage_completion = 0

            async with self._semaphore:
                try:
                    stream = await asyncio.wait_for(
                        handle.client.chat.completions.create(**kwargs),
                        timeout=self.request_timeout,
                    )
                except RateLimitError as exc:
                    await self.reporter.async_warning(
                        f"Rate limit on {endpoint_name}/{model_name}: sleeping {self.sleep_on_rate_limit}s"
                    )
                    await asyncio.sleep(self.sleep_on_rate_limit)
                    raise exc
                except OpenAIError as exc:
                    status = getattr(exc, "http_status", None) or getattr(exc, "status_code", None)
                    if status == 429:
                        await self.reporter.async_warning(
                            f"429 on {endpoint_name}/{model_name}: sleeping {self.sleep_on_rate_limit}s"
                        )
                        await asyncio.sleep(self.sleep_on_rate_limit)
                    raise

                try:
                    _cb = _stream_callback_var.get(None)
                    async for chunk in stream:
                        usage = getattr(chunk, "usage", None)
                        if usage is not None:
                            usage_prompt = getattr(usage, "prompt_tokens", 0) or 0
                            usage_completion = getattr(usage, "completion_tokens", 0) or 0
                        if chunk.choices:
                            delta = chunk.choices[0].delta
                            if delta and delta.content:
                                chunks.append(delta.content)
                                if _cb is not None:
                                    await _cb(delta.content)
                except Exception:
                    if chunks:
                        log.warning(
                            "Stream interrupted after %d chunks for %s/%s (tag=%s); "
                            "returning partial response.",
                            len(chunks), endpoint_name, model_name, tag,
                        )
                    else:
                        raise

            content = _strip_thinking("".join(chunks))
            if self.cost_tracker is not None:
                self.cost_tracker.record(
                    model=canonical_model_id,
                    prompt_tokens=usage_prompt,
                    completion_tokens=usage_completion,
                    duration_s=now() - start,
                    tag=tag,
                    session_id=sid,
                )
            if self.debug:
                await self.reporter.async_success(
                    f"[{tag or 'llm'}] {endpoint_name}/{model_name} → {content[:200]}…"
                )
            return content

        content = await self._retry()(_call)()

        if self.cache is not None and self.cache.enabled and cache_key is not None:
            await self.cache.set(sid, cache_key, content)

        if self.tracer is not None and hasattr(self.tracer, "record") and self.tracer.active:
            self.tracer.record(
                tag=tag,
                endpoint=endpoint_name,
                model=model_name,
                messages=list(messages),
                response=content,
                duration_s=now() - start,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        return content

    async def execute_safe(self, *args, **kwargs) -> Optional[str]:
        """Like :meth:`execute` but returns ``None`` instead of raising on persistent failure."""
        try:
            return await self.execute(*args, **kwargs)
        except Exception as exc:  # pragma: no cover
            log.warning("LLM call failed after retries: %s", exc, exc_info=self.debug)
            return None

    async def execute_concurrently(
        self,
        calls: list[dict[str, Any]],
        *,
        safe: bool = True,
        concurrency: Optional[int] = None,
    ) -> list[Optional[str]]:
        """Run ``calls`` concurrently.

        Each call is still bounded by the global semaphore (HTTP-level throttle).
        When ``concurrency`` is set, an additional local semaphore limits how many
        calls from this batch are in-flight at once — useful when you want fewer
        concurrent community-report calls than extraction calls without changing
        the global limit.
        """
        method = self.execute_safe if safe else self.execute
        if concurrency is None:
            tasks = [method(**call) for call in calls]
            return await asyncio.gather(*tasks)

        sem = asyncio.Semaphore(concurrency)

        async def _throttled(call: dict[str, Any]) -> Optional[str]:
            async with sem:
                return await method(**call)

        return await asyncio.gather(*[_throttled(c) for c in calls])

    # ------------------------------------------------------------------ tool calling

    async def execute_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tag: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send ``messages`` with tool definitions, return the raw assistant message.

        Returns a dict with ``content`` (str | None) and ``tool_calls`` (list | None).
        The caller is responsible for the tool-call loop.
        """
        endpoint_name, model_name = resolve_endpoint_and_model(
            model,
            endpoint=endpoint,
            default_endpoint=self.default_endpoint,
            default_model=self.default_model,
        )
        handle = self._client_for(endpoint_name)
        canonical = f"{endpoint_name}|{model_name}"
        start = now()

        async def _call() -> dict[str, Any]:
            assert self._semaphore is not None
            async with self._semaphore:
                try:
                    response = await asyncio.wait_for(
                        handle.client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            tools=tools,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        ),
                        timeout=self.request_timeout,
                    )
                except RateLimitError:
                    await asyncio.sleep(self.sleep_on_rate_limit)
                    raise

            msg = response.choices[0].message
            usage = getattr(response, "usage", None)
            if self.cost_tracker is not None:
                self.cost_tracker.record(
                    model=canonical,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    duration_s=now() - start,
                    tag=tag,
                )
            tool_calls = None
            if msg.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            content = _strip_thinking(msg.content) if msg.content else msg.content
            return {"content": content, "tool_calls": tool_calls}

        result = await self._retry()(_call)()

        if self.tracer is not None and hasattr(self.tracer, "record") and self.tracer.active:
            self.tracer.record(
                tag=tag,
                endpoint=endpoint_name,
                model=model_name,
                messages=list(messages),
                response=result.get("content"),
                tool_calls=result.get("tool_calls"),
                duration_s=now() - start,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        return result

    # ------------------------------------------------------------------ legacy shim

    async def execute_legacy_prompt(
        self,
        prompt: str,
        *,
        params: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Convenience wrapper for transitional code that still uses a single-string template."""
        rendered = prompt.format(**(params or {})) if params else prompt
        return await self.execute(
            messages=[{"role": "user", "content": rendered}],
            model=model,
            endpoint=endpoint,
            **kwargs,
        )
