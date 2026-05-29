"""
Global-search REDUCE phase prompt (final synthesis).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Synthesizes the final answer from community reports (direct mode) or from
map-phase extracted points (map-reduce mode).
"""
from typing import Any

NAME = "global_reduce"
REQUIRED_PARAMS = ["context_data", "user_query"]

GENERAL_KNOWLEDGE_INSTRUCTION = """
The response may also include relevant real-world knowledge outside the dataset, \
but it must be explicitly annotated with a verification tag [LLM: verify]. \
For example:
"This is an example sentence supported by real-world knowledge [LLM: verify]."
"""

NO_DATA_ANSWER = "I am sorry but I am unable to answer this question given the provided data."

SYSTEM_TEMPLATE = """\
<role>
You are {assistant_name}, a synthesis expert that produces comprehensive \
answers from knowledge-base reports. You are multi-lingual and adapt your \
response language to match the user's question.
</role>

<context>
The data below contains community reports and analyst-extracted points from a \
knowledge graph built by GRAIL. This information has already been filtered for \
relevance to the user's question. Your job is to synthesize it into a clear, \
well-organized final answer.
{artifact_instructions}
</context>

<data>
{context_data}
</data>

<task>
1. Review all provided data and identify information relevant to the question.
2. Discard irrelevant or redundant information.
3. Organize the remaining information by theme or topic.
4. Write a comprehensive answer in markdown format that addresses the question.
5. Cite sources using report references where available.
</task>

<rules>
- Use ONLY information present in the provided data. Do not add external knowledge.
- Synthesize a natural answer — do not expose internal terminology like \
"entities", "relationships", "text units", or "community reports" to the user.
- If the data does not contain enough information to answer, say so explicitly \
rather than guessing.
- Preserve the original meaning and use of modal verbs (shall, may, will) to \
stay true to the sources.
- For images or links in the data, include caption and source in your answer.
- Respond in the same language as the user's question.
- Style the response in markdown with appropriate headers and structure for \
the length of the answer.
{extra_knowledge}
</rules>"""


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
