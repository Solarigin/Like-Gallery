from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue, Empty
from typing import Callable, Iterable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import CONFIG, SIAConfig
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class WatchEvent:
    path: Path
    is_directory: bool


class StableEventHandler(FileSystemEventHandler):
    def __init__(self, queue: Queue[WatchEvent]) -> None:
        super().__init__()
        self.queue = queue

    def on_created(self, event) -> None:  # type: ignore[override]
        self.queue.put(WatchEvent(Path(event.src_path), event.is_directory))

    def on_moved(self, event) -> None:  # type: ignore[override]
        self.queue.put(WatchEvent(Path(event.dest_path), event.is_directory))


class Watcher:
    def __init__(self, callback: Callable[[Iterable[Path]], None], config: Optional[SIAConfig] = None) -> None:
        self._config = config or CONFIG.get()
        self._queue: Queue[WatchEvent] = Queue()
        self._observer = Observer()
        self._callback = callback
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        handler = StableEventHandler(self._queue)
        self._observer.schedule(handler, str(self._config.base_dir), recursive=True)
        self._observer.start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("开始监控 %s", self._config.base_dir)

    def stop(self) -> None:
        self._stop_event.set()
        self._observer.stop()
        self._observer.join(timeout=5)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("停止监控")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=0.5)
            except Empty:
                continue
            path = event.path
            if not path.exists():
                continue
            if self._wait_stable(path):
                logger.info("稳定文件: %s", path)
                self._callback([path])

    def _wait_stable(self, path: Path, wait: float = 1.0, checks: int = 3) -> bool:
        prev_size = -1
        for _ in range(checks):
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                return False
            if size == prev_size:
                return True
            prev_size = size
            time.sleep(wait)
        return False
