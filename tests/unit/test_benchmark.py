"""
Unit tests for the benchmark framework (no LLM calls).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BENCHMARK_PATH = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "simple_benchmark" / "benchmark.json"


@pytest.fixture()
def benchmark():
    with open(BENCHMARK_PATH) as f:
        return json.load(f)


class TestBenchmarkYAML:
    def test_loads_and_has_required_keys(self, benchmark):
        assert "name" in benchmark
        assert "categories" in benchmark
        assert "questions" in benchmark

    def test_has_30_questions(self, benchmark):
        assert len(benchmark["questions"]) == 30

    def test_all_question_ids_unique(self, benchmark):
        ids = [q["id"] for q in benchmark["questions"]]
        assert len(ids) == len(set(ids))

    def test_all_categories_defined(self, benchmark):
        defined = {c["id"] for c in benchmark["categories"]}
        used = {q["category"] for q in benchmark["questions"]}
        assert used <= defined, f"Undefined categories used: {used - defined}"

    def test_question_schema(self, benchmark):
        required = {"id", "category", "difficulty", "question", "gold_answer", "source_refs"}
        for q in benchmark["questions"]:
            missing = required - set(q.keys())
            assert not missing, f"{q['id']} missing keys: {missing}"

    def test_difficulty_values(self, benchmark):
        valid = {"easy", "medium", "hard"}
        for q in benchmark["questions"]:
            assert q["difficulty"] in valid, f"{q['id']} has invalid difficulty: {q['difficulty']}"

    def test_category_distribution(self, benchmark):
        from collections import Counter
        cats = Counter(q["category"] for q in benchmark["questions"])
        assert cats["single_fact"] == 5
        assert cats["multi_chunk"] == 5
        assert cats["cross_source"] == 5
        assert cats["procedural"] == 4
        assert cats["comparative"] == 3
        assert cats["negation_boundary"] == 3
        assert cats["global_synthesis"] == 5


class TestJudgePrompt:
    def test_build_judge_messages(self):
        from benchmarks.judge_prompt import build_judge_messages

        msgs = build_judge_messages(
            question="Test?",
            gold_answer="Gold",
            candidate_answer="Candidate",
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "Test?" in msgs[1]["content"]
        assert "Gold" in msgs[1]["content"]
        assert "Candidate" in msgs[1]["content"]

    def test_weighted_score(self):
        from benchmarks.judge_prompt import weighted_score

        perfect = {
            "correctness": 5,
            "completeness": 5,
            "source_grounding": 5,
            "coherence": 5,
            "no_hallucination": 5,
        }
        assert weighted_score(perfect) == 5.0

        minimum = {
            "correctness": 1,
            "completeness": 1,
            "source_grounding": 1,
            "coherence": 1,
            "no_hallucination": 1,
        }
        assert weighted_score(minimum) == 1.0


class TestRAGBaseline:
    def test_cosine_scores(self):
        import numpy as np
        from benchmarks.rag_baseline import RAGBaseline

        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        matrix = np.array(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.5, 0.5, 0.0]],
            dtype=np.float32,
        )
        scores = RAGBaseline._cosine_scores(query, matrix)
        assert scores[0] == pytest.approx(1.0, abs=1e-5)
        assert scores[1] == pytest.approx(0.0, abs=1e-5)
        assert scores[2] > 0.5

    def test_rag_system_prompt_exists(self):
        from benchmarks.rag_baseline import RAG_SYSTEM_PROMPT
        assert "context" in RAG_SYSTEM_PROMPT.lower()


class TestRunBenchmark:
    def test_filter_by_id(self, benchmark):
        from benchmarks.run_benchmark import filter_questions

        result = filter_questions(benchmark["questions"], ids=["Q01", "Q30"])
        assert len(result) == 2
        assert {q["id"] for q in result} == {"Q01", "Q30"}

    def test_filter_by_category(self, benchmark):
        from benchmarks.run_benchmark import filter_questions

        result = filter_questions(benchmark["questions"], categories=["global_synthesis"])
        assert len(result) == 5
        assert all(q["category"] == "global_synthesis" for q in result)

    def test_generate_report(self, benchmark):
        from benchmarks.run_benchmark import generate_report

        mock_scores = {}
        for q in benchmark["questions"]:
            mock_scores[q["id"]] = {
                "question": q["question"],
                "category": q["category"],
                "rag": {"weighted_score": 2.5},
                "grail_local": {"weighted_score": 4.0},
                "grail_local_reranked": {"weighted_score": 4.2},
                "grail_global": {"weighted_score": 3.5},
            }

        report = generate_report(
            benchmark,
            mock_scores,
            timestamp="2026-05-21T00:00:00Z",
            judge_model="test-model",
        )
        assert "OVERALL" in report
        assert "RAG" in report
        assert "GRAIL Local" in report
        assert "Local+Rerank" in report
        assert "test-model" in report
