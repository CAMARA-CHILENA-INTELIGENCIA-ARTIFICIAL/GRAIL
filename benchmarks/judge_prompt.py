"""
LLM-as-judge scoring prompt for GRAIL benchmarks.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""

JUDGE_SYSTEM_PROMPT = """\
<role>
You are a strict but fair evaluator of question-answering systems. You assess \
the quality of candidate answers against expert-written reference answers.
</role>

<task>
You will receive a question, a reference answer (ground truth from a domain \
expert), and a candidate answer (produced by the system under test).

Score the candidate on five dimensions using a 1-5 integer scale:

1. **Correctness** — Is the candidate factually accurate against the reference?
   - 5: Fully correct, all facts match
   - 3: Mostly correct with minor errors
   - 1: Fundamentally wrong or contradicts the reference

2. **Completeness** — Does the candidate cover all key points of the reference?
   - 5: Covers every key point
   - 3: Covers roughly half the key points
   - 1: Misses most or all key points

3. **Source grounding** — Does the candidate cite correct sources (articles, \
laws, documents, sections), or hallucinate citations?
   - 5: Cites correctly and specifically (references match)
   - 3: Mentions the right source but wrong section, or vague citation
   - 1: No citation or fabricated citation

4. **Coherence** — Is the answer well-structured and understandable to a \
non-expert reader?
   - 5: Clear, well-organized, easy to follow
   - 3: Understandable but disorganized or overly technical
   - 1: Incoherent, contradictory, or unreadable

5. **No hallucination** — Does the candidate avoid fabricating facts not \
present in the source documents?
   - 5: No fabrications at all
   - 3: Minor embellishments that don't mislead
   - 1: Significant fabricated claims
</task>

<output_format>
Return ONLY a JSON object with this exact schema (no markdown, no commentary):

{
  "correctness": <int 1-5>,
  "completeness": <int 1-5>,
  "source_grounding": <int 1-5>,
  "coherence": <int 1-5>,
  "no_hallucination": <int 1-5>,
  "brief_justification": "<one sentence explaining the scores>"
}
</output_format>"""

JUDGE_USER_TEMPLATE = """\
<question language="{language}">
{question}
</question>

<reference_answer>
{gold_answer}
</reference_answer>

<source_references>
{source_refs}
</source_references>

<candidate_answer>
{candidate_answer}
</candidate_answer>

Score the candidate answer against the reference. Return only the JSON object."""

SCORE_WEIGHTS = {
    "correctness": 0.35,
    "completeness": 0.25,
    "source_grounding": 0.15,
    "coherence": 0.10,
    "no_hallucination": 0.15,
}


def build_judge_messages(
    *,
    question: str,
    gold_answer: str,
    candidate_answer: str,
    source_refs: str = "",
    language: str = "es",
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": JUDGE_USER_TEMPLATE.format(
                question=question,
                gold_answer=gold_answer,
                candidate_answer=candidate_answer,
                source_refs=source_refs,
                language=language,
            ),
        },
    ]


def weighted_score(scores: dict[str, int]) -> float:
    total = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        total += scores.get(key, 0) * weight
    return round(total, 2)
