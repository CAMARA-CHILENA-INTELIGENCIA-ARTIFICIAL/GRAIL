"""Custom entity-type discovery prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Given a sample of text from the corpus, ask the LLM to propose a YAML list of
entity types appropriate for the domain. The response is expected to be wrapped
in ``<entities>``...``</entities>`` tags.
"""
from typing import Any

NAME = "create_custom_entities"
REQUIRED_PARAMS = ["texts"]

SYSTEM_TEMPLATE = """You are an AI expert in graph knowledge. We are creating a graph knowledge base using custom files, which can vary in context — code, documents, transcriptions, images, structured data, etc. Your task is to propose customized entity types so the graph works well for the chosen context. These entities will later have relationships and claims so we can build a graph.

--Examples--
# Example 1: Coding scripts
<entities>
["PERSON", "ORGANIZATION", "FUNCTION", "CLASS", "VARIABLE", "METHOD", "MODULE"]
</entities>

# Example 2: Cooking and recipes
<entities>
["PERSON", "ORGANIZATION", "INGREDIENT", "UTENSIL", "TECHNIQUE", "DISH", "CUISINE"]
</entities>

# Example 3: Scientific papers
<entities>
["PERSON", "ORGANIZATION", "CONCEPT", "METHODOLOGY", "FINDING"]
</entities>

# Example 4: Historical and geopolitical analysis
<entities>
["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "ERA", "TREATY", "CONFLICT", "IDEOLOGY", "ARTIFACT"]
</entities>

-Goal-
Propose the best entity types for the given context as a YAML list under <entities>...</entities> tags. The default entities PERSON and ORGANIZATION are always included automatically — do not duplicate them.

This will be the starting point of the graph; pick consistent, high-quality types that are not so specific they fail when new documents are added."""

USER_TEMPLATE = """These are some random texts from the knowledge base.

<texts>
{texts}
</texts>

Create a maximum of 10 entity types for the given text. The final answer must be wrapped in <entities>...</entities> tags."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    if isinstance(params.get("texts"), (list, tuple)):
        params["texts"] = "\n\n---\n\n".join(str(x) for x in params["texts"])
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
