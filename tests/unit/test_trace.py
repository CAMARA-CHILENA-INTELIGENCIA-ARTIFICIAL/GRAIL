"""Unit tests for QueryTracer."""
import json
from pathlib import Path

from grail.query.trace import QueryTracer


def test_tracer_records_entries():
    tracer = QueryTracer()
    tracer.record(
        tag="local_search",
        endpoint="deepinfra",
        model="Qwen/Qwen3-32B",
        messages=[{"role": "user", "content": "hello"}],
        response="world",
        duration_s=1.5,
        max_tokens=1024,
        temperature=0.0,
    )
    assert len(tracer.entries) == 1
    assert tracer.entries[0].tag == "local_search"
    assert tracer.entries[0].response == "world"


def test_tracer_inactive_does_not_record():
    tracer = QueryTracer(_active=False)
    tracer.record(
        tag="x",
        endpoint="e",
        model="m",
        messages=[],
        response="r",
    )
    assert len(tracer.entries) == 0


def test_tracer_dump(tmp_path: Path):
    tracer = QueryTracer()
    tracer.record(
        tag="local_search",
        endpoint="deepinfra",
        model="Qwen/Qwen3-32B",
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is X?"},
        ],
        response="X is a thing.",
        duration_s=2.1,
        max_tokens=2048,
        temperature=0.0,
    )
    tracer.record(
        tag="query_embedding",
        endpoint="deepinfra",
        model="intfloat/multilingual-e5-large",
        messages=[{"role": "user", "content": "embed this"}],
        response="[0.1, 0.2]",
        duration_s=0.3,
        max_tokens=0,
        temperature=0.0,
    )

    path = tracer.dump(
        tmp_path / "traces",
        query="What is X?",
        mode="local",
        result_response="X is a thing.",
        context_text="Entities\nid,name...",
        completion_time=3.5,
        llm_calls=2,
    )

    assert path.exists()
    assert path.suffix == ".json"
    data = json.loads(path.read_text())
    assert data["query"] == "What is X?"
    assert data["mode"] == "local"
    assert data["llm_calls"] == 2
    assert len(data["llm_interactions"]) == 2
    assert data["llm_interactions"][0]["messages"][1]["content"] == "What is X?"
    assert data["final_response"] == "X is a thing."
    assert data["context_text"] == "Entities\nid,name..."


def test_tracer_dump_with_tool_calls(tmp_path: Path):
    tracer = QueryTracer()
    tracer.record(
        tag="agent_search",
        endpoint="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Find info about Y"}],
        response=None,
        tool_calls=[
            {"id": "call_1", "function": {"name": "local_search", "arguments": '{"query":"Y"}'}},
        ],
        duration_s=1.0,
        max_tokens=4096,
        temperature=0.0,
    )

    path = tracer.dump(
        tmp_path / "traces",
        query="Find info about Y",
        mode="agent",
        result_response="Y is...",
        completion_time=5.0,
        llm_calls=3,
    )

    data = json.loads(path.read_text())
    assert data["llm_interactions"][0]["tool_calls"] is not None
    assert data["llm_interactions"][0]["tool_calls"][0]["function"]["name"] == "local_search"
