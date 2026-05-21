"""
Color palettes for the graph viewer.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Design choice: communities are the *primary* visual organizer (clusters carry
the story), so the community palette gets saturated jewel tones for high
distinguishability. Entity type is a *secondary* signal — its palette is more
desaturated and coordinated, so when you flip to "Color by type" it doesn't
shout.

All colors are tuned for a dark background.
"""
from __future__ import annotations

import hashlib
from typing import Iterable


# ── Node-kind palette ─────────────────────────────────────────────────────
# Mirrors the Neo4j label model: Document / Chunk / Entity / Community / Finding.
# Each kind has its own color so that when multiple layers are visible at once,
# the user can read "what is this?" before "what is it about?".
#
# Entities deliberately don't have a kind color — they take their color from
# either their community (default) or their entity type.
KIND_PALETTE: dict[str, str] = {
    "document":  "#d8c474",  # warm gold — anchor at the outer ring
    "chunk":     "#7a8499",  # cool slate — secondary structural node
    "entity":    "#a78bfa",  # placeholder; overridden by community/type
    "community": "#6366f1",  # placeholder; overridden by per-community color
    "finding":   "#94a3b8",  # neutral grey — leaves under a community
}


# ── Entity-type palette (secondary signal — quieter, coordinated) ─────────
# Single-saturation muted family. Adjacent types in the medical pipeline
# (disease → symptom → biomarker → treatment → drug) get adjacent hues so the
# rainbow effect is smoother.
DEFAULT_TYPE_PALETTE: dict[str, str] = {
    "PERSON":             "#9ca8c4",  # cool grey-blue
    "ORGANIZATION":       "#7a90b8",  # steel blue
    "DISEASE":            "#e07a7a",  # muted coral
    "SYMPTOM":            "#e0a070",  # muted orange
    "BIOMARKER":          "#d896b8",  # muted rose
    "TREATMENT":          "#7ac49a",  # muted emerald
    "DRUG":               "#7abfc4",  # muted teal
    "CLINICAL_STUDY":     "#a8a8a8",  # grey
    "GUIDELINE":          "#d8c474",  # muted gold
    "PATIENT_POPULATION": "#b89a78",  # muted tan
}

# Used for entity types not in the default palette.
FALLBACK_PALETTE: list[str] = [
    "#9ca8c4", "#7a90b8", "#e07a7a", "#e0a070",
    "#d896b8", "#7ac49a", "#7abfc4", "#a8a8a8",
    "#d8c474", "#b89a78", "#b894c4", "#c4a878",
    "#94c4b8", "#c478a0", "#7894c4", "#a8c478",
]

# ── Community palette (primary signal — vivid, distinct on dark bg) ───────
# Curated set inspired by D3 schemeCategory10 + ColorBrewer Set3, picked so
# adjacent values are perceptually distinct. 20 entries: most graphs won't have
# more communities than that; if they do, we wrap around.
COMMUNITY_PALETTE: list[str] = [
    "#6366f1",  # indigo-500
    "#ec4899",  # pink-500
    "#14b8a6",  # teal-500
    "#f59e0b",  # amber-500
    "#8b5cf6",  # violet-500
    "#06b6d4",  # cyan-500
    "#ef4444",  # red-500
    "#84cc16",  # lime-500
    "#f97316",  # orange-500
    "#3b82f6",  # blue-500
    "#a855f7",  # purple-500
    "#10b981",  # emerald-500
    "#eab308",  # yellow-500
    "#0ea5e9",  # sky-500
    "#d946ef",  # fuchsia-500
    "#22c55e",  # green-500
    "#f43f5e",  # rose-500
    "#0d9488",  # teal-600
    "#a3a3a3",  # neutral-400 (catch-all)
    "#7c3aed",  # violet-600
]


def build_type_palette(types: Iterable[str]) -> dict[str, str]:
    """Return a palette covering every type in ``types``.

    Known types resolve to their fixed color. Unknown types pull from
    :data:`FALLBACK_PALETTE` in deterministic (sorted) order.
    """
    palette = dict(DEFAULT_TYPE_PALETTE)
    unknown = sorted({t for t in types if t and t not in palette})
    for i, t in enumerate(unknown):
        palette[t] = FALLBACK_PALETTE[i % len(FALLBACK_PALETTE)]
    return palette


def build_community_palette(community_ids: Iterable) -> dict[str, str]:
    """Assign a stable color to each community id.

    Communities are sorted numerically when possible (so community ``0`` always
    gets the first palette entry), then alphabetically.
    """
    palette: dict[str, str] = {}
    raw = [str(c) for c in community_ids if c is not None and str(c) not in ("nan", "")]
    ids = sorted(set(raw), key=_community_sort_key)
    for i, cid in enumerate(ids):
        palette[cid] = COMMUNITY_PALETTE[i % len(COMMUNITY_PALETTE)]
    return palette


def _community_sort_key(cid: str) -> tuple[int, int | str]:
    """Numerics sort numerically, non-numerics sort alphabetically *after*."""
    try:
        return (0, int(cid))
    except ValueError:
        return (1, cid)


def hash_color(key: str, palette: list[str] = FALLBACK_PALETTE) -> str:
    """Deterministic color from an arbitrary string. Last-resort fallback."""
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return palette[h % len(palette)]
