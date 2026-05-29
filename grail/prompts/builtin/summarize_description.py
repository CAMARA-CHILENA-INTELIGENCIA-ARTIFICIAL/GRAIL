"""
Entity/relationship description summarizer (batched).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Accepts multiple entities per call and returns a JSON array of summaries inside
``<summaries>...</summaries>`` tags.  Each summary is 3-5 lines — detailed
enough to stand alone as a knowledge-graph node description.
"""
from typing import Any

NAME = "summarize_description"
REQUIRED_PARAMS = ["entities"]

SYSTEM_TEMPLATE = """\
<role>
You are a knowledge-graph curator responsible for consolidating entity and \
relationship descriptions inside GRAIL.
</role>

<context>
During knowledge-graph construction, the same entity or relationship is \
extracted from multiple text chunks, producing several partial descriptions. \
Your job is to synthesize each entity's descriptions into a single, \
comprehensive description that preserves all unique information.
</context>

<task>
For each numbered entity below, you are given multiple descriptions collected \
from different text chunks. For each entity:

1. Read all its descriptions carefully.
2. Identify unique facts, attributes, and activities across all descriptions.
3. Resolve any contradictions by preferring the most specific and detailed account.
4. Write a single, coherent summary in third person (3-5 lines maximum).
</task>

<output_format>
Return a JSON array inside <summaries>...</summaries> tags. Each element \
corresponds to an entity by its index number:

<summaries>
[
  {{"index": 1, "summary": "The consolidated description..."}},
  {{"index": 2, "summary": "The consolidated description..."}}
]
</summaries>

You may reason before the tags — only the JSON inside is parsed.
</output_format>

<rules>
- Each summary MUST be 3-5 lines: detailed enough to be self-contained, \
concise enough to fit in a knowledge-graph node.
- Include ALL unique facts from the descriptions — do not drop information.
- Do NOT simply concatenate the descriptions. Synthesize them into natural prose.
- Write in third person, including the entity name so the summary stands alone.
- If descriptions contradict each other, prefer the more specific and detailed one.
- Do not add information that does not appear in any description.
- You MUST return one entry for every entity provided, matching its index.
- LANGUAGE: write each summary in the same language as the input descriptions. \
If descriptions are in Spanish, the summary must be in Spanish. If mixed, use \
the dominant language.
</rules>"""

USER_TEMPLATE = """\
<entities>
{entities_text}
</entities>

Synthesize the descriptions for each entity above. Return a JSON array inside \
<summaries>...</summaries> tags with one entry per entity."""


def format_entities(entities: list[dict[str, Any]]) -> str:
    """Format a batch of entities for the prompt.

    Each entity dict has keys: ``index``, ``name``, ``descriptions``.
    """
    parts: list[str] = []
    for ent in entities:
        descs = ent["descriptions"]
        if isinstance(descs, (list, tuple)):
            desc_lines = "\n".join(f"- {d}" for d in descs)
        else:
            desc_lines = f"- {descs}"
        parts.append(
            f"--- Entity {ent['index']}: {ent['name']} ---\n"
            f"Descriptions:\n{desc_lines}"
        )
    return "\n\n".join(parts)


def build_messages(**params: Any) -> list[dict[str, Any]]:
    entities = params.get("entities", [])

    if isinstance(entities, list) and entities:
        entities_text = format_entities(entities)
    else:
        entities_text = str(entities)

    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(entities_text=entities_text)},
    ]
