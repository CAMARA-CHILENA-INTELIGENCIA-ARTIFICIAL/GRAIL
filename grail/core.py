"""
GRAIL — the top-level orchestrator.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

The :class:`GRAIL` class wires Config → Storage → LLM/Embedding clients →
Prompts → indexing stages → query stages. It exposes the user-level operations:

* :meth:`index` — full pipeline: ingest → chunk → entities → communities → reports.
* :meth:`search` — local or global search over an existing index.
* :meth:`create_entity_types` — LLM-driven entity-type discovery from the corpus.
* :meth:`append`, :meth:`edit`, :meth:`delete` — incremental updates (v0.1 stubs that
  re-build the affected stages; smarter incremental paths land in later phases).
* :meth:`status` — report which artefacts exist and when they were last touched.

This is the API the CLI and Python users hit. It deliberately doesn't expose the
internal extractor classes — those are reachable for advanced use via
``from grail.indexing import ...`` and ``from grail.query import ...``.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import networkx as nx
import pandas as pd

from grail._version import __version__ as _GRAIL_VERSION
from grail.config import Config, load_config
from grail.indexing import (
    CommunityExtractor,
    CommunityReportGenerator,
    EntityRelationshipExtractor,
    FileLoader,
    IncrementalCommunityExtractor,
    SummarizeExtractor,
)
from grail.indexing.run_manifest import (
    RunContext,
    generate_run_id,
    resolve_active_run_folder,
    run_folder,
    write_current_run,
    write_llm_calls_log,
    write_manifest,
    write_summary,
)
from grail.llm import CostTracker, EmbeddingClient, Endpoint, EndpointRegistry, LLMCache, LLMClient, RerankerClient
from grail.prompts import PromptRegistry
from grail.query import AgentSearch, DocumentSearch, GlobalSearch, LocalSearch
from grail.query.retrieval import SearchArtifacts, load_artifacts_for_search
from grail.reporting import NullReporter, Reporter
from grail.schemas import SearchResult
from grail.storage import LocalStorage, StorageBackend, get_backend
from grail.vectorstores import BaseVectorStore, LanceDBVectorStore, VectorStoreDocument

log = logging.getLogger("grail.core")


@dataclass
class GRAIL:
    """Top-level orchestrator.

    Build via :meth:`from_config` (recommended) or directly by passing all collaborators.
    """

    config: Config
    storage: StorageBackend
    llm: LLMClient
    embeddings: EmbeddingClient
    prompts: PromptRegistry
    cost_tracker: CostTracker = field(default_factory=CostTracker)
    reporter: Reporter = field(default_factory=NullReporter)
    reranker: Optional[RerankerClient] = None

    # ------------------------------------------------------------------ construction

    @classmethod
    def from_config(
        cls,
        config: Optional[Config | str | Path] = None,
        *,
        reporter: Optional[Reporter] = None,
        vectorstore: Optional[str] = None,
    ) -> "GRAIL":
        if not isinstance(config, Config):
            config = load_config(config)

        if vectorstore is not None:
            config.vectorstore.backend = vectorstore

        # Storage
        s_cfg = config.storage
        if s_cfg.backend == "local":
            storage = LocalStorage(root=s_cfg.root)
        else:
            storage = get_backend(
                s_cfg.backend,
                bucket=s_cfg.s3_bucket,
                prefix=s_cfg.s3_prefix,
                region_name=s_cfg.s3_region,
                endpoint_url=s_cfg.s3_endpoint_url,
            )

        # Endpoint registry, populated from the config's endpoints section.
        registry = EndpointRegistry(endpoints={})
        for name, ep_cfg in (config.endpoints or {}).items():
            registry.register(
                Endpoint(
                    name=name,
                    base_url=ep_cfg.base_url,
                    api_key_env=ep_cfg.api_key_env,
                    requires_key=ep_cfg.requires_key,
                    notes=ep_cfg.notes,
                )
            )

        # Cache
        cache: Optional[LLMCache] = None
        if config.llm.cache_enabled:
            cache_dir = config.llm.cache_dir or str(Path(config.resolved_root()) / "cache" / "llm")
            cache = LLMCache(directory=cache_dir, enabled=True)

        cost = CostTracker()
        # Merge user-supplied pricing on top of DEFAULT_PRICING.
        for key, rate in (config.llm.extra_pricing or {}).items():
            if not isinstance(rate, (list, tuple)) or len(rate) != 2:
                log.warning(
                    "Skipping extra_pricing entry %r — expected [prompt_per_1M, completion_per_1M].",
                    key,
                )
                continue
            cost.pricing[key] = (float(rate[0]), float(rate[1]))
        rep = reporter or NullReporter()

        llm = LLMClient(
            default_endpoint=config.llm.endpoint,
            default_model=config.llm.model,
            request_timeout=config.llm.request_timeout,
            max_retries=config.llm.max_retries,
            max_retry_wait=config.llm.max_retry_wait,
            sleep_on_rate_limit=config.llm.sleep_on_rate_limit,
            concurrent_requests=config.llm.concurrent_requests,
            endpoint_registry=registry,
            cache=cache,
            cost_tracker=cost,
            reporter=rep,
            debug=config.llm.debug,
        )
        embeddings = EmbeddingClient(
            default_endpoint=config.embeddings.endpoint,
            default_model=config.embeddings.model,
            encoding_format=config.embeddings.encoding_format,
            max_batch_size=config.embeddings.max_batch_size,
            concurrent_requests=config.embeddings.concurrent_requests,
            cost_tracker=cost,  # shared with LLMClient — single unified ledger
            request_timeout=config.embeddings.request_timeout,
            max_retries=config.embeddings.max_retries,
            max_retry_wait=config.embeddings.max_retry_wait,
            sleep_on_rate_limit=config.embeddings.sleep_on_rate_limit,
            endpoint_registry=registry,
            reporter=rep,
        )
        prompts = PromptRegistry(
            custom_paths=[Path(p) for p in config.prompts.custom_paths],
            strict=config.prompts.strict,
        )

        reranker: Optional[RerankerClient] = None
        if config.reranker.enabled:
            reranker = RerankerClient(
                default_endpoint=config.reranker.endpoint,
                default_model=config.reranker.model,
                base_url=config.reranker.base_url,
                request_timeout=config.reranker.request_timeout,
                endpoint_registry=registry,
                cost_tracker=cost,
                reporter=rep,
            )

        return cls(
            config=config,
            storage=storage,
            llm=llm,
            embeddings=embeddings,
            prompts=prompts,
            cost_tracker=cost,
            reporter=rep,
            reranker=reranker,
        )

    # ------------------------------------------------------------------ helpers

    # Active run state. Set when index() / append() / edit() / delete() runs;
    # falls back to the current.json pointer when ad-hoc operations (e.g. search
    # from a fresh process) need to read artefacts.
    _active_run: Optional[RunContext] = None

    def _base_output_folder(self) -> str:
        """The top-level output dir as declared in config (default ``"output"``)."""
        return self.config.indexing.output_folder

    def _output_folder(self) -> str:
        """Where stages read from / write to right now.

        * If a run is in progress, return its folder.
        * Else resolve via ``current.json`` (search / standalone operations).
        * Else fall back to the legacy flat path (so projects that pre-date
          the run-folder layout still work read-only).
        """
        if self._active_run is not None:
            return self._active_run.run_dir
        return resolve_active_run_folder(self.storage, self._base_output_folder())

    def _start_run(self, *, operation: str) -> RunContext:
        """Create a new run folder, snapshot the config, and stash the context."""
        base = self._base_output_folder()
        run_id = generate_run_id()
        run_dir = run_folder(base, run_id)
        self.storage.ensure_prefix(run_dir)
        ctx = RunContext(
            run_id=run_id,
            run_dir=run_dir,
            base_output_folder=base,
            config_snapshot=self.config.model_dump(mode="python"),
            grail_version=_GRAIL_VERSION,
        )
        self._active_run = ctx
        return ctx

    def _persist_run(
        self,
        ctx: RunContext,
        *,
        operation: str,
        files_processed: Optional[list[dict[str, Any]]] = None,
        counts: Optional[dict[str, Any]] = None,
    ) -> dict[str, str]:
        """Write manifest / summary / llm_calls.jsonl + update current.json.

        Returns the storage keys of the three written files so the CLI can
        surface them to the user.
        """
        manifest_key = write_manifest(
            self.storage, ctx, self.cost_tracker, files_processed=files_processed
        )
        calls_key = write_llm_calls_log(self.storage, ctx, self.cost_tracker)
        summary_key = write_summary(
            self.storage, ctx, self.cost_tracker, counts=counts or {}
        )
        write_current_run(
            self.storage, self._base_output_folder(), run_id=ctx.run_id, operation=operation
        )
        return {"manifest": manifest_key, "llm_calls": calls_key, "summary": summary_key}

    def _vector_store(self) -> Optional[BaseVectorStore]:
        cfg = self.config.vectorstore
        if isinstance(self.storage, LocalStorage):
            uri = str(self.storage.path_for(cfg.uri or cfg.backend))
        else:
            uri = cfg.uri or f"./{cfg.backend}"

        if cfg.backend == "lancedb":
            store = LanceDBVectorStore(collection_name=cfg.collection_name)
            store.connect(db_uri=uri)
            if self.storage.exists(uri + "/" + cfg.collection_name + ".lance") or (
                isinstance(self.storage, LocalStorage)
                and Path(uri, cfg.collection_name + ".lance").exists()
            ):
                try:
                    store.document_collection = store.db_connection.open_table(cfg.collection_name)
                except Exception:  # pragma: no cover
                    store.document_collection = None
            return store

        if cfg.backend == "faiss":
            from grail.vectorstores.faiss import FAISSVectorStore
            store = FAISSVectorStore(collection_name=cfg.collection_name)
            store.connect(db_uri=uri)
            return store

        if cfg.backend == "chromadb":
            from grail.vectorstores.chroma import ChromaDBVectorStore
            store = ChromaDBVectorStore(collection_name=cfg.collection_name)
            store.connect(db_uri=uri, distance_fn=cfg.distance_fn)
            return store

        return None

    # ------------------------------------------------------------------ INDEX

    async def index(self) -> dict[str, Any]:
        """Run the full indexing pipeline against the configured input folder."""
        ctx = self._start_run(operation="index")
        op = ctx.begin_operation("index")
        started = time.perf_counter()
        self.reporter.info(f"Starting run {ctx.run_id}")

        loader = self._make_loader()

        self.reporter.info("Step 1/4 — chunking source files")
        docs_df, text_units_df, mapping = loader.build_text_units()
        if docs_df.empty:
            ctx.finish_operation(op, ok=False, reason="no input files")
            self._persist_run(ctx, operation="index")
            self.reporter.warning("No input files found; aborting.")
            return {"ok": False, "reason": "no input files", "run_id": ctx.run_id, "run_dir": ctx.run_dir}
        loader.write_artifacts(docs_df, text_units_df, mapping)

        if self.config.indexing.discover_entity_types:
            self.reporter.info("Discovering entity types from corpus…")
            self.config.indexing.entity_types = await self._discover_and_merge_entity_types()

        self.reporter.info("Step 2/4 — extracting entities & relationships")
        extractor = self._make_extractor()
        entities_df, relationships_df, text_units_df, graph = await extractor.process_text_units()
        if entities_df.empty:
            ctx.finish_operation(op, ok=False, reason="no entities")
            self._persist_run(ctx, operation="index")
            self.reporter.warning("Extraction produced no entities; aborting.")
            return {"ok": False, "reason": "no entities", "run_id": ctx.run_id, "run_dir": ctx.run_dir}

        await self._update_vector_store(entities_df)

        self.reporter.info("Step 3/4 — community detection (Leiden)")
        community_extractor = self._make_community_extractor()
        graph, communities, nodes_df, comm_df = community_extractor.extract_communities(
            graph, entities_df=entities_df
        )

        self.reporter.info("Step 4/4 — generating community reports")
        reports_df = await self._generate_community_reports(
            nodes_df, comm_df, entities_df, relationships_df
        )

        counts = {
            "documents": len(docs_df),
            "text_units": len(text_units_df),
            "entities": len(entities_df),
            "relationships": len(relationships_df),
            "communities": int(comm_df["community"].nunique()) if not comm_df.empty else 0,
            "reports": len(reports_df),
        }
        ctx.finish_operation(op, ok=True, stats=counts)

        files_processed = [
            {
                "path": d["path"],
                "title": d["title"],
                "size_chars": int(mapping.get(d["id"], {}).get("size_chars", 0) or 0),
                "n_text_units": len(d["text_unit_ids"]) if isinstance(d["text_unit_ids"], list) else 0,
                "processed_path": mapping.get(d["id"], {}).get("processed_path"),
            }
            for _, d in docs_df.iterrows()
        ]
        artefacts = self._persist_run(
            ctx, operation="index", files_processed=files_processed, counts=counts
        )

        duration_s = time.perf_counter() - started
        return {
            "ok": True,
            "operation": "index",
            "run_id": ctx.run_id,
            "run_dir": ctx.run_dir,
            "duration_s": duration_s,
            **counts,
            "llm_summary": self.cost_tracker.summary(by="tag"),
            "total_cost_usd": self.cost_tracker.total_cost_usd(),
            "total_cost_display": self.cost_tracker.render_total_cost(),
            "pricing_status": self.cost_tracker.pricing_status(),
            "artefacts": artefacts,
        }

    # ------------------------------------------------------------------ SEARCH

    async def search(
        self,
        query: str,
        *,
        mode: str = "local",
        conversation_history: Optional[list[dict[str, Any]]] = None,
        artifact_instructions: str = "",
        document: Optional[str] = None,
        include_entity_names: Optional[list[str]] = None,
        exclude_entity_names: Optional[list[str]] = None,
        use_reranker: Optional[bool] = None,
    ) -> SearchResult:
        """Run a single search.

        ``mode`` is one of ``"local"``, ``"global"``, or ``"document"``.
        For ``"document"`` mode, pass ``document`` (filename, path, or doc ID).

        ``use_reranker`` overrides the config-level reranker setting for this call:
        ``True`` forces reranking on, ``False`` forces it off, ``None`` uses config.
        """
        if use_reranker is True and self.reranker is None:
            raise ValueError(
                "use_reranker=True but no reranker is configured. "
                "Set reranker.enabled: true in your config and provide endpoint/model."
            )

        artifacts = load_artifacts_for_search(self.storage, self._output_folder())
        resp_max = self.config.search.response_max_tokens
        r_cfg = self.config.reranker
        if mode == "local":
            s = LocalSearch(
                storage=self.storage,
                llm=self.llm,
                embeddings=self.embeddings,
                prompts=self.prompts,
                artifacts=artifacts,
                vector_store=self._vector_store(),
                output_folder=self._output_folder(),
                top_k_entities=self.config.search.local_top_k_entities,
                top_k_relationships=self.config.search.local_top_k_relationships,
                max_tokens=self.config.search.local_max_tokens,
                text_unit_prop=self.config.search.local_text_unit_prop,
                community_prop=self.config.search.local_community_prop,
                conversation_history_max_turns=self.config.search.local_conversation_history_max_turns,
                response_max_tokens=resp_max,
                endpoint=self.config.search.local_search_endpoint,
                model=self.config.search.local_search_model,
                reporter=self.reporter,
                reranker=self.reranker,
                reranker_overfetch_factor=r_cfg.overfetch_factor,
                rerank_entities=r_cfg.rerank_entities,
                rerank_text_units=r_cfg.rerank_text_units,
                use_community_summary=self.config.search.use_community_summary,
            )
            return await s.asearch(
                query,
                conversation_history=conversation_history,
                artifact_instructions=artifact_instructions,
                include_entity_names=include_entity_names,
                exclude_entity_names=exclude_entity_names,
                use_reranker=use_reranker,
            )
        elif mode == "global":
            s = GlobalSearch(
                storage=self.storage,
                llm=self.llm,
                prompts=self.prompts,
                artifacts=artifacts,
                output_folder=self._output_folder(),
                chunk_size=self.config.search.global_chunk_size,
                concurrency=self.config.search.global_concurrency,
                map_max_tokens=self.config.search.global_map_max_tokens,
                reduce_max_tokens=self.config.search.global_reduce_max_tokens,
                endpoint=self.config.search.global_search_endpoint,
                model=self.config.search.global_search_model,
                use_community_summary=self.config.search.use_community_summary,
                reporter=self.reporter,
            )
            return await s.asearch(
                query,
                conversation_history=conversation_history,
                artifact_instructions=artifact_instructions,
            )
        elif mode == "document":
            if not document:
                raise ValueError("mode='document' requires a 'document' argument.")
            s = DocumentSearch(
                storage=self.storage,
                llm=self.llm,
                embeddings=self.embeddings,
                prompts=self.prompts,
                artifacts=artifacts,
                output_folder=self._output_folder(),
                max_tokens=self.config.search.local_max_tokens,
                top_k_entities=self.config.search.local_top_k_entities,
                response_max_tokens=resp_max,
                endpoint=self.config.search.local_search_endpoint,
                model=self.config.search.local_search_model,
                reporter=self.reporter,
                reranker=self.reranker,
                reranker_overfetch_factor=r_cfg.overfetch_factor,
                rerank_entities=r_cfg.rerank_entities,
            )
            return await s.asearch(
                query,
                document=document,
                conversation_history=conversation_history,
                artifact_instructions=artifact_instructions,
                use_reranker=use_reranker,
            )
        raise ValueError(f"Unknown search mode: {mode!r}. Expected 'local', 'global', or 'document'.")

    async def agent_search(
        self,
        query: str,
        *,
        conversation_history: Optional[list[dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        max_iterations: int = 5,
    ) -> SearchResult:
        """Agentic search — the LLM decides which search tools to call and iterates.

        The agent has access to ``local_search``, ``global_search``, and
        ``document_search`` as tools. It can call them multiple times with
        different parameters before synthesizing a final answer.
        """
        agent = AgentSearch(
            storage=self.storage,
            llm=self.llm,
            embeddings=self.embeddings,
            prompts=self.prompts,
            vector_store=self._vector_store(),
            output_folder=self._output_folder(),
            max_iterations=max_iterations,
            max_tokens=self.config.search.local_max_tokens,
            top_k_entities=self.config.search.local_top_k_entities,
            text_unit_prop=self.config.search.local_text_unit_prop,
            community_prop=self.config.search.local_community_prop,
            use_community_summary=self.config.search.use_community_summary,
            response_max_tokens=self.config.search.response_max_tokens,
            endpoint=self.config.search.local_search_endpoint,
            model=self.config.search.local_search_model,
            reporter=self.reporter,
        )
        return await agent.asearch(
            query,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
        )

    # ------------------------------------------------------------------ CUSTOM ENTITIES

    async def create_entity_types(
        self,
        *,
        sample_chars: int = 8000,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[str]:
        """LLM-driven entity-type discovery: read a small slice of the corpus and
        propose a YAML list of types to use in subsequent extractions.

        Returns the proposed types. Caller is responsible for persisting them into
        ``config.indexing.entity_types`` for the next run.
        """
        loader = FileLoader(
            storage=self.storage,
            input_folder=self.config.indexing.input_folder,
            output_folder=self._output_folder(),
            chunk_size=self.config.indexing.chunk_size,
            chunk_overlap=self.config.indexing.chunk_overlap,
            encoding_name=self.config.indexing.encoding_name,
            reporter=self.reporter,
        )
        keys = loader.find()
        if not keys:
            return list(self.config.indexing.entity_types)
        sample_texts: list[str] = []
        budget = sample_chars
        for key in keys:
            text = loader._read_one(key)
            slice_ = text[: budget // max(1, len(keys))]
            sample_texts.append(slice_)
            if sum(len(s) for s in sample_texts) >= sample_chars:
                break

        existing = [
            t for t in self.config.indexing.entity_types
            if t not in ("PERSON", "ORGANIZATION")
        ]
        max_types = max(3, self.config.indexing.max_entity_types - 2)
        messages = self.prompts.build(
            "create_custom_entities",
            texts=sample_texts,
            existing_types=existing,
            max_types=max_types,
        )
        response = await self.llm.execute_safe(
            messages=messages,
            endpoint=endpoint,
            model=model,
            max_tokens=self.config.indexing.entity_discovery_max_tokens,
            temperature=0.0,
            tag="create_custom_entities",
        )
        return _parse_entity_types(response, default=self.config.indexing.entity_types)

    async def _discover_and_merge_entity_types(self) -> list[str]:
        """Run LLM entity-type discovery and merge with existing config types.

        The mandatory types (PERSON, ORGANIZATION) are always present. User-defined
        types are kept. LLM-proposed types fill remaining slots up to ``max_entity_types``.
        """
        from grail.config import MANDATORY_ENTITY_TYPES

        max_total = self.config.indexing.max_entity_types
        existing = list(self.config.indexing.entity_types)

        proposed = await self.create_entity_types()

        seen: set[str] = set()
        merged: list[str] = []

        for t in existing:
            upper = t.upper().replace(" ", "_")
            if upper not in seen:
                seen.add(upper)
                merged.append(upper)

        for t in proposed:
            upper = t.upper().replace(" ", "_")
            if upper not in seen and len(merged) < max_total:
                seen.add(upper)
                merged.append(upper)

        self.reporter.info(
            f"Entity types: {len(existing)} existing + "
            f"{len(merged) - len(existing)} discovered → {len(merged)} total"
        )
        return merged

    # ------------------------------------------------------------------ helpers (shared)

    def _make_loader(self) -> FileLoader:
        return FileLoader(
            storage=self.storage,
            input_folder=self.config.indexing.input_folder,
            output_folder=self._output_folder(),
            chunk_size=self.config.indexing.chunk_size,
            chunk_overlap=self.config.indexing.chunk_overlap,
            encoding_name=self.config.indexing.encoding_name,
            document_boundary=self.config.indexing.document_boundary,
            reporter=self.reporter,
        )

    def _make_extractor(self) -> EntityRelationshipExtractor:
        delimiters: dict[str, str] = {}
        if self.config.indexing.tuple_delimiter is not None:
            delimiters["tuple_delimiter"] = self.config.indexing.tuple_delimiter
        if self.config.indexing.record_delimiter is not None:
            delimiters["record_delimiter"] = self.config.indexing.record_delimiter
        if self.config.indexing.completion_delimiter is not None:
            delimiters["completion_delimiter"] = self.config.indexing.completion_delimiter
        if self.config.indexing.start_delimiter is not None:
            delimiters["start_delimiter"] = self.config.indexing.start_delimiter

        from grail.prompts.builtin.entity_relation import DEFAULT_DELIMITERS

        return EntityRelationshipExtractor(
            storage=self.storage,
            llm=self.llm,
            embeddings=self.embeddings,
            prompts=self.prompts,
            entity_types=self.config.indexing.entity_types,
            extraction_endpoint=self.config.indexing.entity_relation_endpoint,
            extraction_model=self.config.indexing.entity_relation_model,
            summarization_endpoint=self.config.indexing.summarization_endpoint,
            summarization_model=self.config.indexing.summarization_model,
            output_folder=self._output_folder(),
            extraction_max_tokens=self.config.indexing.extraction_max_tokens,
            extraction_concurrency=self.config.indexing.extraction_concurrency,
            summarization_concurrency=self.config.indexing.summarization_concurrency,
            delimiters={**DEFAULT_DELIMITERS, **delimiters},
            reporter=self.reporter,
        )

    def _make_community_extractor(self) -> CommunityExtractor:
        return CommunityExtractor(
            storage=self.storage,
            output_folder=self._output_folder(),
            max_cluster_size=self.config.community.max_cluster_size,
            use_lcc=self.config.community.use_lcc,
            min_community_size=self.config.community.min_community_size,
            seed=self.config.community.seed,
            embedding_merge_eps=self.config.community.embedding_merge_eps,
            reporter=self.reporter,
        )

    def _make_incremental_community(self) -> IncrementalCommunityExtractor:
        return IncrementalCommunityExtractor(
            storage=self.storage,
            base_extractor=self._make_community_extractor(),
            change_threshold=self.config.community.incremental_change_threshold,
            output_folder=self._output_folder(),
            reporter=self.reporter,
        )

    async def _update_vector_store(self, entities_df: pd.DataFrame) -> None:
        store = self._vector_store()
        if store is not None and not entities_df.empty:
            docs = [
                VectorStoreDocument(
                    id=row["id"],
                    text=row["description"],
                    vector=row["description_embedding"],
                    attributes={
                        "name": row["name"],
                        "type": row.get("type"),
                        "human_readable_id": int(row.get("human_readable_id", 0)),
                    },
                )
                for _, row in entities_df.iterrows()
                if row["description_embedding"] is not None
            ]
            store.load_documents(docs, overwrite=True)

    async def _generate_community_reports(
        self,
        nodes_df: pd.DataFrame,
        comm_df: pd.DataFrame,
        entities_df: pd.DataFrame,
        relationships_df: pd.DataFrame,
        *,
        affected_community_ids: set[str] | None = None,
    ) -> pd.DataFrame:
        report_gen = CommunityReportGenerator(
            storage=self.storage,
            llm=self.llm,
            prompts=self.prompts,
            output_folder=self._output_folder(),
            report_endpoint=self.config.community.community_report_endpoint,
            report_model=self.config.community.community_report_model,
            json_corrector_endpoint=self.config.community.json_corrector_endpoint,
            json_corrector_model=self.config.community.json_corrector_model,
            max_output_tokens=self.config.community.max_report_length,
            community_level=self.config.community.community_level,
            min_report_size=self.config.community.min_report_size,
            report_concurrency=self.config.community.report_concurrency,
            reporter=self.reporter,
        )
        return await report_gen.generate_reports(
            nodes_df=nodes_df,
            communities_df=comm_df,
            entities_df=entities_df,
            relationships_df=relationships_df,
            affected_community_ids=affected_community_ids,
        )

    # ------------------------------------------------------------------ APPEND / EDIT / DELETE

    async def append(self, new_files: list[str]) -> dict[str, Any]:
        """Incrementally add new files to the knowledge graph.

        Only the new files go through LLM extraction. Existing entities and
        relationships are preserved and merged with the new extractions.
        """
        started = time.perf_counter()
        loader = self._make_loader()

        # Copy files into input folder.
        new_keys: list[str] = []
        for path in new_files:
            dest = self.storage.join(self.config.indexing.input_folder, Path(path).name)
            self.storage.copy_in(path, dest)
            new_keys.append(dest)

        # Layer 1: chunk new files, merge with existing.
        self.reporter.info("Step 1/4 — chunking new files")
        docs_df, text_units_df, mapping, new_tu_ids = loader.append_files(new_keys)
        if not new_tu_ids:
            return {"ok": False, "reason": "no new text units from appended files"}
        loader.write_artifacts(docs_df, text_units_df, mapping)

        # Layer 2: extract entities/relationships from new TUs only, merge.
        self.reporter.info("Step 2/4 — extracting entities from new text units")
        extractor = self._make_extractor()
        (entities_df, rels_df, text_units_df, graph,
         new_entity_names, updated_entity_names) = await extractor.append_extract(
            text_units_df, new_tu_ids
        )

        await self._update_vector_store(entities_df)

        # Layer 3: update communities.
        self.reporter.info("Step 3/4 — updating communities")
        inc = self._make_incremental_community()
        graph, communities, nodes_df, comm_df, affected_cids = inc.update(
            graph,
            new_entity_names=new_entity_names,
            updated_entity_names=updated_entity_names,
        )

        # Layer 4: community reports (only affected communities).
        self.reporter.info("Step 4/4 — generating community reports")
        reports_df = await self._generate_community_reports(
            nodes_df, comm_df, entities_df, rels_df,
            affected_community_ids=affected_cids,
        )

        return {
            "ok": True,
            "operation": "append",
            "duration_s": time.perf_counter() - started,
            "new_files": len(new_files),
            "new_text_units": len(new_tu_ids),
            "new_entities": len(new_entity_names),
            "updated_entities": len(updated_entity_names),
            "total_entities": len(entities_df),
            "total_relationships": len(rels_df),
            "communities": int(comm_df["community"].nunique()) if not comm_df.empty else 0,
            "reports": len(reports_df),
            "llm_summary": self.cost_tracker.summary(by="tag"),
        }

    async def edit(self, replacements: dict[str, str]) -> dict[str, Any]:
        """Edit existing files in the knowledge graph.

        ``replacements`` maps input-folder filename → local path with new content.
        Only the affected text units are re-extracted. Entities that lose all
        references are pruned automatically.
        """
        started = time.perf_counter()
        loader = self._make_loader()

        # Identify doc IDs for the files being replaced.
        doc_ids = loader.get_doc_ids_by_path(list(replacements.keys()))
        if not doc_ids:
            return {"ok": False, "reason": "no matching documents found for the given filenames"}

        # Replace files on disk.
        for name, local_path in replacements.items():
            dest = self.storage.join(self.config.indexing.input_folder, name)
            if self.storage.exists(dest):
                self.storage.delete(dest)
            self.storage.copy_in(local_path, dest)

        # Layer 1: re-chunk edited documents.
        self.reporter.info("Step 1/4 — re-chunking edited documents")
        edits = []
        for doc_id in doc_ids:
            docs_df_tmp, _, _ = loader.load_artifacts()
            doc_row = docs_df_tmp[docs_df_tmp["id"] == doc_id]
            if doc_row.empty:
                continue
            file_path = doc_row.iloc[0]["path"]
            new_content = self.storage.read_text(
                self.storage.join(self.config.indexing.input_folder, file_path)
            )
            edits.append({"doc_id": doc_id, "new_content": new_content})

        docs_df, text_units_df, mapping, edited_tu_ids = loader.batch_edit_documents(edits)
        loader.write_artifacts(docs_df, text_units_df, mapping)

        # Layer 2: re-extract from edited TUs, merge, prune orphans.
        self.reporter.info("Step 2/4 — re-extracting entities from edited text units")
        extractor = self._make_extractor()
        (entities_df, rels_df, text_units_df, graph,
         new_entity_names, updated_entity_names,
         deleted_entity_names) = await extractor.edit_extract(
            text_units_df, edited_tu_ids
        )

        await self._update_vector_store(entities_df)

        # Layer 3: update communities with edit awareness.
        self.reporter.info("Step 3/4 — updating communities")
        inc = self._make_incremental_community()
        graph, communities, nodes_df, comm_df, affected_cids = inc.incremental_edit(
            graph,
            new_entity_names=new_entity_names,
            updated_entity_names=updated_entity_names,
            deleted_entity_names=deleted_entity_names,
        )

        # Layer 4: community reports (only affected communities).
        self.reporter.info("Step 4/4 — generating community reports")
        reports_df = await self._generate_community_reports(
            nodes_df, comm_df, entities_df, rels_df,
            affected_community_ids=affected_cids,
        )

        return {
            "ok": True,
            "operation": "edit",
            "duration_s": time.perf_counter() - started,
            "edited_files": len(replacements),
            "edited_text_units": len(edited_tu_ids),
            "new_entities": len(new_entity_names),
            "updated_entities": len(updated_entity_names),
            "deleted_entities": len(deleted_entity_names),
            "total_entities": len(entities_df),
            "total_relationships": len(rels_df),
            "communities": int(comm_df["community"].nunique()) if not comm_df.empty else 0,
            "reports": len(reports_df),
            "llm_summary": self.cost_tracker.summary(by="tag"),
        }

    async def delete(self, file_names: list[str]) -> dict[str, Any]:
        """Delete files from the knowledge graph.

        Entities and relationships that lose all text-unit references are pruned.
        Communities are updated to reflect the smaller graph.
        """
        started = time.perf_counter()
        loader = self._make_loader()

        doc_ids = loader.get_doc_ids_by_path(file_names)
        if not doc_ids:
            return {"ok": False, "reason": "no matching documents found for the given filenames"}

        # Layer 1: delete docs and text units.
        self.reporter.info("Step 1/4 — deleting documents and text units")
        docs_df, text_units_df, mapping, deleted_tu_ids = loader.batch_delete_documents(doc_ids)
        loader.write_artifacts(docs_df, text_units_df, mapping)

        # Layer 2: strip TU refs, prune orphaned entities/rels.
        self.reporter.info("Step 2/4 — pruning orphaned entities and relationships")
        extractor = self._make_extractor()
        (entities_df, rels_df, text_units_df, graph,
         updated_entity_names, deleted_entity_names) = await extractor.delete_extract(
            text_units_df, deleted_tu_ids
        )

        await self._update_vector_store(entities_df)

        # Layer 3: update communities after deletion.
        self.reporter.info("Step 3/4 — updating communities")
        inc = self._make_incremental_community()
        graph, communities, nodes_df, comm_df, affected_cids = inc.incremental_delete(
            graph, deleted_entity_names=deleted_entity_names,
        )

        # Layer 4: community reports (only affected communities).
        self.reporter.info("Step 4/4 — generating community reports")
        reports_df = await self._generate_community_reports(
            nodes_df, comm_df, entities_df, rels_df,
            affected_community_ids=affected_cids,
        )

        return {
            "ok": True,
            "operation": "delete",
            "duration_s": time.perf_counter() - started,
            "deleted_files": len(file_names),
            "deleted_text_units": len(deleted_tu_ids),
            "updated_entities": len(updated_entity_names),
            "deleted_entities": len(deleted_entity_names),
            "total_entities": len(entities_df),
            "total_relationships": len(rels_df),
            "communities": int(comm_df["community"].nunique()) if not comm_df.empty else 0,
            "reports": len(reports_df),
            "llm_summary": self.cost_tracker.summary(by="tag"),
        }

    # ------------------------------------------------------------------ STATUS

    def status(self) -> dict[str, Any]:
        out_folder = self._output_folder()
        artefacts = {
            "documents": f"{out_folder}/final_docs.parquet",
            "text_units": f"{out_folder}/final_text_units.parquet",
            "entities": f"{out_folder}/final_entities.parquet",
            "relationships": f"{out_folder}/final_relationships.parquet",
            "nodes": f"{out_folder}/final_nodes.parquet",
            "communities": f"{out_folder}/final_communities.parquet",
            "reports": f"{out_folder}/final_community_reports.parquet",
            "graph": f"{out_folder}/entity_relationship_graph.graphml",
            "mapping": "mapping.json",
        }
        return {
            "project_name": self.config.project_name,
            "storage": repr(self.storage),
            "artefacts": {name: self.storage.exists(key) for name, key in artefacts.items()},
        }


def _parse_entity_types(response: Optional[str], *, default: list[str]) -> list[str]:
    if not response:
        return list(default)
    import re

    match = re.search(r"<entities>(.*?)</entities>", response, flags=re.S)
    blob = match.group(1) if match else response
    blob = blob.strip().strip("`")
    try:
        # Most prompts respond with a JSON-style list.
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        try:
            import yaml

            parsed = yaml.safe_load(blob)
        except Exception:
            return list(default)
    if isinstance(parsed, dict):
        # Sometimes the model wraps it as {"entities": [...]}.
        parsed = parsed.get("entities", parsed.get("types", []))
    if not isinstance(parsed, list):
        return list(default)
    cleaned = [str(x).lower().strip() for x in parsed if str(x).strip()]
    return cleaned or list(default)
