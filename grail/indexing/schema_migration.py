"""
Lazy in-memory migration of parquet artefacts.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Phase A of memory mode added columns to the canonical parquet schemas.
Existing KB projects on disk pre-date these columns. Rather than rewrite
every project on first read, we fill the missing columns with sensible
defaults in memory — read code stays unchanged, no migration command needed.

A future ``grail migrate`` command can persist these defaults to disk so old
projects gain the columns permanently, but it is opt-in.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd


# Per-table default factories. Each entry maps a column name to a callable
# that produces the per-row default (called with no args). Lists/dicts need
# fresh instances per row so multiple rows don't share a mutable default.
_DEFAULTS: dict[str, dict[str, Callable[[], Any]]] = {
    "final_entities": {
        "community_ids": list,
        "observed_at": lambda: None,
        "confidence": lambda: 1.0,
        "source": lambda: None,
    },
    "final_relationships": {
        "relationship_type": lambda: "RELATED",
        "observed_at": lambda: None,
        "confidence": lambda: 1.0,
        # Provenance attribution ("agent-claude", "llm", ...). Renamed from
        # ``source`` to avoid colliding with the endpoint-name ``source`` column.
        "source_attribution": lambda: None,
    },
    "final_text_units": {
        "observed_at": lambda: None,
        "confidence": lambda: 1.0,
        "source": lambda: None,
    },
    "final_docs": {
        "category": lambda: None,
        "tags": list,
        "attributes": lambda: None,
        "observed_at": lambda: None,
        "confidence": lambda: 1.0,
        "source": lambda: None,
    },
    "final_communities": {
        "kind": lambda: "leiden",
    },
    "final_community_reports": {
        "source": lambda: "llm",
        "source_path": lambda: None,
    },
}


def migrate_dataframe(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Return ``df`` with any missing schema columns filled with defaults.

    ``table`` is the parquet basename without extension
    (e.g. ``"final_entities"``). Unknown tables are returned unchanged.
    The original DataFrame is never mutated — a shallow copy is taken when
    columns need to be added.

    The ``relationship_type`` column is a special case: if the legacy
    ``type`` column exists, its values are carried over before adding the
    default. This is what makes the rename invisible to old projects.
    """
    spec = _DEFAULTS.get(table)
    if spec is None:
        return df
    if df.empty:
        # Still add columns so downstream code can rely on their existence.
        out = df.copy()
        for col in spec:
            if col not in out.columns:
                out[col] = pd.Series(dtype="object")
        return out

    out = df
    copied = False
    for col, factory in spec.items():
        if col in out.columns:
            continue
        if not copied:
            out = out.copy()
            copied = True
        # Special-case the rename: carry ``type`` → ``relationship_type``
        # when an old relationships parquet is being read.
        if (
            table == "final_relationships"
            and col == "relationship_type"
            and "type" in out.columns
        ):
            out[col] = out["type"].fillna("RELATED")
        else:
            out[col] = [factory() for _ in range(len(out))]
    return out


def needs_migration(df: pd.DataFrame, table: str) -> bool:
    """Cheap probe: does ``df`` have all expected columns for ``table``?"""
    spec = _DEFAULTS.get(table)
    if spec is None:
        return False
    return any(col not in df.columns for col in spec)


__all__ = ["migrate_dataframe", "needs_migration"]
