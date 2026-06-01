"""
S3-backed storage (optional).

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Install with ``pip install 'graphgrail[s3]'``. This module is imported lazily — it is safe
to leave it out of the dependency closure for users who only run locally.
"""
from __future__ import annotations

import io
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "S3 storage requires the [s3] extra. Install with: pip install 'graphgrail[s3]'"
    ) from exc

from grail.storage.base import StorageBackend, normalize_key


class S3Storage(StorageBackend):
    """S3 storage backend. Keys are object names under ``prefix`` within ``bucket``."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        *,
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = normalize_key(prefix)
        self.client = boto3.client(
            "s3",
            region_name=region_name or os.getenv("AWS_REGION_NAME"),
            aws_access_key_id=aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
            endpoint_url=endpoint_url,
        )

    def _full(self, key: str) -> str:
        key = normalize_key(key)
        return f"{self.prefix}/{key}" if self.prefix else key

    def join(self, *parts: str) -> str:
        return normalize_key("/".join(parts))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._full(key))
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def list(self, prefix: str = "") -> list[str]:
        out: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        full_prefix = self._full(prefix) if prefix else (self.prefix + "/" if self.prefix else "")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                if self.prefix and key.startswith(self.prefix + "/"):
                    key = key[len(self.prefix) + 1 :]
                out.append(key)
        return sorted(out)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._full(key))

    def read_bytes(self, key: str) -> bytes:
        buf = io.BytesIO()
        self.client.download_fileobj(self.bucket, self._full(key), buf)
        return buf.getvalue()

    def write_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._full(key), Body=data)

    @contextmanager
    def open_for_read(self, key: str) -> Iterator[Path]:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self.client.download_file(self.bucket, self._full(key), str(tmp_path))
            yield tmp_path
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    @contextmanager
    def open_for_write(self, key: str) -> Iterator[Path]:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            yield tmp_path
            self.client.upload_file(str(tmp_path), self.bucket, self._full(key))
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    def __repr__(self) -> str:
        return f"S3Storage(bucket={self.bucket!r}, prefix={self.prefix!r})"
