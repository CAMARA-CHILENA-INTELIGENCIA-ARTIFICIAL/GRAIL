"""Local-search system prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The legacy version baked the conversation history and user query into the system
string with Nirvai role tokens. Here we emit them as proper chat messages so any
OpenAI-compatible model can route them correctly.
"""
from typing import Any

NAME = "local_search"
REQUIRED_PARAMS = ["context_data", "user_query"]

SYSTEM_TEMPLATE = """You are a helpful multi-lingual assistant called {assistant_name} responding to questions about data in the tables provided.
{artifact_instructions}
---Data tables---
This is the official information delivered by the knowledge base.
{context_data}

Reminders:
- Do not mention entities and relationships directly; they are internal concepts.
- For any images or links your answer must include caption and source.
- Read the sources carefully and use them to answer the question.
- If the data is not there, explain that the data is not available for the specific requirement.
- Use only data explicitly available in Entities, Relationships, and Sources.
- If not sure about a reference, consult the user for clarification.
- You MUST use only the information provided in the data tables above.
- If the question is not related to the data tables or instructions, explain that the question is out of scope.

You are now ready to answer the user queries based on the data tables provided."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    params.setdefault("assistant_name", "GRAIL")
    params.setdefault("artifact_instructions", "")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**params)},
    ]
    history = params.get("conversation_history") or []
    for turn in history:
        # Accept both {"role": ..., "content": ...} and {"user": "..."} / {"assistant": "..."} shapes.
        if "role" in turn:
            messages.append({"role": turn["role"], "content": turn["content"]})
        elif "user" in turn:
            messages.append({"role": "user", "content": turn["user"]})
        elif "assistant" in turn:
            messages.append({"role": "assistant", "content": turn["assistant"]})
    messages.append({"role": "user", "content": params["user_query"]})
    prefix = params.get("prefix_initial")
    if prefix:
        messages.append({"role": "assistant", "content": prefix})
    return messages
