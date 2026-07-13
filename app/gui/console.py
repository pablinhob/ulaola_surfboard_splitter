import logging

from PySide6.QtWidgets import QPlainTextEdit

from app.helpers.logging_utils import build_formatter


class QtLogHandler(logging.Handler):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        self.widget.appendPlainText(self.format(record))


class LogConsole(QPlainTextEdit):
    def __init__(self, parent=None, height=150):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFixedHeight(height)
        self.setStyleSheet(
            "background-color: black; color: #00ff00; font-family: Menlo, monospace;"
        )
        self._attach_to_root_logger()

    def _attach_to_root_logger(self):
        handler = QtLogHandler(self)
        handler.setFormatter(build_formatter())
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
