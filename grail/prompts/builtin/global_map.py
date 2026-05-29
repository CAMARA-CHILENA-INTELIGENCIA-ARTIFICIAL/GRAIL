"""
Global-search MAP phase prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Asks the LLM to extract a JSON list of key points from a chunk of community-report
context, each scored 0-100 for relevance. The output must be wrapped in
``<json>...</json>`` tags for reliable parsing.
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

SYSTEM_TEMPLATE = """\
<role>
You are an analytical researcher extracting key points from knowledge-base \
reports to answer a user question.
</role>

<context>
You are part of a map-reduce pipeline in GRAIL. Your job is the MAP phase: \
extract relevant points from one batch of community reports. Another stage will \
later synthesize all extracted points into a final answer.

Focus on extracting every point that is relevant to the question, scoring each \
by importance. Even marginally relevant points should be included with low \
scores — the reduce phase will filter.
</context>

<task>
1. Read the community reports in the data below.
2. Identify every point that helps answer the user's question.
3. For each point, write a description and assign a relevance score (0-100).
4. Reference source reports in your descriptions.
5. Return the points as JSON inside <json>...</json> tags.
</task>

<output_format>
You may reason about the data before producing output. When ready, return \
JSON inside <json>...</json> tags:

<json>
{{
  "points": [
    {{"description": "...", "score": 85}},
    {{"description": "...", "score": 40}}
  ]
}}
</json>

Score scale:
- 0-20: Tangentially related, minimal relevance to the question
- 21-50: Somewhat relevant, provides background or indirect support
- 51-80: Directly relevant, addresses part of the question with evidence
- 81-100: Critical point that directly and substantially answers the question

Reference format for data-supported points:
"Description of the point [Data: Report Title (id), Report Title2 (id2), ...]"
Use at most 5 report references per point; add "+more" if there are more.
</output_format>

<rules>
- Preserve the original meaning and use of modal verbs (shall, may, will).
- Do not invent information — only extract what appears in the provided data.
- A point with no relevant information should receive score 0.
- Include ALL relevant points, even low-scoring ones — the reduce phase will filter.
</rules>

<data>
{context_data}
</data>"""

USER_TEMPLATE = """\
<query>
{user_query}
</query>

Extract all relevant points from the data and return them as JSON inside \
<json>...</json> tags, each with a description and relevance score (0-100)."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**params)},
    ]
    for turn in params.get("conversation_history") or []:
        if "role" in turn:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": USER_TEMPLATE.format(**params)})
    return messages
