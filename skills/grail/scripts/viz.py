"""Export an interactive HTML visualization of a GRAIL knowledge graph.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Usage:
    python scripts/viz.py --project <ref> [--output graph.html]
                          [--max-entities N] [--seed 42]

Writes a single self-contained HTML file (D3-powered viewer with entity
search, layer toggles, and colouring by community or entity type). The file
opens offline — the renderer is inlined into the page.

Dependency handling
-------------------
The viewer inlines a prebuilt TypeScript/D3 bundle shipped inside the
``graphgrail`` package. Two things can be missing, and each returns
``ok: false`` with an explicit, agent-actionable message so the agent can
ask the user to install what's needed rather than failing silently:

  * ``grail`` not installed            → run ``bash scripts/setup.sh``.
  * the renderer bundle is absent      → only happens in a source checkout
    where the bundle was never built; the agent should ask the user to run
    ``cd grail/viz/web && npm install && npm run build`` (needs Node/npm),
    or to reinstall ``graphgrail`` from PyPI (the wheel ships the bundle).
"""
from __future__ import annotations

from pathlib import Path

from _common import (
    Reply,
    project_argparser,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = project_argparser(description="Export an HTML graph visualization.")
    ap.add_argument(
        "--output", default=None,
        help="Where to write the HTML. Defaults to <project>/graph.html.",
    )
    ap.add_argument(
        "--max-entities", type=int, default=None,
        help="Cap entities rendered (top-N by degree). 0 / omit = no cap.",
    )
    ap.add_argument(
        "--seed", type=int, default=42,
        help="Layout seed — same value reproduces the same layout.",
    )
    args = ap.parse_args()

    project = resolve_project_ref(args.project)

    # grail must be installed. A bare ImportError here means setup never ran;
    # tell the agent exactly how to fix it so it can prompt the user.
    try:
        from grail.viz import build_visualization
    except ImportError:
        return Reply(
            ok=False,
            project=project_envelope(project),
            error="grail is not installed, so the visualization module is unavailable.",
            next_steps=[
                "Ask the user to install GRAIL, then retry: bash scripts/setup.sh",
            ],
        )

    # The viz command reads grail.yaml from the project folder. Memory-only
    # projects without one can't be rendered as a graph HTML.
    if not (project / "grail.yaml").exists():
        return Reply(
            ok=False,
            mode=project_mode(project),
            project=project_envelope(project),
            error=f"no grail.yaml found in {project} — `viz` needs a configured project.",
            next_steps=["scripts/explore.py --project <ref> — inspect graph shape instead"],
        )

    out_arg = Path(args.output).expanduser() if args.output else None

    # RendererBundleMissing (a RuntimeError subclass) is the "dependency not
    # installed" signal — the prebuilt D3 bundle isn't on disk. Catch it
    # *before* the generic RuntimeError so the agent gets the actionable
    # install/build instruction instead of a vague failure.
    from grail.viz.template import RendererBundleMissing

    try:
        out_path = build_visualization(
            project_dir=project,
            output_path=out_arg,
            force_settings={"seed": args.seed},
            max_entities=args.max_entities,
        )
    except RendererBundleMissing:
        return Reply(
            ok=False,
            mode=project_mode(project),
            project=project_envelope(project),
            error=(
                "The prebuilt graph renderer bundle is missing, so the HTML "
                "viewer can't be generated."
            ),
            next_steps=[
                "Ask the user to build the renderer (needs Node/npm): "
                "cd grail/viz/web && npm install && npm run build",
                "Or ask the user to reinstall from PyPI (the wheel ships the "
                "bundle): pip install --upgrade --force-reinstall graphgrail",
            ],
        )
    except RuntimeError as exc:
        # Most commonly: no indexed entities yet.
        return Reply(
            ok=False,
            mode=project_mode(project),
            project=project_envelope(project),
            error=str(exc),
            next_steps=["scripts/index.py --project <ref> — index documents first"],
        )

    size_kb = out_path.stat().st_size // 1024
    return Reply(
        ok=True,
        mode=project_mode(project),
        project=project_envelope(project),
        data={
            "html_path": str(out_path),
            "size_kb": int(size_kb),
            "max_entities": args.max_entities or 0,
        },
        next_steps=[
            f"Open the file in a browser: file://{out_path.resolve()}",
        ],
    )


if __name__ == "__main__":
    run(main)
