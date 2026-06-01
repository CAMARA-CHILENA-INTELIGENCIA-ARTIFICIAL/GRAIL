"""Pluggable storage backends.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Default is :class:`LocalStorage`. Install ``graphgrail[s3]`` and use :class:`S3Storage`
for S3-backed projects. Implement :class:`StorageBackend` for anything else
(GCS, Azure, IPFS, ...).
"""
from grail.storage.base import StorageBackend
from grail.storage.local import LocalStorage

__all__ = ["LocalStorage", "StorageBackend"]


def get_backend(kind: str = "local", **kwargs) -> StorageBackend:
    """Factory: ``get_backend("local", root="...")`` or ``get_backend("s3", bucket="...")``."""
    kind = kind.lower()
    if kind in {"local", "fs", "file"}:
        return LocalStorage(**kwargs)
    if kind == "s3":
        try:
            from grail.storage.s3 import S3Storage  # local import — boto3 is optional.
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "S3 backend requires the optional [s3] extra. "
                "Install with: pip install 'graphgrail[s3]'"
            ) from exc
        return S3Storage(**kwargs)
    raise ValueError(f"Unknown storage backend kind: {kind!r}")
