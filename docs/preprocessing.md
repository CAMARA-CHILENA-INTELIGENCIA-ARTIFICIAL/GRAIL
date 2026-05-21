# Source-file preprocessing

> **Scope.** How GRAIL turns whatever the user drops into ``input/`` into the
> markdown the chunker reads. Code: ``grail/indexing/preprocess.py``.

## What's supported

| Group           | Extensions                                                                                  | Path                                |
|-----------------|----------------------------------------------------------------------------------------------|--------------------------------------|
| **Text-like**   | ``.txt``, ``.md``, ``.markdown``, ``.rst``, ``.log``, ``.srt``, ``.vtt``                     | Read directly — no conversion       |
| **Code (any)**  | ``.py``, ``.ipynb``, ``.js/.ts/.tsx/.jsx``, ``.go``, ``.rs``, ``.java``, ``.kt``, ``.c/.cpp/.h/.hpp``, ``.cs``, ``.rb``, ``.php``, ``.sh/.bash``, ``.sql``, ``.html/.css/.scss``, ``.swift``, ``.scala``, ``.vue`` | Read directly                       |
| **Data**        | ``.json``, ``.jsonl``, ``.yaml``, ``.yml``, ``.toml``, ``.csv``, ``.tsv``, ``.xml``         | Read directly                       |
| **PDF**         | ``.pdf``                                                                                     | Converted to markdown via ``pypdf`` |
| **DOCX**        | ``.docx``, ``.doc``                                                                          | Converted to markdown via ``python-docx`` |

The full list lives in ``grail.indexing.preprocess.SUPPORTED_EXTENSIONS``.
Everything else (images, audio, video, spreadsheets, RTF) is skipped with a
``DEBUG``-level log line — vision-based extraction is a future ``[vision]`` extra.

## The conversion contract

For non-text inputs:

1. The preprocessor runs at index time, lazily — when the loader first reads a
   PDF or DOCX, the cached markdown gets generated.
2. The output lives at ``{input_folder}/_processed/<source-stem>.md``.
   - ``_processed/`` is automatically excluded from input discovery, so the
     processed files don't double-count.
3. If a cached file exists **and** is newer than the source, the cache wins —
   re-runs of ``grail index`` are essentially free on the preprocessing step.
4. The cached markdown is stored in plain UTF-8 with the original document's
   stem as the title (level-1 heading) and per-page or per-section structure
   below. PDF pages become ``## Page N`` sections; DOCX paragraphs preserve
   heading styles (mapped to ``#``/``##``/...) and tables flatten to
   ``|``-separated rows.
5. The ``mapping.json`` for each document records both the original path and
   the processed path — citations always resolve back to the original source.

## What the output looks like

PDF, one of the SEOM 2023 clinical guidelines:

```
# SEOM 2023 cachexia

## Page 1

Vol:.(1234567890)
Clinical and Translational Oncology (2024) 26:2866–2876
…

## Page 2

Cancer-related anorexia-cachexia syndrome (CACS) is a debilitating condition…
```

DOCX, a meeting note:

```
# Q2 planning notes

## Goals

- Launch the new auth service by end of May.
- Ship the migration guide.

### Table 1
Goal | Owner | Due
Auth service | Alice | 2026-05-31
Migration guide | Bob | 2026-06-15
```

## Limitations (today)

- **No OCR.** Image-only PDFs return ``PreprocessingError("no extractable text")``.
  The legacy code had a vision-LLM fallback; that's wired behind a ``[vision]``
  extra slated for a later phase.
- **Local storage only for conversion.** ``pypdf`` and ``python-docx`` need real
  file paths. With a cloud (S3) storage backend, conversion would download to
  a temp file first; the current implementation refuses early with a clear
  error. The roadmap entry is in ``CLAUDE.md`` §12.
- **Tables in DOCX are flattened.** Cell content is concatenated with ``|`` per
  row. Layout-heavy DOCX content (multi-column, embedded objects) is best
  pre-flattened by the author.
- **No automatic re-extraction on prompt edits.** The cache key is the source
  mtime. If you change the preprocessor or the prompt that consumes the
  processed text, ``rm -rf input/_processed`` or pass ``force=True`` when
  invoking ``preprocess_file`` programmatically.

## Programmatic API

```python
from pathlib import Path
from grail.indexing.preprocess import (
    preprocess_directory,    # convert every file under a directory
    preprocess_file,         # convert one file
    get_preprocessor,        # registry lookup
    is_supported,
    needs_preprocessing,
)

# Convert every PDF/DOCX in input/ to input/_processed/*.md
results = preprocess_directory(Path("examples/quickstart/input"))
for r in results:
    if r.ok:
        print(r.source.name, "→", r.processed.name, "(cached)" if r.cached else "")
    else:
        print("FAIL:", r.source.name, r.error)
```

The loader does this automatically — you only need the explicit API when you
want to inspect or force-rebuild.

## Where to look in code

- ``grail/indexing/preprocess.py`` — preprocessors, registry, ``preprocess_file``,
  ``preprocess_directory``.
- ``grail/indexing/loader.py`` — ``FileLoader.find`` enumerates supported
  extensions; ``FileLoader._read_one`` triggers preprocessing on demand and
  returns ``(text, processed_key)`` for ``mapping.json``.
- ``pyproject.toml`` — ``pypdf`` and ``python-docx`` are core dependencies, so
  no extra install step.

## Adding a new format

Implement the :class:`Preprocessor` interface, register it in
``get_preprocessor`` (and add the extension to ``DIRECT_READ_EXTENSIONS`` or
``PREPROCESS_EXTENSIONS``), and the loader picks it up automatically:

```python
class XlsxPreprocessor(Preprocessor):
    output_extension = ".md"

    def extract(self, source: Path) -> str:
        import openpyxl
        wb = openpyxl.load_workbook(source, data_only=True)
        ...
        return markdown
```

The PR that adds this should:
- Update ``SUPPORTED_EXTENSIONS`` / ``PREPROCESS_EXTENSIONS``.
- Document the new format in this file + ``docs/glossary.md``.
- Add the new dep to ``pyproject.toml`` (core or behind an extra — your call).
- Add a unit test covering happy path + at least one failure mode.
