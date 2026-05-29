"""
Claim extraction prompt (optional GraphRAG covariate pipeline).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Extracts claims (covariates) about entities from text, including status
assessment, date ranges, and source evidence. Output is wrapped in
``<extracted_data>...</extracted_data>`` tags for reliable parsing.
"""
from typing import Any

NAME = "claim_extraction"
REQUIRED_PARAMS = ["entity_specs", "claim_description", "input_text"]

DEFAULT_DELIMITERS: dict[str, str] = {
    "tuple_delimiter": "<|>",
    "record_delimiter": "##",
    "completion_delimiter": "</extracted_data>",
    "start_delimiter": "<extracted_data>",
}

SYSTEM_TEMPLATE = """\
<role>
You are an intelligence analyst specializing in extracting and assessing claims \
about entities from source documents.
</role>

<context>
You are part of GRAIL's covariate extraction pipeline. Claims are structured \
assertions about entities — factual statements, allegations, status assessments, \
or evaluations that can be tracked and verified. Each claim is linked to the \
specific text that supports it.
</context>

<task>
Given a text document, an entity specification, and a claim description:

1. Identify all named entities in the text that match the entity specification \
(which may be a list of entity names or entity types).
2. For each matching entity, extract all claims that fit the claim description. \
The entity is the subject of each claim.
3. For each claim, extract these fields:
   - Subject: Name of the subject entity, CAPITALIZED.
   - Object: Name of the object entity involved, or **NONE** if not applicable.
   - Claim Type: Overall category of the claim, CAPITALIZED (e.g., \
REGULATORY_VIOLATION, PERFORMANCE_METRIC, LEGAL_STATUS).
   - Claim Status: Assessment of the claim's veracity:
     - **TRUE**: Explicitly stated as fact in the text with clear evidence.
     - **FALSE**: Explicitly contradicted or denied in the text.
     - **SUSPECTED**: Implied, alleged, or under investigation — not confirmed.
   - Claim Description: Detailed description including all relevant evidence.
   - Claim Date: Date range as (start_date, end_date) in ISO-8601 format \
(YYYY-MM-DD). Use **NONE** for unknown dates.
   - Claim Source Text: List of ALL direct quotes from the original text that \
support this claim.
</task>

<output_format>
You may reason about the text before producing output. When ready, emit the \
structured claims inside {start_delimiter}...{completion_delimiter} tags.

Format each claim as:
({tuple_delimiter}<subject>{tuple_delimiter}<object>{tuple_delimiter}<type>{tuple_delimiter}<status>{tuple_delimiter}<start_date>{tuple_delimiter}<end_date>{tuple_delimiter}<description>{tuple_delimiter}<source_text>)

Use {record_delimiter} to separate claims.
</output_format>

<rules>
- Only extract claims that match the provided claim description.
- Each claim must be supported by specific text from the document.
- Do not fabricate claims or evidence — only report what the text says.
- Use **NONE** for any field where the information is not available.
- Claim source text must be direct quotes, not paraphrases.
</rules>

<example>
Entity specification: [company]
Claim description: legal or regulatory actions involving the company
Text: "In 2023, TechCorp was fined $2M by the SEC for failing to disclose \
material information. The company is also under investigation for potential \
insider trading violations."

{start_delimiter}
("TECHCORP"{tuple_delimiter}"SEC"{tuple_delimiter}"REGULATORY_FINE"{tuple_delimiter}"TRUE"{tuple_delimiter}"2023-01-01"{tuple_delimiter}"2023-12-31"{tuple_delimiter}"TechCorp was fined $2M by the SEC for failing to disclose material information to investors."{tuple_delimiter}"TechCorp was fined $2M by the SEC for failing to disclose material information"){record_delimiter}
("TECHCORP"{tuple_delimiter}"NONE"{tuple_delimiter}"INSIDER_TRADING_INVESTIGATION"{tuple_delimiter}"SUSPECTED"{tuple_delimiter}"NONE"{tuple_delimiter}"NONE"{tuple_delimiter}"TechCorp is under investigation for potential insider trading violations. The investigation status is ongoing and no conclusions have been reached."{tuple_delimiter}"The company is also under investigation for potential insider trading violations"){record_delimiter}
{completion_delimiter}
</example>"""

USER_TEMPLATE = """\
<input>
Entity specification: {entity_specs}
Claim description: {claim_description}

Text:
{input_text}
</input>

Extract all matching claims. You may reason first, then emit structured claims \
inside {start_delimiter}...{completion_delimiter} tags."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    p = {**DEFAULT_DELIMITERS, **params}
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**p)},
        {"role": "user", "content": USER_TEMPLATE.format(**p)},
    ]
