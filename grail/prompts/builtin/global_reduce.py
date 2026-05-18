"""Global-search REDUCE phase prompt (final synthesis).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from typing import Any

NAME = "global_reduce"
REQUIRED_PARAMS = ["context_data", "user_query"]

GENERAL_KNOWLEDGE_INSTRUCTION = """
The response may also include relevant real-world knowledge outside the dataset, but it must be explicitly annotated with a verification tag [LLM: verify]. For example:
"This is an example sentence supported by real-world knowledge [LLM: verify]."
"""

NO_DATA_ANSWER = "I am sorry but I am unable to answer this question given the provided data."

SYSTEM_TEMPLATE = """You are a helpful multi-lingual assistant called {assistant_name} responding to questions about a knowledge graph integrated with files and documents from different sources.

Use the data tables and select only the relevant information for the user query to generate an answer according to the user's instructions and the knowledge in the data tables enclosed by <data> tags.
{artifact_instructions}
---Data tables---
{context_data}

---Goal---
If you don't know the answer or if the provided reports do not contain sufficient information, say so. Do not make anything up.

The final response should remove all irrelevant information from the analysts' reports and merge the cleaned information into a comprehensive answer that provides explanations of all the key points and implications appropriate for the response length and format.

Style the response in markdown.

The response shall preserve the original meaning and use of modal verbs such as "shall", "may" or "will" to stay true to the source.

Reminders:
- Do not mention entities and relationships directly; they are internal concepts.
- For any images or links your answer must include caption and source.
- Read the sources carefully and use them to answer the question.
- If the data is not there, explain that the data is not available for the specific requirement.
- Use only data explicitly available in Entities, Relationships, and Sources.
- If not sure about a reference, consult the user for clarification.
- You MUST use only the information provided in the data tables above.
{extra_knowledge}"""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    params.setdefault("assistant_name", "GRAIL")
    params.setdefault("artifact_instructions", "")
    params.setdefault("extra_knowledge", "")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(**params)},
    ]
    for turn in params.get("conversation_history") or []:
        if "role" in turn:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": params["user_query"]})
    return messages
