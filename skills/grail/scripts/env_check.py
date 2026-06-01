"""Environment probe — confirms GRAIL is installed and which extras are present.

Usage:
    python scripts/env_check.py
"""
from __future__ import annotations

import platform
import sys

from _common import Reply, run


def main() -> Reply:
    try:
        from grail import __version__ as grail_version
    except ImportError:
        return Reply(
            ok=False,
            error="grail is not installed. Run `bash scripts/setup.sh` first.",
        )

    extras_present: list[str] = []
    for mod, label in (
        ("faiss", "faiss"),
        ("chromadb", "chroma"),
        ("boto3", "s3"),
        ("sentence_transformers", "rerank"),
    ):
        try:
            __import__(mod)
            extras_present.append(label)
        except ImportError:
            pass

    return Reply(
        ok=True,
        data={
            "grail_version": grail_version,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "extras_present": extras_present,
        },
        next_steps=[
            "scripts/list_grail_projects.py — see registered projects",
            "scripts/init_project.py — create a new project",
        ],
    )


if __name__ == "__main__":
    run(main)
