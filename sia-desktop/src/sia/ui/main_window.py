from __future__ import annotations

from pathlib import Path
from typing import Optional

try:  # pragma: no cover - UI imports optional during tests
    from PySide6 import QtCore, QtGui, QtWidgets, QtWebEngineWidgets
except ImportError:  # pragma: no cover
    QtCore = QtGui = QtWidgets = QtWebEngineWidgets = None  # type: ignore

from ..core import indexer
from ..core.config import CONFIG, SIAConfig
from ..core.logger import get_logger

logger = get_logger(__name__)


def _require_qt() -> None:
    if QtWidgets is None:
        raise RuntimeError("PySide6 未安装，无法启动图形界面。")


class MainWindow(QtWidgets.QMainWindow):  # type: ignore[misc]
    def __init__(self, config: Optional[SIAConfig] = None) -> None:
        _require_qt()
        super().__init__()
        self.config = config or CONFIG.get()
        self.setWindowTitle("Social Image Archiver")
        self.resize(1280, 768)
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)
        self._build_gallery_tab()
        self._build_tasks_tab()
        self._build_settings_tab()
        self._build_logs_tab()

    # Gallery Tab
    def _build_gallery_tab(self) -> None:
        gallery_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(gallery_widget)
        self.gallery_view = QtWebEngineWidgets.QWebEngineView()
        html_path = Path(__file__).resolve().parents[3] / "gallery.html"
        self.gallery_view.setUrl(QtCore.QUrl.fromLocalFile(str(html_path)))
        layout.addWidget(self.gallery_view)
        button_bar = QtWidgets.QHBoxLayout()
        rebuild_button = QtWidgets.QPushButton("重建索引")
        rebuild_button.clicked.connect(self._rebuild_index)  # type: ignore[attr-defined]
        button_bar.addWidget(rebuild_button)
        self.open_dir_button = QtWidgets.QPushButton("打开目录")
        self.open_dir_button.clicked.connect(self._open_base_dir)  # type: ignore[attr-defined]
        button_bar.addWidget(self.open_dir_button)
        button_bar.addStretch(1)
        layout.addLayout(button_bar)
        self.tabs.addTab(gallery_widget, "图库")

    def _rebuild_index(self) -> None:
        indexer.build_index(self.config)
        if QtWidgets:
            QtWidgets.QMessageBox.information(self, "索引", "已重建 images.json")

    def _open_base_dir(self) -> None:
        if QtGui:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.config.base_dir)))

    # Tasks tab placeholder
    def _build_tasks_tab(self) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        self.task_label = QtWidgets.QLabel("监听未启动")
        layout.addWidget(self.task_label)
        self.tabs.addTab(widget, "任务")

    def _build_settings_tab(self) -> None:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        self.base_dir_edit = QtWidgets.QLineEdit(str(self.config.base_dir))
        form.addRow("根目录", self.base_dir_edit)
        self.port_edit = QtWidgets.QSpinBox()
        self.port_edit.setRange(1024, 65535)
        self.port_edit.setValue(self.config.port)
        form.addRow("端口", self.port_edit)
        save_btn = QtWidgets.QPushButton("保存")
        save_btn.clicked.connect(self._save_config)  # type: ignore[attr-defined]
        form.addRow(save_btn)
        self.tabs.addTab(widget, "设置")

    def _build_logs_tab(self) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        self.tabs.addTab(widget, "日志")

    def _save_config(self) -> None:
        base_dir = Path(self.base_dir_edit.text())
        port = int(self.port_edit.value())
        updated = CONFIG.update(base_dir=str(base_dir), port=port)
        self.config = updated
        if QtWidgets:
            QtWidgets.QMessageBox.information(self, "设置", "配置已保存")
