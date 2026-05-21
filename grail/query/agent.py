"""
Agentic search — LLM-driven tool-calling loop over GRAIL search methods.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The agent receives the user query plus a set of tools (local_search,
global_search, document_search) and decides which to call, with what
parameters. It can iterate — refining filters, switching modes, or
drilling into specific documents — until it has enough context to answer.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from grail.llm import EmbeddingClient, LLMClient
from grail.prompts import PromptRegistry
from grail.query.document_search import DocumentSearch
from grail.query.global_search import GlobalSearch
from grail.query.local_search import LocalSearch
from grail.query.retrieval import SearchArtifacts, load_artifacts_for_search
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import StorageBackend
from grail.vectorstores import LanceDBVectorStore

log = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = """
You are a knowledge-graph research assistant powered by GRAIL. You have access \
to three search tools over an indexed knowledge base:

1. **local_search** — finds entities, relationships, and source text related to \
a query. Use ``include_entities`` / ``exclude_entities`` to filter. Best for \
specific factual questions.
2. **global_search** — synthesises answers from community-level summaries. Best \
for broad, thematic, or comparative questions.
3. **document_search** — searches within a single source document by filename. \
Best when the user asks about a specific file or source.

Strategy:
- Start with the tool that best matches the question type.
- If the first result is incomplete, call another tool to fill gaps.
- Use entity filtering when you need to focus on specific people, places, or concepts.
- Use document_search when the user references a specific file.
- Combine local + global when the user asks both for details and for big-picture context.

When you have enough information, synthesise a final answer. Cite source \
documents when available.\
"""

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "local_search",
            "description": (
                "Search the knowledge graph for entities, relationships, and source text "
                "related to a query. Supports entity filtering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "include_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names to force-include in results.",
                    },
                    "exclude_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names to exclude from results.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of top entities to retrieve (default 10).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "global_search",
            "description": (
                "Search across all community reports for high-level, thematic, or "
                "comparative questions about the entire knowledge base."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "document_search",
            "description": (
                "Search within a specific source document by filename or path. "
                "Use when the user asks about a particular file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "document": {
                        "type": "string",
                        "description": "Document filename, path fragment, or ID.",
                    },
                },
                "required": ["query", "document"],
            },
        },
    },
]


@dataclass
class AgentSearch:
    """Agentic search that lets the LLM call search tools iteratively."""

    storage: StorageBackend
    llm: LLMClient
    embeddings: EmbeddingClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    vector_store: Optional[LanceDBVectorStore] = None
    output_folder: str = "output"
    max_iterations: int = 5
    max_tokens: int = 8192
    top_k_entities: int = 10
    text_unit_prop: float = 0.5
    community_prop: float = 0.1
    response_max_tokens: int = 4096
    endpoint: Optional[str] = None
    model: Optional[str] = None
    reporter: Reporter = field(default_factory=NullReporter)

    async def asearch(
        self,
        query: str,
        *,
        conversation_history: Optional[list[dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> SearchResult:
        started = time.perf_counter()
        self.reporter.info("Loading indexed artifacts…")
        artifacts = load_artifacts_for_search(self.storage, self.output_folder)
        self.reporter.success(
            f"Loaded {len(artifacts.entities)} entities, "
            f"{len(artifacts.relationships)} relationships, "
            f"{len(artifacts.community_reports)} community reports"
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt or AGENT_SYSTEM_PROMPT},
        ]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": query})

        total_llm_calls = 0
        all_context: list[str] = []
        all_context_data: dict[str, Any] = {}

        self.reporter.info(f"Starting agent loop (max {self.max_iterations} iterations)…")

        for iteration in range(self.max_iterations):
            self.reporter.info(f"Iteration {iteration + 1}/{self.max_iterations} — reasoning…")
            result = await self.llm.execute_with_tools(
                messages,
                tools=TOOL_SCHEMAS,
                endpoint=self.endpoint,
                model=self.model,
                max_tokens=self.response_max_tokens,
                tag="agent_search",
            )
            total_llm_calls += 1

            if not result["tool_calls"]:
                self.reporter.success("Agent finished — synthesizing final answer")
                return SearchResult(
                    response=result["content"] or "",
                    context_data=all_context_data,
                    context_text="\n\n".join(all_context),
                    completion_time=time.perf_counter() - started,
                    llm_calls=total_llm_calls,
                )

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": result["content"] or "",
                "tool_calls": [
                    {"id": tc["id"], "type": "function", "function": tc["function"]}
                    for tc in result["tool_calls"]
                ],
            }
            messages.append(assistant_msg)

            for tc in result["tool_calls"]:
                fn_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                args_display = ", ".join(f"{k}={v!r}" for k, v in args.items())
                self.reporter.info(f"Calling tool: {fn_name}({args_display})")
                tool_result = await self._execute_tool(fn_name, args, artifacts)
                total_llm_calls += tool_result.llm_calls
                self.reporter.success(f"{fn_name} returned ({tool_result.llm_calls} LLM calls)")

                tool_output = self._format_tool_output(fn_name, tool_result)
                all_context.append(tool_output)
                for k, v in (tool_result.context_data or {}).items():
                    all_context_data[f"{fn_name}_{k}"] = v

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_output,
                })

        self.reporter.warning("Max iterations reached")
        return SearchResult(
            response=result.get("content") or "I was unable to find a complete answer within the iteration limit.",
            context_data=all_context_data,
            context_text="\n\n".join(all_context),
            completion_time=time.perf_counter() - started,
            llm_calls=total_llm_calls,
        )

    # ------------------------------------------------------------------ tool dispatch

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        artifacts: SearchArtifacts,
    ) -> SearchResult:
        if name == "local_search":
            search = LocalSearch(
                storage=self.storage,
                llm=self.llm,
                embeddings=self.embeddings,
                prompts=self.prompts,
                artifacts=artifacts,
                vector_store=self.vector_store,
                output_folder=self.output_folder,
                max_tokens=self.max_tokens,
                top_k_entities=args.get("top_k", self.top_k_entities),
                text_unit_prop=self.text_unit_prop,
                community_prop=self.community_prop,
                reporter=self.reporter,
            )
            return await search.asearch(
                args["query"],
                include_entity_names=args.get("include_entities"),
                exclude_entity_names=args.get("exclude_entities"),
            )

        if name == "global_search":
            search = GlobalSearch(
                storage=self.storage,
                llm=self.llm,
                prompts=self.prompts,
                artifacts=artifacts,
                output_folder=self.output_folder,
                reporter=self.reporter,
            )
            return await search.asearch(args["query"])

        if name == "document_search":
            search = DocumentSearch(
                storage=self.storage,
                llm=self.llm,
                embeddings=self.embeddings,
                prompts=self.prompts,
                artifacts=artifacts,
                output_folder=self.output_folder,
                max_tokens=self.max_tokens,
                top_k_entities=self.top_k_entities,
                reporter=self.reporter,
            )
            return await search.asearch(
                args["query"],
                document=args["document"],
            )

        return SearchResult(
            response=f"Unknown tool: {name}",
            context_data={},
            context_text="",
            completion_time=0,
            llm_calls=0,
        )

    @staticmethod
    def _format_tool_output(name: str, result: SearchResult) -> str:
        """Format a search result as tool output for the agent."""
        parts = [f"=== {name} result ==="]
        if result.context_text:
            parts.append(result.context_text[:6000])
        if result.response:
            parts.append(f"\nSummary: {result.response[:2000]}")
        return "\n".join(parts)
