"""
Community narrative-report prompt.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Returns JSON shaped like:

    {
      "title": str,
      "summary": str,
      "rating": float,            # 0-10
      "rating_explanation": str,
      "findings": [{"summary": str, "explanation": str}, ...]
    }

The model may reason before outputting the JSON. The structured output must be
wrapped in ``<report_json>...</report_json>`` tags — the parser extracts JSON
from between these tags, ignoring any reasoning or preamble before them.
"""
from typing import Any

NAME = "community_report"
REQUIRED_PARAMS = ["input_text"]

JSON_SCHEMA: dict[str, Any] = {
    "name": "community_report",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "rating": {"type": "number"},
            "rating_explanation": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["summary", "explanation"],
                },
            },
        },
        "required": ["title", "summary", "rating", "rating_explanation", "findings"],
    },
}

SYSTEM_TEMPLATE = """\
<role>
You are a domain analyst working inside GRAIL (Graph RAG with Advanced \
Integration and Learning). Your expertise is in synthesizing structured data \
about entity clusters into clear, actionable narrative reports.
</role>

<context>
GRAIL organizes extracted entities and relationships into **communities** — \
clusters of closely related entities discovered through graph analysis. Each \
community represents a thematic group (e.g., a set of collaborating researchers, \
a drug and its associated clinical trials, a software module and its dependencies).

Your report will be stored alongside the community and used to answer high-level \
questions about the knowledge base. Reports that are too vague are useless for \
search; reports that fabricate details poison downstream answers.
</context>

<task>
Given a list of entities and relationships belonging to one community:

1. Analyze the entities and their connections to understand the community's theme.
2. Write a concise narrative report in JSON format.
3. Assign an importance rating based on the impact and significance of the \
community's information.
</task>

<output_format>
You may reason about the data before producing the report. When ready, output \
the JSON inside <report_json>...</report_json> tags. Everything outside these \
tags is ignored by the parser.

{
  "title": "<short descriptive title -- include key entity names>",
  "summary": "<executive summary of the community's theme and significance, max 5 lines>",
  "rating": <float 0-10>,
  "rating_explanation": "<one sentence justifying the rating>",
  "findings": [
    {
      "summary": "<one-line finding headline>",
      "explanation": "<concise paragraph with evidence from the data, max 3-4 lines>"
    }
  ]
}

Rating scale:
- 0-2: Routine, low-impact information (trivial connections, boilerplate)
- 3-5: Moderately interesting (notable but expected patterns)
- 6-8: Significant, actionable insights (key dependencies, important actors)
- 9-10: Critical findings with urgent implications (risks, breakthroughs)
</output_format>

<rules>
- Write 2-5 findings depending on community complexity. Small communities (3-5 \
entities) need 2; large communities (10+) may warrant up to 5.
- Each finding must reference specific data using the format: \
[Data: Entities (id, id); Relationships (id, id)]. Maximum 5 ids per reference.
- Do NOT invent information — only report what is present in the provided data.
- The title should be specific enough to distinguish this community from others. \
Include the most important entity names.
- Keep the summary self-contained: a reader should understand the community's \
theme without seeing the raw data.
- LANGUAGE: write the report in the same language as the entity descriptions \
in the data. If the data is in Spanish, the report must be in Spanish.
</rules>

<example>
Input:
Entities

id,entity,description
0,BEVACIZUMAB,A monoclonal antibody drug used in cancer treatment that targets VEGF
1,VEGF,Vascular endothelial growth factor; a protein that promotes blood vessel formation in tumors
2,COLORECTAL CANCER,A type of cancer affecting the colon or rectum

Relationships

id,source,target,description
0,BEVACIZUMAB,VEGF,Bevacizumab binds to and inhibits VEGF to prevent tumor angiogenesis
1,BEVACIZUMAB,COLORECTAL CANCER,Bevacizumab is used as a treatment for metastatic colorectal cancer

Output:
<report_json>
{
  "title": "Bevacizumab and VEGF-Targeted Therapy for Colorectal Cancer",
  "summary": "This community centers on bevacizumab, a monoclonal antibody that treats colorectal cancer by inhibiting VEGF-driven tumor angiogenesis. The relationship between drug, target protein, and disease forms a core therapeutic pathway.",
  "rating": 7.5,
  "rating_explanation": "High significance as it describes a well-established cancer treatment mechanism with direct clinical relevance.",
  "findings": [
    {
      "summary": "Bevacizumab inhibits VEGF to block tumor blood vessel formation",
      "explanation": "Bevacizumab is a monoclonal antibody that specifically binds to VEGF, preventing it from promoting angiogenesis in tumors. This mechanism is the drug's primary mode of action. [Data: Entities (0, 1); Relationships (0)]"
    },
    {
      "summary": "Bevacizumab is an established treatment for metastatic colorectal cancer",
      "explanation": "The drug is used in the treatment of metastatic colorectal cancer, representing a direct clinical application of VEGF inhibition in oncology. [Data: Entities (0, 2); Relationships (1)]"
    }
  ]
}
</report_json>
</example>"""

USER_TEMPLATE = """\
Analyze the community data below and produce the JSON report inside \
<report_json>...</report_json> tags.

<data>
{input_text}
</data>

Write the report now. You may reason about the data first — only the JSON \
inside <report_json> tags will be parsed."""


def build_messages(**params: Any) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE},
        {"role": "user", "content": USER_TEMPLATE.format(**params)},
    ]
