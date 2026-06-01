"""
``RecallFilter`` — temporal / structural pre-filter for any search mode.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

A ``RecallFilter`` carries the user's "WHERE clause" — date range, folder /
tag, entity name + type, confidence threshold. It exposes pandas mask methods
that any search builder can apply to its candidate pool *before* the
expensive scoring (cosine, BM25, LLM) runs.

It is also the input to the standalone ``RecallSearch`` peer mode, which
returns matching observations + entities as a SearchResult with no LLM call
at all — useful for "what did I observe in the last hour?" queries.

Time comparisons are lexical (ISO-8601 strings sort correctly). ``category``
uses fnmatch globs (``work/clients/**``). ``tags`` matches when *any* of the
provided tags appears in the document's tag list.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd


# Relative-time tokens we accept on the CLI / SDK: "1h", "7d", "2 weeks ago".
_RELATIVE_RE = re.compile(
    r"^(?:(\d+(?:\.\d+)?)\s*"
    r"(s|sec|secs|second|seconds|"
    r"m|min|mins|minute|minutes|"
    r"h|hr|hrs|hour|hours|"
    r"d|day|days|"
    r"w|week|weeks|"
    r"mo|month|months|"
    r"y|yr|yrs|year|years)"
    r"(?:\s+ago)?|now)$",
    re.IGNORECASE,
)
_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
    "mo": 2_592_000, "month": 2_592_000, "months": 2_592_000,
    "y": 31_536_000, "yr": 31_536_000, "yrs": 31_536_000,
    "year": 31_536_000, "years": 31_536_000,
}


def normalize_time(value: Optional[str], *, now: Optional[datetime] = None) -> Optional[str]:
    """Normalise a user-supplied time spec to an ISO-8601 string.

    Accepts:
      * absolute ISO-8601 (``2026-05-30T10:00:00Z``) — returned as-is.
      * relative (``1h``, ``7d``, ``2 weeks ago``, ``now``) — converted to
        an absolute timestamp relative to ``now`` (defaults to ``utcnow()``).
      * ``None`` → ``None``.
    """
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    m = _RELATIVE_RE.match(s)
    if m is None:
        return s  # assume absolute ISO-8601
    if s.lower() == "now":
        return (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
    qty = float(m.group(1))
    unit = m.group(2).lower()
    secs = qty * _UNIT_SECONDS[unit]
    ref = now or datetime.now(timezone.utc)
    moment = ref - timedelta(seconds=secs)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class RecallFilter:
    """Temporal / structural filter that composes with any search mode.

    All fields default to ``None`` (no filter). Multiple filters AND together.
    Use ``RecallFilter.is_empty()`` to detect a no-op filter.
    """

    since: Optional[str] = None
    before: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    entity_names: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    min_confidence: Optional[float] = None

    def __post_init__(self) -> None:
        # Normalise relative times so downstream comparisons are absolute.
        self.since = normalize_time(self.since)
        self.before = normalize_time(self.before)
        self.entity_names = [n.upper().strip() for n in self.entity_names if n]
        self.entity_types = [t.upper().strip() for t in self.entity_types if t]
        self.tags = [str(t) for t in self.tags if str(t)]

    def is_empty(self) -> bool:
        return (
            self.since is None
            and self.before is None
            and self.category is None
            and not self.tags
            and not self.entity_names
            and not self.entity_types
            and self.min_confidence is None
        )

    # ------------------------------------------------------------------ masks

    def applies_to_text_units(self, df: pd.DataFrame) -> pd.Series:
        """Boolean mask selecting rows of ``df`` (text_units) that pass the filter.

        Pure temporal / confidence filter — ``category`` and ``tags`` live on
        ``documents``, so use ``applies_to_documents`` first and intersect on
        ``document_id`` if you need them combined.
        """
        if df.empty:
            return pd.Series([], dtype=bool)
        mask = pd.Series(True, index=df.index)
        if self.since is not None and "observed_at" in df.columns:
            mask &= df["observed_at"].fillna("").astype(str) >= self.since
        if self.before is not None and "observed_at" in df.columns:
            mask &= df["observed_at"].fillna("").astype(str) < self.before
        if self.min_confidence is not None and "confidence" in df.columns:
            mask &= df["confidence"].fillna(1.0).astype(float) >= self.min_confidence
        return mask

    def applies_to_entities(self, df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series([], dtype=bool)
        mask = pd.Series(True, index=df.index)
        if self.since is not None and "observed_at" in df.columns:
            mask &= df["observed_at"].fillna("").astype(str) >= self.since
        if self.before is not None and "observed_at" in df.columns:
            mask &= df["observed_at"].fillna("").astype(str) < self.before
        if self.min_confidence is not None and "confidence" in df.columns:
            mask &= df["confidence"].fillna(1.0).astype(float) >= self.min_confidence
        if self.entity_names and "name" in df.columns:
            allowed = set(self.entity_names)
            mask &= df["name"].str.upper().isin(allowed)
        if self.entity_types and "type" in df.columns:
            allowed_types = set(self.entity_types)
            mask &= df["type"].str.upper().isin(allowed_types)
        if self.category and "community_ids" in df.columns:
            mask &= df["community_ids"].apply(
                lambda cids: _category_matches_any(self.category, cids)
            )
        return mask

    def applies_to_documents(self, df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series([], dtype=bool)
        mask = pd.Series(True, index=df.index)
        if self.category and "category" in df.columns:
            mask &= df["category"].apply(
                lambda v: _category_matches(self.category, v)
            )
        if self.tags and "tags" in df.columns:
            wanted = set(self.tags)
            mask &= df["tags"].apply(
                lambda x: bool(wanted & set(_iter_tags(x)))
            )
        if self.since is not None and "observed_at" in df.columns:
            mask &= df["observed_at"].fillna("").astype(str) >= self.since
        if self.before is not None and "observed_at" in df.columns:
            mask &= df["observed_at"].fillna("").astype(str) < self.before
        if self.min_confidence is not None and "confidence" in df.columns:
            mask &= df["confidence"].fillna(1.0).astype(float) >= self.min_confidence
        return mask

    # ------------------------------------------------------------------ helpers

    def candidate_text_unit_ids(
        self,
        text_units: pd.DataFrame,
        documents: Optional[pd.DataFrame] = None,
    ) -> Optional[set[str]]:
        """Return the set of TU ids that pass *all* applicable filters.

        ``None`` means "no filter active for text units" — callers should
        treat that as "don't restrict the candidate pool". An empty set
        means the filter is active but matched nothing.
        """
        if self.is_empty():
            return None
        if text_units.empty:
            return set()
        mask = self.applies_to_text_units(text_units)
        # Bring documents into the equation when category/tags apply.
        if documents is not None and not documents.empty and (self.category or self.tags):
            doc_mask = self.applies_to_documents(documents)
            allowed_doc_ids = set(documents.loc[doc_mask, "id"].astype(str))
            if "document_id" in text_units.columns:
                mask &= text_units["document_id"].astype(str).isin(allowed_doc_ids)
            elif "document_ids" in text_units.columns:
                mask &= text_units["document_ids"].apply(
                    lambda x: any(str(d) in allowed_doc_ids for d in _iter_tags(x))
                )
        return set(text_units.loc[mask, "id"].astype(str))

    def candidate_entity_names(
        self,
        entities: pd.DataFrame,
    ) -> Optional[set[str]]:
        if self.is_empty():
            return None
        if entities.empty:
            return set()
        mask = self.applies_to_entities(entities)
        return set(entities.loc[mask, "name"].astype(str))

    def apply_to_artifacts(self, artifacts):  # type: ignore[no-untyped-def]
        """Return a copy of ``SearchArtifacts`` with the filter applied.

        Designed for the "modifier" use case — ``LocalSearch`` / ``CascadeSearch``
        call this at the top of ``asearch`` so the rest of their logic sees
        an already-restricted candidate pool. No-op when the filter is empty.

        Imported lazily to avoid a circular import with ``query.retrieval``.
        """
        from grail.query.retrieval import SearchArtifacts

        if self.is_empty():
            return artifacts
        ents = artifacts.entities
        docs = artifacts.documents
        tus = artifacts.text_units
        rels = artifacts.relationships

        ent_names: Optional[set[str]] = None
        if not ents.empty:
            mask = self.applies_to_entities(ents)
            ents = ents.loc[mask].copy()
            ent_names = set(ents["name"].astype(str)) if not ents.empty else set()
        if not docs.empty and (
            self.category
            or self.tags
            or self.since
            or self.before
            or self.min_confidence is not None
        ):
            doc_mask = self.applies_to_documents(docs)
            docs = docs.loc[doc_mask].copy()
        if not tus.empty:
            allowed_tu_ids = self.candidate_text_unit_ids(tus, artifacts.documents)
            if allowed_tu_ids is not None:
                tus = tus[tus["id"].astype(str).isin(allowed_tu_ids)].copy()
        if not rels.empty and ent_names is not None:
            rels = rels[
                rels["source"].isin(ent_names) & rels["target"].isin(ent_names)
            ].copy()
        return SearchArtifacts(
            entities=ents,
            relationships=rels,
            text_units=tus,
            nodes=artifacts.nodes,
            communities=artifacts.communities,
            community_reports=artifacts.community_reports,
            documents=docs,
            mapping=artifacts.mapping,
        )


# ---------------------------------------------------------------- helpers


def _category_matches(pattern: str, value: Optional[str]) -> bool:
    if not value:
        return False
    v = str(value)
    if v == pattern:
        return True
    if fnmatch.fnmatch(v, pattern):
        return True
    # ``work`` (no trailing /**) should match ``work/clients/acme`` too.
    return v.startswith(pattern.rstrip("/*") + "/") or v.startswith(pattern + "/")


def _category_matches_any(pattern: str, cids: Any) -> bool:
    for cid in _iter_tags(cids):
        if _category_matches(pattern, str(cid)):
            return True
    return False


def _iter_tags(value: Any) -> list[str]:
    """Coerce a possibly-None / possibly-numpy-array tag column into a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    # numpy arrays + pandas Series both have ``tolist``.
    if hasattr(value, "tolist"):
        try:
            return [str(v) for v in value.tolist()]
        except (TypeError, ValueError):
            return []
    if isinstance(value, str):
        return [value]
    return [str(value)]


__all__ = ["RecallFilter", "normalize_time"]
