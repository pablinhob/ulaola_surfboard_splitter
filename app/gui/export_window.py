import logging

import trimesh
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from trimesh.visual.material import SimpleMaterial
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import BOARD_COLOR, CUTLAP_COLOR, STRINGER_COLOR
from app.core.hollow import hollow_piece
from app.gui.panels import CUTLAP_LABELS, PIECE_LABELS
from app.gui.viewer import MeshViewer

# Export formats offered in the selector, in display order. OBJ is first so it
# is the default. ``colors`` flags whether the format carries the piece colors
# (trimesh writes per-vertex colors into OBJ, but not into 3MF).
EXPORT_FORMATS = [
    {
        "label": "OBJ",
        "file_type": "obj",
        "suffix": ".obj",
        "filter": "OBJ Files (*.obj)",
        "colors": True,
    },
    {
        "label": "3MF",
        "file_type": "3mf",
        "suffix": ".3mf",
        "filter": "3MF Files (*.3mf)",
        "colors": False,
    },
]


def _is_hollowable(key):
    """Core pieces (length-2 keys that are not cutlaps) can be hollowed."""
    return len(key) == 2 and key[1] != "cutlap"


def _bounds_overlap(mesh_a, mesh_b):
    """Whether two meshes' axis-aligned bounding boxes overlap."""
    a_min, a_max = mesh_a.bounds
    b_min, b_max = mesh_b.bounds
    return bool((a_min <= b_max).all() and (b_min <= a_max).all())


def _piece_name(key):
    """Human-readable, unique-ish name used for each object in the export file."""
    if len(key) == 1:
        return PIECE_LABELS.get(key[0], str(key[0]))
    if len(key) == 3 and key[1] == "cutlap":
        return f"{CUTLAP_LABELS.get(key[0], 'Cutlap')} - Split {key[2] + 1}"
    if len(key) == 2:
        return f"{PIECE_LABELS.get(key[0], key[0])} - Split {key[1] + 1}"
    return "-".join(str(part) for part in key)


def _piece_color(key):
    """RGBA colour for a piece, matching the viewer's colour scheme."""
    if key[0] == "stringer":
        name = STRINGER_COLOR
    elif len(key) == 3 and key[1] == "cutlap":
        name = CUTLAP_COLOR
    else:
        name = BOARD_COLOR
    return QColor(name).getRgb()  # (r, g, b, a), 0-255


class ExportWindow(QMainWindow):
    def __init__(
        self, pieces, hollow_params, thickness_axis, plug_solids=None, parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Export hollowing")
        self.resize(1000, 700)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)

        self._pieces = pieces
        self._hollow_params = hollow_params
        self._thickness_axis = thickness_axis
        self._plug_solids = plug_solids or []
        self._final_pieces = {}

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

        self.format_combo = QComboBox()
        for fmt in EXPORT_FORMATS:
            self.format_combo.addItem(fmt["label"])
        self.export_button = QPushButton("Export file")
        self.export_button.clicked.connect(self.on_export)

        # Bottom-right: file-type selector on the left, export button on the right.
        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(self.format_combo)
        controls.addWidget(self.export_button)
        layout.addLayout(controls)

        self._set_export_enabled(False)

    def _set_export_enabled(self, enabled):
        self.format_combo.setEnabled(enabled)
        self.export_button.setEnabled(enabled)

    def _subtract_plugs(self, key, piece):
        """Subtract every plug cavity that overlaps this (already-cut) piece."""
        overlapping = [p for p in self._plug_solids if _bounds_overlap(piece, p)]
        if not overlapping:
            return piece

        if not piece.is_volume:
            piece = piece.copy()
            piece.merge_vertices()
            piece.fill_holes()
        if not piece.is_volume:
            # The source STL isn't watertight, so some raw pieces (e.g. the
            # stringer) can't be booleaned; leave them uncut rather than crash.
            logging.warning(f"Piece {key} is not a solid; skipping plug cut")
            return piece

        for plug in overlapping:
            try:
                piece = trimesh.boolean.difference([piece, plug])
            except Exception as exc:
                logging.error(f"Could not subtract plug from piece {key}: {exc}")
        return piece

    def closeEvent(self, event):
        # The VTK render window must be finalised explicitly; otherwise closing
        # the window crashes when VTK tears itself down during destruction.
        self.viewer.close()
        super().closeEvent(event)

    def process_and_show(self):
        """Hollow every eligible piece, subtract the plug cavities, then display."""
        wall_mm, top_mm, bottom_mm, hole_pct = self._hollow_params
        total = len(self._pieces)

        self.setCursor(Qt.WaitCursor)
        QApplication.processEvents()

        final_pieces = {}
        for index, (key, mesh) in enumerate(self._pieces.items(), start=1):
            self.status_label.setText(f"Processing piece {index}/{total}: {key}...")
            QApplication.processEvents()

            if _is_hollowable(key):
                try:
                    piece = hollow_piece(
                        mesh, wall_mm, top_mm, bottom_mm, hole_pct, self._thickness_axis
                    )
                except Exception as exc:
                    logging.error(f"Could not hollow piece {key}: {exc}")
                    piece = mesh.copy()
            else:
                piece = mesh.copy()

            # Carve the plug cavities out of the already-cut, hollowed piece.
            final_pieces[key] = self._subtract_plugs(key, piece)

        self.unsetCursor()

        self._final_pieces = final_pieces
        self.viewer.show_pieces(final_pieces)
        self._set_export_enabled(True)
        self.status_label.setText(
            f"Done: {total} pieces, hollowing applied where allowed."
        )
        logging.info(f"Export hollowing complete: {total} pieces")

    def on_export(self):
        if not self._final_pieces:
            logging.warning("No processed pieces to export yet")
            return

        fmt = EXPORT_FORMATS[self.format_combo.currentIndex()]
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export pieces",
            f"surfboard_pieces{fmt['suffix']}",
            fmt["filter"],
        )
        if not path:
            logging.info("Export cancelled")
            return
        if not path.lower().endswith(fmt["suffix"]):
            path += fmt["suffix"]

        scene = trimesh.Scene()
        for key, mesh in self._final_pieces.items():
            piece = mesh.copy()
            if fmt["colors"]:
                # Colour via a named material (writes a .mtl) rather than
                # per-vertex colours: the latter is a non-standard OBJ extension
                # (6 numbers per "v" line) that some CAD importers reject
                # (e.g. FreeCAD's Arch OBJ importer: "Expected sequence of size 3").
                piece.visual = trimesh.visual.TextureVisuals(
                    material=SimpleMaterial(diffuse=_piece_color(key))
                )
            name = _piece_name(key)
            scene.add_geometry(piece, node_name=name, geom_name=name)

        self.setCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            scene.export(path, file_type=fmt["file_type"])
        except Exception as exc:
            logging.error(f"Could not export {fmt['label']} file '{path}': {exc}")
            self.status_label.setText("Export failed, see log for details.")
            return
        finally:
            self.unsetCursor()

        self.status_label.setText(
            f"Exported {len(self._final_pieces)} pieces to {path}"
        )
        logging.info(f"Exported {fmt['label']}: {path}")
