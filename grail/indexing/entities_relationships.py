"""
Entity / relationship extraction.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Reads ``partial_text_units.parquet``, asks the LLM to extract entities and
relationships per chunk in the GraphRAG tuple format, parses + dedups, summarizes
multi-description entities, embeds entity descriptions, builds a NetworkX graph,
and writes the canonical parquet artefacts:

    final_entities.parquet
    final_relationships.parquet
    final_text_units.parquet                (← annotated with entity_ids / relationship_ids)
    entity_relationship_graph.graphml

The LLM tuple format is contract-bound to the ``entity_relation`` prompt's
``DEFAULT_DELIMITERS``. If you customize the prompt, mirror the delimiters here.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import networkx as nx
import pandas as pd

from grail.indexing.summarize_descriptions import SummarizeExtractor
from grail.llm import EmbeddingClient, LLMClient
from grail.prompts import PromptRegistry
from grail.prompts.builtin import entity_relation as _entity_relation_prompt
from grail.reporting import NullReporter, Reporter
from grail.storage import StorageBackend
from grail.utils.ids import generate_guid

log = logging.getLogger(__name__)


@dataclass
class _Entity:
    name: str
    type: str
    descriptions: list[str] = field(default_factory=list)
    retrieval_queries: list[str] = field(default_factory=list)
    text_unit_ids: set[str] = field(default_factory=set)
    document_ids: set[str] = field(default_factory=set)


@dataclass
class _Relationship:
    source: str
    target: str
    descriptions: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    text_unit_ids: set[str] = field(default_factory=set)
    document_ids: set[str] = field(default_factory=set)


@dataclass
class EntityRelationshipExtractor:
    """End-to-end extraction stage."""

    storage: StorageBackend
    llm: LLMClient
    embeddings: EmbeddingClient
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    summarizer: Optional[SummarizeExtractor] = None
    entity_types: list[str] = field(default_factory=lambda: ["person", "organization"])
    extraction_endpoint: Optional[str] = None
    extraction_model: Optional[str] = None
    summarization_endpoint: Optional[str] = None
    summarization_model: Optional[str] = None
    extraction_max_tokens: int = 4096
    extraction_temperature: float = 0.0
    extraction_concurrency: Optional[int] = None
    summarization_concurrency: Optional[int] = None
    summarization_max_tokens: int = 8192
    summarization_batch_size: int = 10
    output_folder: str = "output"
    delimiters: dict[str, str] = field(default_factory=lambda: dict(_entity_relation_prompt.DEFAULT_DELIMITERS))
    deduplicate_entities: bool = True
    dedup_similarity_threshold: float = 0.90
    dedup_endpoint: Optional[str] = None
    dedup_model: Optional[str] = None
    dedup_max_entities_per_call: int = 50
    reporter: Reporter = field(default_factory=NullReporter)

    def __post_init__(self) -> None:
        if self.summarizer is None:
            self.summarizer = SummarizeExtractor(
                llm=self.llm,
                prompts=self.prompts,
                endpoint=self.summarization_endpoint or self.extraction_endpoint,
                model=self.summarization_model or self.extraction_model,
                max_output_tokens=self.summarization_max_tokens,
                batch_size=self.summarization_batch_size,
            )

    # ------------------------------------------------------------------ run

    async def _extract_raw(
        self, text_units_df: pd.DataFrame
    ) -> tuple[dict[str, _Entity], dict[tuple[str, str], _Relationship]]:
        """Run LLM extraction on text units and return parsed entities/relationships."""
        calls: list[dict[str, Any]] = []
        for _, row in text_units_df.iterrows():
            messages = self.prompts.build(
                "entity_relation",
                entity_types=self.entity_types,
                input_text=row["text"],
                **self.delimiters,
            )
            calls.append(
                {
                    "messages": messages,
                    "endpoint": self.extraction_endpoint,
                    "model": self.extraction_model,
                    "max_tokens": self.extraction_max_tokens,
                    "temperature": self.extraction_temperature,
                    "tag": "entity_extraction",
                }
            )

        self.reporter.info(f"Extracting from {len(calls)} text units…")
        responses = await self.llm.execute_concurrently(
            calls, safe=True, concurrency=self.extraction_concurrency
        )
        return self._parse_responses(text_units_df, responses)

    async def process_text_units(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, nx.Graph]:
        text_units_df = self._read_partial_text_units()
        if text_units_df.empty:
            self.reporter.warning("No text units to process; skipping extraction.")
            return pd.DataFrame(), pd.DataFrame(), text_units_df, nx.Graph()

        entities_by_name, rels_by_pair = await self._extract_raw(text_units_df)
        if not entities_by_name:
            self.reporter.warning("LLM returned no parseable entities.")
            return pd.DataFrame(), pd.DataFrame(), text_units_df, nx.Graph()

        # Summarize multi-description entities / relationships.
        await self._summarize_inplace(entities_by_name, rels_by_pair)

        # Filter relationships whose endpoints don't appear in entities.
        rels_by_pair = {
            k: v for k, v in rels_by_pair.items() if v.source in entities_by_name and v.target in entities_by_name
        }

        entity_names = list(entities_by_name.keys())
        descriptions = [entities_by_name[n].descriptions[0] for n in entity_names]
        queries = [" ".join(entities_by_name[n].retrieval_queries) for n in entity_names]
        embedding_texts = [
            f"{n}: {d} {q}".strip() for n, d, q in zip(entity_names, descriptions, queries)
        ]
        embeddings = await self.embeddings.embed_safe(embedding_texts, tag="entity_embedding")

        # Deduplicate entities via name-embedding similarity + LLM judge.
        if self.deduplicate_entities and len(entity_names) > 1:
            from grail.indexing.entity_dedup import apply_merges, find_duplicates

            types = [entities_by_name[n].type for n in entity_names]
            name_embeddings = await self.embeddings.embed_safe(
                entity_names, tag="entity_name_embedding"
            )
            merge_groups = await find_duplicates(
                entity_names,
                types,
                descriptions,
                name_embeddings,
                llm=self.llm,
                prompts=self.prompts,
                similarity_threshold=self.dedup_similarity_threshold,
                max_entities_per_call=self.dedup_max_entities_per_call,
                endpoint=self.dedup_endpoint or self.extraction_endpoint,
                model=self.dedup_model or self.extraction_model,
                reporter=self.reporter,
            )
            if merge_groups:
                entities_by_name, rels_by_pair = apply_merges(
                    entities_by_name, rels_by_pair, merge_groups
                )
                entity_names = list(entities_by_name.keys())
                descriptions = [entities_by_name[n].descriptions[0] for n in entity_names]
                queries = [" ".join(entities_by_name[n].retrieval_queries) for n in entity_names]
                embedding_texts = [
                    f"{n}: {d} {q}".strip() for n, d, q in zip(entity_names, descriptions, queries)
                ]
                embeddings = await self.embeddings.embed_safe(
                    embedding_texts, tag="entity_embedding"
                )

        entities_df = self._build_entities_df(entity_names, entities_by_name, embeddings)
        relationships_df = self._build_relationships_df(rels_by_pair, entities_df)
        text_units_df = self._annotate_text_units(text_units_df, entities_by_name, rels_by_pair)
        graph = self._build_graph(entities_df, relationships_df)

        self._write_artifacts(entities_df, relationships_df, text_units_df, graph)
        return entities_df, relationships_df, text_units_df, graph

    # ------------------------------------------------------------------ parsing

    def _parse_responses(
        self,
        text_units_df: pd.DataFrame,
        responses: list[Optional[str]],
    ) -> tuple[dict[str, _Entity], dict[tuple[str, str], _Relationship]]:
        entities: dict[str, _Entity] = {}
        rels: dict[tuple[str, str], _Relationship] = {}
        tup = re.escape(self.delimiters["tuple_delimiter"])
        rec = re.escape(self.delimiters["record_delimiter"])
        comp = re.escape(self.delimiters["completion_delimiter"])
        start = self.delimiters.get("start_delimiter", "<extracted_data>")

        for (_, row), response in zip(text_units_df.iterrows(), responses):
            if not response:
                continue
            if start in response:
                response = response.split(start, 1)[1]
            tu_id = row["id"]
            # `row.get("document_ids")` may be a numpy array when loaded from
            # parquet — so we can't use `or` (raises "ambiguous truth value").
            raw_doc_ids = row.get("document_ids")
            if raw_doc_ids is None or (hasattr(raw_doc_ids, "__len__") and len(raw_doc_ids) == 0):
                doc_ids = [row.get("document_id")]
            else:
                doc_ids = list(raw_doc_ids)
            # Strip trailing completion marker + everything after it.
            cleaned = re.split(comp, response, maxsplit=1)[0]
            records = re.split(rec, cleaned)
            for raw in records:
                raw = raw.strip()
                if not raw:
                    continue
                # The legacy code accepts entries with or without surrounding parens.
                inner = raw.strip("()").strip()
                fields = [f.strip().strip('"').strip("'") for f in re.split(tup, inner)]
                if len(fields) < 4:
                    continue
                kind = fields[0].lower()
                if kind == "entity" and len(fields) >= 4:
                    name = fields[1].upper().strip()
                    etype = "_".join(fields[2].strip().upper().split())
                    desc = fields[3].strip()
                    if not name or not desc:
                        continue
                    queries_raw = fields[4].strip() if len(fields) >= 5 else ""
                    ent = entities.setdefault(name, _Entity(name=name, type=etype))
                    ent.descriptions.append(desc)
                    if queries_raw:
                        ent.retrieval_queries.extend(
                            q.strip() for q in queries_raw.split(";") if q.strip()
                        )
                    if not ent.type and etype:
                        ent.type = etype
                    ent.text_unit_ids.add(tu_id)
                    ent.document_ids.update(doc_ids)
                elif kind == "relationship" and len(fields) >= 5:
                    src = fields[1].upper().strip()
                    tgt = fields[2].upper().strip()
                    desc = fields[3].strip()
                    try:
                        weight = float(fields[4])
                    except ValueError:
                        weight = 1.0
                    if not src or not tgt or src == tgt:
                        continue
                    key = tuple(sorted((src, tgt)))  # undirected
                    rel = rels.setdefault(key, _Relationship(source=key[0], target=key[1]))
                    rel.descriptions.append(desc)
                    rel.weights.append(weight)
                    rel.text_unit_ids.add(tu_id)
                    rel.document_ids.update(doc_ids)
        return entities, rels

    # ------------------------------------------------------------------ summarization

    async def _summarize_inplace(
        self,
        entities: dict[str, _Entity],
        rels: dict[tuple[str, str], _Relationship],
    ) -> None:
        assert self.summarizer is not None
        entity_jobs = [(name, ent.descriptions) for name, ent in entities.items() if len(ent.descriptions) > 1]
        rel_jobs = [
            (f"{rel.source} ↔ {rel.target}", rel.descriptions)
            for rel in rels.values()
            if len(rel.descriptions) > 1
        ]
        if entity_jobs:
            results = await self.summarizer.summarize_many(
                entity_jobs, concurrency=self.summarization_concurrency
            )
            for (name, _), summary in zip(entity_jobs, results):
                entities[name].descriptions = [summary]
        else:
            for ent in entities.values():
                if ent.descriptions:
                    ent.descriptions = [ent.descriptions[0]]
        if rel_jobs:
            results = await self.summarizer.summarize_many(
                rel_jobs, concurrency=self.summarization_concurrency
            )
            for (_, _), summary in zip(rel_jobs, results):
                pass
            # Replace descriptions on the rels in order.
            for rel, summary in zip([r for r in rels.values() if len(r.descriptions) > 1], results):
                rel.descriptions = [summary]
        else:
            for rel in rels.values():
                if rel.descriptions:
                    rel.descriptions = [rel.descriptions[0]]

    # ------------------------------------------------------------------ dataframes / graph

    def _build_entities_df(
        self,
        ordered_names: list[str],
        entities: dict[str, _Entity],
        embeddings: list[Optional[list[float]]],
    ) -> pd.DataFrame:
        rows = []
        for i, (name, embedding) in enumerate(zip(ordered_names, embeddings)):
            ent = entities[name]
            rows.append(
                {
                    "id": generate_guid(),
                    "name": name,
                    "title": name,
                    "type": ent.type,
                    "description": ent.descriptions[0] if ent.descriptions else "",
                    "retrieval_queries": ent.retrieval_queries,
                    "human_readable_id": i,
                    "graph_embedding": None,
                    "text_unit_ids": sorted(ent.text_unit_ids),
                    "document_ids": sorted(ent.document_ids),
                    "description_embedding": embedding,
                    "degree": 0,
                }
            )
        return pd.DataFrame(rows)

    def _build_relationships_df(
        self,
        rels: dict[tuple[str, str], _Relationship],
        entities_df: pd.DataFrame,
    ) -> pd.DataFrame:
        name_to_id = dict(zip(entities_df["name"], entities_df["id"]))
        rows = []
        for i, rel in enumerate(rels.values()):
            rows.append(
                {
                    "id": generate_guid(),
                    "source": rel.source,
                    "target": rel.target,
                    "source_id": name_to_id.get(rel.source),
                    "target_id": name_to_id.get(rel.target),
                    "description": rel.descriptions[0] if rel.descriptions else "",
                    "weight": sum(rel.weights) / max(len(rel.weights), 1),
                    "text_unit_ids": sorted(rel.text_unit_ids),
                    "document_ids": sorted(rel.document_ids),
                    "human_readable_id": i,
                    "rank": 0,
                }
            )
        df = pd.DataFrame(rows)
        # Update entity degrees.
        if not df.empty:
            degree = pd.concat([df["source"], df["target"]]).value_counts().to_dict()
            entities_df["degree"] = entities_df["name"].map(degree).fillna(0).astype(int)
            df["source_degree"] = df["source"].map(degree).fillna(0).astype(int)
            df["target_degree"] = df["target"].map(degree).fillna(0).astype(int)
            df["rank"] = df["source_degree"] + df["target_degree"]
        return df

    def _annotate_text_units(
        self,
        text_units_df: pd.DataFrame,
        entities: dict[str, _Entity],
        rels: dict[tuple[str, str], _Relationship],
    ) -> pd.DataFrame:
        # Map TU id → list of entity_ids / relationship_ids that mention it.
        tu_to_entities: dict[str, list[str]] = {}
        tu_to_rels: dict[str, list[str]] = {}
        for ent in entities.values():
            for tu_id in ent.text_unit_ids:
                tu_to_entities.setdefault(tu_id, []).append(ent.name)
        for rel in rels.values():
            for tu_id in rel.text_unit_ids:
                tu_to_rels.setdefault(tu_id, []).append(f"{rel.source}|{rel.target}")
        text_units_df = text_units_df.copy()
        text_units_df["entity_ids"] = text_units_df["id"].map(tu_to_entities).apply(
            lambda v: v if isinstance(v, list) else []
        )
        text_units_df["relationship_ids"] = text_units_df["id"].map(tu_to_rels).apply(
            lambda v: v if isinstance(v, list) else []
        )
        return text_units_df

    def _build_graph(self, entities_df: pd.DataFrame, relationships_df: pd.DataFrame) -> nx.Graph:
        graph = nx.Graph()
        for _, row in entities_df.iterrows():
            graph.add_node(
                row["name"],
                id=row["id"],
                type=row["type"],
                description=row["description"],
                embedding=json.dumps(row["description_embedding"])
                if row["description_embedding"] is not None
                else None,
                degree=int(row["degree"]),
            )
        for _, row in relationships_df.iterrows():
            graph.add_edge(
                row["source"],
                row["target"],
                id=row["id"],
                weight=float(row["weight"]),
                description=row["description"],
                rank=int(row["rank"]),
            )
        return graph

    # ------------------------------------------------------------------ incremental: append

    async def append_extract(
        self,
        text_units_df: pd.DataFrame,
        new_text_unit_ids: list[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, nx.Graph, list[str], list[str]]:
        """Extract from new text units only, merge with existing entities/rels.

        Returns ``(entities_df, relationships_df, text_units_df, graph,
        new_entity_names, updated_entity_names)``.
        """
        new_tus = text_units_df[text_units_df["id"].isin(new_text_unit_ids)]
        new_entities, new_rels = await self._extract_raw(new_tus)
        if not new_entities:
            self.reporter.warning("No entities extracted from new text units.")
            existing_e = self._read_parquet("final_entities.parquet")
            existing_r = self._read_parquet("final_relationships.parquet")
            graph = self._build_graph(existing_e, existing_r) if not existing_e.empty else nx.Graph()
            return existing_e, existing_r, text_units_df, graph, [], []

        existing_e = self._read_parquet("final_entities.parquet")
        existing_r = self._read_parquet("final_relationships.parquet")

        result = await self._merge_with_existing(
            existing_e, existing_r, new_entities, new_rels
        )
        entities_df, rels_df, new_names, updated_names = result

        text_units_df = self._annotate_text_units_from_dfs(text_units_df, entities_df, rels_df)
        graph = self._build_graph(entities_df, rels_df)
        self._write_artifacts(entities_df, rels_df, text_units_df, graph)
        return entities_df, rels_df, text_units_df, graph, new_names, updated_names

    # ------------------------------------------------------------------ incremental: edit

    async def edit_extract(
        self,
        text_units_df: pd.DataFrame,
        edited_text_unit_ids: list[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, nx.Graph, list[str], list[str], list[str]]:
        """Re-extract from edited text units, merge, and prune orphans.

        Returns ``(entities_df, relationships_df, text_units_df, graph,
        new_entity_names, updated_entity_names, deleted_entity_names)``.
        """
        edited_tus = text_units_df[text_units_df["id"].isin(edited_text_unit_ids)]
        new_entities, new_rels = await self._extract_raw(edited_tus)

        existing_e = self._read_parquet("final_entities.parquet")
        existing_r = self._read_parquet("final_relationships.parquet")

        # Strip old TU references for the edited text units from existing entities/rels.
        edited_set = set(edited_text_unit_ids)
        existing_e, existing_r = self._strip_text_unit_refs(existing_e, existing_r, edited_set)

        if not new_entities:
            # No new extractions — just prune orphans from stripping.
            entities_df, deleted_e_names = self._prune_orphan_entities(existing_e)
            rels_df, _ = self._prune_orphan_relationships(existing_r, set(entities_df["name"]))
            text_units_df = self._annotate_text_units_from_dfs(text_units_df, entities_df, rels_df)
            graph = self._build_graph(entities_df, rels_df) if not entities_df.empty else nx.Graph()
            self._write_artifacts(entities_df, rels_df, text_units_df, graph)
            return entities_df, rels_df, text_units_df, graph, [], [], deleted_e_names

        result = await self._merge_with_existing(
            existing_e, existing_r, new_entities, new_rels
        )
        entities_df, rels_df, new_names, updated_names = result

        entities_df, deleted_names = self._prune_orphan_entities(entities_df)
        valid_names = set(entities_df["name"])
        rels_df, _ = self._prune_orphan_relationships(rels_df, valid_names)

        text_units_df = self._annotate_text_units_from_dfs(text_units_df, entities_df, rels_df)
        graph = self._build_graph(entities_df, rels_df) if not entities_df.empty else nx.Graph()
        self._write_artifacts(entities_df, rels_df, text_units_df, graph)
        return entities_df, rels_df, text_units_df, graph, new_names, updated_names, deleted_names

    # ------------------------------------------------------------------ incremental: delete

    async def delete_extract(
        self,
        text_units_df: pd.DataFrame,
        deleted_text_unit_ids: list[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, nx.Graph, list[str], list[str]]:
        """Strip deleted TU refs and prune orphaned entities/relationships.

        Returns ``(entities_df, relationships_df, text_units_df, graph,
        updated_entity_names, deleted_entity_names)``.
        """
        existing_e = self._read_parquet("final_entities.parquet")
        existing_r = self._read_parquet("final_relationships.parquet")

        deleted_set = set(deleted_text_unit_ids)
        existing_e, existing_r = self._strip_text_unit_refs(existing_e, existing_r, deleted_set)

        updated_names = self._names_with_stripped_refs(existing_e, deleted_set)
        entities_df, deleted_names = self._prune_orphan_entities(existing_e)
        valid_names = set(entities_df["name"])
        rels_df, _ = self._prune_orphan_relationships(existing_r, valid_names)

        text_units_df = self._annotate_text_units_from_dfs(text_units_df, entities_df, rels_df)
        graph = self._build_graph(entities_df, rels_df) if not entities_df.empty else nx.Graph()
        self._write_artifacts(entities_df, rels_df, text_units_df, graph)
        return entities_df, rels_df, text_units_df, graph, updated_names, deleted_names

    # ------------------------------------------------------------------ incremental helpers

    def _read_parquet(self, name: str) -> pd.DataFrame:
        key = f"{self.output_folder}/{name}"
        if not self.storage.exists(key):
            return pd.DataFrame()
        with self.storage.open_for_read(key) as path:
            return pd.read_parquet(path)

    async def _merge_with_existing(
        self,
        existing_e: pd.DataFrame,
        existing_r: pd.DataFrame,
        new_entities: dict[str, _Entity],
        new_rels: dict[tuple[str, str], _Relationship],
    ) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
        """Merge new extractions into existing DataFrames.

        Returns ``(entities_df, relationships_df, new_entity_names, updated_entity_names)``.
        """
        existing_by_name: dict[str, dict] = {}
        if not existing_e.empty:
            for _, row in existing_e.iterrows():
                existing_by_name[row["name"]] = row.to_dict()

        existing_rels_by_pair: dict[tuple[str, str], dict] = {}
        if not existing_r.empty:
            for _, row in existing_r.iterrows():
                key = tuple(sorted((row["source"], row["target"])))
                existing_rels_by_pair[key] = row.to_dict()

        new_entity_names: list[str] = []
        updated_entity_names: list[str] = []
        names_to_resummarize: list[tuple[str, list[str]]] = []
        names_to_reembed: list[str] = []

        max_hrid = 0
        if not existing_e.empty and "human_readable_id" in existing_e.columns:
            max_hrid = int(existing_e["human_readable_id"].max())

        for name, ent in new_entities.items():
            if name in existing_by_name:
                existing = existing_by_name[name]
                old_desc = existing.get("description", "")
                new_desc = ent.descriptions[0] if ent.descriptions else ""
                if old_desc != new_desc:
                    names_to_resummarize.append((name, [old_desc, new_desc]))
                    names_to_reembed.append(name)
                    updated_entity_names.append(name)
                old_tus = set(existing.get("text_unit_ids") or [])
                old_docs = set(existing.get("document_ids") or [])
                existing["text_unit_ids"] = sorted(old_tus | ent.text_unit_ids)
                existing["document_ids"] = sorted(old_docs | ent.document_ids)
                old_rq = existing.get("retrieval_queries") or []
                if isinstance(old_rq, str):
                    old_rq = [q.strip() for q in old_rq.split(";") if q.strip()]
                merged_rq = list(dict.fromkeys(old_rq + ent.retrieval_queries))
                existing["retrieval_queries"] = merged_rq
            else:
                max_hrid += 1
                existing_by_name[name] = {
                    "id": generate_guid(),
                    "name": name,
                    "title": name,
                    "type": ent.type,
                    "description": ent.descriptions[0] if ent.descriptions else "",
                    "retrieval_queries": ent.retrieval_queries,
                    "human_readable_id": max_hrid,
                    "graph_embedding": None,
                    "text_unit_ids": sorted(ent.text_unit_ids),
                    "document_ids": sorted(ent.document_ids),
                    "description_embedding": None,
                    "degree": 0,
                }
                new_entity_names.append(name)
                names_to_reembed.append(name)

        # Batch re-summarize changed entity descriptions.
        if names_to_resummarize:
            assert self.summarizer is not None
            results = await self.summarizer.summarize_many(names_to_resummarize)
            for (name, _), summary in zip(names_to_resummarize, results):
                existing_by_name[name]["description"] = summary
                existing_by_name[name]["description_embedding"] = None

        # Batch re-embed affected entities (incremental updates).
        if names_to_reembed:
            embed_texts = []
            for n in names_to_reembed:
                desc = existing_by_name[n]["description"]
                rq = existing_by_name[n].get("retrieval_queries") or []
                rq_text = " ".join(rq) if isinstance(rq, list) else str(rq)
                embed_texts.append(f"{n}: {desc} {rq_text}".strip())
            embeddings = await self.embeddings.embed_safe(embed_texts, tag="entity_embedding")
            for name, emb in zip(names_to_reembed, embeddings):
                existing_by_name[name]["description_embedding"] = emb

        # Merge relationships.
        new_rel_names: list[str] = []
        updated_rel_names: list[str] = []
        rels_to_resummarize: list[tuple[str, list[str]]] = []
        max_rel_hrid = 0
        if not existing_r.empty and "human_readable_id" in existing_r.columns:
            max_rel_hrid = int(existing_r["human_readable_id"].max())

        valid_entity_names = set(existing_by_name.keys())
        for pair, rel in new_rels.items():
            if rel.source not in valid_entity_names or rel.target not in valid_entity_names:
                continue
            key = tuple(sorted((rel.source, rel.target)))
            if key in existing_rels_by_pair:
                existing = existing_rels_by_pair[key]
                old_desc = existing.get("description", "")
                new_desc = rel.descriptions[0] if rel.descriptions else ""
                if old_desc != new_desc:
                    rels_to_resummarize.append((f"{key[0]} ↔ {key[1]}", [old_desc, new_desc]))
                    updated_rel_names.append(f"{key[0]}|{key[1]}")
                old_w = existing.get("weight", 1.0)
                new_w = sum(rel.weights) / max(len(rel.weights), 1)
                existing["weight"] = (old_w + new_w) / 2.0
                old_tus = set(existing.get("text_unit_ids") or [])
                old_docs = set(existing.get("document_ids") or [])
                existing["text_unit_ids"] = sorted(old_tus | rel.text_unit_ids)
                existing["document_ids"] = sorted(old_docs | rel.document_ids)
            else:
                max_rel_hrid += 1
                existing_rels_by_pair[key] = {
                    "id": generate_guid(),
                    "source": key[0],
                    "target": key[1],
                    "description": rel.descriptions[0] if rel.descriptions else "",
                    "weight": sum(rel.weights) / max(len(rel.weights), 1),
                    "text_unit_ids": sorted(rel.text_unit_ids),
                    "document_ids": sorted(rel.document_ids),
                    "human_readable_id": max_rel_hrid,
                    "source_degree": 0,
                    "target_degree": 0,
                    "rank": 0,
                }
                new_rel_names.append(f"{key[0]}|{key[1]}")

        if rels_to_resummarize:
            assert self.summarizer is not None
            results = await self.summarizer.summarize_many(rels_to_resummarize)
            for (label, _), summary in zip(rels_to_resummarize, results):
                parts = label.split(" ↔ ")
                key = tuple(sorted(parts))
                if key in existing_rels_by_pair:
                    existing_rels_by_pair[key]["description"] = summary

        entities_df = pd.DataFrame(list(existing_by_name.values()))
        rels_df = pd.DataFrame(list(existing_rels_by_pair.values()))

        # Recompute degrees.
        if not rels_df.empty and not entities_df.empty:
            degree = pd.concat([rels_df["source"], rels_df["target"]]).value_counts().to_dict()
            entities_df["degree"] = entities_df["name"].map(degree).fillna(0).astype(int)
            rels_df["source_degree"] = rels_df["source"].map(degree).fillna(0).astype(int)
            rels_df["target_degree"] = rels_df["target"].map(degree).fillna(0).astype(int)
            rels_df["rank"] = rels_df["source_degree"] + rels_df["target_degree"]

        return entities_df, rels_df, new_entity_names, updated_entity_names

    @staticmethod
    def _strip_text_unit_refs(
        entities_df: pd.DataFrame,
        rels_df: pd.DataFrame,
        tu_ids_to_strip: set[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Remove references to specific text unit IDs from all entities and rels."""
        if not entities_df.empty and "text_unit_ids" in entities_df.columns:
            entities_df = entities_df.copy()
            entities_df["text_unit_ids"] = entities_df["text_unit_ids"].apply(
                lambda x: [tid for tid in (x if isinstance(x, list) else []) if tid not in tu_ids_to_strip]
            )
        if not rels_df.empty and "text_unit_ids" in rels_df.columns:
            rels_df = rels_df.copy()
            rels_df["text_unit_ids"] = rels_df["text_unit_ids"].apply(
                lambda x: [tid for tid in (x if isinstance(x, list) else []) if tid not in tu_ids_to_strip]
            )
        return entities_df, rels_df

    @staticmethod
    def _names_with_stripped_refs(
        entities_df: pd.DataFrame, tu_ids_stripped: set[str]
    ) -> list[str]:
        """Return names of entities that had references to the stripped TU IDs."""
        if entities_df.empty:
            return []
        return entities_df["name"].tolist()

    @staticmethod
    def _prune_orphan_entities(
        entities_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, list[str]]:
        """Remove entities with no remaining text_unit_ids."""
        if entities_df.empty:
            return entities_df, []
        mask = entities_df["text_unit_ids"].apply(
            lambda x: len(x) > 0 if isinstance(x, list) else True
        )
        deleted = entities_df.loc[~mask, "name"].tolist()
        return entities_df.loc[mask].copy(), deleted

    @staticmethod
    def _prune_orphan_relationships(
        rels_df: pd.DataFrame, valid_entity_names: set[str]
    ) -> tuple[pd.DataFrame, list[str]]:
        """Remove rels with no remaining text_unit_ids or dangling endpoints."""
        if rels_df.empty:
            return rels_df, []
        mask_tus = rels_df["text_unit_ids"].apply(
            lambda x: len(x) > 0 if isinstance(x, list) else True
        )
        mask_endpoints = rels_df["source"].isin(valid_entity_names) & rels_df["target"].isin(valid_entity_names)
        mask = mask_tus & mask_endpoints
        deleted = rels_df.loc[~mask, "id"].tolist()
        return rels_df.loc[mask].copy(), deleted

    def _annotate_text_units_from_dfs(
        self,
        text_units_df: pd.DataFrame,
        entities_df: pd.DataFrame,
        rels_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Re-annotate text units with entity_ids / relationship_ids from DataFrames."""
        tu_to_entities: dict[str, list[str]] = {}
        tu_to_rels: dict[str, list[str]] = {}
        if not entities_df.empty:
            for _, row in entities_df.iterrows():
                for tu_id in (row.get("text_unit_ids") or []):
                    tu_to_entities.setdefault(tu_id, []).append(row["name"])
        if not rels_df.empty:
            for _, row in rels_df.iterrows():
                for tu_id in (row.get("text_unit_ids") or []):
                    tu_to_rels.setdefault(tu_id, []).append(f"{row['source']}|{row['target']}")
        text_units_df = text_units_df.copy()
        text_units_df["entity_ids"] = text_units_df["id"].map(tu_to_entities).apply(
            lambda v: v if isinstance(v, list) else []
        )
        text_units_df["relationship_ids"] = text_units_df["id"].map(tu_to_rels).apply(
            lambda v: v if isinstance(v, list) else []
        )
        return text_units_df

    # ------------------------------------------------------------------ persistence

    def _read_partial_text_units(self) -> pd.DataFrame:
        key = f"{self.output_folder}/partial_text_units.parquet"
        if not self.storage.exists(key):
            return pd.DataFrame()
        with self.storage.open_for_read(key) as path:
            return pd.read_parquet(path)

    def _write_artifacts(
        self,
        entities_df: pd.DataFrame,
        relationships_df: pd.DataFrame,
        text_units_df: pd.DataFrame,
        graph: nx.Graph,
    ) -> None:
        with self.storage.open_for_write(f"{self.output_folder}/final_entities.parquet") as path:
            entities_df.to_parquet(path, index=False)
        with self.storage.open_for_write(
            f"{self.output_folder}/final_relationships.parquet"
        ) as path:
            relationships_df.to_parquet(path, index=False)
        with self.storage.open_for_write(f"{self.output_folder}/final_text_units.parquet") as path:
            text_units_df.to_parquet(path, index=False)
        with self.storage.open_for_write(
            f"{self.output_folder}/entity_relationship_graph.graphml"
        ) as path:
            # GraphML doesn't accept None embeddings; drop them before writing.
            export = graph.copy()
            for _, data in export.nodes(data=True):
                if data.get("embedding") is None:
                    data["embedding"] = ""
            nx.write_graphml(export, path)
        self._write_partial_nodes(entities_df)

    def _write_partial_nodes(self, entities_df: pd.DataFrame) -> None:
        """Write ``partial_nodes.parquet`` — one row per entity with community=None.

        This is the bridge between entity extraction and community detection:
        the community stage reads it, fills in community/level/top_level_node_id,
        and writes ``final_nodes.parquet``.
        """
        if entities_df.empty:
            return
        rows = []
        for _, e in entities_df.iterrows():
            tids = e.get("text_unit_ids")
            if tids is not None and hasattr(tids, "__iter__") and not isinstance(tids, str):
                source_id = ",".join(str(t) for t in tids)
            else:
                source_id = ""
            degree = int(e.get("degree", 0) or 0)
            rows.append({
                "level": 0,
                "title": e["name"],
                "type": e.get("type", ""),
                "description": e.get("description", ""),
                "source_id": source_id,
                "community": None,
                "degree": degree,
                "human_readable_id": int(e.get("human_readable_id", 0) or 0),
                "id": e["id"],
                "size": degree,
                "graph_embedding": e.get("graph_embedding"),
            })
        partial_df = pd.DataFrame(rows)
        with self.storage.open_for_write(
            f"{self.output_folder}/partial_nodes.parquet"
        ) as path:
            partial_df.to_parquet(path, index=False)
