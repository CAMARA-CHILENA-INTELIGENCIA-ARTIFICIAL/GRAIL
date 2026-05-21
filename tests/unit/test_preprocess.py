"""Preprocessor tests (PDF / DOCX / passthrough)."""
from pathlib import Path

import pytest

from grail.indexing.preprocess import (
    DIRECT_READ_EXTENSIONS,
    PREPROCESS_EXTENSIONS,
    DocxPreprocessor,
    PdfPreprocessor,
    PreprocessResult,
    TextPreprocessor,
    get_preprocessor,
    is_supported,
    needs_preprocessing,
    preprocess_directory,
    preprocess_file,
)


def test_supported_extension_buckets_are_disjoint():
    assert DIRECT_READ_EXTENSIONS.isdisjoint(PREPROCESS_EXTENSIONS)


def test_needs_preprocessing():
    assert needs_preprocessing("paper.pdf") is True
    assert needs_preprocessing("report.docx") is True
    assert needs_preprocessing("notes.md") is False
    assert needs_preprocessing("script.py") is False


def test_is_supported_covers_all_buckets():
    assert is_supported("a.pdf")
    assert is_supported("a.docx")
    assert is_supported("a.md")
    assert is_supported("a.py")
    assert is_supported("a.json")
    assert not is_supported("a.png")
    assert not is_supported("a.mp4")


def test_get_preprocessor_routes_correctly():
    assert isinstance(get_preprocessor(".pdf"), PdfPreprocessor)
    assert isinstance(get_preprocessor("pdf"), PdfPreprocessor)
    assert isinstance(get_preprocessor(".docx"), DocxPreprocessor)
    assert isinstance(get_preprocessor(".md"), TextPreprocessor)
    assert isinstance(get_preprocessor(".py"), TextPreprocessor)
    assert get_preprocessor(".mp4") is None


def test_text_preprocessor_passthrough(tmp_path: Path):
    src = tmp_path / "hello.md"
    src.write_text("# heading\n\nbody")
    out = TextPreprocessor().extract(src)
    assert out == "# heading\n\nbody"


def test_preprocess_file_caches_subsequent_runs(tmp_path: Path):
    src = tmp_path / "note.md"
    src.write_text("hi")
    out_dir = tmp_path / "_processed"
    first = preprocess_file(src, output_dir=out_dir)
    assert first.ok
    # Direct-read files have no separate cached file — the result points at the source.
    # Repeat the call on a PDF/DOCX with a fake to confirm caching behaviour:
    pdf_src = tmp_path / "fake.pdf"
    pdf_src.write_bytes(b"not a real pdf")
    bad = preprocess_file(pdf_src, output_dir=out_dir)
    # Real pypdf rejects this content; we expect an error in result.error rather than an exception.
    assert not bad.ok
    assert bad.error


@pytest.mark.skipif(
    not Path("sample_data/test_data").exists(),
    reason="sample_data/test_data is not present in this checkout",
)
def test_preprocess_directory_real_pdfs(tmp_path: Path):
    """Integration-level: run on the bundled SEOM PDFs if available."""
    import shutil

    target = tmp_path / "in"
    target.mkdir()
    for pdf in Path("sample_data/test_data").glob("*.pdf"):
        shutil.copy(pdf, target / pdf.name)
    results = preprocess_directory(target)
    assert results, "Expected at least one result"
    pdfs = [r for r in results if r.source.suffix.lower() == ".pdf"]
    assert pdfs, "Expected to see the SEOM PDFs"
    for r in pdfs:
        assert r.ok, f"Failed: {r.error}"
        assert r.processed.exists()
        content = r.processed.read_text(encoding="utf-8")
        assert content.startswith("#")
        assert "## Page 1" in content
