"""
Agentic search — LLM-driven tool-calling loop over GRAIL search methods.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The agent receives the user query plus a set of tools (local_search,
cascade_search, global_search, document_search) and decides which to call,
with what parameters. It can iterate — refining filters, switching modes, or
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
from grail.utils.tokens import tiktoken_len
from grail.query.document_search import DocumentSearch
from grail.query.global_search import GlobalSearch
from grail.query.local_search import LocalSearch
from grail.query.retrieval import SearchArtifacts, load_artifacts_for_search
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import StorageBackend
from grail.vectorstores import BaseVectorStore

log = logging.getLogger(__name__)


async def _emit_tool_call_tag(name: str, args: dict[str, Any]) -> None:
    """Push a `<tool_call>` block to the active stream callback, if any.

    The block is a self-contained XML chunk that chat frontends parse out
    and render as a styled card. We deliberately use a multi-line shape so
    that markdown renderers leave the inner JSON alone:

        <tool_call name="cascade_search">
        {"query":"What is Law 21250?"}
        </tool_call>

    Emission is fire-and-forget; if no callback is set (CLI, tests, etc.)
    we skip silently.
    """
    from grail.llm.wrapper import _stream_callback_var

    cb = _stream_callback_var.get(None)
    if cb is None:
        return
    safe_name = (name or "unknown").replace('"', "&quot;")
    args_json = json.dumps(args or {}, ensure_ascii=False)
    tag = f"\n<tool_call name=\"{safe_name}\">\n{args_json}\n</tool_call>\n\n"
    try:
        await cb(tag)
    except Exception:  # pragma: no cover — never let stream errors break the agent
        log.debug("Stream callback raised while emitting tool_call tag", exc_info=True)

AGENT_SYSTEM_PROMPT = """\
<role>
You are a knowledge-graph research assistant powered by GRAIL. You answer \
questions by searching an indexed knowledge base using specialized tools. \
You are methodical: you pick the right tool for each question, reflect on \
results, and iterate only when necessary.
</role>

<tools>
You have access to four search tools. Each uses a different retrieval \
strategy — choosing the right one is critical for answer quality.

1. **local_search** — Entity-gated retrieval. Embeds your query, finds the \
most similar entities in the knowledge graph by vector similarity, then \
retrieves text chunks linked to those entities. Best for questions about \
specific, named concepts (people, organizations, laws, procedures) where \
the knowledge graph has strong entity coverage. Supports entity filtering \
via include_entities / exclude_entities to focus or broaden results.

2. **cascade_search** — Hybrid retrieval. Starts with entity-gated search \
(like local_search) but also scores ALL text chunks by direct text matching \
(BM25 keyword + cosine similarity). Chunks that the entity gate misses but \
text matching finds are "rescued" and injected into the results. Use this \
when local_search returns incomplete or low-quality results — it combines \
graph structure with direct text relevance. This is the most robust mode \
for factual questions.

3. **global_search** — Community-report synthesis. Reads pre-generated \
thematic summaries that cover the entire knowledge base and synthesizes an \
answer from them. Does NOT retrieve individual text chunks or entities. \
Best for broad, high-level, or comparative questions ("What are the main \
themes?", "How do X and Y compare overall?", "Summarize the key findings").

4. **document_search** — Document-scoped retrieval. Searches within a \
single source document by filename. Retrieves entities and text chunks \
from that document only. Use when the user asks about a specific file \
or when you need to verify information from a particular source.
</tools>

<strategy>
Follow this workflow:

1. **Assess the question and pick a tool:**
   - Specific factual question → start with **cascade_search** (most robust)
   - Question about a named entity you're confident exists → **local_search**
   - Broad / thematic / comparative question → **global_search**
   - Question about a specific document → **document_search**

2. **Execute one search per turn.** Call exactly ONE tool, then evaluate.

3. **Reflect after each result:**
   - Does this fully answer the question? → synthesize your answer
   - Partial answer with specific gaps? → call another tool targeting the gap
   - Wrong results entirely? → try a different tool or rephrase the query

4. **Iterate sparingly.** Most questions need 1-2 tool calls. If \
local_search missed something, try cascade_search before giving up. If you \
need both detail and overview, combine local/cascade with global.

5. **Synthesize** when you have enough information. Stop calling tools and \
write your response directly.
</strategy>

<rules>
- Call exactly ONE tool per turn. Never call multiple tools simultaneously.
- Do NOT repeat the same tool with the same query. Each call should target \
a different aspect or use a different strategy.
- Be specific. Successive searches should target concrete gaps, not re-ask \
the original question.
- Stop early. If the first search fully answers the question, synthesize immediately.
- Do not expose internal terminology (entities, relationships, communities, \
text units) in your final answer — write naturally for the end user.
</rules>

