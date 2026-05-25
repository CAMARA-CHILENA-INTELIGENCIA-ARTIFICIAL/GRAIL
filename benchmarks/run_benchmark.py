"""
GRAIL Benchmark Runner.

Usage:
    python benchmarks/run_benchmark.py \\
        --config examples/quickstart/grail.yaml \\
        --benchmark benchmarks/simple_benchmark/benchmark.json \\
        --judge-model "deepinfra|Qwen/Qwen3.6-35B-A3B" \\
        --output benchmarks/results/

Can also run a subset:
    --questions Q01,Q02,Q03      # only specific IDs
    --categories single_fact     # only a category
    --skip-rag                   # skip the RAG baseline
    --skip-judge                 # collect responses only, judge later

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so `from grail...` works when
# running this script directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmarks.judge_prompt import build_judge_messages, weighted_score
from benchmarks.rag_baseline import RAGBaseline
from grail.core import GRAIL
from grail.schemas import SearchResult

log = logging.getLogger("grail.benchmarks")


# ======================================================================= I/O
def load_benchmark(path: str | Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def filter_questions(
    questions: list[dict],
    *,
    ids: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
) -> list[dict]:
    out = questions
    if ids:
        out = [q for q in out if q["id"] in ids]
    if categories:
        out = [q for q in out if q["category"] in categories]
    return out


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def write_report(path: Path, report: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


# =================================================================== PHASES

async def collect_grail_responses(
    grail: GRAIL,
    questions: list[dict],
    *,
    include_reranked: bool = False,
) -> dict[str, dict[str, Any]]:
    """Run each question through GRAIL local, global, and optionally local+reranker."""
    results: dict[str, dict[str, Any]] = {}
    total = len(questions)

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        log.info(f"[{i}/{total}] GRAIL — {qid}: {q['question'][:60]}...")

        local_result = await grail.search(
            query=q["question"], mode="local", use_reranker=False
        )
        global_result = await grail.search(query=q["question"], mode="global")

        results[qid] = {
            "question": q["question"],
            "grail_local": {
                "response": local_result.response,
                "completion_time": local_result.completion_time,
                "llm_calls": local_result.llm_calls,
            },
            "grail_global": {
                "response": global_result.response,
                "completion_time": global_result.completion_time,
                "llm_calls": global_result.llm_calls,
            },
        }

        if include_reranked:
            reranked_result = await grail.search(
                query=q["question"], mode="local", use_reranker=True
            )
            results[qid]["grail_local_reranked"] = {
                "response": reranked_result.response,
                "completion_time": reranked_result.completion_time,
                "llm_calls": reranked_result.llm_calls,
            }

    return results


async def collect_rag_responses(
    rag: RAGBaseline,
    questions: list[dict],
) -> dict[str, dict[str, Any]]:
    """Run each question through the naive RAG baseline."""
    results: dict[str, dict[str, Any]] = {}
    total = len(questions)

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        log.info(f"[{i}/{total}] RAG — {qid}: {q['question'][:60]}...")

        result = await rag.query(q["question"])
        results[qid] = {
            "question": q["question"],
            "rag": {
                "response": result.response,
                "completion_time": result.completion_time,
                "llm_calls": result.llm_calls,
            },
        }
    return results


async def judge_responses(
    llm_client,
    questions: list[dict],
    responses: dict[str, dict[str, Any]],
    *,
    language: str = "es",
    judge_endpoint: Optional[str] = None,
    judge_model: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Score every (question, system, response) triple via LLM-as-judge."""
    scores: dict[str, dict[str, Any]] = {}
    total = len(questions)
    systems = ["grail_local", "grail_local_reranked", "grail_global", "rag"]

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        scores[qid] = {"question": q["question"], "category": q["category"]}

        resp_data = responses.get(qid, {})

        for system in systems:
            candidate = resp_data.get(system, {}).get("response", "")
            if not candidate:
                scores[qid][system] = {"skipped": True}
                continue

            log.info(f"[{i}/{total}] Judging {qid}/{system}...")

            source_refs = ", ".join(q.get("source_refs", []))
            messages = build_judge_messages(
                question=q["question"],
                gold_answer=q["gold_answer"],
                candidate_answer=candidate,
                source_refs=source_refs,
                language=language,
            )

            raw = await llm_client.execute(
                messages,
                endpoint=judge_endpoint,
                model=judge_model,
                max_tokens=512,
                temperature=0.0,
                response_format={"type": "json_object"},
                tag="benchmark_judge",
            )

            try:
                parsed = json.loads(raw)
                parsed["weighted_score"] = weighted_score(parsed)
            except (json.JSONDecodeError, TypeError):
                parsed = {"raw": raw, "error": "failed to parse judge response"}

            scores[qid][system] = parsed

    return scores


