"""
Rich-based progress reporter used across indexing and search.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

This is a slim port of the legacy reporter:
- The ``datashaper`` dependency was dropped — we don't need DataShaper progress objects.
- Default prefix is ``"GRAIL"`` rather than the old branded string.
- ``NullReporter`` is a no-op so callers don't have to ``if reporter:`` everywhere.
- Inherits the legacy hierarchical structure: ``parent.child(prefix=...)``.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from rich.console import Console, Group
from rich.live import Live
from rich.progress import Progress, TaskID, TimeElapsedColumn
from rich.spinner import Spinner
from rich.tree import Tree


@runtime_checkable
class Reporter(Protocol):
    """Minimal interface every reporter implements; lets callers stay backend-agnostic."""

    def info(self, message: str) -> None: ...
    def success(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...

    async def async_info(self, message: str) -> None: ...
    async def async_success(self, message: str) -> None: ...
    async def async_warning(self, message: str) -> None: ...
    async def async_error(self, message: str) -> None: ...

    def child(self, prefix: str, transient: bool = True) -> "Reporter": ...
    def dispose(self) -> None: ...


class NullReporter:
    """A no-op reporter used as a default."""

    def info(self, message: str) -> None: ...
    def success(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...

    async def async_info(self, message: str) -> None: ...
    async def async_success(self, message: str) -> None: ...
    async def async_warning(self, message: str) -> None: ...
    async def async_error(self, message: str) -> None: ...

    def child(self, prefix: str, transient: bool = True) -> "NullReporter":
        return self

    def dispose(self) -> None: ...
    async def async_dispose(self) -> None: ...


class RichProgressReporter(BaseModel):
    """A rich-based progress reporter; works in sync and async contexts."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _console: Console
    _group: Group
    _tree: Tree
    _live: Live
    _task: Optional[TaskID] = None
    _prefix: str
    _transient: bool
    _disposing: bool = False
    _progressbar: Optional[Progress] = None

    def __init__(
        self,
        prefix: str = "GRAIL",
        parent: Optional["RichProgressReporter"] = None,
        transient: bool = True,
    ) -> None:
        super().__init__()
        self._prefix = prefix
        if parent is None:
            console = Console()
            group = Group(Spinner("dots", prefix), fit=True)
            tree = Tree(group)
            live = Live(tree, console=console, refresh_per_second=1, vertical_overflow="crop")
            live.start()
            self._console = console
            self._group = group
            self._tree = tree
            self._live = live
            self._transient = False
            self._progressbar = None
        else:
            self._console = parent._console
            self._group = parent._group
            progress_columns = [*Progress.get_default_columns(), TimeElapsedColumn()]
            self._progressbar = Progress(
                *progress_columns, console=self._console, transient=transient
            )
            tree = Tree(prefix)
            tree.add(self._progressbar)
            tree.hide_root = True
            parent_tree = parent._tree
            parent_tree.hide_root = False
            parent_tree.add(tree)
            self._tree = tree
            self._live = parent._live
            self._transient = transient

    @property
    def console(self) -> Console:
        return self._console

    def child(self, prefix: str, transient: bool = True) -> "RichProgressReporter":
        return RichProgressReporter(parent=self, prefix=prefix, transient=transient)

    def dispose(self) -> None:
        self._disposing = True
        self._live.stop()

    def refresh(self) -> None:
        self._live.refresh()

    def info(self, message: str) -> None:
        self._console.print(message)

    def success(self, message: str) -> None:
        self._console.print(f"🚀 [green]{message}[/green]")

    def warning(self, message: str) -> None:
        self._console.print(f"⚠️  [yellow]{message}[/yellow]")

    def error(self, message: str) -> None:
        self._console.print(f"❌ [red]{message}[/red]")

    def debug(self, message: str) -> None:
        self._console.print(f"[dim]{message}[/dim]")

    def update(self, completed: int, total: int, description: str = "") -> None:
        if self._progressbar is None:
            return
        if self._task is None:
            self._task = self._progressbar.add_task(self._prefix)
        self._progressbar.update(
            self._task,
            completed=completed,
            total=total,
            description=f"{self._prefix} - {description}" if description else self._prefix,
        )
        if completed == total and self._transient:
            self._progressbar.update(self._task, visible=False)
        self.refresh()

    # Async façades — delegate to to_thread so we never block the loop on Rich.
    async def async_dispose(self) -> None:
        self._disposing = True
        await asyncio.to_thread(self._live.stop)

    async def async_info(self, message: str) -> None:
        await asyncio.to_thread(self.info, message)

    async def async_success(self, message: str) -> None:
        await asyncio.to_thread(self.success, message)

    async def async_warning(self, message: str) -> None:
        await asyncio.to_thread(self.warning, message)

    async def async_error(self, message: str) -> None:
        await asyncio.to_thread(self.error, message)


def make_reporter(*, enable: bool = True, prefix: str = "GRAIL") -> Reporter:
    """Factory helper. Returns ``NullReporter`` when ``enable`` is False."""
    if not enable:
        return NullReporter()
    return RichProgressReporter(prefix=prefix)
