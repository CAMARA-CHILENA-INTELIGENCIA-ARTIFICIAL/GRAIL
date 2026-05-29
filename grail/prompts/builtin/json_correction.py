"""
JSON repair prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Used as a fallback when ``community_report`` returns malformed JSON.
The corrected JSON must be wrapped in ``<corrected_json>...</corrected_json>``
tags so the parser can reliably extract it.
"""
from typing import Any

NAME = "json_correction"
REQUIRED_PARAMS = ["json_string", "exception"]

SYSTEM_TEMPLATE = """\
<role>
You are a JSON repair specialist. Given a malformed JSON string and the error \
it produced, return a corrected, valid JSON.
</role>

<task>
1. Read the malformed JSON and the error message.
2. Identify the issue (common problems listed below).
3. Fix the JSON while preserving as much original content as possible.
4. Return the corrected JSON inside <corrected_json>...</corrected_json> tags.
</task>

<common_issues>
- Escape sequences: unescaped quotes inside strings, invalid \\n / \\t, single backslashes
- Structure: missing or unmatched braces, brackets, or quotes; trailing commas
- Truncation: incomplete findings array or missing closing braces — trim the \
findings list and close the JSON properly
- Wrapping: JSON nested inside markdown fences or extra text
</common_issues>

<output_format>
The corrected output must match this schema:

{
  "title": "string",
  "summary": "string",
  "rating": number,
  "rating_explanation": "string",
  "findings": [
    {"summary": "string", "explanation": "string"}
  ]
}

Return ONLY the corrected JSON inside <corrected_json>...</corrected_json> tags. \
You may reason before the tags — only the content inside is kept.
</output_format>

<example>
Input (malformed):
{"title": "Example Report", "summary": "A test, "rating": 5, "findings": [{"summary": "test"

Error: Expecting ',' delimiter: line 1 column 37

Output:
<corrected_json>
{"title": "Example Report", "summary": "A test", "rating": 5, "rating_explanation": "", "findings": [{"summary": "test", "explanation": ""}]}
</corrected_json>
</example>"""

USER_TEMPLATE = """\
Correct the following malformed JSON:

<malformed_json>
{json_string}
</malformed_json>

<error>
{exception}
</error>

Return the corrected JSON inside <corrected_json>...</corrected_json> tags."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