# ================================================================== REPORT

def generate_report(
    benchmark: dict,
    scores: dict[str, dict],
    *,
    timestamp: str,
    judge_model: str,
) -> str:
    """Build a markdown report from judge scores."""
    lines = [
        f"# Benchmark Report: {benchmark['name']}",
        f"**Date:** {timestamp}",
        f"**Judge model:** {judge_model}",
        f"**Language:** {benchmark.get('language', 'es')}",
        "",
    ]

    categories = {c["id"]: c["label"] for c in benchmark["categories"]}
    systems = ["rag", "grail_local", "grail_local_reranked", "grail_global"]

    cat_scores: dict[str, dict[str, list[float]]] = {
        cat_id: {s: [] for s in systems} for cat_id in categories
    }

    for qid, qscores in scores.items():
        cat = qscores.get("category", "unknown")
        if cat not in cat_scores:
            continue
        for sys_name in systems:
            s = qscores.get(sys_name, {})
            w = s.get("weighted_score")
            if w is not None:
                cat_scores[cat][sys_name].append(w)

    lines.append("## Summary by Category")
    lines.append("")
    lines.append(
        "| Category | RAG | GRAIL Local | GRAIL Local+Rerank | GRAIL Global | Best delta |"
    )
    lines.append("|---|---|---|---|---|---|")

    all_scores: dict[str, list[float]] = {s: [] for s in systems}

    for cat_id, label in categories.items():
        avgs = {}
        for sys_name in systems:
            vals = cat_scores[cat_id][sys_name]
            avgs[sys_name] = sum(vals) / len(vals) if vals else 0.0

        rag_avg = avgs["rag"]
        best_grail = max(avgs["grail_local"], avgs["grail_local_reranked"], avgs["grail_global"])
        delta = best_grail - rag_avg

        for sys_name in systems:
            all_scores[sys_name].append(avgs[sys_name])

        lines.append(
            f"| {label} | {rag_avg:.2f} | {avgs['grail_local']:.2f} | "
            f"{avgs['grail_local_reranked']:.2f} | "
            f"{avgs['grail_global']:.2f} | {'+' if delta >= 0 else ''}{delta:.2f} |"
        )

    overalls = {s: (sum(v) / len(v) if v else 0) for s, v in all_scores.items()}
    best_grail = max(overalls["grail_local"], overalls["grail_local_reranked"], overalls["grail_global"])
    overall_delta = best_grail - overalls["rag"]

    lines.append(
        f"| **OVERALL** | **{overalls['rag']:.2f}** | **{overalls['grail_local']:.2f}** | "
        f"**{overalls['grail_local_reranked']:.2f}** | "
        f"**{overalls['grail_global']:.2f}** | **{'+' if overall_delta >= 0 else ''}{overall_delta:.2f}** |"
    )
    lines.append("")

    lines.append("## Per-Question Breakdown")
    lines.append("")
    lines.append("| ID | Category | Difficulty | RAG | Local | Local+Rerank | Global |")
    lines.append("|---|---|---|---|---|---|---|")

    q_lookup = {q["id"]: q for q in benchmark["questions"]}
    for qid in sorted(scores.keys()):
        qscores = scores[qid]
        q = q_lookup.get(qid, {})
        row_scores = {}
        for sys_name in systems:
            s = qscores.get(sys_name, {})
            row_scores[sys_name] = s.get("weighted_score", "-")

        def fmt(v):
            return f"{v:.2f}" if isinstance(v, (int, float)) else str(v)

        lines.append(
            f"| {qid} | {q.get('category', '?')} | {q.get('difficulty', '?')} | "
            f"{fmt(row_scores['rag'])} | {fmt(row_scores['grail_local'])} | "
            f"{fmt(row_scores['grail_local_reranked'])} | "
            f"{fmt(row_scores['grail_global'])} |"
        )

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by GRAIL Benchmark Runner on {timestamp}*")
    return "\n".join(lines)


