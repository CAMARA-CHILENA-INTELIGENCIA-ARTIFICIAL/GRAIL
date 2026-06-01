"""
Observation file I/O.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Every memory observation is a markdown file at
``memories/<category>/<ISO_timestamp>_<title_slug>.md``. The file's YAML
frontmatter carries the structured metadata (title, category, tags,
observed_at, confidence, source); the body is the chunkable text.

The slug is derived deterministically from ``observed_at`` + title so the
agent can compute it without round-tripping through the filesystem.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

_SLUG_CLEANUP = re.compile(r"[^a-z0-9]+")


def slugify_title(title: str, *, max_len: int = 60) -> str:
    """Slugify ``title`` to lowercase ascii with hyphens. Empty → ``"untitled"``."""
    # NFKD strips accents to their ascii base; ignore is intentional for emoji etc.
    norm = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    norm = norm.lower().strip()
    slug = _SLUG_CLEANUP.sub("-", norm).strip("-")
    if not slug:
        return "untitled"
    return slug[:max_len].rstrip("-") or "untitled"


def compose_filename(observed_at: str, title: str) -> str:
    """Compose ``YYYY-MM-DDTHH-MM_<slug>.md`` from a timestamp + title.

    ``observed_at`` is parsed leniently — anything ``datetime.fromisoformat``
    accepts (after the trailing-Z fix) works. Falls back to current UTC time
    if parsing fails.
    """
    ts = _parse_iso(observed_at) or datetime.now(timezone.utc)
    stamp = ts.strftime("%Y-%m-%dT%H-%M")
    return f"{stamp}_{slugify_title(title)}.md"


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    s = value.strip()
    # Python's fromisoformat accepts most variants but doesn't love a trailing Z.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compose_observation_markdown(
    *,
    title: str,
    content: str,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    observed_at: Optional[str] = None,
    confidence: float = 1.0,
    source: Optional[str] = None,
    related_to: Optional[list[str]] = None,
    extra_attributes: Optional[dict[str, Any]] = None,
) -> str:
    """Render a frontmatter + body markdown file as a single string.

    Order of frontmatter keys is stable for cleaner git diffs.
    """
    frontmatter: dict[str, Any] = {"title": title}
    if category is not None:
        frontmatter["category"] = category
    if tags:
        frontmatter["tags"] = list(tags)
    if observed_at:
        frontmatter["observed_at"] = observed_at
    if confidence != 1.0:
        frontmatter["confidence"] = confidence
    if source:
        frontmatter["source"] = source
    if related_to:
        frontmatter["related_to"] = list(related_to)
    if extra_attributes:
        for k, v in extra_attributes.items():
            if k not in frontmatter:
                frontmatter[k] = v
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, default_flow_style=False)
    body = content if content.endswith("\n") else content + "\n"
    return f"---\n{fm_yaml}---\n{body}"


def write_observation_file(
    *,
    project_path: str | Path,
    title: str,
    content: str,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    observed_at: Optional[str] = None,
    confidence: float = 1.0,
    source: Optional[str] = None,
    related_to: Optional[list[str]] = None,
    extra_attributes: Optional[dict[str, Any]] = None,
    memories_subdir: str = "memories",
    overwrite: bool = False,
) -> tuple[Path, str]:
    """Write an observation file under ``memories/<category>/`` and return its path + slug.

    Filename collisions append ``-2``, ``-3``, ... unless ``overwrite=True``.
    Returns ``(absolute_path, slug)`` where ``slug`` is the filename stem
    callers use as a key for ``update_observation`` / ``delete_observation``.
    """
    stamp = observed_at or now_iso()
    root = Path(project_path).expanduser().resolve() / memories_subdir
    if category:
        target_dir = root / category
    else:
        target_dir = root
    target_dir.mkdir(parents=True, exist_ok=True)

    base_name = compose_filename(stamp, title)
    candidate = target_dir / base_name
    if candidate.exists() and not overwrite:
        stem = candidate.stem
        suffix = candidate.suffix
        n = 2
        while (target_dir / f"{stem}-{n}{suffix}").exists():
            n += 1
        candidate = target_dir / f"{stem}-{n}{suffix}"

    text = compose_observation_markdown(
        title=title,
        content=content,
        category=category,
        tags=tags,
        observed_at=stamp,
        confidence=confidence,
        source=source,
        related_to=related_to,
        extra_attributes=extra_attributes,
    )
    candidate.write_text(text, encoding="utf-8")
    return candidate, candidate.stem


__all__ = [
    "slugify_title",
    "compose_filename",
    "compose_observation_markdown",
    "write_observation_file",
    "now_iso",
]
