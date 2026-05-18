"""Token-aware text splitter.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Open-source replacement for the proprietary ``TokenTextSplitter``. Splits text into
chunks of at most ``chunk_size`` tokens with ``chunk_overlap`` tokens of overlap.
Uses tiktoken under the hood; the encoding is configurable so callers can match
their target model.
"""
from __future__ import annotations

from dataclasses import dataclass

from grail.utils.tokens import get_encoding


@dataclass
class TokenTextSplitter:
    chunk_size: int = 2000
    chunk_overlap: int = 50
    encoding_name: str = "cl100k_base"

    def __post_init__(self) -> None:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self._enc = get_encoding(self.encoding_name)

    def split_text(self, text: str) -> list[str]:
        if not text:
            return []
        ids = self._enc.encode(text, disallowed_special=())
        if len(ids) <= self.chunk_size:
            return [text]

        step = self.chunk_size - self.chunk_overlap
        chunks: list[str] = []
        for start in range(0, len(ids), step):
            end = min(start + self.chunk_size, len(ids))
            chunks.append(self._enc.decode(ids[start:end]))
            if end == len(ids):
                break
        return chunks

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._enc.encode(text, disallowed_special=()))
