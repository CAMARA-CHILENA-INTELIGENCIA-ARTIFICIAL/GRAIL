"""
Post-extraction entity deduplication.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Uses embedding cosine similarity to find candidate duplicate entities, then
an LLM judge to confirm or reject each candidate group. Confirmed duplicates
are merged: the canonical name is kept, descriptions and provenance are
combined, and all relationship references are updated.

Designed to run between the embedding step and the DataFrame-building step
in :class:`EntityRelationshipExtractor`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from grail.llm import LLMClient
from grail.prompts import PromptRegistry
from grail.prompts.builtin.entity_dedup import format_entity_groups
from grail.reporting import NullReporter, Reporter

log = logging.getLogger(__name__)

_DEDUP_RE = re.compile(r"<dedup_result>(.*?)</dedup_result>", re.S)


@dataclass
class MergeGroup:
    canonical_name: str
    canonical_original: str
    aliases: list[str]
    reason: str


async def find_duplicates(
    names: list[str],
    types: list[str],
    descriptions: list[str],
    embeddings: list[Optional[list[float]]],
    *,
    llm: LLMClient,
    prompts: PromptRegistry,
    similarity_threshold: float = 0.90,
    max_entities_per_call: int = 15,
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 16384,
    reporter: Reporter = field(default_factory=NullReporter),
) -> list[MergeGroup]:
    """Find and confirm duplicate entities via embedding similarity + LLM judge.

    Returns a list of :class:`MergeGroup` objects. Each group has a canonical
    name and a list of alias names that should be merged into it.
    """
    valid_indices, matrix = _build_embedding_matrix(embeddings)
    if matrix is None or len(valid_indices) < 2:
        return []

    candidate_pairs = _find_candidate_pairs(matrix, similarity_threshold)
    if not candidate_pairs:
        reporter.info("Entity dedup: no candidate pairs above threshold")
        return []

    components = _connected_components(candidate_pairs, len(valid_indices))
    multi = [c for c in components if len(c) > 1]
    if not multi:
        return []

    reporter.info(
        f"Entity dedup: {len(candidate_pairs)} candidate pairs in "
        f"{len(multi)} groups — sending to LLM judge"
    )

    groups_for_prompt: list[list[dict[str, str]]] = []
    group_index_maps: list[dict[int, int]] = []

    for component in multi:
        real_indices = [valid_indices[i] for i in component]
        group: list[dict[str, str]] = []
        idx_map: dict[int, int] = {}
        for local_idx, real_idx in enumerate(real_indices, 1):
            group.append({
                "index": str(local_idx),
                "name": names[real_idx],
                "type": types[real_idx],
                "description": descriptions[real_idx][:300],
            })
            idx_map[local_idx] = real_idx
        groups_for_prompt.append(group)
        group_index_maps.append(idx_map)

    batches = _batch_groups(groups_for_prompt, group_index_maps, max_entities_per_call)

    tasks = [
        _judge_batch(
            batch_groups, batch_maps, batch_offset,
            names=names,
            llm=llm,
            prompts=prompts,
            endpoint=endpoint,
            model=model,
            max_tokens=max_tokens,
        )
        for batch_groups, batch_maps, batch_offset in batches
    ]
    batch_results = await asyncio.gather(*tasks)
    all_merges: list[MergeGroup] = [m for batch in batch_results for m in batch]

    if all_merges:
        reporter.success(
            f"Entity dedup: {len(all_merges)} merge group(s) confirmed — "
            f"merging {sum(len(m.aliases) for m in all_merges)} duplicate(s)"
        )
    else:
        reporter.info("Entity dedup: LLM judge found no true duplicates")

    return all_merges


def apply_merges(
    entities: dict[str, Any],
    rels: dict[tuple[str, str, str], Any],
    merge_groups: list[MergeGroup],
) -> tuple[dict[str, Any], dict[tuple[str, str, str], Any]]:
    """Apply merge groups to entity and relationship dicts.

    ``entities`` is keyed by name; each value must have ``text_unit_ids``,
    ``document_ids``, and ``descriptions`` attributes (or be a dict with those
    keys). ``rels`` is keyed by ``(source, target, relationship_type)``
    tuples — typed edges between the same pair stay distinct after a merge.

    Returns the updated ``(entities, rels)`` dicts.
    """
    alias_to_canonical: dict[str, str] = {}
    for group in merge_groups:
        for alias in group.aliases:
            alias_to_canonical[alias] = group.canonical_name

    for group in merge_groups:
        canonical = group.canonical_name
        original = group.canonical_original

        if canonical != original and original in entities:
            entities[canonical] = entities.pop(original)
            ent = entities[canonical]
            ent.name = canonical

        if canonical not in entities:
            continue

        canon_ent = entities[canonical]
        for alias in group.aliases:
            if alias in entities:
                alias_ent = entities.pop(alias)
                canon_ent.text_unit_ids |= alias_ent.text_unit_ids
                canon_ent.document_ids |= alias_ent.document_ids
                if alias_ent.descriptions and (
                    not canon_ent.descriptions
                    or len(alias_ent.descriptions[0]) > len(canon_ent.descriptions[0])
                ):
                    canon_ent.descriptions = alias_ent.descriptions[:1]

    new_rels: dict[tuple[str, str, str], Any] = {}
    for old_key, rel in rels.items():
        # Support legacy 2-tuple callers (pair only) and the new 3-tuple form
        # (pair + relationship_type) without breaking callers mid-migration.
        if len(old_key) == 3:
            src, tgt, rel_type = old_key
        else:
            src, tgt = old_key
            rel_type = getattr(rel, "relationship_type", None) or "RELATED"
        new_src = alias_to_canonical.get(src, src)
        new_tgt = alias_to_canonical.get(tgt, tgt)

        if new_src == new_tgt:
            continue

        pair = tuple(sorted((new_src, new_tgt)))
        new_key = (pair[0], pair[1], rel_type)

        rel.source = pair[0]
        rel.target = pair[1]

        if new_key in new_rels:
            existing = new_rels[new_key]
            if len(rel.descriptions[0]) > len(existing.descriptions[0]):
                existing.descriptions = rel.descriptions[:1]
            existing.weights.extend(rel.weights)
            existing.text_unit_ids |= rel.text_unit_ids
            existing.document_ids |= rel.document_ids
        else:
            new_rels[new_key] = rel

    return entities, new_rels


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_embedding_matrix(
    embeddings: list[Optional[list[float]]],
) -> tuple[list[int], Optional[np.ndarray]]:
    """Return (valid_indices, normalized_matrix) for non-None embeddings."""
    valid: list[tuple[int, list[float]]] = []
    for i, emb in enumerate(embeddings):
        if emb is not None:
            valid.append((i, emb))
    if len(valid) < 2:
        return [i for i, _ in valid], None

    indices = [i for i, _ in valid]
    matrix = np.array([e for _, e in valid], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    matrix = matrix / norms
    return indices, matrix


def _find_candidate_pairs(
    normalized: np.ndarray,
    threshold: float,
) -> list[tuple[int, int]]:
    """Return pairs of matrix-row indices with cosine similarity >= threshold."""
    sim = normalized @ normalized.T
    np.fill_diagonal(sim, 0.0)
    rows, cols = np.where(sim >= threshold)
    return [(int(r), int(c)) for r, c in zip(rows, cols) if r < c]


def _connected_components(
    pairs: list[tuple[int, int]],
    n: int,
) -> list[list[int]]:
    """Find connected components from a list of edges via union-find."""
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values())


def _batch_groups(
    groups: list[list[dict[str, str]]],
    index_maps: list[dict[int, int]],
    max_entities: int,
) -> list[tuple[list[list[dict[str, str]]], list[dict[int, int]], int]]:
    """Split groups into batches that fit within max_entities per LLM call."""
    batches: list[tuple[list[list[dict[str, str]]], list[dict[int, int]], int]] = []
    current_groups: list[list[dict[str, str]]] = []
    current_maps: list[dict[int, int]] = []
    current_count = 0
    current_offset = 0

    for i, (group, idx_map) in enumerate(zip(groups, index_maps)):
        if current_count + len(group) > max_entities and current_groups:
            batches.append((current_groups, current_maps, current_offset))
            current_groups = []
            current_maps = []
            current_count = 0
            current_offset = i

        current_groups.append(group)
        current_maps.append(idx_map)
        current_count += len(group)

    if current_groups:
        batches.append((current_groups, current_maps, current_offset))

    return batches


async def _judge_batch(
    groups: list[list[dict[str, str]]],
    index_maps: list[dict[int, int]],
    group_offset: int,
    *,
    names: list[str],
    llm: LLMClient,
    prompts: PromptRegistry,
    endpoint: Optional[str],
    model: Optional[str],
    max_tokens: int,
) -> list[MergeGroup]:
    """Send one batch of candidate groups to the LLM judge and parse results."""
    entity_groups_text = format_entity_groups(groups)
    messages = prompts.build("entity_dedup", entity_groups=entity_groups_text)

    response = await llm.execute_safe(
        messages=messages,
        endpoint=endpoint,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        tag="entity_dedup",
    )
    if not response:
        return []

    return _parse_judge_response(response, groups, index_maps, group_offset, names)


def _parse_judge_response(
    response: str,
    groups: list[list[dict[str, str]]],
    index_maps: list[dict[int, int]],
    group_offset: int,
    names: list[str],
) -> list[MergeGroup]:
    """Parse the LLM judge response into MergeGroup objects."""
    m = _DEDUP_RE.search(response)
    if not m:
        text = response.strip()
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        else:
            return []
    else:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Entity dedup: failed to parse LLM judge response as JSON")
        return []

    if not isinstance(data, list):
        return []

    results: list[MergeGroup] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue

        group_num = int(entry.get("group", 1))
        local_group_idx = group_num - 1
        if local_group_idx < 0 or local_group_idx >= len(groups):
            continue

        idx_map = index_maps[local_group_idx]
        canonical_local = int(entry.get("canonical_index", 1))
        merge_locals = entry.get("merge_indices", [])
        canonical_name = str(entry.get("canonical_name", ""))

        if canonical_local not in idx_map:
            continue

        canonical_real = idx_map[canonical_local]
        canonical_original = names[canonical_real]
        if not canonical_name:
            canonical_name = canonical_original

        alias_names: list[str] = []
        for ml in merge_locals:
            ml_int = int(ml)
            if ml_int in idx_map and ml_int != canonical_local:
                alias_names.append(names[idx_map[ml_int]])

        if not alias_names:
            continue

        results.append(MergeGroup(
            canonical_name=canonical_name,
            canonical_original=canonical_original,
            aliases=alias_names,
            reason=str(entry.get("reason", "")),
        ))

    return results
