"""Create a new GRAIL project (KB or memory mode).

Default location is ``~/.grail/projects/<name>/`` — predictable so the
agent can always find projects with ``ls ~/.grail/projects``. Pass an
absolute or relative path to override.

Usage:
    # Bare name → ~/.grail/projects/work-memory/
    python scripts/init_project.py --project work-memory --memory

    # Explicit path → wherever you point it
    python scripts/init_project.py --project ./my-kb
    python scripts/init_project.py --project /Users/me/research/kb --memory

Writes:
  * ``<project>/grail.yaml`` — KB or memory template
  * ``<project>/meta.json`` — identity (ULID + name + mode + timestamps)
  * ``<project>/input/`` (KB) or ``<project>/memories/`` (memory)
  * ``<project>/output/``
  * registers the project in ``~/.grail/registry.json``
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from _common import Reply, project_envelope, run


_HOME_PROJECTS = Path.home() / ".grail" / "projects"


def _resolve_project_dir(ref: str) -> Path:
    """Apply the home-dir default for bare names.

    Rules:
      * Bare name (no ``/`` or ``\\``, no ``.`` or ``~`` prefix) →
        ``~/.grail/projects/<name>/``.
      * Anything that looks like a path (contains a separator, starts with
        ``.`` or ``~``, or is absolute) → expanded + resolved as-is.

    This is the *only* place where the home-dir default applies. ``grail
    init`` from the CLI keeps its path-based semantics (KB users in a repo
    often want ``./input/`` next to their code).
    """
    s = ref.strip()
    if not s:
        raise ValueError("--project cannot be empty.")
    looks_like_path = (
        "/" in s or "\\" in s or s.startswith(".") or s.startswith("~")
    )
    if looks_like_path:
        return Path(s).expanduser().resolve()
    return (_HOME_PROJECTS / s).expanduser().resolve()


def main() -> Reply:
    ap = argparse.ArgumentParser(description="Create a new GRAIL project.")
    ap.add_argument(
        "--project",
        required=True,
        help=(
            "Directory to scaffold. Bare names (no slash) default to "
            "~/.grail/projects/<name>/. Pass an absolute or relative path to "
            "override."
        ),
    )
    ap.add_argument("--name", default=None, help="Display name (defaults to folder name).")
    ap.add_argument(
        "--memory", action="store_true",
        help="Scaffold a memory-mode project instead of the default KB mode.",
    )
    ap.add_argument(
        "--no-git", dest="git", action="store_false",
        help="Skip the default-on git init in memory mode.",
    )
    ap.add_argument(
        "--git", dest="git", action="store_true",
        help="Force git init even in KB mode (default: KB no, memory yes).",
    )
    ap.set_defaults(git=None)
    ap.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite an existing grail.yaml / meta.json.",
    )
    args = ap.parse_args()

    project_dir = _resolve_project_dir(args.project)
    project_dir.mkdir(parents=True, exist_ok=True)
    project_name = args.name or project_dir.name
    mode = "memory" if args.memory else "knowledge_base"

    # Delegate to the CLI's ``grail init`` so the templates stay in one place.
    cli_args = ["grail", "init", str(project_dir), "--name", project_name]
    if args.memory:
        cli_args.append("--memory")
    if args.overwrite:
        cli_args.append("--overwrite")
    if args.git is True:
        cli_args.append("--git")
    elif args.git is False:
        cli_args.append("--no-git")

    if shutil.which("grail") is None:
        # ``grail`` wasn't installed as a script — call the module via the
        # interpreter that's running this script (``sys.executable`` is the
        # absolute path, so it doesn't depend on PATH having a ``python``).
        cli_args = [sys.executable, "-m", "grail.cli.main"] + cli_args[1:]

    result = subprocess.run(cli_args, capture_output=True, text=True)
    if result.returncode != 0:
        return Reply(
            ok=False,
            error=f"grail init failed: {result.stderr.strip() or result.stdout.strip()}",
            data={"stdout": result.stdout, "stderr": result.stderr},
        )

    # Annotate where the project landed so the agent can echo it back to the
    # user — especially useful when the bare-name default kicked in. Compare
    # the resolved forms (Path.home() doesn't follow symlinks on macOS where
    # /tmp → /private/tmp, but .resolve() does) so the flag matches reality.
    try:
        resolved_home = _HOME_PROJECTS.resolve()
        landed_in_home = project_dir.is_relative_to(resolved_home)
    except (OSError, ValueError):
        landed_in_home = False
    return Reply(
        ok=True,
        mode=mode,
        project=project_envelope(project_dir),
        data={
            "scaffolded": {
                "config": str(project_dir / "grail.yaml"),
                "meta": str(project_dir / "meta.json"),
                "input_or_memories": str(
                    project_dir / ("memories" if args.memory else "input")
                ),
            },
            "location": str(project_dir),
            "used_home_default": landed_in_home,
            "cli_output": result.stdout,
        },
        next_steps=(
            [
                "Add observations: scripts/memory/add_observation.py",
                "Recall: scripts/memory/recall.py --since 1h",
            ]
            if args.memory
            else [
                "Drop files into ./input/",
                "Index: scripts/index.py --project <ref>",
                "Query: scripts/query.py --project <ref> --query '...'",
            ]
        ),
    )


if __name__ == "__main__":
    run(main)
