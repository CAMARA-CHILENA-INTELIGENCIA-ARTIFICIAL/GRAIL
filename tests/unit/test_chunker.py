"""Token chunker tests."""
from grail.utils.chunker import TokenTextSplitter


def test_chunker_handles_empty():
    splitter = TokenTextSplitter(chunk_size=100, chunk_overlap=10)
    assert splitter.split_text("") == []


def test_chunker_returns_single_chunk_when_under_limit():
    splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=50)
    text = "hello world " * 5
    chunks = splitter.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunker_splits_long_text_with_overlap():
    splitter = TokenTextSplitter(chunk_size=20, chunk_overlap=5)
    # Force well past the threshold.
    text = "the quick brown fox jumps over the lazy dog. " * 30
    chunks = splitter.split_text(text)
    assert len(chunks) > 1
    # Each chunk should be at most chunk_size tokens.
    for chunk in chunks:
        assert splitter.count_tokens(chunk) <= splitter.chunk_size


def test_chunker_rejects_invalid_overlap():
    import pytest

    with pytest.raises(ValueError):
        TokenTextSplitter(chunk_size=10, chunk_overlap=20)
