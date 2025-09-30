from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import uvicorn

from .core.config import CONFIG
from .core.logger import configure_logging, get_logger
from .server import api
from .ui.main_window import MainWindow

logger = get_logger(__name__)


class ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True)
        self.port = port
        self._server: Optional[uvicorn.Server] = None

    def run(self) -> None:  # pragma: no cover - server loop
        config = uvicorn.Config(api.app, host="127.0.0.1", port=self.port, log_level="info")
        self._server = uvicorn.Server(config)
        self._server.run()

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True


def main() -> None:  # pragma: no cover - GUI bootstrap
    config = CONFIG.get()
    configure_logging(config.log_dir)
    server_thread = ServerThread(config.port)
    server_thread.start()
    try:
        from PySide6 import QtWidgets
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PySide6 未安装，无法启动图形界面") from exc
    app = QtWidgets.QApplication([])
    window = MainWindow(config)
    window.show()
    app.exec()
    server_thread.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
