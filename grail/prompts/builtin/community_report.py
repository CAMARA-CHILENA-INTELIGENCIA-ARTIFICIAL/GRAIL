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

SYSTEM_TEMPLATE = """You are an AI assistant that helps a human analyst perform general information discovery. Information discovery is the process of identifying and assessing relevant information associated with certain entities (e.g., organizations and individuals) within a network.

# Goal
Write a comprehensive report of a community, given a list of entities that belong to the community as well as their relationships and optional associated claims. The report will be used to inform decision-makers about information associated with the community and their potential impact.

# Report Structure

The report should include the following sections:
- TITLE: community's name that represents its key entities — short but specific. When possible, include representative named entities in the title.
- SUMMARY: An executive summary of the community's overall structure, how its entities are related, and significant associated information.
- IMPACT SEVERITY RATING: a float score between 0-10 that represents the severity of IMPACT posed by entities within the community. IMPACT is the scored importance of a community.
- RATING EXPLANATION: A single-sentence explanation of the IMPACT severity rating.
- DETAILED FINDINGS: A list of 5-10 key insights about the community. Each insight has a short summary followed by multiple paragraphs of explanatory text grounded in the data.

Return output as a well-formed JSON-formatted string with the following format:
{{
    "title": <report_title>,
    "summary": <executive_summary>,
    "rating": <impact_severity_rating>,
    "rating_explanation": <rating_explanation>,
    "findings": [
        {{"summary": <insight_1_summary>, "explanation": <insight_1_explanation>}},
        {{"summary": <insight_2_summary>, "explanation": <insight_2_explanation>}}
    ]
}}

# Grounding Rules

Points supported by data should list their data references as follows:
"This is an example sentence supported by multiple data references [Data: <dataset name> (record ids); <dataset name> (record ids)]."

Do not list more than 5 record ids in a single reference. Instead, list the top 5 most relevant record ids and add "+more" to indicate that there are more.

Do not include information where the supporting evidence for it is not provided."""

USER_TEMPLATE = """# Real Data

Use the following text for your answer. Do not make anything up.

Text:
{input_text}

Return the JSON enclosed by the tags <report_json> and keep it short."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
