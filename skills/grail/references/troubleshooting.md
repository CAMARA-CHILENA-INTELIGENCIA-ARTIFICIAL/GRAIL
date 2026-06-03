# Troubleshooting

## "externally-managed-environment" / setup.sh refuses to install

`setup.sh` emits a JSON envelope like:

```json
{
  "ok": false,
  "error": "Python at /opt/homebrew/bin/python3 is externally-managed (PEP 668) and no virtual environment is active. Refusing to install graphgrail here. ...",
  "next_steps": [
    "uv venv .venv && source .venv/bin/activate && bash scripts/setup.sh",
    "or: python3 -m venv .venv && source .venv/bin/activate && bash scripts/setup.sh",
    "or: GRAIL_ALLOW_SYSTEM_INSTALL=1 bash scripts/setup.sh  (forces --break-system-packages; risky)"
  ]
}
```

This is by design. Modern Python distributions (Homebrew on macOS,
Debian/Ubuntu, recent Fedora) mark their system interpreter as PEP 668
*externally-managed* — `pip install` against the system Python would
either fail or silently corrupt OS-owned packages. The skill refuses
rather than improvise.

**Fix — create a venv and re-run:**

```bash
# uv (recommended):
uv venv .venv && source .venv/bin/activate && bash scripts/setup.sh

# Or stdlib:
python3 -m venv .venv && source .venv/bin/activate && bash scripts/setup.sh
```

**Force a system install** (CI containers, throwaway VMs only — not on
a Mac you care about):

```bash
GRAIL_ALLOW_SYSTEM_INSTALL=1 bash scripts/setup.sh
```

That passes `--break-system-packages` to pip. You will eventually
regret it on any non-disposable machine.

## "grail is not installed" / setup.sh fails for some other reason

The skill needs `pip install graphgrail` (PyPI distribution name; the
Python import stays `import grail`). Other causes besides PEP 668:

- **No network**: the Anthropic API code-execution runtime has no
  network access — pip can't reach PyPI. This skill is not supported in
  that runtime. Use Claude Code, Codex, or Hermes.
- **Wrong Python interpreter**: `setup.sh` honours `$PYTHON` if set,
  otherwise tries `python`, then `python3`. Make sure your runtime's
  Python ≥ 3.10.
- **Wrong package on PyPI**: do NOT fall back to `pip install grail`
  (without the `graph` prefix) — that's an unrelated test framework on
  PyPI and `import grail` would even succeed but expose totally
  different classes.

## "no project matches '<ref>'"

`resolve_project_ref` couldn't map your `--project` value:

- It doesn't look like a path (no `/` or `.`) **and**
- It isn't an exact name in `~/.grail/registry.json` **and**
- It isn't a unique ULID prefix (≥8 chars).

Fix: pass the absolute path, or check `list_grail_projects.py` and copy
a known name.

## "consolidate refuses below ..."

The default threshold is 30 entities. Below that, communities have no
real signal — read the underlying memory files directly. To force,
lower `memory.min_entities_for_consolidate` in `grail.yaml`.

## "Endpoint(s) not found in final_entities"

`add_relationship` requires both endpoints to exist as entities first.
Run `add_entity` for each, or use `add_observation` and supply both
entities + the relationship together.

## "self-loops are not allowed"

`add_relationship` blocks `source == target`. If you really want a
self-link, use a different relationship type or refactor the model.

## Recall returns nothing

Likely causes:

- **`--since` too narrow** for a memory project that's still small.
- **`--category` glob doesn't match**. `recall` uses `fnmatch`; `work/**`
  matches `work/a/b`. `work` (no glob) only matches exactly `work`.
- **KB project with no `observed_at` data**. `recall` surfaces a
  warning when temporal filters match nothing because the source data
  has no timestamps.

## Search results look stale after editing memory

Memory mode writes the parquets atomically, but the FAISS index isn't
incrementally updated in v1. For embedding-driven searches (local /
cascade), run `grail index` once after a bulk edit — or accept the
degraded recall until then.

## "json.decoder.JSONDecodeError"

A script is returning non-JSON output. Most often this is a script
that imported a module that printed at import time. Try:

```bash
python -c "import grail" 2>&1 | head
```

Anything other than nothing means a noisy import path is the culprit;
file a bug.

## Proposal accepts but nothing visible

`accept_proposal` for `split_folder` writes a shell script under
`output/proposals/<id>_apply.sh` — it doesn't move files automatically.
Inspect + run the script manually.

For `discover_community`, the new row lands in `final_communities.parquet`
with `kind="discovered"`. You'll see it in
`memory/list_communities.py` (TODO: not yet shipped; query via
explore.py or the SDK in the meantime).

## "Refusing to overwrite ..."

`init_project.py` refuses to clobber an existing `grail.yaml`. Pass
`--overwrite` if that's what you actually want. Meta.json is also
regenerated when `--overwrite` is set — the project gets a new ULID.

## Memory project I can't find any more

`meta.json` is authoritative. If `list_grail_projects.py` doesn't show
a project you remember, check:

1. The project directory is still on disk.
2. `~/.grail/registry.json` has it. If not, opening the project via the
   SDK (`from grail import MemoryProject; MemoryProject('/path')`)
   re-registers it.

A future `list_grail_projects.py --rescan` will walk well-known paths
and rebuild the registry from `meta.json` files.
