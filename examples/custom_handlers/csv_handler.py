"""
Example custom file handler — CSV / TSV ingestion.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Copy this file into a directory and point ``handlers.custom_paths`` at that
directory in your ``grail.yaml``::

    handlers:
      custom_paths: ["handlers"]

GRAIL will then ingest ``.csv`` / ``.tsv`` files through ``CsvDescribeHandler``.

Two patterns are shown:

* ``CsvDescribeHandler`` (active, exported as ``HANDLER``) — *describe* mode.
  Profiles the table (schema, dtypes, summary stats, a few sample rows) into a
  markdown document. That markdown flows through the normal GRAIL pipeline, so
  the LLM extracts entities/relationships from a compact, meaningful summary
  instead of choking on tens of thousands of raw rows.

* ``CsvEmitHandler`` (commented out) — *emit* mode. Turns each row into an
  entity deterministically, with no LLM call. Uncomment and swap the export if
  your CSV is a clean entity table (people, products, accounts, …).

Both are pure-Python here, but a handler may use ``ctx.llm`` to *describe*
agentically — e.g. ask the model to narrate what the dataset is about.
"""
from __future__ import annotations

from pathlib import Path

from grail.indexing.handlers import (
    EmitEntity,
    EmitRelationship,
    EmitResult,
    FileHandler,
    HandlerContext,
)


def _read_table(source: Path):
    import pandas as pd

    sep = "\t" if source.suffix.lower() == ".tsv" else ","
    return pd.read_csv(source, sep=sep)


class CsvDescribeHandler(FileHandler):
    """Profile a CSV/TSV into a markdown description for the graph pipeline."""

    NAME = "csv_describe"
    EXTENSIONS = frozenset({".csv", ".tsv"})

    # Cap how many sample rows we inline so a huge file stays a *summary*.
    SAMPLE_ROWS = 10

    async def describe(self, source: Path, ctx: HandlerContext) -> str:
        df = _read_table(source)
        title = source.stem.replace("_", " ").strip()

        lines: list[str] = [f"# {title}", ""]
        lines.append(f"Tabular dataset with {len(df):,} rows and {len(df.columns)} columns.")
        lines.append("")

        lines.append("## Columns")
        lines.append("")
        lines.append("| column | dtype | non-null | sample values |")
        lines.append("| --- | --- | --- | --- |")
        for col in df.columns:
            series = df[col]
            samples = ", ".join(str(v) for v in series.dropna().unique()[:3])
            lines.append(
                f"| {col} | {series.dtype} | {series.notna().sum()}/{len(df)} | {samples} |"
            )
        lines.append("")

        # Numeric summary, when there is anything numeric.
        numeric = df.select_dtypes("number")
        if not numeric.empty:
            lines.append("## Numeric summary")
            lines.append("")
            stats = numeric.describe().round(3)
            lines.append("| stat | " + " | ".join(stats.columns) + " |")
            lines.append("| --- | " + " | ".join("---" for _ in stats.columns) + " |")
            for stat, row in stats.iterrows():
                lines.append(f"| {stat} | " + " | ".join(str(v) for v in row) + " |")
            lines.append("")

        # A few representative rows.
        head = df.head(self.SAMPLE_ROWS)
        lines.append(f"## Sample rows (first {len(head)})")
        lines.append("")
        lines.append("| " + " | ".join(str(c) for c in head.columns) + " |")
        lines.append("| " + " | ".join("---" for _ in head.columns) + " |")
        for _, row in head.iterrows():
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
        lines.append("")

        return "\n".join(lines)


# Active handler GRAIL will pick up.
HANDLER = CsvDescribeHandler()


# --------------------------------------------------------------------------- #
# Emit-mode variant. Uncomment and set ``HANDLER = CsvEmitHandler()`` to turn
# each row of an entity table directly into a graph node (no LLM extraction).
# --------------------------------------------------------------------------- #
#
# class CsvEmitHandler(FileHandler):
#     """Emit one entity per row of a clean entity table."""
#
#     NAME = "csv_emit"
#     EXTENSIONS = frozenset({".csv", ".tsv"})
#
#     # The column whose value names the entity, and its entity type.
#     NAME_COLUMN = "name"
#     ENTITY_TYPE = "RECORD"
#
#     async def emit(self, source: Path, ctx: HandlerContext) -> EmitResult:
#         df = _read_table(source)
#         entities: list[EmitEntity] = []
#         for _, row in df.iterrows():
#             name = str(row[self.NAME_COLUMN]).strip().upper()
#             if not name:
#                 continue
#             description = "; ".join(
#                 f"{col}: {row[col]}" for col in df.columns if col != self.NAME_COLUMN
#             )
#             entities.append(
#                 EmitEntity(name=name, type=self.ENTITY_TYPE, description=description)
#             )
#         return EmitResult(
#             entities=entities,
#             relationships=[],  # add EmitRelationship(...) to link rows
#             text=f"{len(entities)} records emitted from {source.name}.",
#         )
#
# HANDLER = CsvEmitHandler()
