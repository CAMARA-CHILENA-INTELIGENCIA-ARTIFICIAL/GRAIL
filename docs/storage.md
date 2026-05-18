# Storage

> **Scope.** Pluggable backends for everything GRAIL reads and writes. Configures: ``configs/storage.yaml``. Code: ``grail/storage/``.

## Why an abstraction

The legacy code wired S3 directly into every indexer and every loader. GRAIL
inverts that: indexing and querying talk to a :class:`StorageBackend`, and the
backend handles wherever the bytes actually live (filesystem, S3, …). This lets
you:

* Run 100% locally with zero AWS dependencies.
* Migrate a project from local → S3 (or vice versa) by editing one YAML key.
* Plug a custom backend (GCS, Azure, IPFS, an HTTP mirror) by subclassing
  :class:`StorageBackend`.

## Interface

```python
class StorageBackend(ABC):
    def exists(key) -> bool
    def list(prefix="") -> list[str]
    def delete(key) -> None
    def read_bytes(key) -> bytes
    def write_bytes(key, data) -> None
    def open_for_read(key)        # context manager → Path
    def open_for_write(key)       # context manager → Path
    def join(*parts) -> str
```

``open_for_read`` and ``open_for_write`` yield a real :class:`pathlib.Path`. Cloud
backends download/upload around the temp file; the local backend just hands back
the on-disk path. This lets libraries like LanceDB and pyarrow.parquet — which
insist on real paths — work transparently across backends.

## LocalStorage (default)

```yaml
storage:
  backend: local
  root: ~/.grail/projects/my-project
```

Keys are forward-slash paths interpreted relative to ``root``. Path traversal is
blocked: ``../escape.txt`` raises ``PermissionError``.

Writes are atomic: a ``.tmp`` file is created first and ``os.replace``'d on close.
Safer for re-runs that crash midway through.

## S3Storage (optional)

Install the extra:

```bash
uv pip install -e ".[s3]"
```

Configure:

```yaml
storage:
  backend: s3
  s3_bucket: my-bucket
  s3_prefix: projects/grail/example
  s3_region: us-east-1
  s3_endpoint_url: null     # set for MinIO / S3-compatible stores
```

Credentials follow the standard AWS chain — ``AWS_ACCESS_KEY_ID``,
``AWS_SECRET_ACCESS_KEY``, ``AWS_REGION_NAME``, IAM role on EC2, etc. See
``.env.example`` for the full list.

## Building a custom backend

Subclass :class:`StorageBackend`, implement the seven required methods, and pass
an instance to :class:`GRAIL` directly:

```python
from grail import GRAIL
from grail.config import Config
from grail.storage import StorageBackend

class MyGCSBackend(StorageBackend):
    ...

config = Config(project_name="gcs", root_dir="/tmp/grail-gcs")
grail = GRAIL.from_config(config)
grail.storage = MyGCSBackend(bucket="my-bucket")
```

A factory shortcut exists for the built-in backends:

```python
from grail.storage import get_backend
storage = get_backend("local", root="/tmp/proj")
storage = get_backend("s3", bucket="my-bucket", prefix="grail/")
```

## Artefact layout

After ``grail index``, the storage tree looks like:

```
{root}/
├── input/                                 # source files (user-supplied)
├── output/
│   ├── final_docs.parquet
│   ├── partial_text_units.parquet
│   ├── final_text_units.parquet
│   ├── final_entities.parquet
│   ├── final_relationships.parquet
│   ├── final_nodes.parquet
│   ├── final_communities.parquet
│   ├── final_community_reports.parquet
│   └── entity_relationship_graph.graphml
├── lancedb/                                # vectorstore (when backend=lancedb on local)
├── cache/llm/                              # LLM disk cache (when enabled)
└── mapping.json                            # citation root
```

``mapping.json`` is the only artefact at the project root rather than under
``output/`` — it's the human-editable bridge from doc id → original path and is
expected to survive re-indexing.