<output_format>
When synthesizing your final answer (no more tool calls):
- Write in markdown format.
- Cite source documents by name where available in the search results.
- Respond in the same language as the user's question.
- Structure the answer with headers if it covers multiple topics.
</output_format>"""

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "local_search",
            "description": (
                "Entity-gated knowledge graph search. Finds the most relevant entities "
                "by vector similarity, then retrieves text chunks, relationships, and "
                "community context linked to those entities. Best for questions about "
                "specific named concepts where the knowledge graph has strong coverage. "
                "Use include_entities to force specific entities into results, or "
                "exclude_entities to filter out irrelevant ones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query — be specific and descriptive.",
                    },
                    "include_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names (UPPERCASE) to force-include in results.",
                    },
                    "exclude_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names (UPPERCASE) to exclude from results.",
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
            "name": "cascade_search",
            "description": (
                "Hybrid search combining entity-gated retrieval with direct text matching. "
                "First finds entities like local_search, then also scores ALL text chunks "
                "by BM25 keyword matching and cosine similarity. Chunks missed by the "
                "entity gate but found by text matching are rescued and injected into "
                "results. More robust than local_search for factual questions where the "
                "answer might not be directly linked to the top entities. Use this as "
                "your default for factual questions, or as a fallback when local_search "
                "returns incomplete results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query — be specific and descriptive.",
                    },
                    "include_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names (UPPERCASE) to force-include in results.",
                    },
                    "exclude_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names (UPPERCASE) to exclude from results.",
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
                "Thematic synthesis across the entire knowledge base. Reads pre-generated "
                "community report summaries and synthesizes a comprehensive answer. Does "
                "NOT retrieve individual text chunks or entities — works at the community "
                "level. Best for broad questions like 'What are the main themes?', 'How "
                "do X and Y compare overall?', or 'Summarize the key findings'. Not "
                "suitable for specific factual lookups."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query — phrase as a broad, thematic question.",
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
                "Document-scoped search. Retrieves entities and text chunks from a single "
                "source document only. Use when the user asks about a specific file, when "
                "you need to verify information from a particular source, or when you know "
                "which document contains the answer."
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
                        "description": "Document filename (e.g. 'report.pdf'), path fragment, or ID.",
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
    vector_store: Optional[BaseVectorStore] = None
    output_folder: str = "output"
    max_iterations: int = 5
    max_tokens: int = 12_000
    top_k_entities: int = 10
    text_unit_prop: float = 0.5
    community_prop: float = 0.1
    use_community_summary: bool = False
    response_max_tokens: int = 16_384
    agent_tool_context_limit: int = 30_000
    endpoint: Optional[str] = None
    model: Optional[str] = None
    reporter: Reporter = field(default_factory=NullReporter)
    enabled_tools: Optional[set[str]] = None

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
        agent_messages: list[dict[str, Any]] = []

        if self.enabled_tools is not None:
            tool_schemas = [
                s for s in TOOL_SCHEMAS if s["function"]["name"] in self.enabled_tools
            ]
            if not tool_schemas:
                raise ValueError("All agent tools are disabled — enable at least one.")
        else:
            tool_schemas = TOOL_SCHEMAS

        self.reporter.info(f"Starting agent loop (max {self.max_iterations} iterations)…")

        for iteration in range(self.max_iterations):
            self.reporter.info(f"Iteration {iteration + 1}/{self.max_iterations} — reasoning…")
            result = await self.llm.execute_with_tools(
                messages,
                tools=tool_schemas,
                endpoint=self.endpoint,
                model=self.model,
                max_tokens=self.response_max_tokens,
                tag="agent_search",
            )
            total_llm_calls += 1

            if not result["tool_calls"]:
                content = (result["content"] or "").strip()
                if content:
                    self.reporter.success("Agent finished — synthesizing final answer")
                    all_context_data["agent_messages"] = agent_messages
                    return SearchResult(
                        response=content,
                        context_data=all_context_data,
                        context_text="\n\n".join(all_context),
                        completion_time=time.perf_counter() - started,
                        llm_calls=total_llm_calls,
                    )
                # Empty response (thinking model exhausted tokens) — force a final try.
                self.reporter.warning("Empty response — forcing final synthesis")
                break

            tool_calls = result["tool_calls"][:1]
            if len(result["tool_calls"]) > 1:
                log.debug(
                    "Agent returned %d tool calls; enforcing one-at-a-time — "
                    "dropping %d extra call(s)",
                    len(result["tool_calls"]),
                    len(result["tool_calls"]) - 1,
                )

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": result["content"] or "",
                "tool_calls": [
                    {"id": tc["id"], "type": "function", "function": tc["function"]}
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)
            agent_messages.append(assistant_msg)

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                args_display = ", ".join(f"{k}={v!r}" for k, v in args.items())
                self.reporter.info(f"Calling tool: {fn_name}({args_display})")
                # Emit the tool-call XML to the active stream so chat clients
                # render the call as it executes. The same callback receives
                # the final answer text — the tags interleave naturally.
                await _emit_tool_call_tag(fn_name, args)
                tool_result = await self._execute_tool(fn_name, args, artifacts)
                total_llm_calls += tool_result.llm_calls
                self.reporter.success(f"{fn_name} returned ({tool_result.llm_calls} LLM calls)")

                tool_output = self._format_tool_output(fn_name, tool_result)
                all_context.append(tool_output)
                for k, v in (tool_result.context_data or {}).items():
                    all_context_data[f"{fn_name}_{k}"] = v

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_output,
                }
                messages.append(tool_msg)
                agent_messages.append(tool_msg)
        else:
            self.reporter.warning("Max iterations reached — forcing final synthesis")

        # Force a final synthesis: send a user message asking to answer now,
        # with no tools available so the model MUST produce text.
        messages.append({
            "role": "user",
            "content": (
                "You have used all your search calls. Answer the original question NOW "
                "using whatever information you have gathered. If you don't have enough "
                "information, say what you found and what is missing. Do not call any tools."
            ),
        })
        final = await self.llm.execute_safe(
            messages=messages,
            endpoint=self.endpoint,
            model=self.model,
            max_tokens=self.response_max_tokens,
            tag="agent_search_final",
        )
        total_llm_calls += 1
        content = (final or "").strip()
        if not content:
            content = "No pude encontrar suficiente información para responder esta pregunta con los datos disponibles."

        all_context_data["agent_messages"] = agent_messages
        return SearchResult(
            response=content,
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
        """Execute a search tool and return raw structured context.

        Always returns the raw context_text (entities + relationships +
        communities + text units). If the context exceeds
        ``agent_tool_context_limit`` tokens, it is trimmed from the end
        so the agent still sees the highest-ranked content first.
        """
        result = await self._run_search(name, args, artifacts, context_only=True)

        ctx = result.context_text or ""
        ctx_tokens = tiktoken_len(ctx) if ctx else 0

        if ctx_tokens <= self.agent_tool_context_limit:
            self.reporter.info(
                f"{name}: raw context {ctx_tokens} tok ≤ {self.agent_tool_context_limit} → passing through"
            )
            return result

        # Trim to budget — keep the beginning (highest-ranked content).
        self.reporter.info(
            f"{name}: raw context {ctx_tokens} tok > {self.agent_tool_context_limit} → trimming"
        )
        import tiktoken as _tiktoken
        enc = _tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(ctx)
        trimmed = enc.decode(tokens[: self.agent_tool_context_limit])
        return SearchResult(
            response="",
            context_data=result.context_data,
            context_text=trimmed,
            completion_time=result.completion_time,
            llm_calls=result.llm_calls,
        )

    async def _run_search(
        self,
        name: str,
        args: dict[str, Any],
        artifacts: SearchArtifacts,
        *,
        context_only: bool,
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
                use_community_summary=self.use_community_summary,
                reporter=self.reporter,
            )
            return await search.asearch(
                args["query"],
                include_entity_names=args.get("include_entities"),
                exclude_entity_names=args.get("exclude_entities"),
                context_only=context_only,
            )

        if name == "cascade_search":
            from grail.query.cascade_search import CascadeSearch
            search = CascadeSearch(
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
                use_community_summary=self.use_community_summary,
                reporter=self.reporter,
            )
            return await search.asearch(
                args["query"],
                include_entity_names=args.get("include_entities"),
                exclude_entity_names=args.get("exclude_entities"),
                context_only=context_only,
            )

        if name == "global_search":
            search = GlobalSearch(
                storage=self.storage,
                llm=self.llm,
                prompts=self.prompts,
                artifacts=artifacts,
                output_folder=self.output_folder,
                use_community_summary=self.use_community_summary,
                reporter=self.reporter,
            )
            return await search.asearch(args["query"], context_only=context_only)

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
                context_only=context_only,
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
        """Format a search result as tool output for the agent.

        When context_only was used (no LLM call), ``response`` is empty and
        we return the raw context. When the mini-agent ran (context was too
        large), ``response`` contains the LLM summary.
        """
        parts = [f"=== {name} result ==="]
        if result.response:
            parts.append(result.response)
        elif result.context_text:
            parts.append(result.context_text)
        return "\n".join(parts)
