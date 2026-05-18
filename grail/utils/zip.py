"""Zip helpers, directory walkers.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

import zipfile
from pathlib import Path


def unzip_file(zip_path: str | Path, extract_to: str | Path) -> list[str]:
    """Extract ``zip_path`` into ``extract_to`` and return the list of extracted file paths."""
    zip_path = Path(zip_path)
    extract_to = Path(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            zf.extract(member, extract_to)
            extracted.append(str(extract_to / member))
    return extracted


def zip_directory(src_dir: str | Path, zip_path: str | Path) -> Path:
    """Zip the contents of ``src_dir`` into ``zip_path`` (recursively)."""
    src_dir = Path(src_dir)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in src_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(src_dir)))
    return zip_path


def list_files(root: str | Path, *, exclude_patterns: list[str] | None = None) -> list[str]:
    """List files under ``root`` (recursive), excluding any matching ``exclude_patterns``."""
    root = Path(root)
    exclude_patterns = exclude_patterns or []
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        if any(p in rel for p in exclude_patterns):
            continue
        out.append(str(path))
    return out