# ===================================================================== MAIN

async def main(args: argparse.Namespace) -> None:
    benchmark = load_benchmark(args.benchmark)
    questions = filter_questions(
        benchmark["questions"],
        ids=args.questions.split(",") if args.questions else None,
        categories=args.categories.split(",") if args.categories else None,
    )
    if not questions:
        log.error("No questions matched the filter. Exiting.")
        return

    log.info(f"Benchmark: {benchmark['name']} — {len(questions)} questions")

    grail = GRAIL.from_config(args.config)
    language = benchmark.get("language", "es")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_dir = Path(args.output) / timestamp.replace(":", "-")

    include_reranked = args.include_reranked and grail.reranker is not None
    if args.include_reranked and grail.reranker is None:
        log.warning("--include-reranked requested but no reranker configured. Skipping reranked variant.")

    log.info("Phase 1a: collecting GRAIL responses...")
    grail_responses = await collect_grail_responses(
        grail, questions, include_reranked=include_reranked
    )

    # Phase 1b: collect RAG responses
    merged_responses: dict[str, dict[str, Any]] = {}
    for qid, data in grail_responses.items():
        merged_responses[qid] = data

    if not args.skip_rag:
        log.info("Phase 1b: collecting RAG baseline responses...")
        rag = RAGBaseline(
            storage=grail.storage,
            llm=grail.llm,
            embeddings=grail.embeddings,
            output_folder=grail._output_folder(),
            top_k=grail.config.search.local_top_k_entities,
            endpoint=grail.config.search.local_search_endpoint,
            model=grail.config.search.local_search_model,
            reporter=grail.reporter,
        )
        await rag.prepare()
        rag_responses = await collect_rag_responses(rag, questions)
        for qid, data in rag_responses.items():
            merged_responses.setdefault(qid, {}).update(data)
    else:
        log.info("Skipping RAG baseline (--skip-rag)")

    write_json(out_dir / "responses.json", merged_responses)
    log.info(f"Responses saved to {out_dir / 'responses.json'}")

    # Phase 2: judge
    if not args.skip_judge:
        log.info("Phase 2: judging responses...")
        judge_model = args.judge_model
        judge_endpoint = None
        if judge_model and "|" in judge_model:
            judge_endpoint, judge_model = judge_model.split("|", 1)

        judge_scores = await judge_responses(
            grail.llm,
            questions,
            merged_responses,
            language=language,
            judge_endpoint=judge_endpoint,
            judge_model=judge_model,
        )
        write_json(out_dir / "judge_scores.json", judge_scores)
        log.info(f"Scores saved to {out_dir / 'judge_scores.json'}")

        # Phase 3: report
        report = generate_report(
            benchmark,
            judge_scores,
            timestamp=timestamp,
            judge_model=args.judge_model or "default",
        )
        write_report(out_dir / "report.md", report)
        log.info(f"Report saved to {out_dir / 'report.md'}")
        print(report)
    else:
        log.info("Skipping judge (--skip-judge). Re-run without --skip-judge to score.")

    cost = grail.cost_tracker.total_cost_usd()
    log.info(f"Total LLM cost for benchmark: ${cost:.4f}")


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="GRAIL Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", required=True, help="Path to grail.yaml config"
    )
    parser.add_argument(
        "--benchmark", required=True, help="Path to benchmark JSON file"
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model for LLM-as-judge (e.g. 'deepinfra|Qwen/Qwen3.6-35B-A3B')",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/results",
        help="Output directory (default: benchmarks/results/)",
    )
    parser.add_argument(
        "--questions",
        default=None,
        help="Comma-separated question IDs to run (e.g. Q01,Q02)",
    )
    parser.add_argument(
        "--categories",
        default=None,
        help="Comma-separated category IDs to run",
    )
    parser.add_argument(
        "--skip-rag",
        action="store_true",
        help="Skip the RAG baseline",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Collect responses only; skip judging",
    )
    parser.add_argument(
        "--include-reranked",
        action="store_true",
        help="Include GRAIL local search with reranking as a 4th system",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env", override=False)
        config_dir = Path(args.config).resolve().parent
        if (config_dir / ".env").exists():
            load_dotenv(config_dir / ".env", override=False)
    except ImportError:
        pass

    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
