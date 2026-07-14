import logging

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.hollow import hollow_piece
from app.core.mesh_ops import (
    compute_object_stats,
    detect_thickness_axis,
    load_stl,
    split_board,
)
from app.gui.console import LogConsole
from app.gui.export_window import ExportWindow
from app.gui.panels import (
    AccordionSection,
    ObjectStatsPanel,
    PiecesPanel,
    PlugsSetupPanel,
    SplitterParametrizationPanel,
)
from app.gui.viewer import MeshViewer
from app.helpers.path_utils import shorten_path

SPLIT_PATTERN_BY_LABEL = {"Hexagon": "hexagon", "Triangle": "triangle"}

ICON_SIZE = 32
ICON_TOP_PADDING = 10


def _build_plus_icon(size=ICON_SIZE):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont()
    font.setPixelSize(round(size * 0.8))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "+")
    painter.end()

    return QIcon(pixmap)


def _pad_icon_top(icon, size=ICON_SIZE, padding=ICON_TOP_PADDING):
    padded = QPixmap(size, size + padding)
    padded.fill(Qt.GlobalColor.transparent)

    painter = QPainter(padded)
    painter.drawPixmap(0, padding, icon.pixmap(size, size))
    painter.end()

    return QIcon(padded)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UlaOla surfboard splitter")
        self.resize(1200, 800)
        self.setMinimumSize(1200, 800)
        self.mesh = None
        self.pieces = {}
        self.original_pieces = {}
        self.cut_outlines = []
        self.selected_piece = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        left_panel = self._build_left_panel()
        splitter.addWidget(left_panel)

        right_panel = self._build_right_panel()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.handle(1).setEnabled(False)

        logging.info(
            "Welcome to UlaOla Surfboard Splitter! Open an STL file to get started."
        )

    def _build_action_button(self, icon, text, slot):
        button = QToolButton()
        button.setIcon(_pad_icon_top(icon))
        button.setText(text)
        button.setToolTip(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE + ICON_TOP_PADDING))
        button.clicked.connect(slot)
        return button

    def _draw_leash_marker(self):
        """Green vertical cylinder marking the leash-plug position on the board.

        Placed at ``position`` mm from the tail (the length-axis min end), centred
        across the width, ~200 mm long and ``diameter`` mm wide, straddling the
        board's top surface so it visibly intersects the figure.
        """
        if self.mesh is None:
            return

        min_bounds, max_bounds = self.mesh.bounds
        sizes = max_bounds - min_bounds
        length_axis = int(np.argmax(sizes))
        thickness_axis = int(np.argmin(sizes))
        width_axis = 3 - length_axis - thickness_axis

        position = self.leash_plug_panel.position_spin.value()
        center_offset = self.leash_plug_panel.center_spin.value()
        length_pos = min_bounds[length_axis] + position
        # Center offset shifts the marker sideways from the width centreline:
        # positive to one side, negative to the other.
        width_pos = (
            min_bounds[width_axis] + max_bounds[width_axis]
        ) / 2 + center_offset

        # Find the board's top surface at that spot to centre the marker on it.
        origin = np.zeros(3)
        origin[length_axis] = length_pos
        origin[width_axis] = width_pos
        origin[thickness_axis] = min_bounds[thickness_axis] - 1.0
        direction = np.zeros(3)
        direction[thickness_axis] = 1.0
        hits = self.mesh.ray.intersects_location([origin], [direction])[0]
        if len(hits):
            surface = hits[:, thickness_axis].max()
        else:
            surface = (min_bounds[thickness_axis] + max_bounds[thickness_axis]) / 2

        diameter = self.leash_plug_panel.diameter_spin.value()
        center = np.zeros(3)
        center[length_axis] = length_pos
        center[width_axis] = width_pos
        center[thickness_axis] = surface
        self.viewer.set_marker_cylinder(
            center, direction, height=200.0, radius=diameter / 2
        )

    def _link_exclusive(self, sections):
        """Expanding one accordion section collapses the others."""
        for section in sections:
            others = [s for s in sections if s is not section]
            section.toggle_button.toggled.connect(
                lambda checked, others=others: (
                    [other.set_expanded(False) for other in others] if checked else None
                )
            )

    def _build_left_panel(self):
        left_panel = QWidget()
        left_panel.setFixedWidth(440)
        layout = QVBoxLayout(left_panel)

        style = self.style()
        open_previous_button = self._build_action_button(
            style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            "Open Previous",
            self.on_open_previous_project,
        )
        save_project_button = self._build_action_button(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "Save Project",
            self.on_save_project,
        )
        save_as_button = self._build_action_button(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "Save As",
            self.on_save_project_as,
        )
        for button in (open_previous_button, save_project_button, save_as_button):
            button.setEnabled(False)

        buttons = [
            self._build_action_button(
                _build_plus_icon(), "Add STL shape", self.on_open_stl
            ),
            open_previous_button,
            save_project_button,
            save_as_button,
        ]
        button_width = max(button.sizeHint().width() for button in buttons)

        actions_layout = QHBoxLayout()
        for button in buttons:
            button.setFixedWidth(button_width)
            actions_layout.addWidget(button)
        layout.addLayout(actions_layout)

        layout.addSpacing(10)

        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setWordWrap(True)
        layout.addWidget(self.file_path_label)

        layout.addSpacing(10)

        self.parametrization_panel = SplitterParametrizationPanel()
        self.parametrization_panel.execute_button.clicked.connect(self.on_execute)

        self.pieces_panel = PiecesPanel()
        self.pieces_panel.tree.currentItemChanged.connect(
            self.on_piece_selection_changed
        )
        self.pieces_panel.apply_button.clicked.connect(self.on_apply_hollow)
        self.pieces_panel.export_button.clicked.connect(self.on_export_hollow)

        self.plugs_setup_panel = PlugsSetupPanel()
        self.leash_plug_panel = self.plugs_setup_panel.leash_plug_panel
        self.plugs_setup_panel.continue_button.clicked.connect(
            lambda: self.parametrization_section.set_expanded(True)
        )
        for spin in (
            self.leash_plug_panel.position_spin,
            self.leash_plug_panel.diameter_spin,
            self.leash_plug_panel.center_spin,
        ):
            spin.valueChanged.connect(lambda _value: self._draw_leash_marker())

        self.plugs_section = AccordionSection(
            " 1 - Plugs setup", self.plugs_setup_panel
        )
        self.parametrization_section = AccordionSection(
            " 2 - Split model into polygons", self.parametrization_panel
        )
        self.pieces_section = AccordionSection(
            " 3 - Process polygons", self.pieces_panel
        )

        self._link_exclusive(
            [self.plugs_section, self.parametrization_section, self.pieces_section]
        )

        self.plugs_section.set_enabled(False)
        self.parametrization_section.set_enabled(False)
        self.pieces_section.set_enabled(False)

        layout.addWidget(self.plugs_section)
        layout.addWidget(self.parametrization_section)
        layout.addWidget(self.pieces_section)

        layout.addStretch()

        self.stats_panel = ObjectStatsPanel()
        layout.addWidget(self.stats_panel)

        return left_panel

    def _build_right_panel(self):
        right_panel = QWidget()
        layout = QVBoxLayout(right_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.viewer = MeshViewer(right_panel)
        layout.addWidget(self.viewer, stretch=1)

        self.console = LogConsole()
        layout.addWidget(self.console)

        return right_panel

    def on_open_previous_project(self):
        logging.info("Open previous project: not implemented yet")

    def on_save_project(self):
        logging.info("Save project: not implemented yet")

    def on_save_project_as(self):
        logging.info("Save project as: not implemented yet")

    def on_open_stl(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select STL", "", "STL Files (*.stl)"
        )
        if not path:
            logging.info("STL loading cancelled")
            return

        self.file_path_label.setText(shorten_path(path))
        self.file_path_label.setToolTip(path)

        self.pieces = {}
        self.original_pieces = {}
        self.pieces_panel.reset()
        self.pieces_section.set_enabled(False)

        logging.info(f"Loading file: {path}")
        try:
            mesh = load_stl(path)
        except Exception as exc:
            logging.error(f"Could not parse STL file '{path}': {exc}")
            self.mesh = None
            self.plugs_section.set_enabled(False)
            self.parametrization_section.set_enabled(False)
            self.stats_panel.reset()
            return

        self.mesh = mesh
        self.plugs_section.set_enabled(True)
        self.parametrization_section.set_enabled(True)
        self.plugs_section.set_expanded(True)
        self.viewer.show_trimesh(mesh)
        self._draw_leash_marker()
        logging.info(
            f"STL loaded successfully: {len(mesh.vertices)} vertices, "
            f"{len(mesh.faces)} faces"
        )

        stats = compute_object_stats(mesh)
        self.stats_panel.update_stats(stats)
        logging.info(
            f"Bounding box: {stats['size_cm'][0]:.1f} x {stats['size_cm'][1]:.1f} x "
            f"{stats['size_cm'][2]:.1f} cm, volume: {stats['volume_cm3']:.1f} cm3 "
            f"({stats['volume_liters']:.2f} L)"
        )

    def on_execute(self):
        if self.mesh is None:
            logging.warning("No STL loaded, nothing to split")
            return

        shape_label = self.parametrization_panel.shape_combo.currentText()
        split_pattern = SPLIT_PATTERN_BY_LABEL.get(shape_label)
        if split_pattern is None:
            logging.error(f"Split pattern '{shape_label}' is not implemented yet")
            return

        logging.info(
            f"Splitting board lengthwise and into {shape_label.lower()} pieces..."
        )

        stringer_width_mm = self.parametrization_panel.stringer_width_slider.value()
        cutlap_width_mm = self.parametrization_panel.cutlap_width_slider.value()
        piece_radius_mm = self.parametrization_panel.piece_radius_slider.value()

        self.parametrization_panel.execute_button.setEnabled(False)
        self.setCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            pieces, cut_outlines = split_board(
                self.mesh,
                piece_radius_mm=piece_radius_mm,
                stringer_width_mm=stringer_width_mm,
                cutlap_width_mm=cutlap_width_mm,
                split_pattern=split_pattern,
            )
        except Exception as exc:
            logging.error(f"Could not split mesh: {exc}")
            return
        finally:
            self.parametrization_panel.execute_button.setEnabled(True)
            self.unsetCursor()

        self.pieces = pieces
        self.original_pieces = dict(pieces)
        self.cut_outlines = cut_outlines

        self.pieces_panel.populate(pieces)
        self.pieces_section.set_enabled(True)
        self.pieces_section.set_expanded(True)
        self.viewer.show_pieces(
            pieces, cut_outlines=cut_outlines, original_mesh=self.mesh
        )

        logging.info(f"Split complete: {len(pieces)} pieces")

    def on_piece_selection_changed(self, current, _previous):
        if current is None:
            self.selected_piece = None
            return

        selection = current.data(0, Qt.UserRole)
        self.selected_piece = selection
        logging.info(f"Showing: {current.text(0)}")
        self.viewer.set_piece_selection(selection)

    def on_apply_hollow(self):
        key = self.selected_piece
        if key is None or len(key) != 2 or key[1] == "cutlap":
            logging.warning("Select a core piece before applying")
            return

        mesh = self.original_pieces.get(key)
        if mesh is None:
            return

        panel = self.pieces_panel
        wall_mm = panel.wall_width_slider.value() / 10
        top_mm = panel.top_width_slider.value() / 10
        bottom_mm = panel.bottom_width_slider.value() / 10
        hole_pct = panel.hole_radius_slider.value()

        logging.info(
            f"Hollowing {key}: wall={wall_mm} mm, top={top_mm} mm, "
            f"bottom={bottom_mm} mm, hole={hole_pct}%"
        )
        thickness_axis = detect_thickness_axis(self.mesh)
        self.setCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            hollowed = hollow_piece(
                mesh, wall_mm, top_mm, bottom_mm, hole_pct, thickness_axis
            )
        except Exception as exc:
            logging.error(f"Could not hollow piece {key}: {exc}")
            return
        finally:
            self.unsetCursor()

        self.pieces[key] = hollowed
        self.viewer.show_pieces(
            self.pieces,
            cut_outlines=self.cut_outlines,
            original_mesh=self.mesh,
            selection=key,
        )
        self.pieces_panel.export_button.setEnabled(True)
        logging.info(f"Hollow applied to {key}")

    def on_export_hollow(self):
        if not self.original_pieces:
            logging.warning("Nothing to export, run a preview first")
            return

        panel = self.pieces_panel
        hollow_params = (
            panel.wall_width_slider.value() / 10,
            panel.top_width_slider.value() / 10,
            panel.bottom_width_slider.value() / 10,
            panel.hole_radius_slider.value(),
        )
        thickness_axis = detect_thickness_axis(self.mesh)

        logging.info("Exporting hollowing for all pieces...")
        self.export_window = ExportWindow(
            self.original_pieces, hollow_params, thickness_axis, self
        )
        self.export_window.show()
        self.export_window.process_and_show()
