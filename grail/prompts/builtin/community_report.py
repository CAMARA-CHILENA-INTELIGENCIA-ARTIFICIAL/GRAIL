"""Community narrative-report prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Returns JSON shaped like:

    {
      "title": str,
      "summary": str,
      "rating": float,            # 0-10
      "rating_explanation": str,
      "findings": [{"summary": str, "explanation": str}, ...]
    }

The model may reason before outputting the JSON. The structured output must be
wrapped in ``<report_json>...</report_json>`` tags — the parser extracts JSON
from between these tags, ignoring any reasoning or preamble before them.
"""
from typing import Any

NAME = "community_report"
REQUIRED_PARAMS = ["input_text"]

JSON_SCHEMA: dict[str, Any] = {
    "name": "community_report",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "rating": {"type": "number"},
            "rating_explanation": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["summary", "explanation"],
                },
            },
        },
        "required": ["title", "summary", "rating", "rating_explanation", "findings"],
    },
}

SYSTEM_TEMPLATE = """\
You are a knowledge-graph analyst inside GRAIL. Your job is to write a concise \
community report given a list of entities and their relationships.

# Output format

You may reason about the data first. When ready, output the JSON inside \
<report_json>...</report_json> tags. Everything outside these tags is ignored \
by the parser.

<report_json>
{{
  "title": "<short community name — include key entity names>",
  "summary": "<2-3 sentence executive summary>",
  "rating": <float 0-10>,
  "rating_explanation": "<one sentence>",
  "findings": [
    {{"summary": "<one line>", "explanation": "<one short paragraph>"}},
    ...
  ]
}}
</report_json>

# Rules
- Keep it concise: 2-4 findings, each with a 1-sentence summary and a single \
short paragraph explanation.
- Reference data as: [Data: Entities (id, id); Relationships (id, id)]. Max 5 ids per reference.
- Do not invent information — only use what appears in the provided data.
- Keep reasoning brief to stay within the token budget."""

USER_TEMPLATE = """\
Analyze the community data below and produce the JSON report inside \
<report_json>...</report_json> tags.

{input_text}

Output the report now."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
