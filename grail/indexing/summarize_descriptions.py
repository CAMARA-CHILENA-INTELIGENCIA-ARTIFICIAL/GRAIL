"""
Summarize entity/relationship descriptions with the LLM (batched).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Groups entities into batches and sends one LLM call per batch.  Each call
returns a JSON array of summaries inside ``<summaries>`` tags.  Falls back
to individual calls if a batch response cannot be parsed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from grail.llm import LLMClient
from grail.prompts import PromptRegistry
from grail.reporting import NullReporter, Reporter
from grail.utils.tokens import tiktoken_len

log = logging.getLogger(__name__)

_SUMMARIES_RE = re.compile(r"<summaries>(.*?)</summaries>", re.S)


@dataclass
class SummarizeExtractor:
    """Batch-summarize lists of descriptions for entities / relationships."""

    llm: LLMClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    endpoint: Optional[str] = None
    model: Optional[str] = None
    max_input_tokens: int = 4000
    max_output_tokens: int = 8192
    temperature: float = 0.0
    batch_size: int = 10
    tag: str = "summarize_description"
    reporter: Reporter = field(default_factory=NullReporter)

    async def summarize_many(
        self,
        items: list[tuple[str, list[str]]],
        *,
        concurrency: Optional[int] = None,
    ) -> list[str]:
        """Batch helper. Each item is ``(entity_name, [desc, desc, ...])``."""
        if not items:
            return []

        multi = [(name, descs) for name, descs in items if len(descs) > 1]
        singles = {name: descs[0] for name, descs in items if len(descs) == 1}

        if not multi:
            return [singles.get(name, descs[0] if descs else "") for name, descs in items]

        batches = self._make_batches(multi)

        if concurrency is not None:
            sem = asyncio.Semaphore(concurrency)

            async def _throttled(batch: list[tuple[str, list[str]]]) -> dict[str, str]:
                async with sem:
                    return await self._summarize_batch(batch)

            batch_results = await asyncio.gather(*[_throttled(b) for b in batches])
        else:
            batch_results = await asyncio.gather(
                *[self._summarize_batch(b) for b in batches]
            )

        merged: dict[str, str] = {}
        for result in batch_results:
            merged.update(result)

        output: list[str] = []
        for name, descs in items:
            if name in merged:
                output.append(merged[name])
            elif name in singles:
                output.append(singles[name])
            else:
                output.append(descs[0] if descs else "")
        return output

    def _make_batches(
        self, items: list[tuple[str, list[str]]]
    ) -> list[list[tuple[str, list[str]]]]:
        """Split items into batches respecting both count and token limits."""
        batches: list[list[tuple[str, list[str]]]] = []
        current: list[tuple[str, list[str]]] = []
        current_tokens = 0

        for name, descs in items:
            trimmed = self._trim_descriptions(descs)
            item_tokens = sum(tiktoken_len(d) for d in trimmed) + tiktoken_len(name)

            if current and (
                len(current) >= self.batch_size
                or current_tokens + item_tokens > self.max_input_tokens
            ):
                batches.append(current)
                current = []
                current_tokens = 0

            current.append((name, trimmed))
            current_tokens += item_tokens

        if current:
            batches.append(current)

        return batches

    def _trim_descriptions(self, descriptions: list[str]) -> list[str]:
        """Trim a description list to fit within token budget."""
        trimmed: list[str] = []
        used = 0
        per_entity_budget = self.max_input_tokens // max(self.batch_size, 1)
        for d in descriptions:
            count = tiktoken_len(d)
            if used + count > per_entity_budget:
                break
            trimmed.append(d)
            used += count
        if not trimmed:
            trimmed = [descriptions[0][:per_entity_budget * 4]]
        return trimmed

    async def _summarize_batch(
        self, batch: list[tuple[str, list[str]]]
    ) -> dict[str, str]:
        """Send one batch to the LLM. Returns {entity_name: summary}."""
        entities_payload: list[dict[str, Any]] = []
        index_to_name: dict[int, str] = {}

        for i, (name, descs) in enumerate(batch, 1):
            entities_payload.append({
                "index": i,
                "name": name,
                "descriptions": descs,
            })
            index_to_name[i] = name

        messages = self.prompts.build(
            "summarize_description",
            entities=entities_payload,
        )
        response = await self.llm.execute_safe(
            messages=messages,
            endpoint=self.endpoint,
            model=self.model,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
            tag=self.tag,
        )

        parsed = _parse_summaries_response(response, index_to_name)

        if len(parsed) < len(batch):
            missing = [
                (name, descs) for name, descs in batch if name not in parsed
            ]
            if missing:
                log.debug(
                    "Batch returned %d/%d summaries; falling back for %d",
                    len(parsed), len(batch), len(missing),
                )
                fallback = await self._fallback_individual(missing)
                parsed.update(fallback)

        return parsed

    async def _fallback_individual(
        self, items: list[tuple[str, list[str]]]
    ) -> dict[str, str]:
        """Fall back to one-entity-per-call for items that failed in a batch."""
        results: dict[str, str] = {}

        async def _one(name: str, descs: list[str]) -> None:
            entities_payload = [{"index": 1, "name": name, "descriptions": descs}]
            messages = self.prompts.build(
                "summarize_description",
                entities=entities_payload,
            )
            response = await self.llm.execute_safe(
                messages=messages,
                endpoint=self.endpoint,
                model=self.model,
                max_tokens=self.max_output_tokens,
                temperature=self.temperature,
                tag=self.tag,
            )
            parsed = _parse_summaries_response(response, {1: name})
            if name in parsed:
                results[name] = parsed[name]
            else:
                results[name] = " ".join(descs)

        await asyncio.gather(*[_one(n, d) for n, d in items])
        return results


def _parse_summaries_response(
    response: str | None,
    index_to_name: dict[int, str],
) -> dict[str, str]:
    """Extract summaries from an LLM response. Returns {entity_name: summary}."""
    if not response:
        return {}

    m = _SUMMARIES_RE.search(response)
    if m:
        text = m.group(1).strip()
    else:
        start = response.find("[")
        end = response.rfind("]")
        if start >= 0 and end > start:
            text = response[start : end + 1]
        else:
            if len(index_to_name) == 1:
                name = next(iter(index_to_name.values()))
                return {name: response.strip()}
            return {}

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.debug("Failed to parse summaries JSON")
        if len(index_to_name) == 1:
            name = next(iter(index_to_name.values()))
            return {name: response.strip()}
        return {}

    if not isinstance(data, list):
        return {}

    results: dict[str, str] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("index")
        summary = entry.get("summary", "")
        if idx is not None and int(idx) in index_to_name and summary:
            results[index_to_name[int(idx)]] = str(summary).strip()

    return results
