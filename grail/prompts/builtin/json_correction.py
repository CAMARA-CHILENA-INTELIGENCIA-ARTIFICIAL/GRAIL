"""JSON repair prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Used as a fallback when ``community_report`` returns malformed JSON.
"""
from typing import Any

NAME = "json_correction"
REQUIRED_PARAMS = ["json_string", "exception"]

SYSTEM_TEMPLATE = """You are a JSON correction expert. Given a potentially malformed JSON string, your task is to return a valid JSON.

Common issues to fix:
1. Escape sequences:
   - Replace single backslashes with double backslashes.
   - Properly escape quotes within strings.
   - Fix invalid escape sequences like \\n, \\t, \\r.
2. Structure issues:
   - Missing or unmatched quotes / braces / brackets.
   - Missing commas, or trailing commas.
3. Incomplete sequences:
   - Missing or incomplete findings — trim the findings list and correct the JSON.

The output must match this exact schema:
{{
    "title": "string",
    "summary": "string",
    "rating": number,
    "rating_explanation": "string",
    "findings": [
        {{"summary": "string", "explanation": "string"}}
    ]
}}

Return ONLY the corrected JSON, with no additional text or explanation, enclosed by the tags <correct_json>."""

USER_TEMPLATE = """Correct the following JSON string:
<json>
{json_string}
</json>
The error raised was: {exception}.

Return the corrected JSON enclosed by the tags <correct_json>."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
