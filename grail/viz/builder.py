"""
High-level orchestrator for the GRAIL graph viewer.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This is the only file the rest of GRAIL (specifically the CLI) needs to import
from ``grail.viz``. Everything else is implementation detail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from grail.config import Config, load_config
from grail.query.retrieval import load_artifacts_for_search
from grail.storage import LocalStorage, StorageBackend, get_backend
from grail.viz.exporter import build_sigma_graph
from grail.viz.template import render_html

log = logging.getLogger(__name__)


@dataclass
class Visualizer:
    """Builds the static HTML viewer from a project's indexed artefacts."""

    storage: StorageBackend
    output_folder: str = "output"
    project_name: str = "default"
    layout_seed: int = 42
    layout_iterations: int = 200

    def build(self, output_path: Path, *, run_id: str = "") -> Path:
        """Read artefacts, build the Sigma payload, render the HTML, write it.

        Returns the path to the written file.
        """
        artifacts = load_artifacts_for_search(self.storage, self.output_folder)
        if artifacts.entities.empty:
            raise RuntimeError(
                "No indexed entities were found. Run `grail index <project>` first."
            )

        log.info(
            "Building visualization for %d entities, %d relationships",
            len(artifacts.entities), len(artifacts.relationships),
        )
        sigma = build_sigma_graph(
            entities_df=artifacts.entities,
            relationships_df=artifacts.relationships,
            nodes_df=artifacts.nodes,
            documents_df=artifacts.documents,
            text_units_df=artifacts.text_units,
            communities_df=artifacts.communities,
            reports_df=artifacts.community_reports,
            layout_seed=self.layout_seed,
            layout_iterations=self.layout_iterations,
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
    layout_seed: int = 42,
    layout_iterations: int = 200,
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

    viz = Visualizer(
        storage=storage,
        output_folder=output_folder,
        project_name=config.project_name,
        layout_seed=layout_seed,
        layout_iterations=layout_iterations,
    )
    return viz.build(out_path, run_id=run_id)
