"""
Reporter that bridges GRAIL search progress into a Textual UI.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

Implements the :class:`grail.reporting.Reporter` protocol.  Each progress
message is pushed onto an asyncio queue that the TUI worker drains and
renders as live status lines under the active tool card.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

Level = Literal["info", "success", "warning", "error", "debug"]


@dataclass
class ReporterEvent:
    level: Level
    message: str


class TextualReporter:
    """A :class:`Reporter` implementation that pushes events to an asyncio queue.

    Designed to run on a worker thread (search runs in a background asyncio
    task).  The TUI drains the queue on the main thread.
    """

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the event loop that owns the queue (for thread-safe puts)."""
        self._loop = loop

    def _put(self, event: ReporterEvent) -> None:
        if self._loop is None:
            try:
                self._queue.put_nowait(event)
            except Exception:
                pass
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            try:
                self._queue.put_nowait(event)
            except Exception:
                pass

    # ----- sync methods -----
    def info(self, message: str) -> None: self._put(ReporterEvent("info", message))
    def success(self, message: str) -> None: self._put(ReporterEvent("success", message))
    def warning(self, message: str) -> None: self._put(ReporterEvent("warning", message))
    def error(self, message: str) -> None: self._put(ReporterEvent("error", message))
    def debug(self, message: str) -> None: self._put(ReporterEvent("debug", message))

    # ----- async methods -----
    async def async_info(self, message: str) -> None: self.info(message)
    async def async_success(self, message: str) -> None: self.success(message)
    async def async_warning(self, message: str) -> None: self.warning(message)
    async def async_error(self, message: str) -> None: self.error(message)

    # ----- child / dispose (Reporter protocol) -----
    def child(self, prefix: str, transient: bool = True) -> "TextualReporter":
        return self

    def dispose(self) -> None:
        pass
