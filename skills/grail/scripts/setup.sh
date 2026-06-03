#!/usr/bin/env bash
# Idempotent dependency check for the GRAIL skill.
#
# Safe to call every session — exits 0 with status="already-installed" when
# GRAIL is importable. Otherwise pip-installs ``graphgrail[faiss]`` from
# requirements.txt.
#
# Will REFUSE to install into a PEP 668 externally-managed system Python
# (Homebrew on macOS, Debian/Ubuntu, recent Fedora) when no virtual
# environment is active — emits a clean JSON envelope with next-steps
# pointing at ``uv venv``. Override with GRAIL_ALLOW_SYSTEM_INSTALL=1 if
# you really know what you're doing.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Prefer python3 when the bare ``python`` isn't a Python 3 (older macOS, etc.).
PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY="python3"
fi

# Quick path: GRAIL already importable → success, exit immediately.
if "$PY" -c "import grail" 2>/dev/null; then
  GRAIL_VER="$("$PY" -c 'from grail import __version__; print(__version__)' 2>/dev/null || echo unknown)"
  printf '{"ok": true, "status": "already-installed", "grail_version": "%s"}\n' "$GRAIL_VER"
  exit 0
fi

# Detect: are we in a venv, and is this interpreter externally-managed (PEP 668)?
VENV_CHECK="$("$PY" - <<'PYEOF'
import os, sys, sysconfig
from pathlib import Path
in_venv = (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)
# PEP 668 marker lives INSIDE the stdlib dir, not its parent.
marker = Path(sysconfig.get_paths()["stdlib"]) / "EXTERNALLY-MANAGED"
externally_managed = marker.exists()
print(f"{int(in_venv)} {int(externally_managed)} {sys.executable}")
PYEOF
)"
read -r IN_VENV MANAGED PY_PATH <<< "$VENV_CHECK"

# Refuse to install into an externally-managed system Python unless the
# user explicitly overrides. Cleaner than ``--break-system-packages``
# silently breaking somebody's macOS.
if [ "$IN_VENV" = "0" ] && [ "$MANAGED" = "1" ] && [ -z "${GRAIL_ALLOW_SYSTEM_INSTALL:-}" ]; then
  cat <<EOF
{"ok": false, "error": "Python at $PY_PATH is externally-managed (PEP 668) and no virtual environment is active. Refusing to install graphgrail here. Activate a venv and re-run, or set GRAIL_ALLOW_SYSTEM_INSTALL=1 to force.", "data": {"python": "$PY_PATH", "in_venv": false, "externally_managed": true}, "next_steps": ["uv venv .venv && source .venv/bin/activate && bash scripts/setup.sh", "or: python3 -m venv .venv && source .venv/bin/activate && bash scripts/setup.sh", "or: GRAIL_ALLOW_SYSTEM_INSTALL=1 bash scripts/setup.sh  (forces --break-system-packages; risky)"]}
EOF
  exit 1
fi

# Install. Prefer ``uv pip install`` when uv is on PATH — it's much
# faster than stock pip on a tree this large (graspologic + faiss +
# lancedb + ...). Fall back to ``python -m pip install`` otherwise.
INSTALLER="pip"
if command -v uv >/dev/null 2>&1; then
  INSTALLER="uv"
  UV_FLAGS=( --quiet --python "$PY" )
  if [ "$IN_VENV" = "0" ]; then
    # When we got past the refusal check above, the user explicitly
    # opted into a system install via GRAIL_ALLOW_SYSTEM_INSTALL=1.
    # ``uv pip install`` refuses to touch a non-venv Python by default,
    # so pass ``--system`` (plus ``--break-system-packages`` when the
    # interpreter is PEP 668 marked).
    UV_FLAGS+=( --system )
    if [ "$MANAGED" = "1" ]; then
      UV_FLAGS+=( --break-system-packages )
    fi
  fi
  uv pip install "${UV_FLAGS[@]}" -r "$SCRIPT_DIR/../requirements.txt"
else
  PIP_ARGS=( -q )
  if [ -n "${GRAIL_ALLOW_SYSTEM_INSTALL:-}" ] && [ "$MANAGED" = "1" ]; then
    PIP_ARGS+=( --break-system-packages )
  fi
  "$PY" -m pip install "${PIP_ARGS[@]}" -r "$SCRIPT_DIR/../requirements.txt"
fi

GRAIL_VER="$("$PY" -c 'from grail import __version__; print(__version__)' 2>/dev/null || echo unknown)"
IN_VENV_BOOL=false
[ "$IN_VENV" = "1" ] && IN_VENV_BOOL=true
printf '{"ok": true, "status": "installed", "grail_version": "%s", "in_venv": %s, "installer": "%s"}\n' "$GRAIL_VER" "$IN_VENV_BOOL" "$INSTALLER"
