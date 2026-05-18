"""
PromptRegistry — discover, resolve, and customise GRAIL prompts.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Built-ins live in ``grail/prompts/builtin/`` as Python modules. Users override one or
more prompts by pointing the registry at a directory whose ``.py`` files match the
built-in ``NAME`` constants. Resolution order:

    custom_paths (in given order) → builtin → KeyError

A custom prompt module **must** expose ``NAME``, ``REQUIRED_PARAMS``, and
``build_messages(**params) -> list[dict]``. The registry validates this on load and
raises a descriptive error if anything is missing — so failures show up at start-up,
not deep inside the indexing pipeline.

Strict mode (``PromptRegistry(custom_paths=..., strict=True)``) requires that a
custom directory provide every built-in prompt — useful when you want to enforce an
all-or-nothing override (e.g. a fully translated prompt pack).
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, runtime_checkable

_BUILTIN_PACKAGE = "grail.prompts.builtin"
_BUILTIN_DIR = Path(__file__).parent / "builtin"

BUILTIN_PROMPT_NAMES: tuple[str, ...] = (
    "entity_relation",
    "summarize_description",
    "community_report",
    "json_correction",
    "create_custom_entities",
    "local_search",
    "global_map",
    "global_reduce",
    "claim_extraction",
)


@runtime_checkable
class PromptModule(Protocol):
    """Interface every prompt file must satisfy."""

    NAME: str
    REQUIRED_PARAMS: list[str]
    build_messages: Callable[..., list[dict[str, Any]]]


def _validate_module(module: Any, *, source: str) -> PromptModule:
    for attr in ("NAME", "REQUIRED_PARAMS", "build_messages"):
        if not hasattr(module, attr):
            raise AttributeError(
                f"Prompt module at {source} is missing '{attr}'. "
                f"Every prompt must define NAME, REQUIRED_PARAMS, build_messages(**params)."
            )
    if not callable(module.build_messages):
        raise TypeError(f"{source}.build_messages must be callable.")
    return module  # type: ignore[return-value]


def _load_path(path: Path) -> PromptModule:
    """Load a single prompt .py file by path, give it a unique module name."""
    spec = importlib.util.spec_from_file_location(f"grail_prompts_custom.{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load prompt module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return _validate_module(module, source=str(path))


def _load_builtin(name: str) -> PromptModule:
    module = importlib.import_module(f"{_BUILTIN_PACKAGE}.{name}")
    return _validate_module(module, source=f"{_BUILTIN_PACKAGE}.{name}")


@dataclass
class PromptRegistry:
    """Resolves prompt modules by name, with optional user overrides.

    Parameters
    ----------
    custom_paths:
        Directories to search before the built-ins. Earlier entries take precedence.
    strict:
        When True, every built-in name must be overridden in at least one custom_path
        (i.e. a full prompt pack). When False (default), per-file overrides are allowed.
    """

    custom_paths: list[Path] = field(default_factory=list)
    strict: bool = False

    _cache: dict[str, PromptModule] = field(default_factory=dict, init=False, repr=False)
    _index: dict[str, Path] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        # Normalise paths.
        self.custom_paths = [Path(p) for p in self.custom_paths]
        for p in self.custom_paths:
            if not p.exists() or not p.is_dir():
                raise FileNotFoundError(f"Custom prompts directory does not exist: {p}")
            for py in p.glob("*.py"):
                if py.stem.startswith("_"):
                    continue
                self._index.setdefault(py.stem, py)
        if self.strict:
            missing = [name for name in BUILTIN_PROMPT_NAMES if name not in self._index]
            if missing:
                raise ValueError(
                    "strict=True but the custom prompts directory is missing "
                    f"required prompts: {missing}. Provide all of {list(BUILTIN_PROMPT_NAMES)} "
                    "or set strict=False to fall back to built-ins per prompt."
                )

    # ------------------------------------------------------------------ resolution

    def get(self, name: str) -> PromptModule:
        if name in self._cache:
            return self._cache[name]
        if name in self._index:
            module = _load_path(self._index[name])
        else:
            module = _load_builtin(name)
        if module.NAME != name:
            raise ValueError(
                f"Prompt module declares NAME={module.NAME!r} but was looked up as {name!r}; "
                "the filename and the NAME constant must agree."
            )
        self._cache[name] = module
        return module

    def build(self, name: str, **params: Any) -> list[dict[str, Any]]:
        """Convenience: resolve ``name`` and call ``build_messages(**params)``."""
        module = self.get(name)
        missing = [p for p in module.REQUIRED_PARAMS if p not in params]
        if missing:
            raise KeyError(
                f"Missing required params for prompt '{name}': {missing}. "
                f"Required: {module.REQUIRED_PARAMS}"
            )
        return module.build_messages(**params)

    def discover(self) -> dict[str, str]:
        """Map prompt name → source file path (custom path or built-in)."""
        out: dict[str, str] = {}
        for name in BUILTIN_PROMPT_NAMES:
            if name in self._index:
                out[name] = str(self._index[name])
            else:
                builtin_path = _BUILTIN_DIR / f"{name}.py"
                out[name] = str(builtin_path)
        # Surface any extra custom prompts the user dropped in.
        for stem, path in self._index.items():
            if stem not in out:
                out[stem] = str(path)
        return out

    def names(self) -> list[str]:
        """All known prompt names (built-ins ∪ custom files)."""
        return sorted(set(BUILTIN_PROMPT_NAMES) | set(self._index.keys()))


def required_prompts() -> tuple[str, ...]:
    """Return the canonical list of built-in prompt names — for docs and tests."""
    return BUILTIN_PROMPT_NAMES
