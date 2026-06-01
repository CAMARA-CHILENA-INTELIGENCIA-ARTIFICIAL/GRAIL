"""
``RecallSearch`` — the no-LLM temporal / structural search peer mode.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

``recall`` is to the other search modes what ``WHERE`` is to SQL: it returns
the matching observations + entities directly, with no LLM call and no
embedding pass. Useful when the user wants "what did I observe in the last
hour" / "everything tagged 'pricing' under work/clients/**" — pure structural
slicing of the corpus.

It composes with the other modes via :class:`grail.query.recall_filter.RecallFilter`:
* Standalone (``--mode recall``): this class.
* Modifier (``--mode cascade --since 1h``): pass a ``RecallFilter`` into the
  cascade / local / document search ``asearch`` call; they pre-filter their
  candidate pool before the expensive scoring runs.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from grail.query.recall_filter import RecallFilter, _iter_tags
from grail.query.retrieval import SearchArtifacts, load_artifacts_for_search
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import StorageBackend


@dataclass
class RecallSearch:
    """Standalone temporal / structural search.

    No LLM, no embedding. Returns the matching rows as ``context_data``
    DataFrames and a compact text rendering as ``context_text`` / ``response``
    for the agent to consume.
    """

    storage: StorageBackend
    artifacts: Optional[SearchArtifacts] = None
    output_folder: str = "output"
    max_results: int = 200
    reporter: Reporter = field(default_factory=NullReporter)

    async def asearch(
        self,
        filter: RecallFilter,
        *,
        query: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> SearchResult:
        """Apply ``filter`` to the indexed artefacts and return matches.

        ``query`` is accepted for API parity with the other search modes but
        is *not* used (recall is structural-only). To combine a natural-
        language query with recall filters, use a different mode and pass
        the filter as a modifier instead.
        """
        started = time.perf_counter()
        artifacts = self.artifacts or load_artifacts_for_search(self.storage, self.output_folder)

        if artifacts.entities.empty and artifacts.text_units.empty:
            return SearchResult(
                response="No indexed data was found. Run `grail index` first.",
                context_data={},
                context_text="",
                completion_time=time.perf_counter() - started,
                llm_calls=0,
            )

        # KB projects without ``observed_at`` get a graceful warning surfaced
        # in the response text; the filter still runs and returns whatever
        # it can match on category / tag / entity name / type.
        warnings: list[str] = []
        if (
            (filter.since or filter.before)
            and "observed_at" in artifacts.text_units.columns
            and artifacts.text_units["observed_at"].isna().all()
        ):
            warnings.append(
                "this project has no observed_at metadata — temporal filters "
                "matched everything. The data was indexed before memory mode "
                "or without YAML frontmatter."
            )

        limit_value = int(limit) if limit is not None else self.max_results

        # Entities pass.
        ent_mask = filter.applies_to_entities(artifacts.entities)
        matched_entities = artifacts.entities.loc[ent_mask].head(limit_value)

        # Documents pass (category + tags).
        doc_mask = filter.applies_to_documents(artifacts.documents)
        matched_docs = artifacts.documents.loc[doc_mask].head(limit_value)

        # Text units pass (temporal + confidence). Then intersect with the
        # category/tag-filtered docs when those filters are active.
        tu_ids = filter.candidate_text_unit_ids(
            artifacts.text_units, artifacts.documents
        )
        if tu_ids is None:
            matched_tus = artifacts.text_units.head(limit_value)
        else:
            matched_tus = (
                artifacts.text_units[artifacts.text_units["id"].astype(str).isin(tu_ids)]
                .head(limit_value)
            )

        # Relationships: keep only those whose endpoints survived the entity
        # filter (when active) and whose TUs survived the TU filter.
        rels = artifacts.relationships
        if not rels.empty:
            valid_names = set(matched_entities["name"].astype(str))
            if (
                filter.entity_names
                or filter.entity_types
                or filter.category
                or filter.since
                or filter.before
                or filter.min_confidence is not None
            ):
                rels = rels[
                    rels["source"].isin(valid_names) & rels["target"].isin(valid_names)
                ]
            if tu_ids is not None and "text_unit_ids" in rels.columns:
                rels = rels[
                    rels["text_unit_ids"].apply(
                        lambda x: any(t in tu_ids for t in _iter_tags(x))
                    )
                ]
            rels = rels.head(limit_value)

        # Render context as a compact summary the agent can read directly.
        context_text = _render_context(
            matched_entities, matched_docs, matched_tus, rels, filter
        )
        response = _render_response(
            matched_entities, matched_docs, matched_tus, rels, filter, warnings
        )

        return SearchResult(
            response=response,
            context_data={
                "entities": matched_entities.reset_index(drop=True),
                "documents": matched_docs.reset_index(drop=True),
                "text_units": matched_tus.reset_index(drop=True),
                "relationships": rels.reset_index(drop=True),
            },
            context_text=context_text,
            completion_time=time.perf_counter() - started,
            llm_calls=0,
        )


# ---------------------------------------------------------------- rendering


def _render_response(
    entities: pd.DataFrame,
    docs: pd.DataFrame,
    text_units: pd.DataFrame,
    rels: pd.DataFrame,
    filter: RecallFilter,
    warnings: list[str],
) -> str:
    """Compact prose summary for the agent — counts + a few highlights."""
    lines: list[str] = []
    lines.append(_filter_summary(filter))
    lines.append("")
    lines.append(
        f"matches: {len(entities)} entities, {len(docs)} documents, "
        f"{len(text_units)} text units, {len(rels)} relationships."
    )
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(f"warning: {w}")
    if not entities.empty:
        lines.append("")
        lines.append("Top entities:")
        for _, row in entities.head(10).iterrows():
            desc = (row.get("description") or "").replace("\n", " ")[:120]
            lines.append(f"- {row['name']} ({row.get('type', '?')}): {desc}")
    if not docs.empty:
        lines.append("")
        lines.append("Documents:")
        for _, row in docs.head(10).iterrows():
            cat = row.get("category") or ""
            tags = _iter_tags(row.get("tags"))
            tag_str = ", ".join(tags) if tags else ""
            line = f"- {row.get('title', '?')}"
            if cat:
                line += f"  [{cat}]"
            if tag_str:
                line += f"  ({tag_str})"
            lines.append(line)
    return "\n".join(lines)


def _render_context(
    entities: pd.DataFrame,
    docs: pd.DataFrame,
    text_units: pd.DataFrame,
    rels: pd.DataFrame,
    filter: RecallFilter,
) -> str:
    """XML-tagged context block, matching the shape used by other search modes."""
    parts: list[str] = []
    if not entities.empty:
        parts.append("<entities>")
        parts.append("id,entity,type,description,observed_at,confidence")
        for _, row in entities.iterrows():
            desc = (row.get("description") or "").replace("\n", " ").replace(",", ";")[:300]
            parts.append(
                f"{row.get('human_readable_id', '')},{row['name']},{row.get('type', '')},"
                f"{desc},{row.get('observed_at') or ''},{row.get('confidence') or 1.0}"
            )
        parts.append("</entities>")
    if not rels.empty:
        parts.append("<relationships>")
        parts.append("id,source,target,description,relationship_type,weight")
        for _, row in rels.iterrows():
            desc = (row.get("description") or "").replace("\n", " ").replace(",", ";")[:300]
            rt = row.get("relationship_type") or row.get("type") or "RELATED"
            parts.append(
                f"{row.get('human_readable_id', '')},{row['source']},{row['target']},"
                f"{desc},{rt},{row.get('weight', 1.0):.2f}"
            )
        parts.append("</relationships>")
    if not text_units.empty:
        parts.append("<sources>")
        for _, row in text_units.iterrows():
            doc_id = row.get("document_id") or ""
            parts.append(f'<source id="{row["id"]}" document_id="{doc_id}">')
            parts.append((row.get("text") or "")[:1000])
            parts.append("</source>")
        parts.append("</sources>")
    return "\n".join(parts)


def _filter_summary(f: RecallFilter) -> str:
    """One-line description of the filter for the user-facing response."""
    bits: list[str] = []
    if f.since:
        bits.append(f"since={f.since}")
    if f.before:
        bits.append(f"before={f.before}")
    if f.category:
        bits.append(f"category={f.category}")
    if f.tags:
        bits.append(f"tags=[{','.join(f.tags)}]")
    if f.entity_names:
        bits.append(f"entities=[{','.join(f.entity_names)}]")
    if f.entity_types:
        bits.append(f"types=[{','.join(f.entity_types)}]")
    if f.min_confidence is not None:
        bits.append(f"min_confidence={f.min_confidence}")
    return "Recall filter: " + (", ".join(bits) if bits else "(no filter)")


__all__ = ["RecallSearch"]
