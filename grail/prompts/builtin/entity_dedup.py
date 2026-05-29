"""
Entity deduplication judge prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Given a group of entities with high embedding similarity, asks the LLM to
determine which ones are true duplicates (same real-world concept) versus
distinct entities that happen to have similar descriptions.

Multiple candidate groups can be batched into a single prompt to minimize
LLM calls. The output is wrapped in ``<dedup_result>...</dedup_result>``
tags for reliable parsing.
"""
from typing import Any

NAME = "entity_dedup"
REQUIRED_PARAMS = ["entity_groups"]

SYSTEM_TEMPLATE = """\
<role>
You are an entity resolution expert for a knowledge graph. Your job is to \
determine which entities refer to the same real-world concept and should be \
merged, and which are distinct despite having similar descriptions.
</role>

<context>
During knowledge-graph construction, the same concept often gets extracted \
under slightly different names from different text chunks (e.g., \
"CANCER-RELATED ANOREXIA-CACHEXIA SYNDROME" vs "CANCER-ASSOCIATED CACHEXIA \
SYNDROME (CACS)"). These need to be merged. However, entities with similar \
descriptions may still be genuinely distinct — for example, "PRE-CACHEXIA" \
and "CACHEXIA" are different clinical stages, not duplicates.
</context>

<task>
For each numbered group of candidate entities below:

1. Read all entity names, types, and descriptions carefully.
2. Determine which entities refer to the EXACT SAME real-world concept.
3. For each set of true duplicates, pick the most complete and descriptive \
name as the canonical form.
4. Report your findings as JSON inside <dedup_result> tags.
</task>

<output_format>
Return a JSON list inside <dedup_result>...</dedup_result> tags. Each entry \
represents one set of duplicates to merge within a group:

<dedup_result>
[
  {
    "group": 1,
    "canonical_name": "THE BEST NAME FOR THIS ENTITY",
    "canonical_index": 1,
    "merge_indices": [3, 5],
    "reason": "brief explanation of why these are the same"
  }
]
</dedup_result>

- "group": which candidate group this merge belongs to (matches the group \
number in the input)
- "canonical_index": the index (within the group) of the entity whose name \
and description best represents the concept
- "canonical_name": the name to keep — usually the entity at canonical_index, \
but you may clean it up (e.g., remove redundant parenthetical abbreviations)
- "merge_indices": indices of entities that should be merged INTO the canonical
- "reason": one-sentence justification

If a group has NO true duplicates, omit it from the output. \
If no groups have duplicates at all, return an empty list: []
</output_format>

<rules>
- Two entities are duplicates ONLY if they refer to the exact same concept. \
Subtypes, stages, or related-but-distinct concepts are NOT duplicates.
- Prefer the most complete, unabbreviated name as canonical.
- Entities with different types (e.g., DISEASE vs SYMPTOM) are almost never \
duplicates — flag only when the type assignment is clearly wrong.
- When in doubt, keep entities separate. False merges are worse than missed \
merges — a missed merge just means slightly redundant data, while a false \
merge destroys information.
- You may reason before the <dedup_result> tags. Only the JSON inside is parsed.
</rules>"""

USER_TEMPLATE = """\
{entity_groups}

Analyze each group and identify true duplicates. Return your findings as \
JSON inside <dedup_result>...</dedup_result> tags."""


def format_entity_groups(
    groups: list[list[dict[str, str]]],
) -> str:
    """Format candidate groups for the prompt.

    Each group is a list of dicts with keys: index, name, type, description.
    """
    parts: list[str] = []
    for g_idx, group in enumerate(groups, 1):
        lines = [f"--- Group {g_idx} ---"]
        for ent in group:
            lines.append(
                f"{ent['index']}. {ent['name']}\n"
                f"   Type: {ent['type']}\n"
                f"   Description: \"{ent['description']}\""
            )
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def build_messages(**params: Any) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
