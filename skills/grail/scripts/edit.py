"""Replace the content of indexed files (KB mode incremental edit).

Usage:
    python scripts/edit.py --project <ref> \
        --replace path/old.md=path/new.md \
        --replace report.pdf=updated_report.pdf
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from _common import (
    Reply,
    load_grail,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = argparse.ArgumentParser(description="Replace indexed files.")
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--replace",
        action="append",
        required=True,
        metavar="OLD_FILENAME=NEW_FILE_PATH",
        help="Replace OLD_FILENAME in the index with the content of NEW_FILE_PATH.",
    )
    args = ap.parse_args()
    project = resolve_project_ref(args.project)
    mode = project_mode(project)

    replacements: dict[str, str] = {}
    for entry in args.replace:
        if "=" not in entry:
            return Reply(
                ok=False,
                error=f"--replace expects OLD=NEW (got {entry!r}).",
            )
        old, new = entry.split("=", 1)
        new_path = Path(new).expanduser().resolve()
        if not new_path.exists():
            return Reply(ok=False, error=f"new file not found: {new_path}")
        replacements[old] = new_path.read_text(encoding="utf-8")

    grail = load_grail(project)
    result = asyncio.run(grail.edit(replacements=replacements))
    if not result.get("ok"):
        return Reply(
            ok=False,
            mode=mode,
            project=project_envelope(project),
            error=str(result.get("reason") or "edit failed"),
            data=result,
        )

    return Reply(
        ok=True,
        mode=mode,
        project=project_envelope(project),
        data={
            "edited": list(replacements.keys()),
            "cost": grail.cost_tracker.render_total_cost(),
        },
        next_steps=["scripts/status.py --project <ref>"],
    )


if __name__ == "__main__":
    run(main)
