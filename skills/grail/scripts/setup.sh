#!/usr/bin/env bash
# Idempotent dependency check for the GRAIL skill.
#
# Safe to call every session — exits 0 with status="already-installed" when
# GRAIL is importable. Otherwise pip-installs from requirements.txt.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Prefer python3 when the bare ``python`` isn't a Python 3 (older macOS, etc.).
PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY="python3"
fi

if "$PY" -c "import grail" 2>/dev/null; then
  GRAIL_VER="$("$PY" -c 'from grail import __version__; print(__version__)' 2>/dev/null || echo unknown)"
  printf '{"ok": true, "status": "already-installed", "grail_version": "%s"}\n' "$GRAIL_VER"
  exit 0
fi

"$PY" -m pip install -q -r "$SCRIPT_DIR/../requirements.txt"

GRAIL_VER="$("$PY" -c 'from grail import __version__; print(__version__)' 2>/dev/null || echo unknown)"
printf '{"ok": true, "status": "installed", "grail_version": "%s"}\n' "$GRAIL_VER"
