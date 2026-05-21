"""Custom entity-type discovery prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Given a sample of text from the corpus, ask the LLM to propose a YAML list of
entity types appropriate for the domain. The response is expected to be wrapped
in ``<entities>``...``</entities>`` tags.

Optional params ``existing_types`` and ``max_types`` let the caller communicate
what's already configured so the model avoids duplicates and respects the budget.
"""
from typing import Any

NAME = "create_custom_entities"
REQUIRED_PARAMS = ["texts"]

SYSTEM_TEMPLATE = """
You are an expert in knowledge-graph design working inside **GRAIL** (Graph RAG \
with Advanced Integration and Learning). GRAIL builds a queryable knowledge \
graph from source documents by:

1. Chunking input files into text units.
2. Extracting **entities** (typed named concepts) and **relationships** between \
them from every chunk using an LLM.
3. Building communities of related entities via graph clustering.
4. Generating narrative reports per community.
5. Answering questions by searching the graph.

The quality of the entire pipeline depends on choosing the right **entity types**. \
Types that are too generic (e.g. "THING") produce noisy, unhelpful nodes. Types \
that are too specific (e.g. "PHASE_III_RANDOMIZED_CLINICAL_TRIAL") will not \
generalise when new documents are added and pollute the type namespace.

-Rules-
• Each type must be a short UPPER_SNAKE_CASE label (1–3 words).
• Types must be broad enough to apply across multiple documents in the corpus, \
yet specific enough to be meaningfully distinct from each other.
• Do NOT propose types that overlap heavily (e.g. DRUG and MEDICATION — pick one).
• PERSON and ORGANIZATION are always included automatically — never duplicate them.
{existing_clause}
-Examples-

# Coding scripts
<entities>
["FUNCTION", "CLASS", "MODULE", "LIBRARY", "DESIGN_PATTERN"]
</entities>

# Cooking and recipes
<entities>
["INGREDIENT", "TECHNIQUE", "DISH", "CUISINE", "UTENSIL"]
</entities>

# Scientific papers
<entities>
["CONCEPT", "METHODOLOGY", "FINDING", "DATASET", "METRIC"]
</entities>

# Historical / geopolitical analysis
<entities>
["LOCATION", "EVENT", "ERA", "TREATY", "CONFLICT", "IDEOLOGY"]
</entities>

# Clinical oncology guidelines
<entities>
["DISEASE", "DRUG", "TREATMENT", "SYMPTOM", "BIOMARKER", "GUIDELINE", "CLINICAL_STUDY"]
</entities>

-Goal-
Read the corpus sample below. Propose the best entity types for this specific \
domain as a JSON list wrapped in <entities>...</entities> tags. Propose between \
{min_types} and {max_types} types (excluding PERSON and ORGANIZATION, which are \
added automatically)."""

USER_TEMPLATE = """
Below are representative excerpts from the knowledge base that GRAIL will index. \
Read them carefully and identify what kinds of named concepts appear repeatedly \
— those are your entity types.

<texts>
{texts}
</texts>

Now propose {min_types}–{max_types} entity types in UPPER_SNAKE_CASE that best \
capture the recurring named concepts in these texts. Remember:
• Short labels (1–3 words), UPPER_SNAKE_CASE.
• Broad enough to generalise, specific enough to be useful.
• No duplicates of PERSON, ORGANIZATION{existing_reminder}.

Return ONLY a JSON list inside <entities>...</entities> tags."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    if isinstance(params.get("texts"), (list, tuple)):
        params["texts"] = "\n\n---\n\n".join(str(x) for x in params["texts"])

    existing: list[str] = params.get("existing_types") or []
    max_types: int = params.get("max_types", 10)
    min_types: int = max(3, max_types // 2)

    if existing:
        names = ", ".join(existing)
        existing_clause = (
            f"• These types are already configured and MUST NOT be duplicated: "
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
