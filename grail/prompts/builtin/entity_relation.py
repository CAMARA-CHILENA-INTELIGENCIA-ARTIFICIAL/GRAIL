"""
Entity & relationship extraction prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Sends a text chunk to the model and asks for entities + relationships in the
GraphRAG canonical tuple format:

    ("entity"<|>NAME<|>TYPE<|>DESC)## ("relationship"<|>SRC<|>TGT<|>DESC<|>STRENGTH)<|COMPLETE|>

The DEFAULT_DELIMITERS dict is the contract between this prompt and
:mod:`grail.indexing.entities_relationships` — the parser there reads the same
tokens, so don't change them in only one place.
"""
from typing import Any

NAME = "entity_relation"

REQUIRED_PARAMS = ["entity_types", "input_text"]

DEFAULT_DELIMITERS: dict[str, str] = {
    "tuple_delimiter": "<|>",
    "record_delimiter": "##",
    "completion_delimiter": "<|COMPLETE|>",
}

SYSTEM_TEMPLATE = """-Goal-
Given a text document that is potentially relevant to this activity and a list of entity types, identify all entities of those types from the text and all relationships among the identified entities.

-Steps-
1. Identify all entities. For each identified entity, extract the following information:
- entity_name: Name of the entity, capitalized
- entity_type: One of the following types: [{entity_types}]
- entity_description: Comprehensive description of the entity's attributes and activities
Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>)

2. From the entities identified in step 1, identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
For each pair of related entities, extract the following information:
- source_entity: name of the source entity, as identified in step 1
- target_entity: name of the target entity, as identified in step 1
- relationship_description: explanation as to why you think the source entity and the target entity are related to each other
- relationship_strength: a numeric score indicating the strength of the relationship between the source entity and target entity
Format each relationship as ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_strength>)

3. Return output in English as a single list of all the entities and relationships identified in steps 1 and 2. Use **{record_delimiter}** as the list delimiter.

4. When finished, output {completion_delimiter}

######################
-Examples-
######################
Example 1: Books

Entity_types: [person, technology, mission, organization, location]
Text:
while Alex clenched his jaw, the buzz of frustration dull against the backdrop of Taylor's authoritarian certainty. It was this competitive undercurrent that kept him alert, the sense that his and Jordan's shared commitment to discovery was an unspoken rebellion against Cruz's narrowing vision of control and order.

Then Taylor did something unexpected. They paused beside Jordan and, for a moment, observed the device with something akin to reverence. "If this tech can be understood..." Taylor said, their voice quieter, "It could change the game for us. For all of us."
################
Output:
("entity"{tuple_delimiter}"Alex"{tuple_delimiter}"person"{tuple_delimiter}"Alex is a character who experiences frustration and is observant of the dynamics among other characters."){record_delimiter}
("entity"{tuple_delimiter}"Taylor"{tuple_delimiter}"person"{tuple_delimiter}"Taylor is portrayed with authoritarian certainty and shows a moment of reverence towards a device, indicating a change in perspective."){record_delimiter}
("entity"{tuple_delimiter}"Jordan"{tuple_delimiter}"person"{tuple_delimiter}"Jordan shares a commitment to discovery and has a significant interaction with Taylor regarding a device."){record_delimiter}
("entity"{tuple_delimiter}"Cruz"{tuple_delimiter}"person"{tuple_delimiter}"Cruz is associated with a vision of control and order, influencing the dynamics among other characters."){record_delimiter}
("entity"{tuple_delimiter}"The Device"{tuple_delimiter}"technology"{tuple_delimiter}"The Device is central to the story, with potential game-changing implications, and is revered by Taylor."){record_delimiter}
("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Taylor"{tuple_delimiter}"Alex is affected by Taylor's authoritarian certainty and observes changes in Taylor's attitude towards the device."{tuple_delimiter}7){record_delimiter}
("relationship"{tuple_delimiter}"Taylor"{tuple_delimiter}"The Device"{tuple_delimiter}"Taylor shows reverence towards the device, indicating its importance and potential impact."{tuple_delimiter}9){completion_delimiter}
#############################
Example 2: Code

Entity_types: [function, class, variable, method, module]
Text:
```python
class DataPreprocessor:
    def __init__(self, data):
        self.data = data
    def normalize(self):
        return (self.data - np.mean(self.data)) / np.std(self.data)
```
Output:
("entity"{tuple_delimiter}"DataPreprocessor"{tuple_delimiter}"class"{tuple_delimiter}"A class that handles data preprocessing operations, including initialization with data and a method for normalization."){record_delimiter}
("entity"{tuple_delimiter}"normalize"{tuple_delimiter}"method"{tuple_delimiter}"A method of the DataPreprocessor class that normalizes the data using mean and standard deviation."){record_delimiter}
("relationship"{tuple_delimiter}"DataPreprocessor"{tuple_delimiter}"normalize"{tuple_delimiter}"The normalize method is part of the DataPreprocessor class."{tuple_delimiter}9){completion_delimiter}
#############################
Example 3: Scientific papers

Entity_types: [concept, methodology, finding, author, institution, journal]
Text:
Dr. Sarah Chen and Prof. Michael Bergman from Stanford's Institute of Quantum Biology have published groundbreaking research in Nature Physics on quantum entanglement in photosynthesis. Using two-dimensional electronic spectroscopy and quantum dynamics simulations, they studied the Fenna-Matthews-Olson (FMO) complex in green sulfur bacteria.
Output:
("entity"{tuple_delimiter}"Quantum Entanglement"{tuple_delimiter}"concept"{tuple_delimiter}"A quantum phenomenon where particles' states remain interconnected over distances."){record_delimiter}
("entity"{tuple_delimiter}"Dr. Sarah Chen"{tuple_delimiter}"author"{tuple_delimiter}"Primary researcher and author of the paper on quantum entanglement in photosynthesis."){record_delimiter}
("entity"{tuple_delimiter}"Institute of Quantum Biology"{tuple_delimiter}"institution"{tuple_delimiter}"Research institution at Stanford University where the study was conducted."){record_delimiter}
("relationship"{tuple_delimiter}"Dr. Sarah Chen"{tuple_delimiter}"Institute of Quantum Biology"{tuple_delimiter}"Dr. Chen is affiliated with the Institute of Quantum Biology at Stanford University."{tuple_delimiter}7){completion_delimiter}
#############################"""

USER_TEMPLATE = """Remember to identify entities and then create relationships for them; relationships can only reference defined entities. This is the real data.

-Real Data-
######################
Entity_types: {entity_types}
Text: {input_text}
--END--

Now create the entities and relationships with scores requested from the text.

The final output must use the delimited format: {tuple_delimiter} and {record_delimiter}, and finish with {completion_delimiter}."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    """Return chat messages ready for the LLM.

    ``entity_types`` may be a list or a comma-joined string. Delimiters default to the
    canonical ``<|>``, ``##``, ``<|COMPLETE|>`` triplet and can be overridden per call.
    """
    p = {**DEFAULT_DELIMITERS, **params}
    if isinstance(p.get("entity_types"), (list, tuple)):
        p["entity_types"] = ", ".join(str(x) for x in p["entity_types"])
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**p)},
        {"role": "user", "content": USER_TEMPLATE.format(**p)},
    ]
