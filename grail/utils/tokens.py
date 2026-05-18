"""Token counting (tiktoken-based).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=8)
def _encoding(name: str) -> tiktoken.Encoding:
    try:
        return tiktoken.get_encoding(name)
    except (ValueError, KeyError):
        return tiktoken.get_encoding("cl100k_base")


def tiktoken_len(text: str, encoding_name: str = "cl100k_base") -> int:
    """Return the token count of ``text`` using the given tiktoken encoding."""
    if not text:
        return 0
    return len(_encoding(encoding_name).encode(text, disallowed_special=()))


def get_encoding(name: str = "cl100k_base") -> tiktoken.Encoding:
    """Cached accessor for a tiktoken encoding."""
    return _encoding(name)
