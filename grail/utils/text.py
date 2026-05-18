"""Lightweight content-type detection from a path or file extension.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This is intentionally simple — the indexing pipeline only needs a rough bucket
(``text``, ``code``, ``data``, ``image``, ``audio``, ``video``, ``office``, ``unknown``)
to choose extraction strategy. For finer-grained MIME detection use ``python-magic``
externally.
"""
from __future__ import annotations

from pathlib import Path

_TEXT = {".txt", ".md", ".markdown", ".rst", ".log", ".srt", ".vtt"}
_CODE = {
    ".py", ".ipynb", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb", ".php",
    ".java", ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".scala",
    ".sh", ".bash", ".zsh", ".sql", ".html", ".css", ".scss", ".vue",
}
_DATA = {".json", ".jsonl", ".yaml", ".yml", ".toml", ".csv", ".tsv", ".xml", ".parquet"}
_OFFICE = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".ods", ".odp", ".pdf"}
_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}
_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def detect_data_type(path: str | Path) -> str:
    """Return one of: text, code, data, office, image, audio, video, unknown."""
    suffix = Path(path).suffix.lower()
    if suffix in _TEXT:
        return "text"
    if suffix in _CODE:
        return "code"
    if suffix in _DATA:
        return "data"
    if suffix in _OFFICE:
        return "office"
    if suffix in _IMAGE:
        return "image"
    if suffix in _AUDIO:
        return "audio"
    if suffix in _VIDEO:
        return "video"
    return "unknown"
