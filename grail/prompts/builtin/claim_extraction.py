"""Claim extraction prompt (optional GraphRAG covariate pipeline).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from typing import Any

NAME = "claim_extraction"
REQUIRED_PARAMS = ["entity_specs", "claim_description", "input_text"]

DEFAULT_DELIMITERS: dict[str, str] = {
    "tuple_delimiter": "<|>",
    "record_delimiter": "##",
    "completion_delimiter": "<|COMPLETE|>",
}

SYSTEM_TEMPLATE = """-Target activity-
You are an intelligent assistant that helps a human analyst to analyze claims against certain entities presented in a text document.

-Goal-
Given a text document that is potentially relevant to this activity, an entity specification, and a claim description, extract all entities that match the entity specification and all claims against those entities.

-Steps-
1. Extract all named entities that match the predefined entity specification. The specification can be a list of entity names or a list of entity types.
2. For each entity identified in step 1, extract all claims associated with the entity. Each claim must match the claim description, and the entity is the subject of the claim.

For each claim, extract:
- Subject: name of the subject entity, capitalized.
- Object: name of the object entity. If unknown, use **NONE**.
- Claim Type: overall category, capitalized.
- Claim Status: **TRUE**, **FALSE**, or **SUSPECTED**.
- Claim Description: detailed description with all related evidence.
- Claim Date: (start_date, end_date) in ISO-8601, or **NONE**.
- Claim Source Text: list of **all** quotes from the original text relevant to the claim.

Format each claim as:
({tuple_delimiter}<subject>{tuple_delimiter}<object>{tuple_delimiter}<type>{tuple_delimiter}<status>{tuple_delimiter}<start>{tuple_delimiter}<end>{tuple_delimiter}<description>{tuple_delimiter}<source>)

3. Return output as a single list of all claims. Use **{record_delimiter}** as the list delimiter.
4. When finished, output {completion_delimiter}."""

USER_TEMPLATE = """-Real Data-
Entity specification: {entity_specs}
Claim description: {claim_description}
Text: {input_text}"""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    p = {**DEFAULT_DELIMITERS, **params}
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**p)},
        {"role": "user", "content": USER_TEMPLATE.format(**p)},
    ]
