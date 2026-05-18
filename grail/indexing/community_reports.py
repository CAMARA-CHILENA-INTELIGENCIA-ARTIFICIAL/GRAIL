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
    reporter: Reporter = field(default_factory=NullReporter)

    # ------------------------------------------------------------------ run

    async def generate_reports(
        self,
        nodes_df: Optional[pd.DataFrame] = None,
        communities_df: Optional[pd.DataFrame] = None,
        entities_df: Optional[pd.DataFrame] = None,
        relationships_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        nodes_df = self._coalesce(nodes_df, "final_nodes.parquet")
        communities_df = self._coalesce(communities_df, "final_communities.parquet")
        entities_df = self._coalesce(entities_df, "final_entities.parquet")
        relationships_df = self._coalesce(relationships_df, "final_relationships.parquet")

        if communities_df.empty or entities_df.empty:
            self.reporter.warning("Missing community / entity tables; skipping report generation.")
            return pd.DataFrame()

        # Use the highest community level — it represents the most coarse-grained groupings.
        top_level = int(communities_df["level"].max())
        top_communities = communities_df[communities_df["level"] == top_level]

        rep_rows = []
        for _, row in top_communities.iterrows():
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
                response_format={"type": "json_object"},
            )
            parsed = await self._parse_with_repair(response)
            return {
                "id": row["id"],
                "community": row["community"],
                "level": row["level"],
                "title": parsed.get("title", row["title"]),
                "summary": parsed.get("summary", ""),
                "full_content": json.dumps(parsed),
                "rank": float(parsed.get("rating", 5.0)),
                "rank_explanation": parsed.get("rating_explanation", ""),
                "findings": parsed.get("findings", []),
            }

        reports = await asyncio.gather(*(_one(r, c) for r, c in rep_rows))
        reports_df = pd.DataFrame(reports)
        with self.storage.open_for_write(
            f"{self.output_folder}/final_community_reports.parquet"
        ) as path:
            reports_df.to_parquet(path, index=False)
        return reports_df

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
            response_format={"type": "json_object"},
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
