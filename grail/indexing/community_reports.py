"""
Community-report generator.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

For each community produced by :class:`CommunityExtractor`, build a CSV-style
context (entities + relationships) and ask the LLM for a JSON narrative report
(``title, summary, rating, rating_explanation, findings[]``). Malformed JSON
gets a three-pass repair: raw parse → cleanup parse → LLM-driven correction.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from grail.llm import LLMClient
from grail.prompts import PromptRegistry
from grail.reporting import NullReporter, Reporter
from grail.storage import StorageBackend
from grail.utils.tokens import tiktoken_len

log = logging.getLogger(__name__)


@dataclass
class CommunityReportGenerator:
    storage: StorageBackend
    llm: LLMClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    output_folder: str = "output"
    report_endpoint: Optional[str] = None
    report_model: Optional[str] = None
    json_corrector_endpoint: Optional[str] = None
    json_corrector_model: Optional[str] = None
    max_input_tokens: int = 8000
    max_output_tokens: int = 2048
    temperature: float = 0.0
    # Which Leiden hierarchy level to summarise. "coarsest" / "finest" / "all" / int.
    community_level: str | int = "coarsest"
    # Minimum entities per community to qualify for a report. Filters out
    # singletons + tiny dust clusters; 0 disables.
    min_report_size: int = 3
    report_concurrency: Optional[int] = None
    reporter: Reporter = field(default_factory=NullReporter)

    # ------------------------------------------------------------------ level resolution

    def _resolve_levels(self, available: list[int]) -> list[int]:
        """Translate ``community_level`` into the concrete list of levels to report on."""
        if not available:
            return []
        if isinstance(self.community_level, int):
            return [self.community_level] if self.community_level in available else []
        token = str(self.community_level).strip().lower()
        if token == "coarsest":
            return [min(available)]
        if token == "finest":
            return [max(available)]
        if token == "all":
            return list(available)
        # Numeric strings like "1".
        try:
            level = int(token)
            return [level] if level in available else []
        except ValueError:
            self.reporter.warning(
                f"Unknown community_level {self.community_level!r}; defaulting to 'coarsest'."
            )
            return [min(available)]

    # ------------------------------------------------------------------ run

    async def generate_reports(
        self,
        nodes_df: Optional[pd.DataFrame] = None,
        communities_df: Optional[pd.DataFrame] = None,
        entities_df: Optional[pd.DataFrame] = None,
        relationships_df: Optional[pd.DataFrame] = None,
        *,
        affected_community_ids: Optional[set[str]] = None,
    ) -> pd.DataFrame:
        """Generate community reports.

        When ``affected_community_ids`` is provided, only those communities are
        sent to the LLM. Existing reports for unaffected communities are preserved.
        Communities that no longer exist in ``communities_df`` are removed.
        """
        nodes_df = self._coalesce(nodes_df, "final_nodes.parquet")
        communities_df = self._coalesce(communities_df, "final_communities.parquet")
        entities_df = self._coalesce(entities_df, "final_entities.parquet")
        relationships_df = self._coalesce(relationships_df, "final_relationships.parquet")

        if communities_df.empty or entities_df.empty:
            self.reporter.warning("Missing community / entity tables; skipping report generation.")
            return pd.DataFrame()

        # Pick which Leiden hierarchy level(s) to summarise.
        all_levels = sorted({int(lv) for lv in communities_df["level"].unique()})
        selected_levels = self._resolve_levels(all_levels)
        top_communities = communities_df[
            communities_df["level"].astype(int).isin(selected_levels)
        ]

        # Filter out tiny communities (singletons + dust clusters from isolated
        # entities) before we generate reports for them.
        if self.min_report_size > 0:
            before = len(top_communities)
            top_communities = top_communities[top_communities["size"] >= self.min_report_size]
            skipped = before - len(top_communities)
            if skipped:
                self.reporter.info(
                    f"Skipped {skipped} community(ies) below min_report_size={self.min_report_size}."
                )

        if top_communities.empty:
            self.reporter.warning(
                "No communities qualified for reports after level + size filtering."
            )
            return pd.DataFrame()
        current_community_ids = set(top_communities["community"].astype(str))

        # Load existing reports for the selective path.
        existing_reports: dict[str, dict[str, Any]] = {}
        if affected_community_ids is not None:
            existing_reports = self._load_existing_reports()

        # Decide which communities need (re-)generation.
        if affected_community_ids is not None:
            communities_to_generate = top_communities[
                top_communities["community"].astype(str).isin(affected_community_ids)
            ]
            self.reporter.info(
                f"Selective report generation: {len(communities_to_generate)} of "
                f"{len(top_communities)} communities affected."
            )
        else:
            communities_to_generate = top_communities

        rep_rows = []
        for _, row in communities_to_generate.iterrows():
            context = self._build_context(row["entity_ids"], entities_df, relationships_df)
            rep_rows.append((row, context))

        async def _one(row, context) -> dict[str, Any]:
            messages = self.prompts.build("community_report", input_text=context)
            response = await self.llm.execute_safe(
                messages=messages,
                endpoint=self.report_endpoint,
                model=self.report_model,
                max_tokens=self.max_output_tokens,
                temperature=self.temperature,
                tag="community_report",
            )
            parsed = await self._parse_with_repair(response)
            if not parsed.get("title") and not parsed.get("summary"):
                _dump_debug(
                    community_id=str(row["community"]),
                    messages=messages,
                    raw_response=response,
                    parsed=parsed,
                )
            return {
                "id": row["id"],
                "community": row["community"],
                "level": row["level"],
                "title": parsed.get("title", row["title"]),
                "summary": parsed.get("summary", ""),
                "full_content": _render_markdown(parsed),
                "full_content_json": json.dumps(parsed),
                "rank": float(parsed.get("rating", 5.0)),
                "rank_explanation": parsed.get("rating_explanation", ""),
                "findings": parsed.get("findings", []),
            }

        if self.report_concurrency is not None:
            sem = asyncio.Semaphore(self.report_concurrency)

            async def _throttled(row: Any, ctx: str) -> dict[str, Any]:
                async with sem:
                    return await _one(row, ctx)

            new_reports = await asyncio.gather(*(_throttled(r, c) for r, c in rep_rows))
        else:
            new_reports = await asyncio.gather(*(_one(r, c) for r, c in rep_rows))

        if affected_community_ids is not None:
            # Merge: start from existing, update affected, remove deleted.
            merged: dict[str, dict[str, Any]] = {}
            for cid, report in existing_reports.items():
                if str(cid) in current_community_ids:
                    merged[str(cid)] = report
            for report in new_reports:
                merged[str(report["community"])] = report
            reports_df = pd.DataFrame(list(merged.values()))
        else:
            reports_df = pd.DataFrame(new_reports)

        if not reports_df.empty:
            with self.storage.open_for_write(
                f"{self.output_folder}/final_community_reports.parquet"
            ) as path:
                reports_df.to_parquet(path, index=False)

            self._enrich_communities(reports_df, nodes_df, relationships_df)
        return reports_df

    def _load_existing_reports(self) -> dict[str, dict[str, Any]]:
        key = f"{self.output_folder}/final_community_reports.parquet"
        if not self.storage.exists(key):
            return {}
        with self.storage.open_for_read(key) as path:
            df = pd.read_parquet(path)
        return {str(row["community"]): row.to_dict() for _, row in df.iterrows()}

    # ------------------------------------------------------------------ community enrichment

    def _enrich_communities(
        self,
        reports_df: pd.DataFrame,
        nodes_df: Optional[pd.DataFrame],
        relationships_df: Optional[pd.DataFrame],
    ) -> None:
        """Update ``final_communities.parquet`` with legacy-standard columns.

        Adds ``raw_community`` (JSON list of entity names),
        ``relationship_ids`` (JSON list), ``text_unit_ids`` (JSON list),
        and overrides ``title`` with the LLM-generated report title.
        """
        comm_key = f"{self.output_folder}/final_communities.parquet"
        if not self.storage.exists(comm_key):
            return
        with self.storage.open_for_read(comm_key) as path:
            comm_df = pd.read_parquet(path)

        entities_df = self._coalesce(None, "final_entities.parquet")
        relationships_df = self._coalesce(relationships_df, "final_relationships.parquet")

        report_title_map = {
            str(row["community"]): row["title"]
            for _, row in reports_df.iterrows()
            if row.get("title")
        }

        raw_communities = []
        rel_ids_list = []
        tu_ids_list = []
        titles = []

        for _, row in comm_df.iterrows():
            entity_names = row.get("entity_ids", [])
            if entity_names is None:
                entity_names = []

            raw_communities.append(json.dumps(list(entity_names)))

            names_set = set(entity_names)

            if not relationships_df.empty:
                rels = relationships_df[
                    relationships_df["source"].isin(names_set)
                    & relationships_df["target"].isin(names_set)
                ]
                rel_ids_list.append(json.dumps(rels["id"].tolist()))
            else:
                rel_ids_list.append(json.dumps([]))

            if not entities_df.empty and "text_unit_ids" in entities_df.columns:
                tu_ids: set[str] = set()
                matching = entities_df[entities_df["name"].isin(names_set)]
                for _, e in matching.iterrows():
                    tids = e.get("text_unit_ids")
                    if tids is not None and hasattr(tids, "__iter__") and not isinstance(tids, str):
                        tu_ids.update(tids)
                tu_ids_list.append(json.dumps(sorted(tu_ids)))
            else:
                tu_ids_list.append(json.dumps([]))

            cid = str(row["community"])
            titles.append(report_title_map.get(cid, row.get("title", "")))

        comm_df["raw_community"] = raw_communities
        comm_df["relationship_ids"] = rel_ids_list
        comm_df["text_unit_ids"] = tu_ids_list
        comm_df["title"] = titles

        with self.storage.open_for_write(comm_key) as path:
            comm_df.to_parquet(path, index=False)

    # ------------------------------------------------------------------ context

    def _build_context(
        self,
        entity_ids: list[str],
        entities_df: pd.DataFrame,
        relationships_df: pd.DataFrame,
    ) -> str:
        entities = entities_df[entities_df["name"].isin(entity_ids)]
        rels = relationships_df[
            relationships_df["source"].isin(entity_ids)
            & relationships_df["target"].isin(entity_ids)
        ] if not relationships_df.empty else pd.DataFrame()

        ent_lines = ["Entities", "", "id,entity,description"]
        for _, r in entities.iterrows():
            desc = (r["description"] or "").replace("\n", " ").replace(",", ";")
            ent_lines.append(f"{r['human_readable_id']},{r['name']},{desc}")

        rel_lines = ["", "Relationships", "", "id,source,target,description"]
        if not rels.empty:
            for _, r in rels.iterrows():
                desc = (r["description"] or "").replace("\n", " ").replace(",", ";")
                rel_lines.append(f"{r['human_readable_id']},{r['source']},{r['target']},{desc}")

        text = "\n".join(ent_lines + rel_lines)
        # Trim to fit the model.
        while tiktoken_len(text) > self.max_input_tokens and (ent_lines or rel_lines):
            if rel_lines and len(rel_lines) > 4:
                rel_lines.pop()
            elif ent_lines and len(ent_lines) > 4:
                ent_lines.pop()
            else:
                break
            text = "\n".join(ent_lines + rel_lines)
        return text

    # ------------------------------------------------------------------ parsing + repair

    async def _parse_with_repair(self, response: Optional[str]) -> dict[str, Any]:
        if not response:
            return _EMPTY_REPORT
        # Pass 1: as-is JSON parse.
        try:
            return _coerce_report(json.loads(response))
        except json.JSONDecodeError:
            pass
        # Pass 2: strip leading/trailing junk, fenced code, etc.
        cleaned = _strip_to_json(response)
        try:
            return _coerce_report(json.loads(cleaned))
        except json.JSONDecodeError as exc:
            json_exc = exc
        # Pass 3: ask the LLM to fix it.
        messages = self.prompts.build(
            "json_correction", json_string=cleaned, exception=str(json_exc)
        )
        fixed = await self.llm.execute_safe(
            messages=messages,
            endpoint=self.json_corrector_endpoint or self.report_endpoint,
            model=self.json_corrector_model or self.report_model,
            max_tokens=self.max_output_tokens,
            temperature=0.0,
            tag="json_correction",
        )
        if not fixed:
            return _EMPTY_REPORT
        try:
            return _coerce_report(json.loads(_strip_to_json(fixed)))
        except json.JSONDecodeError:
            self.reporter.warning("JSON correction still failed; emitting empty report.")
            return _EMPTY_REPORT

    # ------------------------------------------------------------------ helpers

    def _coalesce(self, df: Optional[pd.DataFrame], key: str) -> pd.DataFrame:
        if df is not None:
            return df
        full = f"{self.output_folder}/{key}"
        if not self.storage.exists(full):
            return pd.DataFrame()
        with self.storage.open_for_read(full) as path:
            return pd.read_parquet(path)


_EMPTY_REPORT: dict[str, Any] = {
    "title": "",
    "summary": "",
    "rating": 0.0,
    "rating_explanation": "",
    "findings": [],
}


def _render_markdown(parsed: dict[str, Any]) -> str:
    """Render a parsed report dict as a markdown document (legacy ``full_content`` format)."""
    title = parsed.get("title", "Report")
    summary = parsed.get("summary", "")
    findings = parsed.get("findings", [])
    sections = "\n\n".join(
        f"## {f.get('summary', '')}\n\n{f.get('explanation', '')}"
        for f in findings
        if isinstance(f, dict)
    )
    return f"# {title}\n\n{summary}\n\n{sections}" if sections else f"# {title}\n\n{summary}"


def _strip_to_json(text: str) -> str:
    """Strip ``<report_json>``, ``<correct_json>``, markdown fences, and trim to outer braces."""
    text = re.sub(r"^.*?(?:<report_json>|<correct_json>|```json|```)", "", text, count=1, flags=re.S)
    text = re.sub(r"(?:</report_json>|</correct_json>|```)\s*$", "", text, count=1, flags=re.S)
    text = text.strip()
    if not text.startswith("{"):
        idx = text.find("{")
        if idx >= 0:
            text = text[idx:]
    if not text.endswith("}"):
        idx = text.rfind("}")
        if idx >= 0:
            text = text[: idx + 1]
    return text


def _coerce_report(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _EMPTY_REPORT
    # Unwrap {"report_json": "..."} or {"report": "..."} patterns where the
    # model stringified the real JSON inside a wrapper key.
    for wrapper_key in ("report_json", "report", "result", "output"):
        if wrapper_key in data and isinstance(data[wrapper_key], str) and "title" not in data:
            try:
                inner = json.loads(data[wrapper_key])
                if isinstance(inner, dict):
                    data = inner
                    break
            except (json.JSONDecodeError, TypeError):
                pass
    out = {
        "title": str(data.get("title", "")),
        "summary": str(data.get("summary", "")),
        "rating": float(data.get("rating", 0.0) or 0.0),
        "rating_explanation": str(data.get("rating_explanation", "")),
        "findings": [],
    }
    findings = data.get("findings") or []
    if isinstance(findings, list):
        for f in findings:
            if isinstance(f, dict):
                out["findings"].append(
                    {"summary": str(f.get("summary", "")), "explanation": str(f.get("explanation", ""))}
                )
    return out


def _dump_debug(
    *,
    community_id: str,
    messages: list[dict[str, Any]],
    raw_response: Optional[str],
    parsed: dict[str, Any],
) -> None:
    """Write the prompt + raw LLM response to /tmp/debug_grail/ for inspection."""
    from pathlib import Path
    import datetime

    debug_dir = Path("/tmp/debug_grail")
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"community_{community_id}_{ts}"

    prompt_path = debug_dir / f"{stem}_prompt.json"
    prompt_path.write_text(json.dumps(messages, indent=2, ensure_ascii=False))

    response_path = debug_dir / f"{stem}_response.txt"
    response_path.write_text(raw_response or "<EMPTY / None>")

    parsed_path = debug_dir / f"{stem}_parsed.json"
    parsed_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False))

    log.warning(
        "Empty community report for community %s — debug files written to %s",
        community_id, debug_dir,
    )
