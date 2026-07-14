"""
Pluggable file handlers — teach GRAIL to ingest arbitrary formats.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

GRAIL's built-in pipeline reads text/code/data files directly and converts
PDF/DOCX via :mod:`grail.indexing.preprocess`. Anything else is unknown. A
**handler** lets a user (or the SDK) register custom Python logic for any
extension — a plain function, a pandas profiler, or an LLM-driven "agentic"
describe loop — without forking the library.

Two output protocols, picked per handler:

* **describe** (default) — ``async describe(source, ctx) -> str`` returns
  markdown/plain text. The output is written to ``input/_processed/<stem>.md``
  and flows through the normal chunk → LLM-extract → graph pipeline, exactly
  like a PDF. Inspectable and cache-aware.

* **emit** (opt-in) — ``async emit(source, ctx) -> EmitResult`` returns
  deterministic entities + relationships, bypassing LLM extraction. Cheap,
  precise, and reproducible. The merge code synthesises a Document + TextUnit
  for citation provenance and embeds the descriptions; the user only returns
  plain :class:`EmitEntity` / :class:`EmitRelationship` records.

Registration mirrors the prompt system (:class:`grail.prompts.loader.PromptRegistry`):
point ``handlers.custom_paths`` at a directory of ``.py`` files, each exposing
``HANDLER`` (an instance) or ``HANDLERS`` (a list of instances). The SDK can
also register handlers in-process via :meth:`GRAIL.register_handler`.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from grail.config import Config

log = logging.getLogger(__name__)


class UnhandledFileError(RuntimeError):
    """Raised when ``input/`` holds files no reader or handler claims and the
    ``handlers.on_unhandled`` policy is ``error`` (the default)."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = list(keys)
        shown = ", ".join(self.keys[:8]) + ("…" if len(self.keys) > 8 else "")
        super().__init__(
            f"{len(self.keys)} input file(s) have no handler: {shown}. "
            "Register a handler (handlers.custom_paths in grail.yaml) for the "
            "extension(s), or set handlers.on_unhandled to 'warn' or 'skip' to "
            "ignore them."
        )


# ----------------------------------------------------------------------- context


@dataclass
class HandlerContext:
    """Collaborators handed to a handler at run time.

    A *pure* handler ignores all of this. An *agentic* handler uses ``llm`` (and
    optionally ``prompts``) to summarise / describe its input. Embeddings are
    available for handlers that want to compute their own vectors, though the
    emit-merge path embeds descriptions for you.
    """

    llm: Any = None
    embeddings: Any = None
    config: "Optional[Config]" = None
    prompts: Any = None
    reporter: Any = None


# ----------------------------------------------------------------------- emit records


@dataclass
class EmitEntity:
    """A graph node produced deterministically by a handler.

    The merge code assigns the GUID, embeds ``description``, and attaches the
    synthetic text-unit / document provenance — callers only supply semantics.
    """

    name: str
    type: str = "ENTITY"
    description: str = ""
    retrieval_queries: list[str] = field(default_factory=list)


@dataclass
class EmitRelationship:
    """A graph edge produced deterministically by a handler."""

    source: str
    target: str
    description: str = ""
    type: str = "RELATED"
    weight: float = 1.0


@dataclass
class EmitResult:
    """What an ``emit`` handler returns for one source file."""

    entities: list[EmitEntity] = field(default_factory=list)
    relationships: list[EmitRelationship] = field(default_factory=list)
    # Optional human-readable text. Becomes the synthetic TextUnit body so
    # search can cite *something* concrete; falls back to a generated stub.
    text: Optional[str] = None


# ----------------------------------------------------------------------- interface


class FileHandler(ABC):
    """Base class for a custom file handler.

    Subclasses set ``NAME`` and ``EXTENSIONS`` and override **exactly one** of
    :meth:`describe` or :meth:`emit`. The overridden method determines the
    handler's :attr:`mode`.
    """

    NAME: str = ""
    EXTENSIONS: frozenset[str] = frozenset()

    async def describe(self, source: Path, ctx: HandlerContext) -> str:
        """Return markdown/plain text for the normal indexing pipeline."""
        raise NotImplementedError

    async def emit(self, source: Path, ctx: HandlerContext) -> EmitResult:
        """Return deterministic entities + relationships (bypasses LLM extraction)."""
        raise NotImplementedError

    @property
    def mode(self) -> str:
        """``"describe"`` or ``"emit"`` — auto-detected from the override."""
        cls = type(self)
        describes = cls.describe is not FileHandler.describe
        emits = cls.emit is not FileHandler.emit
        if describes and emits:
            raise TypeError(
                f"Handler {self.NAME!r} overrides both describe() and emit(); "
                "implement exactly one so the mode is unambiguous."
            )
        if emits:
            return "emit"
        if describes:
            return "describe"
        raise TypeError(
            f"Handler {self.NAME!r} overrides neither describe() nor emit(). "
            "Implement one of them."
        )

    def normalised_extensions(self) -> frozenset[str]:
        """Lower-cased, dot-prefixed extension set."""
        out = set()
        for ext in self.EXTENSIONS:
            e = ext.lower()
            out.add(e if e.startswith(".") else "." + e)
        return frozenset(out)


