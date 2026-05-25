"""
Query tracing — captures prompts, responses, and context for debugging.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

When enabled via ``--trace <dir>`` on the CLI, every LLM call made during
a search is recorded with its full messages list, response, timing, and
metadata. The trace is written as a structured JSON file after the search
completes.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TraceEntry:
    """One LLM interaction."""

    tag: Optional[str]
    endpoint: Optional[str]
    model: Optional[str]
    messages: list[dict[str, Any]]
    response: Optional[str]
    tool_calls: Optional[list[dict[str, Any]]] = None
    duration_s: float = 0.0
    max_tokens: int = 0
    temperature: float = 0.0


@dataclass
class QueryTracer:
    """Collects LLM call traces during a search operation."""

    entries: list[TraceEntry] = field(default_factory=list)
    _active: bool = True

    @property
    def active(self) -> bool:
        return self._active

    def record(
        self,
        *,
        tag: Optional[str],
        endpoint: Optional[str],
        model: Optional[str],
        messages: list[dict[str, Any]],
        response: Optional[str],
        tool_calls: Optional[list[dict[str, Any]]] = None,
        duration_s: float = 0.0,
        max_tokens: int = 0,
        temperature: float = 0.0,
    ) -> None:
        if not self._active:
            return
        self.entries.append(
            TraceEntry(
                tag=tag,
                endpoint=endpoint,
                model=model,
                messages=messages,
                response=response,
                tool_calls=tool_calls,
                duration_s=duration_s,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )

    def dump(
        self,
        trace_dir: Path,
        *,
        query: str,
        mode: str,
        result_response: str,
        context_text: str = "",
        completion_time: float = 0.0,
        llm_calls: int = 0,
        extra: Optional[dict[str, Any]] = None,
    ) -> Path:
        """Write the trace to ``trace_dir`` as a JSON file. Returns the file path."""
        trace_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
        filename = f"trace_{mode}_{timestamp}.json"
        path = trace_dir / filename

        doc = {
            "query": query,
            "mode": mode,
            "completion_time_s": round(completion_time, 3),
            "llm_calls": llm_calls,
            "llm_interactions": [
                {
                    "tag": e.tag,
                    "endpoint": e.endpoint,
                    "model": e.model,
                    "messages": e.messages,
                    "response": e.response,
                    "tool_calls": e.tool_calls,
                    "duration_s": round(e.duration_s, 3),
                    "max_tokens": e.max_tokens,
                    "temperature": e.temperature,
                }
                for e in self.entries
            ],
            "context_text": context_text,
            "final_response": result_response,
        }
        if extra:
            doc["extra"] = extra

        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
        return path
