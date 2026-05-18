"""
File loader and chunker.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Walks a directory of source files, reads them, splits them into token-sized chunks
with mixed-document support, and emits two parquet artefacts that the rest of the
pipeline consumes:

* ``final_docs.parquet`` — one row per source file (id, title, raw_content, path,
  text_unit_ids — the chunks generated from this doc).
* ``partial_text_units.parquet`` — one row per chunk (id, text, n_tokens,
  document_id, document_ids).

Plus a ``mapping.json`` keyed by document_id with the original on-disk path,
source extension, and any extracted metadata. ``mapping.json`` is the citation
root: every search response resolves text_unit → document_ids → mapping →
original_path.

v0.1 supports text-like files (extensions in :func:`grail.utils.detect_data_type`
buckets ``text``, ``code``, ``data``). PDF / Office / vision extraction will land
in a later phase via the same provenance schema — slot a pre-processing step in
``FileLoader._read_one`` that returns plain text per file.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from grail.reporting import NullReporter, Reporter
from grail.storage import LocalStorage, StorageBackend
from grail.utils.chunker import TokenTextSplitter
from grail.utils.ids import generate_guid
from grail.utils.text import detect_data_type

log = logging.getLogger(__name__)

_DEFAULT_DOC_BOUNDARY = "\n\n---DOCUMENT_BOUNDARY---\n\n"
_READABLE_TYPES = {"text", "code", "data"}


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
    reporter: Reporter = field(default_factory=NullReporter)

    def __post_init__(self) -> None:
        self._splitter = TokenTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            encoding_name=self.encoding_name,
        )

    # ------------------------------------------------------------------ discovery

    def find(self) -> list[str]:
        """Return keys (relative to storage root) for every readable input file."""
        keys = self.storage.list(self.input_folder)
        out: list[str] = []
        for key in keys:
            base = key.rsplit("/", 1)[-1]
            if base.startswith(".") or base.startswith("_"):
                continue
            if any(pat in key for pat in self.exclude_patterns):
                continue
            if detect_data_type(key) not in _READABLE_TYPES:
                # We log but don't fail — multi-modal hooks plug in here later.
                log.debug("Skipping %s (unsupported type)", key)
                continue
            out.append(key)
        return sorted(out)

    def _read_one(self, key: str) -> str:
        """Read ``key`` from storage and return its text content."""
        try:
            return self.storage.read_text(key)
        except UnicodeDecodeError:
            data = self.storage.read_bytes(key)
            return data.decode("utf-8", errors="replace")

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

        # First pass: read every file, record offsets in the concatenated buffer.
        buffer_parts: list[str] = []
        char_offsets: list[tuple[str, int, int]] = []  # (doc_id, start_char, end_char)
        cursor = 0
        for key in keys:
            text = self._read_one(key)
            doc_id = generate_guid()
            title = Path(key).name
            documents.append(
                {
                    "id": doc_id,
                    "title": title,
                    "raw_content": text,
                    "path": key,
                    "text_unit_ids": [],
                }
            )
            mapping[doc_id] = {
                "original_path": key,
                "title": title,
                "extension": Path(key).suffix.lower(),
                "data_type": detect_data_type(key),
                "size_chars": len(text),
            }
            start = cursor
            buffer_parts.append(text)
            cursor += len(text)
            char_offsets.append((doc_id, start, cursor))
            buffer_parts.append(self.document_boundary)
            cursor += len(self.document_boundary)

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
            text_units.append(
                {
                    "id": tu_id,
                    "text": chunk,
                    "n_tokens": self._splitter.count_tokens(chunk),
                    "document_id": doc_ids[0],
                    "document_ids": doc_ids,
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
        text_units_df = pd.DataFrame()
        if self.storage.exists(f"{self.output_folder}/partial_text_units.parquet"):
            with self.storage.open_for_read(
                f"{self.output_folder}/partial_text_units.parquet"
            ) as path:
                text_units_df = pd.read_parquet(path)
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
