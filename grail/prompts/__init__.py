"""Prompt registry and builder API.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Every GRAIL prompt is a Python module that exposes:

* ``NAME: str`` — registry key.
* ``REQUIRED_PARAMS: list[str]`` — names that must be supplied to :func:`build_messages`.
* ``build_messages(**params) -> list[dict]`` — returns an OpenAI-compatible messages array.
* Optional module-level constants (delimiters, JSON schemas, etc.) read by downstream parsers.

Built-in prompts live in :mod:`grail.prompts.builtin`. To override one, drop a file with
the same ``NAME`` into a custom directory and pass that directory to :class:`PromptRegistry`.
"""
from grail.prompts.loader import (
    BUILTIN_PROMPT_NAMES,
    PromptModule,
    PromptRegistry,
)

__all__ = [
    "BUILTIN_PROMPT_NAMES",
    "PromptModule",
    "PromptRegistry",
]
