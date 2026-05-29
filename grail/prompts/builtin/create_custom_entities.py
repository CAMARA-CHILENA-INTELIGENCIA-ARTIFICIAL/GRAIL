"""
Custom entity-type discovery prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Given a sample of text from the corpus, ask the LLM to propose a JSON list of
entity types appropriate for the domain. The response is expected to be wrapped
in ``<entities>``...``</entities>`` tags.

Optional params ``existing_types`` and ``max_types`` let the caller communicate
what's already configured so the model avoids duplicates and respects the budget.
"""
from typing import Any

NAME = "create_custom_entities"
REQUIRED_PARAMS = ["texts"]

SYSTEM_TEMPLATE = """\
<role>
You are an expert in knowledge-graph design working inside GRAIL (Graph RAG \
with Advanced Integration and Learning).
</role>

<context>
GRAIL builds a queryable knowledge graph from source documents by:

1. Chunking input files into text units.
2. Extracting **entities** (typed named concepts) and **relationships** between \
them from every chunk using an LLM.
3. Building communities of related entities via graph clustering.
4. Generating narrative reports per community.
5. Answering questions by searching the graph.

The quality of the entire pipeline depends on choosing the right **entity types**. \
Types that are too generic (e.g., "THING") produce noisy, unhelpful nodes. Types \
that are too specific (e.g., "PHASE_III_RANDOMIZED_CLINICAL_TRIAL") fail to \
generalize when new documents are added and pollute the type namespace.
</context>

<task>
Read the corpus sample provided and propose the best entity types for this \
specific domain. Think carefully about what kinds of named concepts appear \
repeatedly in the text — those recurring patterns are your entity types.
</task>

<output_format>
You may reason about the text before proposing types. When ready, output a \
JSON list of type names inside <entities>...</entities> tags. Only the content \
inside these tags is parsed.

Example outputs for various domains:

Coding scripts:
<entities>
["FUNCTION", "CLASS", "MODULE", "LIBRARY", "DESIGN_PATTERN"]
</entities>

Scientific papers:
<entities>
["CONCEPT", "METHODOLOGY", "FINDING", "DATASET", "METRIC"]
</entities>

Clinical oncology:
<entities>
["DISEASE", "DRUG", "TREATMENT", "SYMPTOM", "BIOMARKER", "GUIDELINE", "CLINICAL_STUDY"]
</entities>

Historical / geopolitical analysis:
<entities>
["LOCATION", "EVENT", "ERA", "TREATY", "CONFLICT", "IDEOLOGY"]
</entities>
</output_format>

<rules>
- Each type must be a short UPPER_SNAKE_CASE label (1-3 words).
- Types must be broad enough to apply across multiple documents in the corpus, \
yet specific enough to be meaningfully distinct from each other.
- Do NOT propose types that overlap heavily (e.g., DRUG and MEDICATION — pick one).
- PERSON and ORGANIZATION are always included automatically — never duplicate them.
- Propose between {min_types} and {max_types} types (excluding PERSON and ORGANIZATION).
{existing_clause}
</rules>"""

USER_TEMPLATE = """\
Below are representative excerpts from the knowledge base that GRAIL will index. \
Read them carefully and identify what kinds of named concepts appear repeatedly \
— those are your entity types.

<texts>
{texts}
</texts>

Propose {min_types}-{max_types} entity types in UPPER_SNAKE_CASE that best \
capture the recurring named concepts in these texts.

Remember:
- Short labels (1-3 words), UPPER_SNAKE_CASE.
- Broad enough to generalize, specific enough to be useful.
- No duplicates of PERSON, ORGANIZATION{existing_reminder}.

You may reason about the domain first. Return the JSON list inside \
<entities>...</entities> tags."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    if isinstance(params.get("texts"), (list, tuple)):
        params["texts"] = "\n\n---\n\n".join(str(x) for x in params["texts"])

    existing: list[str] = params.get("existing_types") or []
    max_types: int = params.get("max_types", 10)
    min_types: int = max(3, max_types // 2)

    if existing:
        names = ", ".join(existing)
        existing_clause = (
            f"- These types are already configured and MUST NOT be duplicated: "
            f"{names}.\n"
        )
        existing_reminder = f", or any of: {names}"
    else:
        existing_clause = ""
        existing_reminder = ""

    system = SYSTEM_TEMPLATE.format(
        existing_clause=existing_clause,
        min_types=min_types,
        max_types=max_types,
    )
    user = USER_TEMPLATE.format(
        texts=params["texts"],
        min_types=min_types,
        max_types=max_types,
        existing_reminder=existing_reminder,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
