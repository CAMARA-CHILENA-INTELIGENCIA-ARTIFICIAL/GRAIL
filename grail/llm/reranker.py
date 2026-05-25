"""
RerankerClient — async cross-encoder re-ranking via HTTP API.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Qwen3-Reranker (and similar models) expose a dedicated reranking endpoint that
is NOT OpenAI Chat Completions — it accepts ``{queries, documents}`` and returns
``{results: [{index, relevance_score}]}``. This client wraps that protocol.

The reranker is optional. When ``reranker.enabled: true`` in config, GRAIL
over-fetches entity candidates by vector similarity, then re-ranks with the
cross-encoder to pick the final top-k. Users can toggle per-query via
``--rerank / --no-rerank`` on the CLI or ``use_reranker=`` in the Python API.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from grail.llm.providers import EndpointRegistry, resolve_endpoint_and_model
from grail.reporting import NullReporter

log = logging.getLogger("grail.llm.reranker")

RERANKER_URL_PATTERNS: dict[str, str] = {
    "deepinfra": "https://api.deepinfra.com/v1/inference/{model}",
}


@dataclass
class RerankResult:
    """One scored document from a reranking call."""

    index: int
    score: float
    text: str


class RerankerClient(BaseModel):
    """Async reranker client for cross-encoder models served over HTTP."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    default_endpoint: str = Field(
        default="deepinfra",
        description="Endpoint name — used to resolve api_key_env.",
    )
    default_model: str = Field(
        default="Qwen/Qwen3-Reranker-0.6B",
        description="Reranker model name.",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Full base URL override. When null, auto-derived from endpoint name.",
    )
    request_timeout: float = Field(default=30.0)
    max_retries: int = Field(default=5)
    max_retry_wait: float = Field(default=5.0)
    sleep_on_rate_limit: float = Field(default=15.0)
    endpoint_registry: EndpointRegistry = Field(default_factory=EndpointRegistry)
    cost_tracker: Optional[Any] = None
    reporter: Any = Field(default_factory=NullReporter)

    _http_client: Optional[httpx.AsyncClient] = None

    def model_post_init(self, __context: Any) -> None:
        self._http_client = None

    def _resolve_url(self, endpoint_name: str, model_name: str) -> str:
        if self.base_url:
            url = self.base_url.rstrip("/")
            if "{model}" in url:
                return url.format(model=model_name)
            return f"{url}/{model_name}"

        if endpoint_name in RERANKER_URL_PATTERNS:
            return RERANKER_URL_PATTERNS[endpoint_name].format(model=model_name)

        ep = self.endpoint_registry.get(endpoint_name)
        base = ep.base_url.rstrip("/")
        if base.endswith("/openai"):
            base = base[: -len("/openai")]
        return f"{base}/inference/{model_name}"

    def _resolve_api_key(self, endpoint_name: str) -> Optional[str]:
        try:
            ep = self.endpoint_registry.get(endpoint_name)
            return ep.resolve_api_key()
        except KeyError:
            return None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self.request_timeout)
        return self._http_client

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        top_k: Optional[int] = None,
        tag: str = "rerank",
        session_id: Optional[str] = None,
    ) -> list[RerankResult]:
        """Score ``documents`` against ``query`` and return results sorted by relevance (descending)."""
        if not documents:
            return []

        endpoint_name, model_name = resolve_endpoint_and_model(
            model,
            endpoint=endpoint,
            default_endpoint=self.default_endpoint,
            default_model=self.default_model,
        )
        url = self._resolve_url(endpoint_name, model_name)
        api_key = self._resolve_api_key(endpoint_name)
        canonical_model_id = f"{endpoint_name}|{model_name}"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"bearer {api_key}"

        payload: dict[str, Any] = {
            "queries": [query],
            "documents": documents,
        }
        if top_k is not None:
            payload["top_n"] = top_k

        start = time.perf_counter()
        response_data = await self._call_with_retry(url, headers, payload)
        duration = time.perf_counter() - start

        if self.cost_tracker is not None:
            input_tokens = response_data.get("input_tokens", 0) or 0
            self.cost_tracker.record(
                model=canonical_model_id,
                prompt_tokens=input_tokens,
                completion_tokens=0,
                duration_s=duration,
                tag=tag,
                session_id=session_id,
            )

        results = self._parse_response(response_data, documents)

        results.sort(key=lambda r: r.score, reverse=True)
        if top_k is not None:
            results = results[:top_k]

        log.debug(
            "Reranked %d documents via %s in %.2fs (top score: %.4f)",
            len(documents),
            canonical_model_id,
            duration,
            results[0].score if results else 0.0,
        )
        return results

    async def _call_with_retry(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_fixed(self.max_retry_wait),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
            reraise=True,
        )
        async def _do() -> dict[str, Any]:
            client = await self._get_client()
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 429:
                log.warning("Reranker rate-limited, sleeping %.0fs", self.sleep_on_rate_limit)
                await asyncio.sleep(self.sleep_on_rate_limit)
                resp.raise_for_status()
            resp.raise_for_status()
            return resp.json()

        return await _do()

    @staticmethod
    def _parse_response(data: dict[str, Any], documents: list[str]) -> list[RerankResult]:
        results: list[RerankResult] = []

        # DeepInfra format: {"scores": [0.95, 0.12, ...]} — flat list indexed by document
        if "scores" in data:
            for idx, score in enumerate(data["scores"]):
                text = documents[idx] if idx < len(documents) else ""
                results.append(RerankResult(index=idx, score=float(score), text=text))
            return results

        # Cohere/generic format: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
        for item in data.get("results", []):
            idx = item.get("index", 0)
            score = float(item.get("relevance_score", item.get("score", 0.0)))
            text = documents[idx] if idx < len(documents) else ""
            results.append(RerankResult(index=idx, score=score, text=text))
        return results

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
