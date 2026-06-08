"""
High-level orchestrator for the GRAIL graph viewer.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This is the only file the rest of GRAIL (specifically the CLI) needs to import
from ``grail.viz``. Everything else is implementation detail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from grail.config import Config, load_config
from grail.query.retrieval import load_artifacts_for_search
from grail.storage import LocalStorage, StorageBackend, get_backend
from grail.viz.exporter import build_sigma_graph
from grail.viz.template import render_html

log = logging.getLogger(__name__)


@dataclass
class Visualizer:
    """Builds the static HTML viewer from a project's indexed artefacts.

    ``force_settings`` overrides individual force-simulation knobs the
    client renderer reads on first start (e.g. ``{"seed": 7, "chargeStrength": -2000}``).
    ``max_entities`` enforces a top-N-by-degree cap; ``None`` or ``0`` means
    no cap (write everything to the HTML).
    """

    storage: StorageBackend
    output_folder: str = "output"
    project_name: str = "default"
    force_settings: dict[str, Any] = field(default_factory=dict)
    max_entities: Optional[int] = None

    def build(self, output_path: Path, *, run_id: str = "") -> Path:
        """Read artefacts, build the payload, render the HTML, write it.

        Returns the path to the written file.
        """
        from grail.viz.sampling import top_n_by_degree

        artifacts = load_artifacts_for_search(self.storage, self.output_folder)
        if artifacts.entities.empty:
            raise RuntimeError(
                "No indexed entities were found. Run `grail index <project>` first."
            )

        cap = self.max_entities if (self.max_entities or 0) > 0 else None
        sampled = top_n_by_degree(
            entities=artifacts.entities,
            relationships=artifacts.relationships,
            text_units=artifacts.text_units,
            nodes=artifacts.nodes,
            communities=artifacts.communities,
            community_reports=artifacts.community_reports,
            documents=artifacts.documents,
            max_entities=cap,
        )

        truncation_meta: Optional[dict[str, Any]] = (
            {
                "truncated": True,
                "total_entities": sampled.total_entities,
                "total_relationships": sampled.total_relationships,
                "kept_entities": sampled.kept_entities,
                "kept_relationships": sampled.kept_relationships,
                "policy": sampled.policy,
                "cap": cap or 0,
            }
            if sampled.truncated
            else None
        )

        log.info(
            "Building visualization for %d / %d entities, %d / %d relationships%s",
            sampled.kept_entities, sampled.total_entities,
            sampled.kept_relationships, sampled.total_relationships,
            " (top-N by degree)" if sampled.truncated else "",
        )
        sigma = build_sigma_graph(
            entities_df=sampled.entities,
            relationships_df=sampled.relationships,
            nodes_df=sampled.nodes,
            documents_df=sampled.documents,
            text_units_df=sampled.text_units,
            communities_df=sampled.communities,
            reports_df=sampled.community_reports,
            force_settings=self.force_settings or None,
            truncation=truncation_meta,
        )
        title = f"GRAIL — {self.project_name}" if self.project_name else "GRAIL Knowledge Graph"
        html = render_html(
            sigma.to_dict(),
            title=title,
            project_name=self.project_name,
            run_id=run_id,
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        log.info("Wrote visualization to %s (%d KB)", output_path, len(html) // 1024)
        return output_path


def build_visualization(
    project_dir: str | Path,
    *,
    output_path: Optional[str | Path] = None,
    config: Optional[Config] = None,
    force_settings: Optional[dict[str, Any]] = None,
    max_entities: Optional[int] = None,
    # Legacy kwargs kept for back-compat with older CLI versions; the
    # iterations flag no longer applies (D3 simulation handles convergence
    # on its own). ``layout_seed`` is honoured as ``force_settings.seed``.
    layout_seed: Optional[int] = None,
    layout_iterations: Optional[int] = None,
) -> Path:
    """Convenience wrapper: build the viewer for a project directory.

    ``project_dir`` is the folder containing ``grail.yaml``. ``output_path``
    defaults to ``<project_dir>/graph.html``.
    """
    project_dir = Path(project_dir)

    if config is None:
        config = load_config(project_dir / "grail.yaml")

    if config.storage.backend == "local":
        storage: StorageBackend = LocalStorage(root=config.storage.root)
    else:
        storage = get_backend(
            config.storage.backend,
            bucket=config.storage.s3_bucket,
            prefix=config.storage.s3_prefix,
            region_name=config.storage.s3_region,
            endpoint_url=config.storage.s3_endpoint_url,
        )

    # Resolve the active run folder so we read the latest artefacts.
    from grail.indexing.run_manifest import resolve_active_run_folder
    output_folder = resolve_active_run_folder(storage, config.indexing.output_folder)

    # Try to pull the run id from the storage's current.json pointer for the header.
    run_id = ""
    current_key = f"{config.indexing.output_folder}/current.json"
    if storage.exists(current_key):
        try:
            import json
            current = json.loads(storage.read_text(current_key))
            run_id = str(current.get("run_id", ""))
        except Exception:  # pragma: no cover — header decoration only
            run_id = ""

    out_path = Path(output_path) if output_path else (project_dir / "graph.html")

    resolved_force: dict[str, Any] = dict(force_settings or {})
    if layout_seed is not None and "seed" not in resolved_force:
        resolved_force["seed"] = layout_seed
    if layout_iterations is not None:
        log.warning(
            "viz: --iterations is deprecated; the D3 simulation handles convergence "
            "automatically. Use --alpha-decay or --charge to tune layout instead."
        )

    viz = Visualizer(
        storage=storage,
        output_folder=output_folder,
        project_name=config.project_name,
        force_settings=resolved_force,
        max_entities=max_entities,
    )
    return viz.build(out_path, run_id=run_id)
