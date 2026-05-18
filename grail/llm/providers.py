"""
Endpoint registry.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

GRAIL speaks one protocol — the OpenAI Chat Completions / Embeddings API. An
**endpoint** is just a deployment of that protocol: a ``base_url``, optionally an
``api_key_env``, plus a name to refer to it by. Endpoints are first-class
config; "openai" is no more special than "vllm" or "my-internal-cluster".

Endpoint and model are kept as **separate fields** in config and in public API.
A shorthand pipe-separated string (``"openai|gpt-4o-mini"``) is recognized for
power-user convenience in per-call overrides, but configs and docs lead with the
explicit form:

    llm:
      endpoint: openai
      model: gpt-4o-mini

To plug in your own deployment, drop an entry into ``configs/endpoints.yaml``:

    my-vllm:
      base_url: http://my-vllm.internal:8000/v1
      api_key_env: VLLM_API_KEY
      requires_key: false

Then ``endpoint: my-vllm`` anywhere works.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Endpoint:
    """One OpenAI-protocol deployment."""

    name: str
    base_url: str
    api_key_env: Optional[str] = None
    requires_key: bool = True
    notes: str = ""

    def resolve_api_key(self) -> Optional[str]:
        if self.api_key_env is None:
            return None
        return os.environ.get(self.api_key_env)


#: Built-in deployments. All speak the OpenAI protocol — no vendor-specific code paths.
#: To add or override, use :class:`EndpointRegistry.register` or the ``endpoints`` config block.
DEFAULT_ENDPOINTS: dict[str, Endpoint] = {
    "openai": Endpoint(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    ),
    "anthropic": Endpoint(
        name="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        notes="Anthropic exposes /v1/messages over the OpenAI-compatible protocol.",
    ),
    "deepinfra": Endpoint(
        name="deepinfra",
        base_url="https://api.deepinfra.com/v1/openai",
        api_key_env="DEEPINFRA_API_KEY",
    ),
    "together": Endpoint(
        name="together",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
    ),
    "groq": Endpoint(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
    ),
    "openrouter": Endpoint(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
    "ollama": Endpoint(
        name="ollama",
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        requires_key=False,
        notes="Local Ollama server.",
    ),
    "vllm": Endpoint(
        name="vllm",
        base_url="http://localhost:8000/v1",
        api_key_env="VLLM_API_KEY",
        requires_key=False,
        notes="Self-hosted vLLM server speaking OpenAI's protocol.",
    ),
    "sglang": Endpoint(
        name="sglang",
        base_url="http://localhost:30000/v1",
        api_key_env="SGLANG_API_KEY",
        requires_key=False,
        notes="Self-hosted SGLang server speaking OpenAI's protocol.",
    ),
    "lmstudio": Endpoint(
        name="lmstudio",
        base_url="http://localhost:1234/v1",
        api_key_env="LMSTUDIO_API_KEY",
        requires_key=False,
        notes="LM Studio local server.",
    ),
    "local": Endpoint(
        name="local",
        base_url="http://localhost:8000/v1",
        api_key_env="LOCAL_API_KEY",
        requires_key=False,
        notes="Catch-all for any locally hosted OpenAI-compatible server.",
    ),
}


@dataclass
class EndpointRegistry:
    """Mutable endpoint registry. Extend via :meth:`register` or by passing entries in config."""

    endpoints: dict[str, Endpoint] = field(default_factory=lambda: dict(DEFAULT_ENDPOINTS))

    def register(self, endpoint: Endpoint) -> None:
        self.endpoints[endpoint.name] = endpoint

    def get(self, name: str) -> Endpoint:
        if name not in self.endpoints:
            raise KeyError(
                f"Unknown endpoint '{name}'. Known: {sorted(self.endpoints)}. "
                "Register via EndpointRegistry.register(...) or add it under `endpoints:` in config."
            )
        return self.endpoints[name]

    def override(self, name: str, **kwargs) -> None:
        """Patch an existing endpoint (e.g. swap ``base_url`` for a private deployment)."""
        current = self.get(name)
        self.endpoints[name] = Endpoint(
            name=name,
            base_url=kwargs.get("base_url", current.base_url),
            api_key_env=kwargs.get("api_key_env", current.api_key_env),
            requires_key=kwargs.get("requires_key", current.requires_key),
            notes=kwargs.get("notes", current.notes),
        )


def resolve_endpoint_and_model(
    model: str | None,
    *,
    endpoint: str | None = None,
    default_endpoint: str = "openai",
    default_model: str | None = None,
) -> tuple[str, str]:
    """Pick the (endpoint, model) pair to use for one call.

    Resolution rules:

    * If ``endpoint`` is given explicitly, use it.
    * Else if ``model`` is in ``"<endpoint>|<model>"`` shorthand form, split it.
    * Else fall back to ``default_endpoint``.

    ``model`` itself can be ``None`` to fall back to ``default_model`` (with the
    same shorthand support).
    """
    selected = model if model is not None else default_model
    if selected is None:
        raise ValueError("No model selected and no default available.")
    if endpoint is not None:
        # Strip any pipe shorthand from the model name if both were supplied.
        if "|" in selected:
            _, _, selected = selected.partition("|")
        return endpoint, selected.strip()
    if "|" in selected:
        ep, _, mod = selected.partition("|")
        return ep.strip(), mod.strip()
    return default_endpoint, selected.strip()


# --- legacy shim ----------------------------------------------------------------
# Some external code may still import the old names. Keep them as thin aliases so
# the refactor doesn't break in-flight ports.
ProviderConfig = Endpoint
ProviderRegistry = EndpointRegistry
DEFAULT_PROVIDERS = DEFAULT_ENDPOINTS


def parse_model_id(model_id: str) -> tuple[str, str]:
    """Legacy alias for the pipe-shorthand splitter. Prefer :func:`resolve_endpoint_and_model`."""
    if "|" in model_id:
        ep, _, mod = model_id.partition("|")
        return ep.strip(), mod.strip()
    return "openai", model_id.strip()
