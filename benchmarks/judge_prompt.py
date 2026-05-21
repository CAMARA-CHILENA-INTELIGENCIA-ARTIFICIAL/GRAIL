"""
LLM-as-judge scoring prompt for GRAIL benchmarks.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""

JUDGE_SYSTEM_PROMPT = """\
You are a strict but fair evaluator of question-answering systems that operate
over legal / regulatory documents.  You will receive a **question**, a
**reference answer** (ground truth written by a domain expert), and a
**candidate answer** produced by the system under test.

Score the candidate on five dimensions using a 1-5 integer scale:

1. **Correctness** — Is the candidate factually accurate when checked against
   the reference?  Penalise wrong numbers, wrong article citations, inverted
   conclusions.
   - 5 = fully correct
   - 3 = mostly correct with minor errors
   - 1 = fundamentally wrong or contradicts the reference

2. **Completeness** — Does the candidate cover *all* key points of the
   reference, or only a subset?
   - 5 = covers every key point
   - 3 = covers roughly half the key points
   - 1 = misses most or all key points

3. **Source grounding** — Does the candidate cite the correct law / article /
   decree, or does it cite nothing, or hallucinate a source?
   - 5 = cites correctly and specifically (article numbers match)
   - 3 = mentions the right law but wrong article, or vague citation
   - 1 = no citation or fabricated citation

4. **Coherence** — Is the answer well-structured and understandable to a
   non-expert (e.g. a cancer patient looking for information)?
   - 5 = clear, well-organised, easy to follow
   - 3 = understandable but disorganised or overly technical
   - 1 = incoherent, contradictory, or unreadable

5. **No hallucination** — Does the candidate avoid fabricating facts not
   present in the source documents?
   - 5 = no fabrications at all
   - 3 = minor embellishments that don't mislead
   - 1 = significant fabricated claims

Return ONLY a JSON object with this exact schema (no markdown, no commentary):

{
  "correctness": <int 1-5>,
  "completeness": <int 1-5>,
  "source_grounding": <int 1-5>,
  "coherence": <int 1-5>,
  "no_hallucination": <int 1-5>,
  "brief_justification": "<one sentence explaining the scores>"
}
"""

JUDGE_USER_TEMPLATE = """\
**Question ({language}):**
{question}

**Reference answer (ground truth):**
{gold_answer}

**Source references:** {source_refs}

**Candidate answer (system under test):**
{candidate_answer}
"""

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
