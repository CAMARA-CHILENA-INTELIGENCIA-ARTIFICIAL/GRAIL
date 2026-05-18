"""Stable identifier generation.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import hashlib
import uuid


def generate_guid() -> str:
    """Return a random UUID4 as a string. Used wherever the legacy code did the same."""
    return str(uuid.uuid4())


def stable_id_from_text(text: str, *, prefix: str = "") -> str:
    """Deterministic hash-based id, useful for de-duplicating chunks across reruns."""
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:24]
    return f"{prefix}{digest}" if prefix else digest