class FunctionHandler(FileHandler):
    """Wrap a plain ``(Path) -> str`` callable as a describe-mode handler.

    Convenience for the common case of a synchronous, LLM-free converter::

        HANDLER = FunctionHandler(
            name="csv_describe",
            extensions={".csv"},
            fn=lambda path: my_describe(path),
        )
    """

    def __init__(
        self,
        *,
        name: str,
        extensions: set[str] | frozenset[str],
        fn: Callable[[Path], str],
    ) -> None:
        self.NAME = name
        self.EXTENSIONS = frozenset(extensions)
        self._fn = fn

    async def describe(self, source: Path, ctx: HandlerContext) -> str:  # noqa: D102
        return self._fn(source)


# ----------------------------------------------------------------------- loading


def _load_module_from_path(path: Path) -> Any:
    """Import a single ``.py`` file under a unique module name."""
    spec = importlib.util.spec_from_file_location(
        f"grail_handlers_custom.{path.stem}", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load handler module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _handlers_from_module(module: Any, *, source: str) -> list[FileHandler]:
    found: list[FileHandler] = []
    if hasattr(module, "HANDLERS"):
        candidates = list(module.HANDLERS)
    elif hasattr(module, "HANDLER"):
        candidates = [module.HANDLER]
    else:
        raise AttributeError(
            f"Handler module at {source} exposes neither HANDLER nor HANDLERS. "
            "Define HANDLER = MyHandler() or HANDLERS = [MyHandler(), ...]."
        )
    for h in candidates:
        if not isinstance(h, FileHandler):
            raise TypeError(
                f"{source}: {h!r} is not a FileHandler instance."
            )
        if not h.NAME:
            raise ValueError(f"{source}: handler is missing a NAME.")
        if not h.normalised_extensions():
            raise ValueError(f"{source}: handler {h.NAME!r} declares no EXTENSIONS.")
        # Validates mode (raises if neither/both overridden).
        _ = h.mode
        found.append(h)
    return found


# ----------------------------------------------------------------------- registry


@dataclass
class HandlerRegistry:
    """Resolve custom file handlers by extension.

    Loads ``*.py`` modules from ``custom_paths`` and builds an extension → handler
    map. Programmatic handlers can be added with :meth:`register`. Built-in
    PDF/DOCX/text formats are **not** owned here — the loader resolves those
    first; the registry only covers user-supplied formats.
    """

    custom_paths: list[Path] = field(default_factory=list)

    _by_ext: dict[str, FileHandler] = field(default_factory=dict, init=False, repr=False)
    _by_name: dict[str, FileHandler] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.custom_paths = [Path(p) for p in self.custom_paths]
        for p in self.custom_paths:
            if not p.exists() or not p.is_dir():
                raise FileNotFoundError(f"Handlers directory does not exist: {p}")
            for py in sorted(p.glob("*.py")):
                if py.stem.startswith("_"):
                    continue
                module = _load_module_from_path(py)
                for handler in _handlers_from_module(module, source=str(py)):
                    self.register(handler)

    # ------------------------------------------------------------------ mutation

    def register(self, handler: FileHandler) -> None:
        """Add a handler. Extension collisions raise (last-loaded would shadow)."""
        if not isinstance(handler, FileHandler):
            raise TypeError(f"{handler!r} is not a FileHandler.")
        _ = handler.mode  # validate
        for ext in handler.normalised_extensions():
            existing = self._by_ext.get(ext)
            if existing is not None and existing.NAME != handler.NAME:
                raise ValueError(
                    f"Extension '{ext}' is claimed by both handlers "
                    f"{existing.NAME!r} and {handler.NAME!r}. Each extension may "
                    "be owned by only one handler."
                )
            self._by_ext[ext] = handler
        self._by_name[handler.NAME] = handler

    # ------------------------------------------------------------------ resolution

    def resolve(self, extension: str) -> Optional[FileHandler]:
        """Return the handler that claims ``extension`` (custom only), or None."""
        ext = extension.lower()
        if not ext.startswith("."):
            ext = "." + ext
        return self._by_ext.get(ext)

    def is_handled(self, extension: str) -> bool:
        return self.resolve(extension) is not None

    def extensions(self) -> frozenset[str]:
        """All extensions claimed by custom handlers."""
        return frozenset(self._by_ext)

    def list_handlers(self) -> list[dict[str, Any]]:
        """Serialisable view for the CLI / MCP."""
        out: list[dict[str, Any]] = []
        for name, handler in sorted(self._by_name.items()):
            out.append(
                {
                    "name": name,
                    "extensions": sorted(handler.normalised_extensions()),
                    "mode": handler.mode,
                }
            )
        return out
