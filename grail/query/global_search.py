"""
Global search.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Two paths:

* **Single-pass reduce** when the community-report context fits inside
  ``chunk_size`` tokens. Faster, fewer LLM calls.
* **Map-reduce** otherwise. Each chunk is mapped to a JSON list of key points
  (description + score 0–100); the highest-scoring points are concatenated and
  fed to the reduce prompt for final synthesis.

The map-reduce implementation is in-house: it does not depend on the proprietary
``ReduceMap`` utility from the legacy codebase.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from grail.llm import LLMClient
from grail.prompts import PromptRegistry
from grail.query.retrieval import (
    SearchArtifacts,
    build_community_context,
    load_artifacts_for_search,
)
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import StorageBackend
from grail.utils.tokens import tiktoken_len

log = logging.getLogger(__name__)


@dataclass
class GlobalSearch:
    storage: StorageBackend
    llm: LLMClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    artifacts: Optional[SearchArtifacts] = None
    output_folder: str = "output"
    chunk_size: int = 100_000
    concurrency: int = 5
    map_max_tokens: int = 2000
    reduce_max_tokens: int = 6000
    response_temperature: float = 0.0
    endpoint: Optional[str] = None
    model: Optional[str] = None
    assistant_name: str = "GRAIL"
    reporter: Reporter = field(default_factory=NullReporter)

    async def asearch(
        self,
        query: str,
        *,
        conversation_history: Optional[list[dict[str, Any]]] = None,
        artifact_instructions: str = "",
        extra_knowledge: str = "",
    ) -> SearchResult:
        started = time.perf_counter()
        self.reporter.info("Loading indexed artifacts…")
        artifacts = self.artifacts or load_artifacts_for_search(self.storage, self.output_folder)
        if artifacts.community_reports.empty:
            return SearchResult(
                response="No community reports were found. Run `grail index` first.",
                context_data={},
                context_text="",
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )
        self.reporter.success(
            f"Loaded {len(artifacts.community_reports)} community reports"
        )

        self.reporter.info("Building community context…")
        context_text, used_reports = build_community_context(
            artifacts.community_reports, max_tokens=self.chunk_size
        )

        llm_calls = 0
        if isinstance(context_text, str):
            self.reporter.info("Single-pass reduce — context fits in one chunk")
            self.reporter.info("Generating response…")
            answer, calls = await self._reduce(
                context_text,
                query,
                conversation_history=conversation_history,
                artifact_instructions=artifact_instructions,
                extra_knowledge=extra_knowledge,
            )
            llm_calls += calls
            return SearchResult(
                response=answer,
                context_data={"reports": used_reports},
                context_text=context_text,
                completion_time=time.perf_counter() - started,
                llm_calls=llm_calls,
            )

        chunks = context_text  # list of strings
        self.reporter.info(f"Map-reduce — {len(chunks)} chunks to process")
        sem = asyncio.Semaphore(self.concurrency)

        async def _map_one(chunk: str) -> list[dict[str, Any]]:
            async with sem:
                messages = self.prompts.build(
                    "global_map",
                    context_data=chunk,
                    user_query=query,
                    conversation_history=conversation_history or [],
                )
                resp = await self.llm.execute_safe(
                    messages=messages,
                    endpoint=self.endpoint,
                    model=self.model,
                    max_tokens=self.map_max_tokens,
                    temperature=self.response_temperature,
                    tag="global_map",
                    response_format={"type": "json_object"},
                )
                return _parse_map_points(resp)

        self.reporter.info("Mapping chunks…")
        mapped = await asyncio.gather(*(_map_one(chunk) for chunk in chunks))
        llm_calls += len(chunks)
        all_points: list[dict[str, Any]] = [pt for batch in mapped for pt in batch]
        all_points.sort(key=lambda p: p.get("score", 0), reverse=True)
        self.reporter.success(f"Mapped {len(all_points)} key points")

        reduce_context = "\n".join(
            f"- ({p.get('score', 0)}) {p.get('description', '')}" for p in all_points
        )

        self.reporter.info("Reducing to final answer…")
        answer, calls = await self._reduce(
            reduce_context,
            query,
            conversation_history=conversation_history,
            artifact_instructions=artifact_instructions,
            extra_knowledge=extra_knowledge,
        )
        llm_calls += calls

        return SearchResult(
            response=answer,
            context_data={"reports": used_reports, "map_points": pd.DataFrame(all_points)},
            context_text=reduce_context,
            completion_time=time.perf_counter() - started,
            llm_calls=llm_calls,
        )

    async def _reduce(
        self,
        context_text: str,
        query: str,
        *,
        conversation_history: Optional[list[dict[str, Any]]],
        artifact_instructions: str,
        extra_knowledge: str,
    ) -> tuple[str, int]:
        messages = self.prompts.build(
            "global_reduce",
            context_data=context_text,
            user_query=query,
            assistant_name=self.assistant_name,
            artifact_instructions=artifact_instructions,
            extra_knowledge=extra_knowledge,
            conversation_history=conversation_history or [],
        )
        response = await self.llm.execute_safe(
            messages=messages,
            endpoint=self.endpoint,
            model=self.model,
            max_tokens=self.reduce_max_tokens,
            temperature=self.response_temperature,
            tag="global_reduce",
        )
        return response or "", 1


def _parse_map_points(response: Optional[str]) -> list[dict[str, Any]]:
    if not response:
        return []
    text = response.strip()
    # Strip <json>…</json> wrapper if present.
    m = re.search(r"<json>(.*?)</json>", text, flags=re.S)
    if m:
        text = m.group(1)
    text = text.strip().strip("`")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object inside the response.
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    points = data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list):
        return []
    out = []
    for p in points:
        if not isinstance(p, dict):
            continue
        out.append(
            {
                "description": str(p.get("description", "")),
                "score": int(p.get("score", 0) or 0),
            }
        )
    return out
