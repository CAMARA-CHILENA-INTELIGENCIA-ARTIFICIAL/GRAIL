"""
Unit tests for the RerankerClient.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import pytest

from grail.config import Config, RerankerConfig
from grail.llm.reranker import RERANKER_URL_PATTERNS, RerankerClient, RerankResult


class TestRerankResult:
    def test_fields(self):
        r = RerankResult(index=0, score=0.95, text="hello")
        assert r.index == 0
        assert r.score == 0.95
        assert r.text == "hello"


class TestRerankerConfig:
    def test_defaults(self):
        cfg = RerankerConfig()
        assert cfg.enabled is False
        assert cfg.endpoint == "deepinfra"
        assert cfg.model == "Qwen/Qwen3-Reranker-0.6B"
        assert cfg.overfetch_factor == 3
        assert cfg.rerank_entities is True
        assert cfg.rerank_text_units is True

    def test_in_config(self):
        cfg = Config()
        assert cfg.reranker.enabled is False

    def test_from_dict(self):
        cfg = Config.model_validate({
            "reranker": {
                "enabled": True,
                "endpoint": "openai",
                "model": "my-reranker",
                "overfetch_factor": 5,
            }
        })
        assert cfg.reranker.enabled is True
        assert cfg.reranker.endpoint == "openai"
        assert cfg.reranker.model == "my-reranker"
        assert cfg.reranker.overfetch_factor == 5

    def test_overfetch_bounds(self):
        with pytest.raises(Exception):
            RerankerConfig(overfetch_factor=0)
        with pytest.raises(Exception):
            RerankerConfig(overfetch_factor=11)


class TestURLResolution:
    def test_deepinfra_pattern(self):
        client = RerankerClient()
        url = client._resolve_url("deepinfra", "Qwen/Qwen3-Reranker-0.6B")
        assert url == "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-0.6B"

    def test_explicit_base_url(self):
        client = RerankerClient(base_url="http://localhost:8080/rerank")
        url = client._resolve_url("local", "my-model")
        assert url == "http://localhost:8080/rerank/my-model"

    def test_base_url_with_placeholder(self):
        client = RerankerClient(base_url="http://myhost/v1/inference/{model}")
        url = client._resolve_url("local", "my-model")
        assert url == "http://myhost/v1/inference/my-model"

    def test_unknown_endpoint_derives_from_base(self):
        from grail.llm.providers import Endpoint, EndpointRegistry

        registry = EndpointRegistry(endpoints={})
        registry.register(Endpoint(
            name="custom",
            base_url="https://custom.example.com/v1/openai",
            requires_key=False,
        ))
        client = RerankerClient(endpoint_registry=registry)
        url = client._resolve_url("custom", "reranker-3B")
        assert url == "https://custom.example.com/v1/inference/reranker-3B"


class TestResponseParsing:
    def test_parse_deepinfra_scores_format(self):
        data = {"scores": [0.95, 0.12, 0.73]}
        docs = ["doc A", "doc B", "doc C"]
        results = RerankerClient._parse_response(data, docs)
        assert len(results) == 3
        assert results[0].index == 0
        assert results[0].score == 0.95
        assert results[0].text == "doc A"
        assert results[2].index == 2
        assert results[2].score == 0.73

    def test_parse_cohere_results_format(self):
        data = {
            "results": [
                {"index": 0, "relevance_score": 0.95},
                {"index": 1, "relevance_score": 0.12},
            ]
        }
        docs = ["doc A", "doc B"]
        results = RerankerClient._parse_response(data, docs)
        assert len(results) == 2
        assert results[0].score == 0.95
        assert results[1].score == 0.12

    def test_parse_empty(self):
        results = RerankerClient._parse_response({"results": []}, [])
        assert results == []

    def test_parse_empty_scores(self):
        results = RerankerClient._parse_response({"scores": []}, [])
        assert results == []

    def test_parse_score_fallback_key(self):
        data = {"results": [{"index": 0, "score": 0.5}]}
        results = RerankerClient._parse_response(data, ["hello"])
        assert results[0].score == 0.5


class TestRerankerClientInit:
    def test_default_fields(self):
        client = RerankerClient()
        assert client.default_endpoint == "deepinfra"
        assert client.default_model == "Qwen/Qwen3-Reranker-0.6B"
        assert client.request_timeout == 30.0

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self):
        client = RerankerClient()
        results = await client.rerank("query", [])
        assert results == []


class TestRerankerURLPatterns:
    def test_deepinfra_in_patterns(self):
        assert "deepinfra" in RERANKER_URL_PATTERNS
        assert "{model}" in RERANKER_URL_PATTERNS["deepinfra"]
