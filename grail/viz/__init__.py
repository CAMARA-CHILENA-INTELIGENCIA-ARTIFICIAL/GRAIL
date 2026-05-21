"""
GRAIL graph visualization — an optional, self-contained feature that turns the
indexed knowledge graph into a static HTML page powered by Sigma.js v3.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This module is intentionally isolated from the main indexing / query pipelines:
- It only depends on artefacts already on disk (parquet + graphml).
- It only imports ``pandas``, ``networkx``, and stdlib.
- It exposes a single high-level entry point: :func:`build_visualization`.

Usage::

    from grail.viz import build_visualization
    out = build_visualization(project_dir="examples/quickstart")
    # out -> Path to the generated HTML file

Or via the CLI::

    grail viz examples/quickstart
"""
from grail.viz.builder import Visualizer, build_visualization

__all__ = ["Visualizer", "build_visualization"]
