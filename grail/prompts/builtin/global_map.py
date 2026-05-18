"""Global-search MAP phase prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Asks the LLM to extract a JSON list of key points from a chunk of community-report
context, each scored 0–100 for relevance.
"""
from typing import Any

NAME = "global_map"
REQUIRED_PARAMS = ["context_data", "user_query"]

JSON_SCHEMA: dict[str, Any] = {
    "name": "global_map_points",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "description": {"type": "string"},
                        "score": {"type": "integer"},
                    },
                    "required": ["description", "score"],
                },
            },
        },
        "required": ["points"],
    },
}

SYSTEM_TEMPLATE = """You are a helpful assistant responding to questions about data in the tables provided. Your task is to create a list of relevant points for the user query using the data tables.

The response shall preserve the original meaning and use of modal verbs such as "shall", "may" or "will".

Points supported by data should list the relevant reports as references like this:
"This is an example sentence supported by data references [Data: report title (id), report2 title2 (id2), ...]"

Do not list more than 5 record titles in a single reference. Instead, list the top 5 most relevant record titles and add "+more" to indicate that there are more.

---Goal---
Generate a response consisting of a list of key points that responds to the user's question, summarizing all relevant information in the input data tables.

Use the data provided in the data tables below as the primary context. If the data tables do not contain sufficient information, say so. Do not make anything up.

Each key point in the response should have:
- description: A comprehensive description of the point.
- score: An integer 0-100 indicating how important the point is to answering the question. An 'I don't know' type response should have score 0.

Return JSON enclosed by the tag <json>:
<json>
{{
    "points": [
        {{"description": "...", "score": 0}}
    ]
}}
</json>

---Data tables---
{context_data}"""

USER_TEMPLATE = """<query>
{user_query}
</query>
Return the most important points in JSON format enclosed by <json> tags."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**params)},
    ]
    for turn in params.get("conversation_history") or []:
        if "role" in turn:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": USER_TEMPLATE.format(**params)})
    return messages
