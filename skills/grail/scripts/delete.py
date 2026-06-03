"""Remove files from the index (KB mode incremental delete).

Usage:
    python scripts/delete.py --project <ref> --files report.pdf notes.md
"""
from __future__ import annotations

import argparse
import asyncio

from _common import (
    Reply,
    load_grail,
    project_envelope,
    project_mode,
    resolve_project_ref,
    run,
)


def main() -> Reply:
    ap = argparse.ArgumentParser(description="Remove indexed files.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--files", nargs="+", required=True, help="Filenames to delete.")
    args = ap.parse_args()
    project = resolve_project_ref(args.project)
    mode = project_mode(project)

    grail = load_grail(project)
    # GRAIL.delete's parameter is ``file_names`` (snake_case with the
    # underscore). Earlier versions passed ``filenames=`` which TypeErrored.
    result = asyncio.run(grail.delete(file_names=args.files))
    if not result.get("ok"):
        return Reply(
            ok=False,
            mode=mode,
            project=project_envelope(project),
            error=str(result.get("reason") or "delete failed"),
            data=result,
        )

    return Reply(
        ok=True,
        mode=mode,
        project=project_envelope(project),
        data={
            "deleted": args.files,
            "remaining_entities": int(result.get("entities", 0)),
        },
    )


if __name__ == "__main__":
    run(main)
