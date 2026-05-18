"""
EmbeddingClient — async embedding wrapper.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Same shape as :class:`LLMClient` — endpoint and model are separate first-class
fields. GRAIL speaks the OpenAI embeddings protocol; drop in any compatible
endpoint (DeepInfra, OpenAI, vLLM, your own…).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from openai import AsyncOpenAI, OpenAIError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from grail.llm.providers import EndpointRegistry, resolve_endpoint_and_model
from grail.reporting import NullReporter, Reporter

log = logging.getLogger("grail.llm.embeddings")


@dataclass
class _ClientHandle:
    client: AsyncOpenAI
    base_url: str


class EmbeddingClient(BaseModel):
    """Async embedding client."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    default_endpoint: str = Field(
        default="deepinfra",
        description="Endpoint name used when callers don't override.",
    )
    default_model: str = Field(
        default="intfloat/multilingual-e5-large",
        description="Embedding model name within the default endpoint.",
    )
    encoding_format: str = Field(default="float")
    max_batch_size: int = Field(default=1024, description="Max inputs per HTTP call.")
    concurrent_requests: int = Field(default=30)
    request_timeout: float = Field(default=180.0)
    max_retries: int = Field(default=10)
    max_retry_wait: float = Field(default=10.0)
    sleep_on_rate_limit: float = Field(default=30.0)
    endpoint_registry: EndpointRegistry = Field(default_factory=EndpointRegistry)
    reporter: Any = Field(default_factory=NullReporter)

    _semaphore: Optional[asyncio.Semaphore] = None
    _clients: dict[str, _ClientHandle] = {}

    def model_post_init(self, __context: Any) -> None:
        self._semaphore = asyncio.Semaphore(self.concurrent_requests)
        self._clients = {}

    def _client_for(self, endpoint_name: str) -> _ClientHandle:
        if endpoint_name in self._clients:
            return self._clients[endpoint_name]
        ep = self.endpoint_registry.get(endpoint_name)
        api_key = ep.resolve_api_key()
        if ep.requires_key and not api_key:
            raise RuntimeError(
                f"Embedding endpoint '{endpoint_name}' requires {ep.api_key_env}."
            )
        handle = _ClientHandle(
            client=AsyncOpenAI(api_key=api_key or "no-key", base_url=ep.base_url),
            base_url=ep.base_url,
        )
        self._clients[endpoint_name] = handle
        return handle

    def _retry(self):
        return retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_fixed(self.max_retry_wait),
            retry=retry_if_exception(
                lambda e: isinstance(e, RateLimitError)
                or (isinstance(e, OpenAIError) and getattr(e, "http_status", None) == 429)
            ),
            reraise=True,
        )

    async def _execute(
        self,
        inputs: list[str],
        *,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[list[float]]:
        endpoint_name, model_name = resolve_endpoint_and_model(
            model,
            endpoint=endpoint,
            default_endpoint=self.default_endpoint,
            default_model=self.default_model,
        )
        handle = self._client_for(endpoint_name)

        async def _call() -> list[list[float]]:
            assert self._semaphore is not None
            async with self._semaphore:
                try:
                    response = await asyncio.wait_for(
                        handle.client.embeddings.create(
                            input=inputs,
                            model=model_name,
                            encoding_format=self.encoding_format,
                        ),
                        timeout=self.request_timeout,
                    )
                except RateLimitError as exc:
                    await self.reporter.async_warning(
                        f"Embedding rate limit on {endpoint_name}/{model_name}: "
                        f"sleeping {self.sleep_on_rate_limit}s"
                    )
                    await asyncio.sleep(self.sleep_on_rate_limit)
                    raise exc
                except OpenAIError as exc:
                    if getattr(exc, "http_status", None) == 429:
                        await asyncio.sleep(self.sleep_on_rate_limit)
                    raise
            return [record.embedding for record in response.data]

        return await self._retry()(_call)()

    async def embed(
        self,
        texts: list[str],
        *,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        concurrent: bool = True,
    ) -> list[list[float]]:
        """Embed ``texts``, batching by :attr:`max_batch_size`."""
        if not texts:
            return []
        batches = [
            texts[i : i + self.max_batch_size]
            for i in range(0, len(texts), self.max_batch_size)
        ]
        if concurrent:
            tasks = [self._execute(b, endpoint=endpoint, model=model) for b in batches]
            results = await asyncio.gather(*tasks)
        else:
            results = [await self._execute(b, endpoint=endpoint, model=model) for b in batches]
        return [vec for batch in results for vec in batch]

    async def embed_one(
        self, text: str, *, endpoint: Optional[str] = None, model: Optional[str] = None
    ) -> list[float]:
        out = await self.embed([text], endpoint=endpoint, model=model)
        return out[0]

    async def embed_safe(
        self,
        texts: list[str],
        *,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[Optional[list[float]]]:
        """Like :meth:`embed` but returns ``None`` per batch on failure."""
        try:
            return list(await self.embed(texts, endpoint=endpoint, model=model))
        except Exception as exc:  # pragma: no cover
            log.warning("Embedding failed after retries: %s", exc)
            return [None] * len(texts)
