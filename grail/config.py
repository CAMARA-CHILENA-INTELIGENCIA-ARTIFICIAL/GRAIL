"""
Configuration loader.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

GRAIL configs are YAML files. Two layouts are supported:

* **Single file** — pass any YAML path; sections matching the schema fill in.
* **Directory layout** — pass a directory containing ``grail.yaml`` (the master)
  plus optional per-module YAMLs (``llm.yaml``, ``indexing.yaml``,
  ``endpoints.yaml``, ...). Sibling files merge into matching sections.

Environment substitution: any string ``${VAR}`` or ``${VAR:-default}`` is
resolved against ``os.environ`` after parsing.

Endpoints are first-class: a top-level ``endpoints`` section maps endpoint
names → ``{base_url, api_key_env, requires_key, notes}``. The defaults cover
common deployments (openai, anthropic, deepinfra, together, groq, openrouter,
ollama, vllm, sglang, lmstudio, local). User overrides merge with the defaults,
so you can append a new entry without restating the built-ins.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from grail.llm.providers import DEFAULT_ENDPOINTS


# Entity types that are always guaranteed to be present in the extraction prompt,
# regardless of what the user puts in ``IndexingConfig.entity_types``. PERSON and
# ORGANIZATION are the GraphRAG canonical defaults — useful for almost any corpus
# (the extractor still won't surface them if no people / orgs appear in the text).
MANDATORY_ENTITY_TYPES: tuple[str, ...] = ("PERSON", "ORGANIZATION")

DEFAULT_ENTITY_TYPES: tuple[str, ...] = (
    "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT",
)

_MODULES = (
    "endpoints",
    "llm",
    "embeddings",
    "indexing",
    "community",
    "search",
    "reranker",
    "storage",
    "prompts",
    "vectorstore",
)


class EndpointConfig(BaseModel):
    """One endpoint entry (matches :class:`grail.llm.providers.Endpoint`)."""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    api_key_env: Optional[str] = None
    requires_key: bool = True
    notes: str = ""


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(default="openai", description="Default endpoint name (must exist in endpoints config).")
    model: str = Field(default="gpt-4o-mini", description="Default model name within the default endpoint.")
    concurrent_requests: int = 15
    request_timeout: float = 180.0
    max_retries: int = 10
    max_retry_wait: float = 10.0
    sleep_on_rate_limit: float = 30.0
    debug: bool = False
    cache_enabled: bool = False
    cache_dir: Optional[str] = None

    # Extra pricing entries merged into the CostTracker at construction time.
    # Keyed by ``"endpoint|model"`` (canonical) or bare model name. Values are
    # ``[prompt_per_1M_usd, completion_per_1M_usd]``. See docs/glossary.md#llm.
    #
    # Example (DeepInfra publishes pricing via a non-OpenAI metadata extension —
    # paste the rates you care about here):
    #   extra_pricing:
    #     "deepinfra|google/gemma-4-26B-A4B-it": [0.07, 0.34]
    #     "deepinfra|Qwen/Qwen3-Embedding-0.6B": [0.005, 0.0]
    extra_pricing: dict[str, list[float]] = Field(default_factory=dict)


class EmbeddingsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = "deepinfra"
    model: str = "intfloat/multilingual-e5-large"
    encoding_format: str = "float"
    max_batch_size: int = 1024
    concurrent_requests: int = 30
    request_timeout: float = 180.0
    max_retries: int = 10
    max_retry_wait: float = 10.0
    sleep_on_rate_limit: float = 30.0


class IndexingConfig(BaseModel):
    """Stage-specific endpoint/model overrides default to ``null`` → inherit from
    :class:`LLMConfig`. Override per-stage by setting either ``*_endpoint`` or
    ``*_model`` (or both) — handy when you want to use a cheaper model for
    extraction and the headline model only for synthesis.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_size: int = 2000
    chunk_overlap: int = 50
    encoding_name: str = "cl100k_base"
    document_boundary: str = "\n\n---DOCUMENT_BOUNDARY---\n\n"
    input_folder: str = "input"
    output_folder: str = "output"
    cache_folder: str = "cache"

    entity_relation_endpoint: Optional[str] = None
    entity_relation_model: Optional[str] = None
    summarization_endpoint: Optional[str] = None
    summarization_model: Optional[str] = None

    entity_types: list[str] = Field(default_factory=lambda: list(DEFAULT_ENTITY_TYPES))
    discover_entity_types: bool = False
    max_entity_types: int = 15
    tuple_delimiter: Optional[str] = None
    record_delimiter: Optional[str] = None
    completion_delimiter: Optional[str] = None
    start_delimiter: Optional[str] = None
    extraction_max_tokens: int = 8192
    extraction_concurrency: Optional[int] = None
    summarization_concurrency: Optional[int] = None
    entity_discovery_max_tokens: int = 2048
    max_summarization_tokens: int = 756
    max_gleanings: int = 0

    @field_validator("entity_types", mode="after")
    @classmethod
    def _normalize_entity_types(cls, value: list[str]) -> list[str]:
        """Normalize every type to UPPER_SNAKE_CASE and guarantee MANDATORY_ENTITY_TYPES
        are present at the head of the list. Whitespace inside type names is
        collapsed to underscores so the prompt format stays clean.
        """
        seen: set[str] = set()
        normalized: list[str] = []
        for raw in list(MANDATORY_ENTITY_TYPES) + list(value or []):
            if not isinstance(raw, str):
                continue
            token = "_".join(raw.strip().upper().split())
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)
        return normalized

    MIN_ENTITY_TYPES: int = 5

    @model_validator(mode="after")
    def _check_min_entity_types(self) -> "IndexingConfig":
        if not self.discover_entity_types and len(self.entity_types) < self.MIN_ENTITY_TYPES:
            raise ValueError(
                f"indexing.entity_types has only {len(self.entity_types)} types "
                f"(minimum {self.MIN_ENTITY_TYPES}). Either add more types to the "
                f"list or set discover_entity_types: true to let the LLM propose them."
            )
        return self


class CommunityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_cluster_size: int = 50
    use_lcc: bool = False
    strategy: str = "leiden"
    seed: Optional[int] = None
    community_report_endpoint: Optional[str] = None
    community_report_model: Optional[str] = None
    json_corrector_endpoint: Optional[str] = None
    json_corrector_model: Optional[str] = None
    max_report_length: int = 4000
    report_concurrency: Optional[int] = None
    include_covariates: bool = False
    incremental_change_threshold: float = 0.3
    min_community_size: int = 10
    embedding_merge_eps: float = 0.5

    # Which Leiden hierarchy level gets community reports generated for it.
    # Values: "coarsest" (smallest level number — fewest, broadest communities;
    # default and recommended), "finest" (largest level number — most granular),
    # "all" (every level — matches the legacy + Microsoft GraphRAG behaviour),
    # or an int (specific level after inspecting final_communities.parquet).
    community_level: str | int = "coarsest"

    # Communities with fewer than this many entities are skipped at report
    # generation time. Defends against the long tail of singleton "communities"
    # produced by isolated entities (no relationships). 0 disables the filter.
    min_report_size: int = 3


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_search_endpoint: Optional[str] = None
    local_search_model: Optional[str] = None
    global_search_endpoint: Optional[str] = None
    global_search_model: Optional[str] = None
    local_max_tokens: int = 32_000
    local_text_unit_prop: float = 0.5
    local_community_prop: float = 0.1
    local_conversation_history_max_turns: int = 5
    local_top_k_entities: int = 10
    local_top_k_relationships: int = 10
    use_community_summary: bool = False
    global_map_max_tokens: int = 2000
    global_reduce_max_tokens: int = 8192
    global_chunk_size: int = 100_000
    global_concurrency: int = 5
    response_max_tokens: int = 16_384
    response_type: str = "Multiple Paragraphs"


class RerankerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    endpoint: str = "deepinfra"
    model: str = "Qwen/Qwen3-Reranker-0.6B"
    base_url: Optional[str] = None
    overfetch_factor: int = Field(default=3, ge=1, le=10)
    rerank_entities: bool = True
    rerank_text_units: bool = True
    request_timeout: float = 30.0


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str = "local"
    root: str = "~/.grail/projects/default"
    s3_bucket: Optional[str] = None
    s3_prefix: Optional[str] = None
    s3_region: Optional[str] = None
    s3_endpoint_url: Optional[str] = None


class PromptsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    custom_paths: list[str] = Field(default_factory=list)
    strict: bool = False


class VectorStoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str = "lancedb"
    collection_name: str = "entity_descriptions"
    uri: Optional[str] = None
    distance_fn: str = "l2"

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        allowed = {"lancedb", "faiss", "chromadb"}
        if v not in allowed:
            raise ValueError(f"vectorstore.backend must be one of {allowed}, got {v!r}")
        return v


def _default_endpoints() -> dict[str, EndpointConfig]:
    return {
        name: EndpointConfig(
            base_url=ep.base_url,
            api_key_env=ep.api_key_env,
            requires_key=ep.requires_key,
            notes=ep.notes,
        )
        for name, ep in DEFAULT_ENDPOINTS.items()
    }


class Config(BaseModel):
    """Top-level config object."""

    model_config = ConfigDict(extra="forbid")

    project_name: str = "default"
    root_dir: str = "~/.grail/projects/default"

    endpoints: dict[str, EndpointConfig] = Field(default_factory=_default_endpoints)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    community: CommunityConfig = Field(default_factory=CommunityConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    vectorstore: VectorStoreConfig = Field(default_factory=VectorStoreConfig)

    def resolved_root(self) -> Path:
        return Path(os.path.expanduser(self.root_dir)).resolve()


# ----------------------------------------------------------------------- helpers

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _substitute_env(value: Any) -> Any:
    if isinstance(value, str):
        def repl(match: re.Match) -> str:
            name = match.group(1)
            default = match.group(2) or ""
            return os.environ.get(name, default)

        return _ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def _merge_endpoints_with_defaults(merged: dict[str, Any]) -> dict[str, Any]:
    """Ensure user-supplied endpoints add to (don't replace) the built-in set."""
    defaults = {name: ep.model_dump() for name, ep in _default_endpoints().items()}
    user_endpoints = merged.get("endpoints") or {}
    if not isinstance(user_endpoints, dict):
        return merged
    merged_endpoints: dict[str, Any] = dict(defaults)
    for name, value in user_endpoints.items():
        if isinstance(value, dict) and name in merged_endpoints:
            merged_endpoints[name] = _deep_merge(merged_endpoints[name], value)
        else:
            merged_endpoints[name] = value
    merged["endpoints"] = merged_endpoints
    return merged


def load_config(source: str | Path | None = None) -> Config:
    """Load a GRAIL config.

    Parameters
    ----------
    source:
        * ``None`` — return the default :class:`Config`.
        * A YAML file path — load it as the master config.
        * A directory path — load ``<dir>/grail.yaml`` and merge any sibling
          per-module YAMLs.
    """
    if source is None:
        return Config()

    path = Path(source).expanduser().resolve()
    merged: dict[str, Any] = {}

    if path.is_dir():
        master = path / "grail.yaml"
        merged = _load_yaml(master)
        for module in _MODULES:
            mod_path = path / f"{module}.yaml"
            if mod_path.exists():
                mod_data = _load_yaml(mod_path)
                section = merged.get(module, {})
                if not isinstance(section, dict):
                    section = {}
                merged[module] = _deep_merge(section, mod_data)
    else:
        merged = _load_yaml(path)

    merged = _substitute_env(merged)
    merged = _merge_endpoints_with_defaults(merged)
    return Config.model_validate(merged)


def dump_config(config: Config, path: str | Path) -> Path:
    """Write ``config`` to ``path`` as a single YAML file."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config.model_dump(mode="python"), fh, sort_keys=False, default_flow_style=False)
    return out


__all__ = [
    "CommunityConfig",
    "Config",
    "EmbeddingsConfig",
    "EndpointConfig",
    "IndexingConfig",
    "LLMConfig",
    "PromptsConfig",
    "RerankerConfig",
    "SearchConfig",
    "StorageConfig",
    "VectorStoreConfig",
    "dump_config",
    "load_config",
]
