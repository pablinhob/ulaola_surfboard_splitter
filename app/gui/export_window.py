import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from app.core.hollow import hollow_piece
from app.gui.viewer import MeshViewer


def _is_hollowable(key):
    """Core pieces (length-2 keys that are not cutlaps) can be hollowed."""
    return len(key) == 2 and key[1] != "cutlap"


class ExportWindow(QMainWindow):
    def __init__(self, pieces, hollow_params, thickness_axis, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export hollowing")
        self.resize(1000, 700)

        self._pieces = pieces
        self._hollow_params = hollow_params
        self._thickness_axis = thickness_axis

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.status_label = QLabel(
            "Processing hollowing for every piece, this may take a while..."
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.viewer = MeshViewer(central)
        layout.addWidget(self.viewer, stretch=1)

    def process_and_show(self):
        """Hollow every eligible piece with the preview parameters, then display."""
        wall_mm, top_mm, bottom_mm, hole_pct = self._hollow_params
        total = len(self._pieces)

        self.setCursor(Qt.WaitCursor)
        QApplication.processEvents()

        final_pieces = {}
        for index, (key, mesh) in enumerate(self._pieces.items(), start=1):
            self.status_label.setText(
                f"Processing piece {index}/{total}: {key}..."
            )
            QApplication.processEvents()

            if _is_hollowable(key):
                try:
                    final_pieces[key] = hollow_piece(
                        mesh,
                        wall_mm,
                        top_mm,
                        bottom_mm,
                        hole_pct,
                        self._thickness_axis,
                    )
                except Exception as exc:
                    logging.error(f"Could not hollow piece {key}: {exc}")
                    final_pieces[key] = mesh.copy()
            else:
                final_pieces[key] = mesh.copy()

        self.unsetCursor()

        self.viewer.show_pieces(final_pieces)
        self.status_label.setText(
            f"Done: {total} pieces, hollowing applied where allowed."
        )
        logging.info(f"Export hollowing complete: {total} pieces")
