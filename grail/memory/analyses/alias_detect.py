"""
Alias detection — surface entities that look like the same thing under
different names.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Two signals:
  * Name-embedding cosine similarity (only when ``description_embedding`` is
    populated on both entities).
  * Jaro-Winkler edit-distance on the names (always available — no LLM, no
    embedding).

A proposal fires when either signal crosses the configured threshold. The
canonical name is chosen as the longer of the two (or the one with more
text_units when names tie in length).
"""
from __future__ import annotations

from itertools import combinations
from typing import Any, Optional

import numpy as np
import pandas as pd

from grail.config import MemoryConfig
from grail.memory.proposals import Proposal


class AliasDetect:
    name = "alias_detect"

    def propose(self, snapshot, config: MemoryConfig) -> list[Proposal]:
        ents = snapshot.entities
        if ents.empty or len(ents) < 2:
            return []

        proposals: list[Proposal] = []
        seen: set[frozenset[str]] = set()

        names = ents["name"].astype(str).tolist()
        types = ents["type"].astype(str).tolist() if "type" in ents.columns else [""] * len(names)
        embeddings: dict[str, np.ndarray] = {}
        if "description_embedding" in ents.columns:
            for _, row in ents.iterrows():
                emb = row.get("description_embedding")
                if emb is None or (isinstance(emb, float) and pd.isna(emb)):
                    continue
                try:
                    arr = np.asarray(list(emb), dtype=float)
                except (TypeError, ValueError):
                    continue
                if arr.size > 0:
                    embeddings[str(row["name"])] = arr

        tu_count: dict[str, int] = {}
        if "text_unit_ids" in ents.columns:
            for _, row in ents.iterrows():
                tus = row.get("text_unit_ids")
                tu_count[str(row["name"])] = len(_aslist(tus))

        for (i, n1), (j, n2) in combinations(enumerate(names), 2):
            if types[i] and types[j] and types[i] != types[j]:
                # Only consider merges within the same type.
                continue
            pair = frozenset((n1, n2))
            if pair in seen:
                continue

            jw = _jaro_winkler(n1.upper(), n2.upper())
            cosine: Optional[float] = None
            if n1 in embeddings and n2 in embeddings:
                cosine = float(_cosine(embeddings[n1], embeddings[n2]))

            jw_hit = jw >= config.alias_min_jaro_winkler
            emb_hit = cosine is not None and cosine >= config.alias_min_embedding_cosine
            if not (jw_hit or emb_hit):
                continue
            seen.add(pair)

            # Canonical name: prefer the one with more text_units, then the
            # longer name, then the lexically first.
            scores = {
                n1: (tu_count.get(n1, 0), len(n1), -names.index(n1)),
                n2: (tu_count.get(n2, 0), len(n2), -names.index(n2)),
            }
            canonical = max(scores, key=lambda k: scores[k])
            alias = n2 if canonical == n1 else n1

            confidence = max(jw, cosine if cosine is not None else 0.0)
            method = []
            if jw_hit:
                method.append(f"jaro_winkler={jw:.3f}")
            if emb_hit and cosine is not None:
                method.append(f"embedding_cosine={cosine:.3f}")

            rationale = (
                f"{n1} and {n2} look like aliases ({', '.join(method)}). "
                f"Suggested canonical: {canonical}. "
                "Accepting will merge text_units, document_ids, and rewrite "
                "relationship endpoints to the canonical name."
            )

            proposals.append(
                Proposal.fresh(
                    kind="merge_aliases",
                    rationale=rationale,
                    confidence=confidence,
                    payload={
                        "canonical": canonical,
                        "aliases": [alias],
                    },
                    evidence={
                        "jaro_winkler": float(jw),
                        "embedding_cosine": float(cosine) if cosine is not None else None,
                        "tu_count": {
                            canonical: tu_count.get(canonical, 0),
                            alias: tu_count.get(alias, 0),
                        },
                    },
                )
            )
        return proposals


def _aslist(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if hasattr(value, "tolist"):
        return list(value.tolist())
    return [value]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _jaro_winkler(s1: str, s2: str) -> float:
    """Inline copy of the helper in ``grail.memory.project``.

    Duplicated here to keep the analyses package free of cyclic imports.
    """
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    match_distance = max(len(s1), len(s2)) // 2 - 1
    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0
    for i, c in enumerate(s1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len(s2))
        for j in range(start, end):
            if s2_matches[j] or s2[j] != c:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    t = 0
    k = 0
    for i, c in enumerate(s1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if c != s2[k]:
            t += 1
        k += 1
    t /= 2
    jaro = (matches / len(s1) + matches / len(s2) + (matches - t) / matches) / 3
    prefix = 0
    for c1, c2 in zip(s1, s2):
        if c1 != c2:
            break
        prefix += 1
        if prefix == 4:
            break
    return jaro + prefix * 0.1 * (1 - jaro)


__all__ = ["AliasDetect"]
