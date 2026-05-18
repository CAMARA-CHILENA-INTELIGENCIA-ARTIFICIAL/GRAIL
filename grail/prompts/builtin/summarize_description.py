"""Entity/relationship description summarizer.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from typing import Any

NAME = "summarize_description"
REQUIRED_PARAMS = ["entity_name", "description_list"]

SYSTEM_TEMPLATE = """You are a helpful assistant responsible for generating a comprehensive summary of the data provided below.
Given one or two entities, and a list of descriptions, all related to the same entity or group of entities.
Please concatenate all of these into a single, comprehensive description. Make sure to include information collected from all the descriptions; the description must be detailed.
If the provided descriptions are contradictory, please resolve the contradictions and provide a single, coherent summary.
Make sure it is written in the third person, and include the entity names so we have the full context."""

USER_TEMPLATE = """#######
-Real Data-
Entities: {entity_name}
Description List: {description_list}
#######"""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    if isinstance(params.get("description_list"), (list, tuple)):
        params["description_list"] = "\n- " + "\n- ".join(str(x) for x in params["description_list"])
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
