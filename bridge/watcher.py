"""Watch the WoW SavedVariables file for changes and trigger a callback."""

from __future__ import annotations

import pathlib
import threading
from typing import Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer


class _Handler(FileSystemEventHandler):
    def __init__(self, target: pathlib.Path, callback: Callable[[pathlib.Path], None]) -> None:
        self._target = str(target.resolve())
        self._callback = callback

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory and event.src_path == self._target:
            self._callback(pathlib.Path(event.src_path))


class SavedVarsWatcher:
    """Watches a single SavedVariables file and fires *callback* on change."""

    def __init__(self, path: pathlib.Path, callback: Callable[[pathlib.Path], None]) -> None:
        self._path = path.resolve()
        self._callback = callback
        self._observer: Observer | None = None

    def start(self) -> None:
        handler = _Handler(self._path, self._callback)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._path.parent), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
