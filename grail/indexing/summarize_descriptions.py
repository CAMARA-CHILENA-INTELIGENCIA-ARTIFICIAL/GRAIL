"""
Summarize entity/relationship descriptions with the LLM.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from grail.llm import LLMClient
from grail.prompts import PromptRegistry
from grail.reporting import NullReporter, Reporter
from grail.utils.tokens import tiktoken_len


@dataclass
class SummarizeExtractor:
    """Batch-summarize lists of descriptions for entities / relationships."""

    llm: LLMClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    endpoint: Optional[str] = None
    model: Optional[str] = None
    max_input_tokens: int = 4000
    max_output_tokens: int = 756
    temperature: float = 0.0
    tag: str = "summarize_description"
    reporter: Reporter = field(default_factory=NullReporter)

    async def summarize_one(self, entity_name: str, descriptions: list[str]) -> str:
        if not descriptions:
            return ""
        if len(descriptions) == 1:
            return descriptions[0]

        # Trim the description list so the prompt fits the model's window.
        trimmed: list[str] = []
        used = 0
        for d in descriptions:
            count = tiktoken_len(d)
            if used + count > self.max_input_tokens:
                break
            trimmed.append(d)
            used += count
        if not trimmed:
            trimmed = [descriptions[0][: self.max_input_tokens * 4]]

        messages = self.prompts.build(
            "summarize_description",
            entity_name=entity_name,
            description_list=trimmed,
        )
        response = await self.llm.execute_safe(
            messages=messages,
            endpoint=self.endpoint,
            model=self.model,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
            tag=self.tag,
        )
        return response or " ".join(trimmed)

    async def summarize_many(
        self,
        items: list[tuple[str, list[str]]],
        *,
        concurrency: Optional[int] = None,
    ) -> list[str]:
        """Batch helper. Each item is ``(entity_name, [desc, desc, ...])``."""
        if concurrency is None:
            tasks = [self.summarize_one(name, descs) for name, descs in items]
            return await asyncio.gather(*tasks)

        sem = asyncio.Semaphore(concurrency)

        async def _throttled(name: str, descs: list[str]) -> str:
            async with sem:
                return await self.summarize_one(name, descs)

        return await asyncio.gather(*[_throttled(n, d) for n, d in items])
