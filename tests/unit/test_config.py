"""Config loader tests."""
import os
from pathlib import Path

import pytest

from grail.config import Config, dump_config, load_config


def test_defaults_load_without_a_file():
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.llm.endpoint == "openai"
    assert cfg.llm.model == "gpt-4o-mini"
    assert "openai" in cfg.endpoints
    assert cfg.endpoints["openai"].base_url == "https://api.openai.com/v1"


def test_single_file_loads(tmp_path: Path):
    cfg_path = tmp_path / "grail.yaml"
    cfg_path.write_text(
        "project_name: my-proj\n"
        "root_dir: /tmp/xyz\n"
        "llm:\n"
        "  endpoint: deepinfra\n"
        "  model: Qwen/Qwen3-32B\n"
        "  concurrent_requests: 4\n"
    )
    cfg = load_config(cfg_path)
    assert cfg.project_name == "my-proj"
    assert cfg.llm.endpoint == "deepinfra"
    assert cfg.llm.model == "Qwen/Qwen3-32B"
    assert cfg.llm.concurrent_requests == 4


def test_directory_layout_merges_per_module_files(tmp_path: Path):
    (tmp_path / "grail.yaml").write_text("project_name: dirproj\nroot_dir: /tmp/x\n")
    (tmp_path / "llm.yaml").write_text("endpoint: groq\nmodel: llama-3.3-70b\nrequest_timeout: 90\n")
    (tmp_path / "indexing.yaml").write_text("chunk_size: 1500\n")
    cfg = load_config(tmp_path)
    assert cfg.project_name == "dirproj"
    assert cfg.llm.endpoint == "groq"
    assert cfg.llm.model == "llama-3.3-70b"
    assert cfg.llm.request_timeout == 90
    assert cfg.indexing.chunk_size == 1500


def test_env_var_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MY_MODEL", "gpt-4o")
    (tmp_path / "grail.yaml").write_text(
        "project_name: env\nllm:\n  endpoint: openai\n  model: ${MY_MODEL}\n"
    )
    cfg = load_config(tmp_path / "grail.yaml")
    assert cfg.llm.model == "gpt-4o"


def test_env_var_default_used_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNSET_VAR", raising=False)
    (tmp_path / "grail.yaml").write_text(
        "project_name: env\nllm:\n  endpoint: openai\n  model: ${UNSET_VAR:-gpt-4o-mini}\n"
    )
    cfg = load_config(tmp_path / "grail.yaml")
    assert cfg.llm.model == "gpt-4o-mini"


def test_dump_roundtrip(tmp_path: Path):
    cfg = Config()
    cfg.project_name = "rt"
    out = dump_config(cfg, tmp_path / "out.yaml")
    reloaded = load_config(out)
    assert reloaded.project_name == "rt"
    assert reloaded.llm.endpoint == "openai"


def test_user_endpoints_merge_with_defaults(tmp_path: Path):
    (tmp_path / "grail.yaml").write_text("project_name: ep\n")
    (tmp_path / "endpoints.yaml").write_text(
        "my-vllm:\n"
        "  base_url: http://my-vllm:8000/v1\n"
        "  api_key_env: MY_VLLM_KEY\n"
        "  requires_key: false\n"
    )
    cfg = load_config(tmp_path)
    # User entry shows up …
    assert "my-vllm" in cfg.endpoints
    assert cfg.endpoints["my-vllm"].base_url == "http://my-vllm:8000/v1"
    # … and built-in entries still exist.
    assert "openai" in cfg.endpoints
    assert "deepinfra" in cfg.endpoints


def test_user_endpoint_can_override_default(tmp_path: Path):
    (tmp_path / "grail.yaml").write_text("project_name: ep\n")
    (tmp_path / "endpoints.yaml").write_text(
        "openai:\n  base_url: https://my-openai-proxy/v1\n"
    )
    cfg = load_config(tmp_path)
    assert cfg.endpoints["openai"].base_url == "https://my-openai-proxy/v1"
    # The api_key_env from the built-in default still applies (deep merge).
    assert cfg.endpoints["openai"].api_key_env == "OPENAI_API_KEY"
