"""
MemoryProject — agentic-memory SDK entry point.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

``MemoryProject`` is the universal agent-facing write path. It produces the
same parquet artefacts as ``GRAIL`` (batch indexing) so every existing search
mode (local / cascade / global / document / agent / recall) works on the
same project. The difference is the write path:

* ``GRAIL.index()`` runs LLM extraction over an ``input/`` folder.
* ``MemoryProject.add_observation(...)`` writes a markdown file under
  ``memories/`` with YAML frontmatter, then merges agent-supplied entities
  and relationships directly into the parquets — no LLM extraction.

Both modes interoperate. Configuring ``mode: knowledge_base`` in
``grail.yaml`` and using ``MemoryProject`` for incremental writes is the
"KB-incremental" workflow.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import networkx as nx
import pandas as pd

from grail.config import Config, load_config
from grail.indexing.loader import FileLoader
from grail.indexing.schema_migration import migrate_dataframe
from grail.memory._merge import (
    _MergeEntity,
    _MergeRelationship,
    _aslist,
    merge_entities,
    merge_relationships,
    recompute_degrees,
)
from grail.memory.identity import (
    ProjectMeta,
    read_meta,
    register_project,
    touch_indexed,
    write_meta,
)
from grail.memory.observation import (
    compose_observation_markdown,
    now_iso,
    slugify_title,
    write_observation_file,
)
from grail.memory.types import (
    CommunityRecord,
    EntityRecord,
    Observation,
    RelationshipRecord,
    Reply,
    SimilarEntity,
)
from grail.reporting import NullReporter, Reporter
from grail.storage import LocalStorage
from grail.utils.ids import generate_guid

log = logging.getLogger(__name__)


_OUTPUT_FOLDER = "output"
_MEMORIES_FOLDER = "memories"
_HISTORY_FILE = "_history.jsonl"


class MemoryProject:
    """Open or create a memory-mode GRAIL project.

    ``path`` is the project directory. If ``meta.json`` already exists at the
    path, the project is opened; otherwise a fresh ``meta.json`` is written
    and the project is added to ``~/.grail/registry.json``.

    ``config`` overrides the on-disk ``grail.yaml`` (handy in tests). When
    neither a passed config nor an on-disk config is found, defaults apply.
    ``embeddings`` is an optional pre-built ``EmbeddingClient``; when omitted
    the project tries to build one from ``config.embeddings``, falling back
    to ``None`` if no API key is present (zero-LLM mode).
    """

    def __init__(
        self,
        path: str | Path,
        *,
        config: Optional[Config] = None,
        embeddings: Any = None,
        reporter: Optional[Reporter] = None,
        registry_home: Optional[str | Path] = None,
        grail_version: str = "",
        name: Optional[str] = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.reporter = reporter or NullReporter()
        self.config = config or self._load_or_default_config()
        self.storage = LocalStorage(root=self.path)
        self.embeddings = embeddings
        self._registry_home = registry_home

        # Identity: open or create meta.json + register.
        existing = read_meta(self.path)
        if existing is None:
            display_name = name or self.path.name
            meta = ProjectMeta.fresh(
                name=display_name,
                mode="memory",
                grail_version=grail_version,
            )
            write_meta(self.path, meta)
            self._ensure_scaffolding()
        else:
            meta = existing
            self._ensure_scaffolding()
        self.meta = meta
        register_project(self.path, meta, home=registry_home)

        # FileLoader, configured against the loader-style storage rooted at
        # the project. We reuse it for both batch parse and per-file parse.
        idx = self.config.indexing
        self.loader = FileLoader(
            storage=self.storage,
            input_folder=_MEMORIES_FOLDER,
            output_folder=_OUTPUT_FOLDER,
            chunk_size=idx.chunk_size,
            chunk_overlap=idx.chunk_overlap,
            encoding_name=idx.encoding_name,
            parse_frontmatter=idx.parse_frontmatter,
            reporter=self.reporter,
        )

    # ------------------------------------------------------------------ setup helpers

    def _load_or_default_config(self) -> Config:
        cfg_yaml = self.path / "grail.yaml"
        if cfg_yaml.exists():
            return load_config(self.path)
        cfg = load_config(None)
        cfg.mode = "memory"
        cfg.root_dir = str(self.path)
        return cfg

    def _ensure_scaffolding(self) -> None:
        """Make sure ``memories/`` and ``output/`` exist."""
        (self.path / _MEMORIES_FOLDER).mkdir(parents=True, exist_ok=True)
        (self.path / _OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ parquet I/O

    def _read_parquet(self, name: str) -> pd.DataFrame:
        key = f"{_OUTPUT_FOLDER}/{name}"
        if not self.storage.exists(key):
            return pd.DataFrame()
        with self.storage.open_for_read(key) as path:
            df = pd.read_parquet(path)
        return migrate_dataframe(df, name.removesuffix(".parquet"))

    def _write_parquet(self, name: str, df: pd.DataFrame) -> None:
        with self.storage.open_for_write(f"{_OUTPUT_FOLDER}/{name}") as path:
            df.to_parquet(path, index=False)

    def _sync_partial_text_units(self) -> None:
        """Mirror ``final_text_units`` into ``partial_text_units``.

        Why this exists: the KB pipeline writes ``partial_text_units.parquet``
        during chunking (stage 1) and enriches it into ``final_text_units``
        during extraction (stage 2). Memory mode skips stage 2 — it writes
        straight to ``final_text_units`` — but ``FileLoader.load_artifacts``
        (used by ``GRAIL.delete`` / ``GRAIL.edit``) reads the *partial*
        file. Without this mirror, those CLI ops blow up with ``KeyError:
        'id'`` on memory projects because the partial file is missing and
        an empty DataFrame returns.

        We strip annotation columns (``entity_ids`` / ``relationship_ids``)
        so the partial file matches the KB convention exactly — it carries
        the raw chunks, nothing else.
        """
        final = self._read_parquet("final_text_units.parquet")
        partial_key = f"{_OUTPUT_FOLDER}/partial_text_units.parquet"
        if final.empty:
            # Project was emptied (last observation deleted) — drop the
            # mirror so the next ``load_artifacts`` returns an empty df
            # without a stale partial.
            if self.storage.exists(partial_key):
                self.storage.delete(partial_key)
            return
        keep_cols = [
            c for c in (
                "id", "text", "n_tokens", "document_id", "document_ids",
                "observed_at", "confidence", "source",
            )
            if c in final.columns
        ]
        self._write_parquet("partial_text_units.parquet", final[keep_cols])

    # ------------------------------------------------------------------ audit log

    def _append_history(self, op: str, payload: dict[str, Any]) -> None:
        line = json.dumps(
            {"ts": now_iso(), "op": op, **payload},
            default=str,
        )
        history = self.path / _HISTORY_FILE
        with history.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # ------------------------------------------------------------------ embeddings (optional)

    async def _maybe_embed(self, texts: list[str]) -> list[Optional[list[float]]]:
        if self.embeddings is None:
            return [None] * len(texts)
        embedded = await self.embeddings.embed_safe(texts, tag="entity_embedding")
        return embedded

    # ============================================================ write path
    # ------------------------------------------------------------------ add_observation

    async def add_observation(
        self,
        *,
        title: str,
        content: str,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        entities: Optional[list[dict[str, Any]]] = None,
        relationships: Optional[list[dict[str, Any]]] = None,
        observed_at: Optional[str] = None,
        confidence: float = 1.0,
        source: Optional[str] = None,
        related_to: Optional[list[str]] = None,
    ) -> Reply:
        """Write a markdown observation + merge agent-supplied entities/rels.

        Returns ``Reply.data = {observation_id, slug, file_path,
        new_entities, updated_entities, new_relationships}``.
        """
        warnings: list[str] = []
        next_steps: list[str] = []
        observed_at = observed_at or now_iso()
        tags = list(tags or [])
        entities = list(entities or [])
        relationships = list(relationships or [])

        # 1. Write the markdown file under memories/<category>/.
        file_path, slug = write_observation_file(
            project_path=self.path,
            title=title,
            content=content,
            category=category,
            tags=tags,
            observed_at=observed_at,
            confidence=confidence,
            source=source,
            related_to=related_to,
        )

        # Steps 2-8 + return Reply run inside try/except so any failure
        # rolls back the markdown file we just wrote — otherwise a retry
        # creates a ``<slug>-2.md`` collision. Parquet rows written before
        # the failure are NOT rolled back; deeper atomicity is a follow-up.
        try:
            # 2. Use FileLoader to chunk just this one file. Storage-relative key:
            rel_key = str(file_path.relative_to(self.path)).replace("\\", "/")
            docs_df, text_units_df, mapping = self.loader.build_text_units(keys=[rel_key])
            if docs_df.empty:
                return Reply(
                    ok=False,
                    error="FileLoader produced no documents — file may be empty.",
                )
    
            doc_id = str(docs_df.iloc[0]["id"])
            tu_ids = list(text_units_df["id"].astype(str))
    
            # 3. Merge into existing artefacts.
            existing_docs = self._read_parquet("final_docs.parquet")
            existing_tus = self._read_parquet("final_text_units.parquet")
            all_docs = pd.concat([existing_docs, docs_df], ignore_index=True) if not existing_docs.empty else docs_df
            # text_units need the entity_ids / relationship_ids columns; populate
            # them when the agent supplied entities/rels for this file.
            text_units_df = text_units_df.copy()
            text_units_df["entity_ids"] = [
                [e["name"].upper().strip() for e in entities] for _ in range(len(text_units_df))
            ]
            text_units_df["relationship_ids"] = [
                [f"{r['source'].upper()}|{r['target'].upper()}|{r.get('relationship_type', 'RELATED').upper()}"
                 for r in relationships]
                for _ in range(len(text_units_df))
            ]
            all_tus = (
                pd.concat([existing_tus, text_units_df], ignore_index=True)
                if not existing_tus.empty
                else text_units_df
            )
            self._write_parquet("final_docs.parquet", all_docs)
            self._write_parquet("final_text_units.parquet", all_tus)
            # mapping.json
            mapping_path = self.path / "mapping.json"
            existing_mapping: dict[str, Any] = {}
            if mapping_path.exists():
                try:
                    existing_mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    existing_mapping = {}
            existing_mapping.update(mapping)
            mapping_path.write_text(json.dumps(existing_mapping, indent=2), encoding="utf-8")
    
            # 4. Build _MergeEntity / _MergeRelationship from agent input.
            # Folder-as-community: when ``category`` is set the entities are
            # auto-tagged with that community id so multi-membership "just works".
            community_ids = [category] if category else []
            merge_ents: list[_MergeEntity] = []
            for spec in entities:
                name = str(spec["name"]).upper().strip()
                if not name:
                    warnings.append("Skipped entity with empty name.")
                    continue
                etype = str(spec.get("type", "CONCEPT")).upper().strip() or "CONCEPT"
                description = str(spec.get("description", "")).strip()
                if not description:
                    warnings.append(f"Entity {name!r} has empty description.")
                merge_ents.append(
                    _MergeEntity(
                        name=name,
                        type=etype,
                        description=description,
                        retrieval_queries=[str(q) for q in spec.get("retrieval_queries", []) or []],
                        text_unit_ids=set(tu_ids),
                        document_ids={doc_id},
                        community_ids=list(spec.get("community_ids") or community_ids),
                        observed_at=observed_at,
                        confidence=float(spec.get("confidence", confidence)),
                        source=spec.get("source", source),
                    )
                )
    
            merge_rels: list[_MergeRelationship] = []
            for spec in relationships:
                src = str(spec["source"]).upper().strip()
                tgt = str(spec["target"]).upper().strip()
                if not src or not tgt:
                    warnings.append("Skipped relationship with empty endpoint(s).")
                    continue
                rel_type = str(spec.get("relationship_type", "RELATED")).upper().strip() or "RELATED"
                description = str(spec.get("description", "")).strip()
                weight = float(spec.get("weight", 1.0))
                merge_rels.append(
                    _MergeRelationship(
                        source=src,
                        target=tgt,
                        relationship_type=rel_type,
                        description=description,
                        weight=weight,
                        text_unit_ids=set(tu_ids),
                        document_ids={doc_id},
                        observed_at=observed_at,
                        confidence=float(spec.get("confidence", confidence)),
                        source_attribution=spec.get("source", source),
                    )
                )
    
            # 5. Merge with existing parquets.
            existing_e = self._read_parquet("final_entities.parquet")
            existing_r = self._read_parquet("final_relationships.parquet")
            merged_e, new_e_names, updated_e_names = merge_entities(existing_e, merge_ents)
            valid_names = set(merged_e["name"]) if not merged_e.empty else set()
            merged_r, new_r_keys, updated_r_keys = merge_relationships(
                existing_r, merge_rels, valid_names
            )
            merged_e, merged_r = recompute_degrees(merged_e, merged_r)
    
            # 6. Optional re-embed of new + updated entities.
            affected_names = list(dict.fromkeys(new_e_names + updated_e_names))
            if affected_names and self.embeddings is not None and not merged_e.empty:
                embed_inputs = []
                for n in affected_names:
                    row = merged_e.loc[merged_e["name"] == n]
                    if row.empty:
                        embed_inputs.append("")
                        continue
                    r = row.iloc[0]
                    rq = _aslist(r.get("retrieval_queries"))
                    rq_text = " ".join(str(q) for q in rq)
                    embed_inputs.append(f"{n}: {r.get('description', '')} {rq_text}".strip())
                embeddings = await self._maybe_embed(embed_inputs)
                # ``.at`` lets us assign a list as a single cell value without
                # pandas trying to broadcast it across rows.
                for n, emb in zip(affected_names, embeddings):
                    if emb is None:
                        continue
                    idxs = merged_e.index[merged_e["name"] == n]
                    for idx in idxs:
                        merged_e.at[idx, "description_embedding"] = emb
            elif affected_names and self.embeddings is None:
                warnings.append(
                    "No embeddings client configured — entities written without "
                    "description_embedding. Semantic search will be degraded until you "
                    "configure ``embeddings`` and call MemoryProject.reembed()."
                )
    
            # 7. Compute the folder-threshold nudge BEFORE persisting so a
            #    defensive crash here can't leave half-written parquets +
            #    .md on disk (which used to trigger duplicate "-2.md" files
            #    when the agent retried). ``_aslist`` normalises pandas
            #    round-tripped numpy arrays — ``cids or []`` would raise
            #    the ambiguous-truth error when cids is a multi-element
            #    array.
            if category and not merged_e.empty:
                cat_entities = merged_e["community_ids"].apply(
                    lambda cids: category in _aslist(cids)
                ).sum()
                if cat_entities >= 5:
                    next_steps.append(
                        f"folder '{category}' now has {int(cat_entities)} entities — "
                        f"consider writing memories/{category}/meta.md"
                    )

            # 8. Persist.
            self._write_parquet("final_entities.parquet", merged_e)
            self._write_parquet("final_relationships.parquet", merged_r)
            self._sync_partial_text_units()
    
            self._append_history(
                "add_observation",
                {
                    "observation_id": doc_id,
                    "slug": slug,
                    "file_path": str(file_path),
                    "category": category,
                    "new_entities": new_e_names,
                    "updated_entities": updated_e_names,
                    "new_relationships": [
                        f"{k[0]}|{k[1]}|{k[2]}" for k in new_r_keys
                    ],
                },
            )
            touch_indexed(self.path)
    
            return Reply(
                ok=True,
                data={
                    "observation_id": doc_id,
                    "slug": slug,
                    "file_path": str(file_path),
                    "category": category,
                    "new_entities": new_e_names,
                    "updated_entities": updated_e_names,
                    "new_relationships": [
                        f"{k[0]}|{k[1]}|{k[2]}" for k in new_r_keys
                    ],
                },
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception:
            # Roll back the markdown file so a retry won't collide.
            file_path.unlink(missing_ok=True)
            raise

    # ============================================================ tools (B5)
    # ------------------------------------------------------------------ add_entity

    async def add_entity(
        self,
        *,
        name: str,
        type: str,
        description: str,
        retrieval_queries: Optional[list[str]] = None,
        community_ids: Optional[list[str]] = None,
        confidence: float = 1.0,
        source: Optional[str] = None,
        observed_at: Optional[str] = None,
    ) -> Reply:
        """Declare a stand-alone entity without an underlying observation file.

        Useful when the agent wants to assert a fact ("X exists, is a PERSON")
        without writing a memory. A warning fires because there's no source
        provenance — the entity has empty ``text_unit_ids`` and
        ``document_ids``.
        """
        warnings: list[str] = []
        next_steps: list[str] = []
        name = name.upper().strip()
        if not name:
            return Reply(ok=False, error="Entity name is required.")
        warnings.append(
            "Entity has no underlying observation — consider calling "
            "add_observation() instead so the fact has source provenance."
        )

        existing_e = self._read_parquet("final_entities.parquet")
        ent = _MergeEntity(
            name=name,
            type=type.upper().strip() or "CONCEPT",
            description=description,
            retrieval_queries=list(retrieval_queries or []),
            text_unit_ids=set(),
            document_ids=set(),
            community_ids=list(community_ids or []),
            observed_at=observed_at or now_iso(),
            confidence=confidence,
            source=source,
        )
        merged_e, new_names, updated_names = merge_entities(existing_e, [ent])
        # Re-embed if possible (single entity, cheap call).
        if (new_names or updated_names) and self.embeddings is not None:
            rq_text = " ".join(ent.retrieval_queries)
            embeds = await self._maybe_embed(
                [f"{name}: {description} {rq_text}".strip()]
            )
            if embeds and embeds[0] is not None:
                idxs = merged_e.index[merged_e["name"] == name]
                for idx in idxs:
                    merged_e.at[idx, "description_embedding"] = embeds[0]
        existing_r = self._read_parquet("final_relationships.parquet")
        merged_e, merged_r = recompute_degrees(merged_e, existing_r)
        self._write_parquet("final_entities.parquet", merged_e)
        self._write_parquet("final_relationships.parquet", merged_r)
        self._append_history(
            "add_entity",
            {"name": name, "new": bool(new_names), "updated": bool(updated_names)},
        )
        return Reply(
            ok=True,
            data={
                "name": name,
                "was_new": bool(new_names),
                "was_updated": bool(updated_names),
            },
            warnings=warnings,
            next_steps=next_steps,
        )

    # ------------------------------------------------------------------ add_relationship

    async def add_relationship(
        self,
        *,
        source: str,
        target: str,
        description: str,
        relationship_type: str = "RELATED",
        weight: float = 1.0,
        confidence: float = 1.0,
        observed_at: Optional[str] = None,
        source_attribution: Optional[str] = None,
    ) -> Reply:
        warnings: list[str] = []
        src = source.upper().strip()
        tgt = target.upper().strip()
        if not src or not tgt:
            return Reply(ok=False, error="source and target are both required.")
        if src == tgt:
            return Reply(ok=False, error="self-loops are not allowed.")
        rel_type = relationship_type.upper().strip() or "RELATED"

        # Endpoint existence check.
        existing_e = self._read_parquet("final_entities.parquet")
        valid_names = set(existing_e["name"]) if not existing_e.empty else set()
        missing = [n for n in (src, tgt) if n not in valid_names]
        if missing:
            return Reply(
                ok=False,
                error=(
                    f"Endpoint(s) not found in final_entities: {missing}. "
                    "Call add_entity() first."
                ),
                data={"missing_entities": missing},
            )
        # Vocabulary warning.
        if self.config.indexing.relationship_types and rel_type not in (
            t.upper() for t in self.config.indexing.relationship_types
        ):
            warnings.append(
                f"relationship_type {rel_type!r} not in indexing.relationship_types. "
                "Allowed: " + ", ".join(self.config.indexing.relationship_types)
            )

        existing_r = self._read_parquet("final_relationships.parquet")
        rel = _MergeRelationship(
            source=src,
            target=tgt,
            relationship_type=rel_type,
            description=description,
            weight=weight,
            text_unit_ids=set(),
            document_ids=set(),
            observed_at=observed_at or now_iso(),
            confidence=confidence,
            source_attribution=source_attribution,
        )
        merged_r, new_keys, updated_keys = merge_relationships(
            existing_r, [rel], valid_names
        )
        existing_e, merged_r = recompute_degrees(existing_e, merged_r)
        self._write_parquet("final_entities.parquet", existing_e)
        self._write_parquet("final_relationships.parquet", merged_r)
        self._append_history(
            "add_relationship",
            {
                "source": src,
                "target": tgt,
                "relationship_type": rel_type,
                "was_new": bool(new_keys),
                "was_updated": bool(updated_keys),
            },
        )
        return Reply(
            ok=True,
            data={
                "source": src,
                "target": tgt,
                "relationship_type": rel_type,
                "was_new": bool(new_keys),
                "was_updated": bool(updated_keys),
            },
            warnings=warnings,
        )

    # ------------------------------------------------------------------ add_community

    def add_community(
        self,
        *,
        community_id: str,
        title: str,
        member_entity_names: list[str],
        kind: str = "folder",
        report_content: Optional[str] = None,
        findings: Optional[list[dict[str, str]]] = None,
        rank: float = 5.0,
        level: int = 0,
    ) -> Reply:
        """Declare a community (typically folder-as-community).

        ``member_entity_names`` must all exist in ``final_entities``. The
        community is appended to each member's ``community_ids`` list, and a
        row is added to ``final_communities`` (+ optional report).
        """
        warnings: list[str] = []
        existing_e = self._read_parquet("final_entities.parquet")
        valid_names = set(existing_e["name"]) if not existing_e.empty else set()
        upper_members = [n.upper().strip() for n in member_entity_names]
        missing = [n for n in upper_members if n not in valid_names]
        if missing:
            return Reply(
                ok=False,
                error=f"members not in final_entities: {missing}",
                data={"missing_entities": missing},
            )

        # Append community_id to each member's community_ids list.
        existing_e = existing_e.copy()
        for name in upper_members:
            idxs = existing_e.index[existing_e["name"] == name]
            for idx in idxs:
                cids = list(_aslist(existing_e.at[idx, "community_ids"]))
                if community_id not in cids:
                    cids.append(community_id)
                existing_e.at[idx, "community_ids"] = cids
        self._write_parquet("final_entities.parquet", existing_e)

        # Communities row.
        comm_df = self._read_parquet("final_communities.parquet")
        new_row = {
            "id": f"{level}-{community_id}",
            "level": int(level),
            "community": str(community_id),
            "title": title,
            "entity_ids": sorted(upper_members),
            "size": len(upper_members),
            "kind": kind,
        }
        if not comm_df.empty:
            comm_df = comm_df[comm_df["community"].astype(str) != str(community_id)]
            comm_df = pd.concat([comm_df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            comm_df = pd.DataFrame([new_row])
        self._write_parquet("final_communities.parquet", comm_df)

        # Optional report row.
        if report_content is not None:
            reports = self._read_parquet("final_community_reports.parquet")
            new_report = {
                "id": new_row["id"],
                "community": str(community_id),
                "level": int(level),
                "title": title,
                "summary": (report_content.splitlines()[0] if report_content else "")[:200],
                "full_content": report_content,
                "full_content_json": json.dumps(
                    {
                        "title": title,
                        "summary": (report_content.splitlines()[0] if report_content else "")[:200],
                        "findings": findings or [],
                    }
                ),
                "rank": float(rank),
                "rank_explanation": "",
                "findings": findings or [],
                "source": "agent",
                "source_path": None,
            }
            if not reports.empty:
                reports = reports[reports["community"].astype(str) != str(community_id)]
                reports = pd.concat([reports, pd.DataFrame([new_report])], ignore_index=True)
            else:
                reports = pd.DataFrame([new_report])
            self._write_parquet("final_community_reports.parquet", reports)

        if len(upper_members) < 3:
            warnings.append(
                f"Community {community_id!r} has only {len(upper_members)} members; "
                "reports are typically more useful at ≥3."
            )

        self._append_history(
            "add_community",
            {
                "community_id": community_id,
                "kind": kind,
                "members": upper_members,
                "has_report": report_content is not None,
            },
        )
        return Reply(
            ok=True,
            data={
                "community_id": community_id,
                "members": upper_members,
                "size": len(upper_members),
            },
            warnings=warnings,
        )

    # ------------------------------------------------------------------ update_community_report

    def update_community_report(
        self,
        *,
        community_id: str,
        title: str,
        content: str,
        findings: Optional[list[dict[str, str]]] = None,
        rank: float = 5.0,
    ) -> Reply:
        reports = self._read_parquet("final_community_reports.parquet")
        comm_df = self._read_parquet("final_communities.parquet")
        if comm_df.empty or str(community_id) not in set(comm_df["community"].astype(str)):
            return Reply(
                ok=False,
                error=f"community {community_id!r} not found in final_communities.",
            )
        level = int(comm_df.loc[comm_df["community"].astype(str) == str(community_id), "level"].iloc[0])
        new_report = {
            "id": f"{level}-{community_id}",
            "community": str(community_id),
            "level": level,
            "title": title,
            "summary": (content.splitlines()[0] if content else "")[:200],
            "full_content": content,
            "full_content_json": json.dumps(
                {
                    "title": title,
                    "summary": (content.splitlines()[0] if content else "")[:200],
                    "findings": findings or [],
                }
            ),
            "rank": float(rank),
            "rank_explanation": "",
            "findings": findings or [],
            "source": "agent",
            "source_path": None,
        }
        if not reports.empty:
            reports = reports[reports["community"].astype(str) != str(community_id)]
            reports = pd.concat([reports, pd.DataFrame([new_report])], ignore_index=True)
        else:
            reports = pd.DataFrame([new_report])
        self._write_parquet("final_community_reports.parquet", reports)
        self._append_history(
            "update_community_report", {"community_id": community_id, "title": title}
        )
        return Reply(ok=True, data={"community_id": community_id})

    # ------------------------------------------------------------------ delete_observation

    def delete_observation(self, slug: str, reason: Optional[str] = None) -> Reply:
        """Remove an observation file + strip its text_unit refs from entities/rels.

        Orphaned entities/relationships (those whose only TU was the deleted
        file) are pruned.
        """
        # Locate the file by slug.
        memories_root = self.path / _MEMORIES_FOLDER
        matches = list(memories_root.rglob(f"{slug}.md"))
        if not matches:
            return Reply(ok=False, error=f"no observation with slug {slug!r} found.")
        file_path = matches[0]

        docs = self._read_parquet("final_docs.parquet")
        if docs.empty:
            return Reply(ok=False, error="no docs parquet — nothing to delete.")
        rel_key = str(file_path.relative_to(self.path)).replace("\\", "/")
        doc_row = docs[docs["path"] == rel_key]
        if doc_row.empty:
            return Reply(ok=False, error=f"no doc found with path {rel_key!r}.")
        doc_id = str(doc_row.iloc[0]["id"])
        tu_ids = set(_aslist(doc_row.iloc[0].get("text_unit_ids")))

        # Strip TU refs from entities and rels, prune orphans.
        ents = self._read_parquet("final_entities.parquet")
        rels = self._read_parquet("final_relationships.parquet")
        if not ents.empty:
            ents = ents.copy()
            # Compute "was this entity backed by the deleted observation?"
            # *before* stripping, so we can tell post-strip empties from
            # always-empty standalone entities.
            was_backed_by_deleted = ents["document_ids"].apply(
                lambda x: doc_id in _aslist(x)
            )
            ents["text_unit_ids"] = ents["text_unit_ids"].apply(
                lambda x: [t for t in _aslist(x) if t not in tu_ids]
            )
            ents["document_ids"] = ents["document_ids"].apply(
                lambda x: [d for d in _aslist(x) if d != doc_id]
            )
            has_remaining_tus = ents["text_unit_ids"].apply(
                lambda x: bool(_aslist(x))
            )
            # Drop an entity only when it *was* backed by the deleted doc AND
            # has nothing left. Standalone (never-backed) entities are kept.
            keep = has_remaining_tus | (~was_backed_by_deleted)
            ents = ents.loc[keep].copy()
        if not rels.empty:
            rels = rels.copy()
            rels["text_unit_ids"] = rels["text_unit_ids"].apply(
                lambda x: [t for t in _aslist(x) if t not in tu_ids]
            )
            rels["document_ids"] = rels["document_ids"].apply(
                lambda x: [d for d in _aslist(x) if d != doc_id]
            )
            valid_names = set(ents["name"]) if not ents.empty else set()
            keep_r = (
                rels["source"].isin(valid_names) & rels["target"].isin(valid_names)
            )
            rels = rels.loc[keep_r].copy()
        ents, rels = recompute_degrees(ents, rels)
        self._write_parquet("final_entities.parquet", ents)
        self._write_parquet("final_relationships.parquet", rels)

        # Remove the doc row + TUs.
        tus = self._read_parquet("final_text_units.parquet")
        if not tus.empty:
            tus = tus[~tus["id"].astype(str).isin(tu_ids)].copy()
            self._write_parquet("final_text_units.parquet", tus)
        docs = docs[docs["id"].astype(str) != doc_id].copy()
        self._write_parquet("final_docs.parquet", docs)
        # Mirror to partial_text_units so GRAIL.delete / GRAIL.edit work
        # on this memory project. See ``_sync_partial_text_units`` for why.
        self._sync_partial_text_units()

        # Update mapping.json.
        mapping_path = self.path / "mapping.json"
        if mapping_path.exists():
            try:
                mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
                mapping.pop(doc_id, None)
                mapping_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
            except (json.JSONDecodeError, OSError):
                pass

        # Remove the file last so failures above don't leave a missing file.
        file_path.unlink(missing_ok=True)
        self._append_history(
            "delete_observation",
            {"slug": slug, "doc_id": doc_id, "reason": reason},
        )
        return Reply(
            ok=True,
            data={"slug": slug, "doc_id": doc_id, "file_path": str(file_path)},
        )

    # ------------------------------------------------------------------ update_observation

    async def update_observation(
        self,
        slug: str,
        *,
        content: Optional[str] = None,
        title: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        entities: Optional[list[dict[str, Any]]] = None,
        relationships: Optional[list[dict[str, Any]]] = None,
        observed_at: Optional[str] = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
    ) -> Reply:
        """Update by delete + re-add. Preserves the slug when content changes.

        Memory-mode semantics: edits are full rewrites. The agent passes the
        new body (and optionally new entities/relationships); the old file +
        its TU references are stripped, the new content is written and
        merged. The slug stays the same unless the title changes.
        """
        memories_root = self.path / _MEMORIES_FOLDER
        matches = list(memories_root.rglob(f"{slug}.md"))
        if not matches:
            return Reply(ok=False, error=f"no observation with slug {slug!r}.")
        file_path = matches[0]
        # Read current frontmatter+body to preserve unspecified fields.
        from grail.indexing.loader import parse_frontmatter
        text = file_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)

        new_title = title or fm.get("title") or slug
        new_category = category if category is not None else fm.get("category")
        new_tags = tags if tags is not None else list(fm.get("tags") or [])
        new_observed = observed_at or fm.get("observed_at")
        new_confidence = (
            confidence if confidence is not None else float(fm.get("confidence", 1.0))
        )
        new_source = source if source is not None else fm.get("source")
        new_content = content if content is not None else body

        # Delete the old file/refs first.
        del_reply = self.delete_observation(slug, reason="update_observation")
        if not del_reply.ok:
            return del_reply
        # Re-add.
        return await self.add_observation(
            title=new_title,
            content=new_content,
            category=new_category,
            tags=new_tags,
            entities=entities,
            relationships=relationships,
            observed_at=new_observed,
            confidence=new_confidence,
            source=new_source,
        )

    # ============================================================ reads (B6)
    # ------------------------------------------------------------------ find_similar_entity

    async def find_similar_entity(
        self, name: str, *, top_k: int = 5
    ) -> Reply:
        """Return entities with similar names/descriptions to ``name``.

        Tries exact match, then name-embedding cosine (if embeddings
        configured), then Jaro-Winkler edit distance. Used by the agent's
        skill prompt to check for existing matches *before* adding.
        """
        candidates: list[SimilarEntity] = []
        target = name.upper().strip()
        ents = self._read_parquet("final_entities.parquet")
        if ents.empty:
            return Reply(ok=True, data={"query": name, "candidates": []})

        # Exact match short-circuits.
        exact = ents[ents["name"].str.upper() == target]
        if not exact.empty:
            for _, row in exact.iterrows():
                candidates.append(
                    SimilarEntity(
                        name=row["name"],
                        similarity=1.0,
                        method="exact",
                        description=row.get("description"),
                        type=row.get("type"),
                    )
                )

        # Edit-distance fallback (cheap, always available).
        for _, row in ents.iterrows():
            n = str(row["name"])
            if n.upper() == target:
                continue
            sim = _jaro_winkler(target, n.upper())
            if sim >= 0.85:
                candidates.append(
                    SimilarEntity(
                        name=n,
                        similarity=float(sim),
                        method="edit_distance",
                        description=row.get("description"),
                        type=row.get("type"),
                    )
                )

        # Embedding cosine — only if embeddings configured.
        if self.embeddings is not None:
            embedded = await self._maybe_embed([name])
            qvec = embedded[0]
            if qvec is not None:
                qarr = _np_array(qvec)
                for _, row in ents.iterrows():
                    emb = row.get("description_embedding")
                    if emb is None:
                        continue
                    try:
                        score = float(_cosine(qarr, _np_array(emb)))
                    except (ValueError, TypeError):
                        continue
                    if score >= 0.7:
                        candidates.append(
                            SimilarEntity(
                                name=row["name"],
                                similarity=score,
                                method="embedding",
                                description=row.get("description"),
                                type=row.get("type"),
                            )
                        )

        # Dedup by (name, method) keeping the best score.
        seen: dict[tuple[str, str], SimilarEntity] = {}
        for c in candidates:
            k = (c.name, c.method)
            if k not in seen or c.similarity > seen[k].similarity:
                seen[k] = c
        ranked = sorted(seen.values(), key=lambda c: c.similarity, reverse=True)[:top_k]
        return Reply(
            ok=True,
            data={
                "query": name,
                "candidates": [
                    {
                        "name": c.name,
                        "similarity": c.similarity,
                        "method": c.method,
                        "description": c.description,
                        "type": c.type,
                    }
                    for c in ranked
                ],
            },
        )

    # ------------------------------------------------------------------ list_*

    def list_categories(self) -> Reply:
        """Distinct ``category`` values across documents + the on-disk tree."""
        cats: set[str] = set()
        docs = self._read_parquet("final_docs.parquet")
        if not docs.empty and "category" in docs.columns:
            for v in docs["category"].dropna():
                if v:
                    cats.add(str(v))
        # Also walk the on-disk memories/ tree so empty (no-content-yet)
        # folders are visible.
        memories_root = self.path / _MEMORIES_FOLDER
        if memories_root.exists():
            for sub in memories_root.rglob("*"):
                if sub.is_dir() and sub != memories_root:
                    rel = sub.relative_to(memories_root)
                    cats.add(str(rel).replace("\\", "/"))
        return Reply(ok=True, data={"categories": sorted(cats)})

    def list_entities(
        self,
        *,
        category: Optional[str] = None,
        type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Reply:
        ents = self._read_parquet("final_entities.parquet")
        if ents.empty:
            return Reply(ok=True, data={"entities": []})
        mask = pd.Series(True, index=ents.index)
        if category:
            # Same numpy-ndarray fix as add_observation.
            mask &= ents["community_ids"].apply(
                lambda cids: category in _aslist(cids)
            )
        if type:
            mask &= ents["type"].str.upper() == type.upper()
        view = ents.loc[mask]
        if limit is not None:
            view = view.head(int(limit))
        out = [
            {
                "name": r["name"],
                "type": r["type"],
                "description": r.get("description", ""),
                "community_ids": _aslist(r.get("community_ids")),
                "observed_at": r.get("observed_at"),
                "confidence": r.get("confidence"),
                "degree": int(r.get("degree", 0) or 0),
            }
            for _, r in view.iterrows()
        ]
        return Reply(ok=True, data={"entities": out, "total": int(mask.sum())})

    def list_communities(self) -> Reply:
        comms = self._read_parquet("final_communities.parquet")
        if comms.empty:
            return Reply(ok=True, data={"communities": []})
        out = [
            {
                "id": r["community"],
                "title": r["title"],
                "level": int(r["level"]),
                "size": int(r["size"]),
                "kind": r.get("kind", "leiden"),
            }
            for _, r in comms.iterrows()
        ]
        return Reply(ok=True, data={"communities": out})

    def list_observations(
        self,
        *,
        category: Optional[str] = None,
        since: Optional[str] = None,
        before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Reply:
        docs = self._read_parquet("final_docs.parquet")
        if docs.empty:
            return Reply(ok=True, data={"observations": []})
        tus = self._read_parquet("final_text_units.parquet")
        # Approximate observed_at per doc by taking the max across its TUs.
        doc_to_observed: dict[str, Optional[str]] = {}
        if not tus.empty and "observed_at" in tus.columns:
            for _, tu in tus.iterrows():
                doc_id = str(tu.get("document_id"))
                obs = tu.get("observed_at")
                if not obs or pd.isna(obs):
                    continue
                cur = doc_to_observed.get(doc_id)
                if cur is None or str(obs) > cur:
                    doc_to_observed[doc_id] = str(obs)

        out = []
        for _, row in docs.iterrows():
            cat = row.get("category")
            observed = doc_to_observed.get(str(row["id"]))
            if category and (not cat or not _category_matches(str(cat), category)):
                continue
            if since and (not observed or observed < since):
                continue
            if before and (observed and observed >= before):
                continue
            out.append(
                {
                    "id": row["id"],
                    "title": row.get("title"),
                    "path": row.get("path"),
                    "category": cat,
                    "tags": _aslist(row.get("tags")),
                    "observed_at": observed,
                }
            )
        if limit is not None:
            out = out[: int(limit)]
        return Reply(ok=True, data={"observations": out})

    # ------------------------------------------------------------------ recall (Phase C — proper search mode)

    async def recall(
        self,
        query: Optional[str] = None,
        *,
        mode: str = "recall",
        since: Optional[str] = None,
        before: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[list[str]] = None,
        entity: Optional[str] = None,
        entity_names: Optional[list[str]] = None,
        type: Optional[str] = None,
        entity_types: Optional[list[str]] = None,
        min_confidence: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> Reply:
        """Recall observations / entities matching a structural + optional query.

        ``mode`` selects the underlying search:
          * ``recall`` (default): pure pandas filter, no LLM, no embedding.
            ``query`` is ignored. Returns observations + entities + text_units.
          * ``cascade``, ``local``, ``document``, ``global``: runs the named
            search with the filter applied as a modifier, requires ``query``.
        """
        from grail.query.recall_filter import RecallFilter
        from grail.query.recall_search import RecallSearch

        all_tags: list[str] = []
        if tag:
            all_tags.append(tag)
        if tags:
            all_tags.extend(tags)
        all_entities: list[str] = []
        if entity:
            all_entities.append(entity)
        if entity_names:
            all_entities.extend(entity_names)
        all_types: list[str] = []
        if type:
            all_types.append(type)
        if entity_types:
            all_types.extend(entity_types)

        rfilter = RecallFilter(
            since=since,
            before=before,
            category=category,
            tags=all_tags,
            entity_names=all_entities,
            entity_types=all_types,
            min_confidence=min_confidence,
        )

        if mode == "recall":
            recaller = RecallSearch(
                storage=self.storage,
                output_folder=_OUTPUT_FOLDER,
                reporter=self.reporter,
            )
            result = await recaller.asearch(rfilter, query=query, limit=limit)
            # Render observations from the matched documents so callers can
            # iterate rows directly (matches the Phase B contract that the
            # existing tests check).
            obs_rows = _docs_df_to_observations(
                result.context_data.get("documents", pd.DataFrame()),
                result.context_data.get("text_units", pd.DataFrame()),
            )
            ent_rows = _df_to_records(
                result.context_data.get("entities", pd.DataFrame()),
                columns=["name", "type", "description", "community_ids",
                         "observed_at", "confidence", "degree"],
            )
            return Reply(
                ok=True,
                data={
                    "mode": "recall",
                    "response": result.response,
                    "context_text": result.context_text,
                    "completion_time": result.completion_time,
                    "observations": obs_rows,
                    "entities": ent_rows,
                    "matches": {
                        k: int(len(v)) for k, v in result.context_data.items()
                        if hasattr(v, "__len__")
                    },
                },
            )

        # Non-recall modes need a query and an LLM. Defer construction so
        # tests that don't exercise them don't pay the import cost.
        if not query:
            return Reply(
                ok=False,
                error=f"mode={mode!r} requires a query.",
            )
        if self.config.llm is None:
            return Reply(
                ok=False,
                error=(
                    f"mode={mode!r} needs an LLM, but this project has no "
                    "llm config. Use mode='recall' for structural-only "
                    "recall, or configure llm in grail.yaml."
                ),
            )

        # Lazy-build clients only when actually needed.
        from grail.llm import EmbeddingClient, LLMClient

        llm = LLMClient(config=self.config.llm, endpoints=self.config.endpoints)
        embeds = self.embeddings or EmbeddingClient(
            config=self.config.embeddings, endpoints=self.config.endpoints
        )

        if mode == "cascade":
            from grail.query.cascade_search import CascadeSearch

            searcher = CascadeSearch(
                storage=self.storage,
                llm=llm,
                embeddings=embeds,
                output_folder=_OUTPUT_FOLDER,
                reporter=self.reporter,
            )
            result = await searcher.asearch(query, filter=rfilter)
        elif mode == "local":
            from grail.query.local_search import LocalSearch

            searcher = LocalSearch(
                storage=self.storage,
                llm=llm,
                embeddings=embeds,
                output_folder=_OUTPUT_FOLDER,
                reporter=self.reporter,
            )
            result = await searcher.asearch(query, filter=rfilter)
        elif mode == "global":
            from grail.query.global_search import GlobalSearch

            searcher = GlobalSearch(
                storage=self.storage,
                llm=llm,
                output_folder=_OUTPUT_FOLDER,
                reporter=self.reporter,
            )
            result = await searcher.asearch(query, filter=rfilter)
        else:
            return Reply(ok=False, error=f"unsupported mode {mode!r}.")

        return Reply(
            ok=True,
            data={
                "mode": mode,
                "response": result.response,
                "context_text": result.context_text,
                "completion_time": result.completion_time,
                "llm_calls": result.llm_calls,
            },
        )

    # ============================================================ consolidate (Phase D)
    # ------------------------------------------------------------------ consolidate

    def consolidate(self) -> Reply:
        """Run the proposal analyses and persist the result.

        Pure read pass — never mutates parquets. Returns a ``Reply`` whose
        ``data`` includes the proposal-set path, generated count by kind, and
        a few-line summary.
        """
        from grail.memory.consolidate import (
            build_snapshot,
            proposal_set_path,
            run_consolidate,
        )

        ents = self._read_parquet("final_entities.parquet")
        if len(ents) < self.config.memory.min_entities_for_consolidate:
            return Reply(
                ok=False,
                error=(
                    f"consolidate refuses below "
                    f"memory.min_entities_for_consolidate="
                    f"{self.config.memory.min_entities_for_consolidate} "
                    f"(currently {len(ents)} entities). Communities only become "
                    "useful at scale; until then, the agent can read the "
                    "underlying memory files directly."
                ),
                data={"entities": int(len(ents))},
            )

        snapshot = build_snapshot(
            entities=ents,
            relationships=self._read_parquet("final_relationships.parquet"),
            text_units=self._read_parquet("final_text_units.parquet"),
            documents=self._read_parquet("final_docs.parquet"),
            communities=self._read_parquet("final_communities.parquet"),
            community_reports=self._read_parquet("final_community_reports.parquet"),
        )
        ps = run_consolidate(snapshot, self.config.memory)
        path = proposal_set_path(self.path, output_folder=_OUTPUT_FOLDER)
        ps.save(path)
        # Audit + meta.
        by_kind: dict[str, int] = {}
        for p in ps.proposals:
            by_kind[p.kind] = by_kind.get(p.kind, 0) + 1
        self._append_history(
            "consolidate",
            {
                "proposal_set": str(path),
                "by_kind": by_kind,
                "total": len(ps.proposals),
            },
        )
        return Reply(
            ok=True,
            data={
                "proposal_set_path": str(path),
                "total": len(ps.proposals),
                "by_kind": by_kind,
                "graph_snapshot": dict(ps.graph_snapshot),
                "proposals": [
                    {
                        "id": p.id,
                        "kind": p.kind,
                        "confidence": p.confidence,
                        "rationale": p.rationale,
                    }
                    for p in ps.proposals
                ],
            },
        )

    # ------------------------------------------------------------------ list_proposals

    def list_proposals(
        self, *, status: Optional[str] = None
    ) -> Reply:
        """List proposals from the most-recent ``consolidate`` run."""
        from grail.memory.proposals import latest_proposal_set

        ps = latest_proposal_set(self.path, output_folder=_OUTPUT_FOLDER)
        if ps is None:
            return Reply(
                ok=True,
                data={"proposals": [], "set_path": None},
                next_steps=["call consolidate() to generate proposals"],
            )
        proposals = ps.proposals
        if status:
            proposals = [p for p in proposals if p.status == status]
        return Reply(
            ok=True,
            data={
                "set_path": str(ps.path) if ps.path else None,
                "proposals": [p.to_dict() for p in proposals],
            },
        )

    # ------------------------------------------------------------------ accept / reject

    def accept_proposal(self, proposal_id: str) -> Reply:
        """Apply a pending proposal. Mutation depends on the proposal kind."""
        from grail.memory.proposals import (
            latest_proposal_set,
            maybe_archive,
        )

        ps = latest_proposal_set(self.path, output_folder=_OUTPUT_FOLDER)
        if ps is None or ps.path is None:
            return Reply(
                ok=False,
                error="no proposal set found — run consolidate() first.",
            )
        proposal = ps.find(proposal_id)
        if proposal is None:
            return Reply(ok=False, error=f"no proposal matches id {proposal_id!r}.")
        if proposal.status not in {"pending", "accepted-pending-manual"}:
            return Reply(
                ok=False,
                error=f"proposal {proposal.id} is {proposal.status!r}, cannot accept.",
            )

        try:
            outcome = self._apply_proposal(proposal)
        except Exception as exc:  # pragma: no cover - defensive
            proposal.status = "pending"
            proposal.resolved_reason = f"apply failed: {type(exc).__name__}: {exc}"
            ps.save(ps.path)
            return Reply(ok=False, error=proposal.resolved_reason)

        proposal.applied_outcome = outcome.get("outcome", {})
        proposal.status = outcome.get("status", "accepted")
        proposal.resolved_at = now_iso()
        ps.save(ps.path)
        maybe_archive(ps.path, ps)

        self._append_history(
            "accept_proposal",
            {
                "proposal_id": proposal.id,
                "kind": proposal.kind,
                "status": proposal.status,
                "outcome": proposal.applied_outcome,
            },
        )
        return Reply(
            ok=True,
            data={
                "proposal_id": proposal.id,
                "kind": proposal.kind,
                "status": proposal.status,
                "outcome": proposal.applied_outcome,
            },
        )

    def reject_proposal(
        self, proposal_id: str, *, reason: Optional[str] = None
    ) -> Reply:
        from grail.memory.proposals import latest_proposal_set, maybe_archive

        ps = latest_proposal_set(self.path, output_folder=_OUTPUT_FOLDER)
        if ps is None or ps.path is None:
            return Reply(ok=False, error="no proposal set found.")
        proposal = ps.find(proposal_id)
        if proposal is None:
            return Reply(ok=False, error=f"no proposal matches id {proposal_id!r}.")
        if proposal.status != "pending":
            return Reply(
                ok=False,
                error=f"proposal {proposal.id} is {proposal.status!r}, cannot reject.",
            )
        proposal.status = "rejected"
        proposal.resolved_at = now_iso()
        proposal.resolved_reason = reason
        ps.save(ps.path)
        maybe_archive(ps.path, ps)
        self._append_history(
            "reject_proposal",
            {"proposal_id": proposal.id, "reason": reason},
        )
        return Reply(
            ok=True,
            data={"proposal_id": proposal.id, "status": "rejected"},
        )

    # ------------------------------------------------------------------ per-kind apply

    def _apply_proposal(self, proposal) -> dict[str, Any]:
        kind = proposal.kind
        if kind == "discover_community":
            return self._apply_discover_community(proposal)
        if kind == "move_entity":
            return self._apply_move_entity(proposal)
        if kind == "merge_aliases":
            return self._apply_merge_aliases(proposal)
        if kind == "split_folder":
            return self._apply_split_folder(proposal)
        raise ValueError(f"unsupported proposal kind: {kind!r}")

    def _apply_discover_community(self, proposal) -> dict[str, Any]:
        payload = proposal.payload
        suggested_id = str(payload.get("suggested_id") or f"discovered/{proposal.id}")
        members = [str(m) for m in payload.get("members") or []]
        if not members:
            raise ValueError("discover_community proposal has no members")
        reply = self.add_community(
            community_id=suggested_id,
            title=f"Discovered: {', '.join(members[:3])}{' …' if len(members) > 3 else ''}",
            member_entity_names=members,
            kind="discovered",
        )
        if not reply.ok:
            raise ValueError(reply.error or "add_community failed")
        return {
            "status": "accepted",
            "outcome": {
                "community_id": suggested_id,
                "members": members,
            },
        }

    def _apply_move_entity(self, proposal) -> dict[str, Any]:
        entity = str(proposal.payload.get("entity") or "").upper().strip()
        add_cids = [str(c) for c in proposal.payload.get("add_community_ids") or []]
        if not entity or not add_cids:
            raise ValueError("move_entity proposal missing entity or community ids")
        ents = self._read_parquet("final_entities.parquet")
        if ents.empty or entity not in set(ents["name"].astype(str)):
            raise ValueError(f"entity {entity!r} not found in final_entities")
        ents = ents.copy()
        idxs = ents.index[ents["name"] == entity]
        added: list[str] = []
        for idx in idxs:
            cids = _aslist(ents.at[idx, "community_ids"])
            for c in add_cids:
                if c not in cids:
                    cids.append(c)
                    added.append(c)
            ents.at[idx, "community_ids"] = cids
        self._write_parquet("final_entities.parquet", ents)
        # Also update final_communities so the new membership shows up in lists.
        comm = self._read_parquet("final_communities.parquet")
        for cid in set(added):
            level = 0
            row = {
                "id": f"{level}-{cid}",
                "level": level,
                "community": cid,
                "title": f"Discovered: {cid}",
                "entity_ids": [entity],
                "size": 1,
                "kind": "discovered",
            }
            if comm.empty:
                comm = pd.DataFrame([row])
            elif cid not in set(comm["community"].astype(str)):
                comm = pd.concat([comm, pd.DataFrame([row])], ignore_index=True)
            else:
                # Append entity to the existing community row.
                mask = comm["community"].astype(str) == cid
                for i in comm.index[mask]:
                    members = _aslist(comm.at[i, "entity_ids"])
                    if entity not in members:
                        members.append(entity)
                    comm.at[i, "entity_ids"] = sorted(members)
                    comm.at[i, "size"] = len(members)
        self._write_parquet("final_communities.parquet", comm)
        return {
            "status": "accepted",
            "outcome": {"entity": entity, "added_community_ids": added},
        }

    def _apply_merge_aliases(self, proposal) -> dict[str, Any]:
        canonical = str(proposal.payload.get("canonical") or "").upper().strip()
        aliases = [str(a).upper().strip() for a in proposal.payload.get("aliases") or []]
        if not canonical or not aliases:
            raise ValueError("merge_aliases proposal missing canonical or aliases")

        ents = self._read_parquet("final_entities.parquet")
        rels = self._read_parquet("final_relationships.parquet")
        if ents.empty:
            raise ValueError("no entities to merge")
        ents = ents.copy()
        # Find canonical row; if absent, pick the first alias and rename it.
        if canonical not in set(ents["name"].astype(str)):
            for alias in aliases:
                if alias in set(ents["name"].astype(str)):
                    canonical = alias
                    aliases = [a for a in aliases if a != canonical]
                    break
        canonical_mask = ents["name"] == canonical
        if not canonical_mask.any():
            raise ValueError(f"canonical {canonical!r} not found")
        canon_idx = ents.index[canonical_mask][0]

        merged_tus = set(_aslist(ents.at[canon_idx, "text_unit_ids"]))
        merged_docs = set(_aslist(ents.at[canon_idx, "document_ids"]))
        merged_rq = list(_aslist(ents.at[canon_idx, "retrieval_queries"]))
        merged_cids = list(_aslist(ents.at[canon_idx, "community_ids"]))
        merged_alias_names: list[str] = []
        for alias in aliases:
            if alias not in set(ents["name"].astype(str)):
                continue
            alias_mask = ents["name"] == alias
            alias_idx = ents.index[alias_mask][0]
            merged_tus |= set(_aslist(ents.at[alias_idx, "text_unit_ids"]))
            merged_docs |= set(_aslist(ents.at[alias_idx, "document_ids"]))
            for q in _aslist(ents.at[alias_idx, "retrieval_queries"]):
                if q not in merged_rq:
                    merged_rq.append(q)
            for c in _aslist(ents.at[alias_idx, "community_ids"]):
                if c not in merged_cids:
                    merged_cids.append(c)
            merged_alias_names.append(alias)
            ents = ents[ents["name"] != alias].copy()

        # Re-find canonical index (concat may have changed positions).
        canon_idx = ents.index[ents["name"] == canonical][0]
        ents.at[canon_idx, "text_unit_ids"] = sorted(merged_tus)
        ents.at[canon_idx, "document_ids"] = sorted(merged_docs)
        ents.at[canon_idx, "retrieval_queries"] = merged_rq
        ents.at[canon_idx, "community_ids"] = merged_cids
        # Stale embedding — the alias may have changed the entity's "voice".
        ents.at[canon_idx, "description_embedding"] = None

        # Rewrite relationships.
        if not rels.empty:
            rels = rels.copy()
            for alias in merged_alias_names:
                rels.loc[rels["source"] == alias, "source"] = canonical
                rels.loc[rels["target"] == alias, "target"] = canonical
            # Drop self-loops created by the rewrite.
            rels = rels[rels["source"] != rels["target"]].copy()
            # Dedup by (src, tgt, relationship_type); keep first.
            rels["__k__"] = (
                rels["source"].astype(str)
                + "|"
                + rels["target"].astype(str)
                + "|"
                + rels.get("relationship_type", pd.Series(["RELATED"] * len(rels))).fillna("RELATED").astype(str)
            )
            rels = rels.drop_duplicates(subset="__k__", keep="first").drop(columns="__k__")
        ents, rels = recompute_degrees(ents, rels)
        self._write_parquet("final_entities.parquet", ents)
        self._write_parquet("final_relationships.parquet", rels)
        return {
            "status": "accepted",
            "outcome": {
                "canonical": canonical,
                "merged_aliases": merged_alias_names,
            },
        }

    def _apply_split_folder(self, proposal) -> dict[str, Any]:
        """Generate a shell script the agent reviews and runs to move files.

        Does not move files itself — filesystem mutations are destructive and
        memory observations live in git.
        """
        folder = str(proposal.payload.get("folder") or "")
        split = proposal.payload.get("suggested_split") or []
        if not folder or not split:
            raise ValueError("split_folder proposal missing folder or suggested_split")

        proposals_dir = self.path / _OUTPUT_FOLDER / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        script_path = proposals_dir / f"{proposal.id}_apply.sh"
        lines: list[str] = [
            "#!/usr/bin/env bash",
            "# Auto-generated by MemoryProject.accept_proposal for proposal",
            f"# {proposal.id}. Review carefully before running.",
            "set -euo pipefail",
            f'cd "$(dirname "$0")/../../memories/{folder}"',
        ]
        # For each sub-cluster, suggest creating a sub-folder and moving the
        # observation files whose document_ids belong to those entities.
        ents = self._read_parquet("final_entities.parquet")
        docs = self._read_parquet("final_docs.parquet")
        for cluster in split:
            sub_id = str(cluster.get("id") or "")
            sub_folder = sub_id.split("/", 1)[1] if "/" in sub_id else sub_id
            members = [str(m).upper() for m in cluster.get("members") or []]
            lines.append("")
            lines.append(f'mkdir -p "{sub_folder}"')
            doc_ids: set[str] = set()
            if not ents.empty:
                mask = ents["name"].isin(members)
                for _, row in ents.loc[mask].iterrows():
                    for d in _aslist(row.get("document_ids")):
                        doc_ids.add(str(d))
            if not docs.empty and doc_ids:
                for _, row in docs[docs["id"].astype(str).isin(doc_ids)].iterrows():
                    p = str(row.get("path") or "")
                    if not p:
                        continue
                    # Files live under memories/<folder>/; the script cd'd there.
                    rel = p.replace(f"memories/{folder}/", "", 1)
                    lines.append(f'mv "{rel}" "{sub_folder}/"  # {row.get("title", "")}')
        script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        script_path.chmod(0o755)
        return {
            "status": "accepted-pending-manual",
            "outcome": {
                "apply_script": str(script_path),
                "note": "split_folder is destructive; review and run the script manually.",
            },
        }


# ---------------------------------------------------------------- module helpers


def _category_matches(value: str, pattern: str) -> bool:
    """Glob-style match: ``work/**`` matches ``work/clients/acme``."""
    import fnmatch

    return fnmatch.fnmatch(value, pattern) or value == pattern or value.startswith(pattern.rstrip("*"))


def _docs_df_to_observations(
    docs_df: pd.DataFrame, text_units_df: pd.DataFrame
) -> list[dict[str, Any]]:
    """Render the matched documents as a list-of-dicts shaped like list_observations."""
    if docs_df is None or docs_df.empty:
        return []
    # Build doc → max observed_at across its TUs.
    doc_to_observed: dict[str, Optional[str]] = {}
    if text_units_df is not None and not text_units_df.empty and "observed_at" in text_units_df.columns:
        for _, tu in text_units_df.iterrows():
            doc_id = str(tu.get("document_id"))
            obs = tu.get("observed_at")
            if not obs or pd.isna(obs):
                continue
            cur = doc_to_observed.get(doc_id)
            if cur is None or str(obs) > cur:
                doc_to_observed[doc_id] = str(obs)
    return [
        {
            "id": row["id"],
            "title": row.get("title"),
            "path": row.get("path"),
            "category": row.get("category"),
            "tags": _aslist(row.get("tags")),
            "observed_at": doc_to_observed.get(str(row["id"])),
        }
        for _, row in docs_df.iterrows()
    ]


def _df_to_records(
    df: pd.DataFrame, *, columns: list[str]
) -> list[dict[str, Any]]:
    """Project a DataFrame down to a list of dicts using only the requested columns."""
    if df is None or df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        rec: dict[str, Any] = {}
        for c in columns:
            v = row.get(c) if c in df.columns else None
            if c in ("community_ids", "tags") and not isinstance(v, list):
                v = _aslist(v)
            rec[c] = v
        out.append(rec)
    return out


def _jaro_winkler(s1: str, s2: str) -> float:
    """Pure-Python Jaro-Winkler similarity in [0, 1]."""
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
    # Winkler bonus: up to first 4 matching chars from the start, weight 0.1.
    prefix = 0
    for c1, c2 in zip(s1, s2):
        if c1 != c2:
            break
        prefix += 1
        if prefix == 4:
            break
    return jaro + prefix * 0.1 * (1 - jaro)


def _np_array(v):  # type: ignore[no-untyped-def]
    import numpy as np

    return np.asarray(v, dtype=float)


def _cosine(a, b) -> float:  # type: ignore[no-untyped-def]
    import numpy as np

    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


__all__ = ["MemoryProject"]

