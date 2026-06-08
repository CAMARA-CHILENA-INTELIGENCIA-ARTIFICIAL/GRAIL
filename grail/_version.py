"""Runtime version constant.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Reads the version from the installed package metadata so it stays in sync
with ``pyproject.toml``. The hardcoded fallback is only used in editable
installs or other environments where ``importlib.metadata`` can't find
``graphgrail`` — keep it in sync with the pyproject's version field so
``import grail; grail.__version__`` never lies.
"""
try:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("graphgrail")
    except PackageNotFoundError:
        # Editable / source install where the dist-info isn't present.
        __version__ = "0.1.4"
except ImportError:  # pragma: no cover - Python <3.8, not supported anyway
    __version__ = "0.1.4"
