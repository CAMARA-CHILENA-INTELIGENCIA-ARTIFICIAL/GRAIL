"""
File loader and chunker.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Walks a directory of source files, preprocesses non-text formats (PDF, DOCX)
into markdown, splits everything into token-sized chunks with mixed-document
support, and emits two parquet artefacts that the rest of the pipeline consumes:

* ``final_docs.parquet`` — one row per source file (id, title, raw_content, path,
  text_unit_ids — the chunks generated from this doc).
* ``partial_text_units.parquet`` — one row per chunk (id, text, n_tokens,
  document_id, document_ids).

Plus a ``mapping.json`` keyed by document_id with the original on-disk path,
the processed-file path (when conversion happened), source extension, and other
metadata. ``mapping.json`` is the citation root: every search response resolves
text_unit → document_ids → mapping → original_path.

Supported source types live in :mod:`grail.indexing.preprocess`. Text-like /
code / data files are read directly; PDFs and DOCX are converted to markdown via
the registered :class:`Preprocessor` and the result is cached under
``{input_folder}/_processed/`` so subsequent runs are O(1).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml

from grail.indexing.preprocess import (
    PREPROCESS_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    PreprocessResult,
    preprocess_file,
)
from grail.indexing.schema_migration import migrate_dataframe
from grail.reporting import NullReporter, Reporter
from grail.storage import LocalStorage, StorageBackend
from grail.utils.chunker import TokenTextSplitter
from grail.utils.ids import generate_guid
from grail.utils.text import detect_data_type

log = logging.getLogger(__name__)

_DEFAULT_DOC_BOUNDARY = "\n\n---DOCUMENT_BOUNDARY---\n\n"
PROCESSED_SUBDIR = "_processed"

# Frontmatter keys we lift directly into typed columns on ``final_docs``.
# Anything else found in the frontmatter is preserved into the ``attributes``
# JSON column so memory-mode users don't lose unstructured metadata.
_KNOWN_FRONTMATTER_KEYS = frozenset({
    "title",
    "category",
    "tags",
    "observed_at",
    "confidence",
    "source",
    "related_to",
})

# ``---\n<yaml>\n---\n`` block at the very start of a file. Matches the standard
# Jekyll/Hugo/Pandoc frontmatter convention.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from a markdown body.

    Returns ``(frontmatter_dict, body_text)``. If no frontmatter block is
    present, returns ``({}, text)`` unchanged. Malformed YAML is logged and
    the file content is returned with no frontmatter (lenient by design —
    we never want a typo in YAML to silently drop a memory).
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_yaml = match.group(1)
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        log.warning("Malformed frontmatter — ignoring: %s", exc)
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    body = text[match.end():]
    return data, body


@dataclass
class FileLoader:
    """Discover, read, and chunk source files.

    ``storage`` is the StorageBackend rooted at the project directory. Inputs live
    under ``input_folder`` (relative key), outputs go under ``output_folder``.
    ``mapping.json`` is kept at the project root so it can be edited by humans.
    """

    storage: StorageBackend
    input_folder: str = "input"
    output_folder: str = "output"
    chunk_size: int = 2000
    chunk_overlap: int = 50
    encoding_name: str = "cl100k_base"
    document_boundary: str = _DEFAULT_DOC_BOUNDARY
    exclude_patterns: list[str] = field(default_factory=list)
    parse_frontmatter: bool = True
    reporter: Reporter = field(default_factory=NullReporter)

    def __post_init__(self) -> None:
        self._splitter = TokenTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            encoding_name=self.encoding_name,
        )

    # ------------------------------------------------------------------ discovery

    def find(self) -> list[str]:
        """Return keys (relative to storage root) for every supported input file.

        Files whose extension is in :data:`SUPPORTED_EXTENSIONS` qualify. PDFs
        and DOCX files are listed by their **original** path here — preprocessing
        happens lazily during :meth:`_read_one`.
        """
        keys = self.storage.list(self.input_folder)
        out: list[str] = []
        for key in keys:
            base = key.rsplit("/", 1)[-1]
            if base.startswith(".") or base.startswith("_"):
                continue
            # Skip anything that lives inside the processed-output directory.
            if f"/{PROCESSED_SUBDIR}/" in f"/{key}/":
                continue
            if any(pat in key for pat in self.exclude_patterns):
                continue
            if Path(key).suffix.lower() not in SUPPORTED_EXTENSIONS:
                log.debug("Skipping %s (unsupported extension)", key)
                continue
            out.append(key)
        return sorted(out)

    def _processed_path_for(self, key: str) -> Path:
        """Where the processed version of ``key`` lives on disk.

        Only meaningful for backends that expose a real filesystem path. Cloud
        backends would need a different cache layout — that's a follow-up.
        """
        if not isinstance(self.storage, LocalStorage):
            raise RuntimeError(
                "PDF/DOCX preprocessing currently requires the LocalStorage backend "
                "(needs a real on-disk path for pypdf / python-docx). "
                "S3/remote support is on the roadmap."
            )
        return (
            self.storage.path_for(self.input_folder) / PROCESSED_SUBDIR
        )

    def _read_one(self, key: str) -> tuple[str, Optional[str], dict[str, Any]]:
        """Read ``key`` from storage and return ``(text, processed_key, frontmatter)``.

        For text-like files, ``processed_key`` is ``None`` (no conversion happened).
        For PDFs / DOCX, ``processed_key`` is the storage-relative path to the
        cached markdown produced by preprocessing.

        ``frontmatter`` is the parsed YAML frontmatter dict (empty when the file
        had none or when ``parse_frontmatter=False``). When frontmatter is
        present, ``text`` is the body **with the frontmatter block stripped** so
        chunking doesn't index YAML as content.
        """
        ext = Path(key).suffix.lower()
        if ext in PREPROCESS_EXTENSIONS:
            source = self.storage.path_for(key) if isinstance(self.storage, LocalStorage) else None
            if source is None:
                raise RuntimeError(
                    f"Cannot preprocess {key} — non-local storage backends are not yet supported."
                )
            output_dir = self._processed_path_for(key)
            result: PreprocessResult = preprocess_file(source, output_dir=output_dir)
            if not result.ok:
                self.reporter.warning(
                    f"Preprocessing failed for {Path(key).name}: {result.error}"
                )
                raise ValueError(result.error)
            self.reporter.info(
                f"Preprocessed {Path(key).name} → {result.processed.name}"
                + (" (cached)" if result.cached else "")
            )
            processed_key = self.storage.join(
                self.input_folder, PROCESSED_SUBDIR, result.processed.name
            )
            text = self.storage.read_text(processed_key)
            fm, body = self._maybe_parse_frontmatter(text, ext=".md")
            return body, processed_key, fm

        try:
            text = self.storage.read_text(key)
        except UnicodeDecodeError:
            data = self.storage.read_bytes(key)
            text = data.decode("utf-8", errors="replace")
        fm, body = self._maybe_parse_frontmatter(text, ext=ext)
        return body, None, fm

    def _maybe_parse_frontmatter(
        self, text: str, *, ext: str
    ) -> tuple[dict[str, Any], str]:
        """Parse frontmatter only for markdown-family files when enabled."""
        if not self.parse_frontmatter:
            return {}, text
        if ext not in {".md", ".markdown"}:
            return {}, text
        return parse_frontmatter(text)

    # ------------------------------------------------------------------ chunking

    def build_text_units(
        self, keys: Optional[list[str]] = None
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        """Read all input files, chunk them, return (docs_df, text_units_df, mapping).

        The mixed-document chunker concatenates the source files into one big buffer
        separated by :attr:`document_boundary`, then chunks it with :class:`TokenTextSplitter`.
        For each chunk we record which documents contributed any text, so search
        results can cite multiple source files when chunks straddle a boundary.
        """
        keys = keys if keys is not None else self.find()
        if not keys:
            return pd.DataFrame(), pd.DataFrame(), {}

        documents: list[dict[str, Any]] = []
        mapping: dict[str, Any] = {}
        # doc_id -> {observed_at, confidence, source} for inheritance into chunks.
        doc_provenance: dict[str, dict[str, Any]] = {}

        # First pass: read every file (preprocessing PDFs/DOCX on the fly), record
        # offsets in the concatenated buffer for chunk → doc back-mapping.
        buffer_parts: list[str] = []
        char_offsets: list[tuple[str, int, int]] = []  # (doc_id, start_char, end_char)
        cursor = 0
        for key in keys:
            try:
                text, processed_key, frontmatter = self._read_one(key)
            except (ValueError, RuntimeError) as exc:
                self.reporter.warning(f"Skipping {key}: {exc}")
                continue
            doc_id = generate_guid()
            # ``title`` from frontmatter takes precedence over the filename when
            # the agent supplied one (memory mode); otherwise the basename wins.
            title = str(frontmatter.get("title") or Path(key).name)
            category = frontmatter.get("category")
            tags_raw = frontmatter.get("tags", []) or []
            tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else [str(tags_raw)]
            attributes = {
                k: v for k, v in frontmatter.items() if k not in _KNOWN_FRONTMATTER_KEYS
            }
            doc_observed = frontmatter.get("observed_at")
            doc_observed_iso = (
                doc_observed.isoformat()
                if hasattr(doc_observed, "isoformat")
                else (str(doc_observed) if doc_observed else None)
            )
            doc_confidence = (
                float(frontmatter["confidence"])
                if "confidence" in frontmatter and frontmatter["confidence"] is not None
                else 1.0
            )
            doc_source = (
                str(frontmatter["source"]) if frontmatter.get("source") else None
            )
            documents.append(
                {
                    "id": doc_id,
                    "title": title,
                    "raw_content": text,
                    "path": key,
                    "text_unit_ids": [],
                    "mapping": key,
                    "category": str(category) if category is not None else None,
                    "tags": tags,
                    "attributes": json.dumps(attributes) if attributes else None,
                    # Provenance: document-level mirror of what text_units carry,
                    # so RecallFilter can filter docs by date / confidence / source
                    # without joining to TUs.
                    "observed_at": doc_observed_iso,
                    "confidence": doc_confidence,
                    "source": doc_source,
                }
            )
            mapping[doc_id] = {
                "original_path": key,
                "processed_path": processed_key,  # None when no preprocessing was needed
                "title": title,
                "extension": Path(key).suffix.lower(),
                "data_type": detect_data_type(key),
                "size_chars": len(text),
            }
            doc_provenance[doc_id] = {
                "observed_at": frontmatter.get("observed_at"),
                "confidence": float(frontmatter["confidence"])
                if "confidence" in frontmatter and frontmatter["confidence"] is not None
                else 1.0,
                "source": str(frontmatter["source"]) if frontmatter.get("source") else None,
            }
            start = cursor
            buffer_parts.append(text)
            cursor += len(text)
            char_offsets.append((doc_id, start, cursor))
            buffer_parts.append(self.document_boundary)
            cursor += len(self.document_boundary)

        if not documents:
            self.reporter.warning("No files were successfully read.")
            return pd.DataFrame(), pd.DataFrame(), {}

        combined = "".join(buffer_parts)

        chunks = self._splitter.split_text(combined)
        # Locate each chunk back in the combined buffer to figure out which docs it touched.
        search_start = 0
        text_units: list[dict[str, Any]] = []
        for chunk in chunks:
            idx = combined.find(chunk, search_start)
            if idx == -1:
                # tiktoken decode can drift on multi-byte chars; fall back to a fresh search.
                idx = combined.find(chunk)
                if idx == -1:
                    idx = search_start
            chunk_start, chunk_end = idx, idx + len(chunk)
            search_start = max(search_start, chunk_end - self.chunk_overlap)

            doc_ids = [
                doc_id
                for doc_id, dstart, dend in char_offsets
                if not (dend <= chunk_start or dstart >= chunk_end)
            ]
            if not doc_ids:
                doc_ids = [char_offsets[0][0]]
            tu_id = generate_guid()
            # Provenance: when a chunk straddles multiple docs we use the
            # *primary* doc (first / largest contribution) — observed_at takes
            # the max across contributing docs, confidence the min, source the
            # primary doc's value. This mirrors how we'll aggregate further up
            # to entities/relationships in Phase A3.
            primary = doc_provenance.get(doc_ids[0], {})
            observed_vals = [
                doc_provenance.get(d, {}).get("observed_at") for d in doc_ids
            ]
            # PyYAML may give us either strings or datetime objects. Normalise
            # to ISO-8601 strings so ``max()`` compares lexically (works for
            # ISO-8601, which is sortable as text).
            observed_vals = [
                v.isoformat() if hasattr(v, "isoformat") else str(v)
                for v in observed_vals if v is not None
            ]
            confidence_vals = [
                doc_provenance.get(d, {}).get("confidence", 1.0) for d in doc_ids
            ]
            text_units.append(
                {
                    "id": tu_id,
                    "text": chunk,
                    "n_tokens": self._splitter.count_tokens(chunk),
                    "document_id": doc_ids[0],
                    "document_ids": doc_ids,
                    "observed_at": max(observed_vals) if observed_vals else None,
                    "confidence": min(confidence_vals) if confidence_vals else 1.0,
                    "source": primary.get("source"),
                }
            )

        # Backfill each document with the text_unit_ids it contributes to.
        doc_to_tus: dict[str, list[str]] = {d["id"]: [] for d in documents}
        for tu in text_units:
            for doc_id in tu["document_ids"]:
                doc_to_tus.setdefault(doc_id, []).append(tu["id"])
        for doc in documents:
            doc["text_unit_ids"] = doc_to_tus.get(doc["id"], [])

        docs_df = pd.DataFrame(documents)
        text_units_df = pd.DataFrame(text_units)
        return docs_df, text_units_df, mapping

    # ------------------------------------------------------------------ persistence

    def write_artifacts(
        self,
        docs_df: pd.DataFrame,
        text_units_df: pd.DataFrame,
        mapping: dict[str, Any],
    ) -> None:
        """Write parquet + mapping.json into the output folder."""
        self.storage.ensure_prefix(self.output_folder)
        with self.storage.open_for_write(f"{self.output_folder}/final_docs.parquet") as path:
            docs_df.to_parquet(path, index=False)
        with self.storage.open_for_write(
            f"{self.output_folder}/partial_text_units.parquet"
        ) as path:
            text_units_df.to_parquet(path, index=False)
        self.storage.write_text("mapping.json", json.dumps(mapping, indent=2))

    def load_artifacts(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        """Read previously written parquet + mapping.json. Empty DataFrames if missing."""
        if not self.storage.exists(f"{self.output_folder}/final_docs.parquet"):
            return pd.DataFrame(), pd.DataFrame(), {}
        with self.storage.open_for_read(f"{self.output_folder}/final_docs.parquet") as path:
            docs_df = pd.read_parquet(path)
        docs_df = migrate_dataframe(docs_df, "final_docs")
        text_units_df = pd.DataFrame()
        if self.storage.exists(f"{self.output_folder}/partial_text_units.parquet"):
            with self.storage.open_for_read(
                f"{self.output_folder}/partial_text_units.parquet"
            ) as path:
                text_units_df = pd.read_parquet(path)
            text_units_df = migrate_dataframe(text_units_df, "final_text_units")
        mapping: dict[str, Any] = {}
        if self.storage.exists("mapping.json"):
            mapping = json.loads(self.storage.read_text("mapping.json"))
        return docs_df, text_units_df, mapping

    # ------------------------------------------------------------------ convenience

    # ------------------------------------------------------------------ incremental ops

    def append_files(
        self, new_keys: list[str]
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], list[str]]:
        """Incrementally add new files without re-processing existing ones.

        Chunks only the new files, merges with existing artifacts.
        Returns ``(docs_df, text_units_df, mapping, new_text_unit_ids)``.
        """
        existing_docs_df, existing_text_units_df, existing_mapping = self.load_artifacts()

        new_docs_df, new_text_units_df, new_mapping = self.build_text_units(keys=new_keys)
        if new_docs_df.empty:
            return existing_docs_df, existing_text_units_df, existing_mapping, []

        docs_df = pd.concat([existing_docs_df, new_docs_df], ignore_index=True)
        text_units_df = pd.concat(
            [existing_text_units_df, new_text_units_df], ignore_index=True
        )
        mapping = {**existing_mapping, **new_mapping}
        new_text_unit_ids = new_text_units_df["id"].tolist()

        self.reporter.info(
            f"Appended {len(new_docs_df)} file(s) → {len(new_text_unit_ids)} new text unit(s)."
        )
        return docs_df, text_units_df, mapping, new_text_unit_ids

    def batch_edit_documents(
        self, edits: list[dict[str, Any]]
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], list[str]]:
        """Re-chunk edited documents, properly handling mixed-document text units.

        ``edits`` is a list of ``{"doc_id": str, "new_content": str}``.

        Finds every text unit that references an edited document (including mixed
        chunks that straddle multiple docs), removes them, re-chunks the affected
        document groups with new content.

        Returns ``(docs_df, text_units_df, mapping, edited_text_unit_ids)`` where
        ``edited_text_unit_ids`` are the IDs of the *newly created* replacement TUs.
        """
        docs_df, text_units_df, mapping = self.load_artifacts()
        doc_edits = {e["doc_id"]: e["new_content"] for e in edits}

        affected_tu_ids: set[str] = set()
        for doc_id in doc_edits:
            if "document_ids" in text_units_df.columns:
                mask = text_units_df["document_ids"].apply(
                    lambda x, did=doc_id: did in x if isinstance(x, list) else did == x
                )
            else:
                mask = text_units_df["document_id"] == doc_id
            affected_tu_ids.update(text_units_df.loc[mask, "id"].tolist())

        units_to_recreate: list[dict[str, Any]] = []
        for tu_id in affected_tu_ids:
            row = text_units_df[text_units_df["id"] == tu_id].iloc[0]
            doc_ids = row.get("document_ids", [row.get("document_id")])
            if not isinstance(doc_ids, list):
                doc_ids = [doc_ids]
            units_to_recreate.append(
                {"doc_ids": doc_ids, "start_doc_id": row["document_id"]}
            )

        text_units_df = text_units_df[~text_units_df["id"].isin(affected_tu_ids)].copy()

        for doc_id, new_content in doc_edits.items():
            mask = docs_df["id"] == doc_id
            docs_df.loc[mask, "raw_content"] = new_content
            for idx in docs_df.index[mask]:
                docs_df.at[idx, "text_unit_ids"] = []
            if doc_id in mapping:
                mapping[doc_id]["size_chars"] = len(new_content)

        doc_groups: dict[tuple[str, ...], list[dict]] = {}
        for info in units_to_recreate:
            key = tuple(sorted(info["doc_ids"]))
            doc_groups.setdefault(key, []).append(info)

        new_text_units: list[dict[str, Any]] = []
        all_edited_tu_ids: list[str] = []

        for doc_ids_tuple, unit_infos in doc_groups.items():
            doc_ids = list(doc_ids_tuple)
            parts: list[str] = []
            for i, doc_id in enumerate(doc_ids):
                if i > 0:
                    parts.append(self.document_boundary)
                if doc_id in doc_edits:
                    parts.append(doc_edits[doc_id])
                else:
                    doc_row = docs_df[docs_df["id"] == doc_id]
                    if not doc_row.empty:
                        parts.append(doc_row.iloc[0]["raw_content"])

            combined = "".join(parts)
            chunks = self._splitter.split_text(combined)
            start_doc_id = unit_infos[0]["start_doc_id"]

            for chunk in chunks:
                tu_id = generate_guid()
                all_edited_tu_ids.append(tu_id)
                new_text_units.append(
                    {
                        "id": tu_id,
                        "text": chunk,
                        "n_tokens": self._splitter.count_tokens(chunk),
                        "document_id": start_doc_id,
                        "document_ids": doc_ids,
                    }
                )
                for doc_id in doc_ids:
                    for idx in docs_df.index[docs_df["id"] == doc_id]:
                        current = docs_df.at[idx, "text_unit_ids"]
                        if not isinstance(current, list):
                            current = []
                        current.append(tu_id)
                        docs_df.at[idx, "text_unit_ids"] = current

        if new_text_units:
            text_units_df = pd.concat(
                [text_units_df, pd.DataFrame(new_text_units)], ignore_index=True
            )

        self.reporter.info(
            f"Edited {len(doc_edits)} doc(s): removed {len(affected_tu_ids)} TU(s), "
            f"created {len(all_edited_tu_ids)} replacement(s)."
        )
        return docs_df, text_units_df, mapping, all_edited_tu_ids

    def batch_delete_documents(
        self, doc_ids: list[str]
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], list[str]]:
        """Delete documents and their text units.

        Also removes source files from the input folder.
        Returns ``(docs_df, text_units_df, mapping, deleted_text_unit_ids)``.
        """
        docs_df, text_units_df, mapping = self.load_artifacts()

        docs_to_delete = docs_df[docs_df["id"].isin(doc_ids)]
        if docs_to_delete.empty:
            self.reporter.warning("No matching documents found for deletion.")
            return docs_df, text_units_df, mapping, []

        tu_ids_to_delete: list[str] = []
        for _, doc in docs_to_delete.iterrows():
            tu_ids = doc.get("text_unit_ids", [])
            if isinstance(tu_ids, list):
                tu_ids_to_delete.extend(tu_ids)

        for _, doc in docs_to_delete.iterrows():
            key = self.storage.join(self.input_folder, doc["path"])
            if self.storage.exists(key):
                self.storage.delete(key)

        docs_df = docs_df[~docs_df["id"].isin(doc_ids)].copy()
        text_units_df = text_units_df[~text_units_df["id"].isin(tu_ids_to_delete)].copy()
        for did in doc_ids:
            mapping.pop(did, None)

        self.reporter.info(
            f"Deleted {len(doc_ids)} doc(s) and {len(tu_ids_to_delete)} text unit(s)."
        )
        return docs_df, text_units_df, mapping, tu_ids_to_delete

    def get_doc_ids_by_path(self, filenames: list[str]) -> list[str]:
        """Look up document IDs for filenames matching the ``path`` column."""
        docs_df, _, _ = self.load_artifacts()
        if docs_df.empty:
            return []
        basenames = {Path(f).name for f in filenames}
        mask = docs_df["path"].apply(lambda p: Path(p).name in basenames)
        return docs_df.loc[mask, "id"].tolist()

    # ------------------------------------------------------------------ convenience

    @classmethod
    def from_local_root(cls, root: str | os.PathLike, **kwargs: Any) -> "FileLoader":
        """Quickstart helper: bind a :class:`LocalStorage` rooted at ``root``."""
        return cls(storage=LocalStorage(root=root), **kwargs)
