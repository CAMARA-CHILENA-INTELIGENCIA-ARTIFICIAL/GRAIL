"""
GRAIL — Graph RAG with Advanced Integration and Learning.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Public surface re-exports the most common entry points so users can do::

    from grail import GRAIL, LLMClient, EmbeddingClient
    from grail import load_config, PromptRegistry
"""
from grail._version import __version__
from grail.config import Config, load_config
from grail.llm import EmbeddingClient, LLMClient
from grail.prompts import PromptRegistry
from grail.schemas import (
    Community,
    CommunityReport,
    Covariate,
    Document,
    Entity,
    Relationship,
    SearchResult,
    TextUnit,
)

__all__ = [
    "Community",
    "CommunityReport",
    "Config",
    "Covariate",
    "Document",
    "EmbeddingClient",
    "Entity",
    "LLMClient",
    "PromptRegistry",
    "Relationship",
    "SearchResult",
    "TextUnit",
    "__version__",
    "load_config",
]
