from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    BOTTOM_WIDTH_DEFAULT_MM,
    BOTTOM_WIDTH_MAX_MM,
    BOTTOM_WIDTH_MIN_MM,
    CUTLAP_WIDTH_DEFAULT_MM,
    CUTLAP_WIDTH_MAX_MM,
    CUTLAP_WIDTH_MIN_MM,
    HOLE_RADIUS_DEFAULT_PCT,
    HOLE_RADIUS_MAX_PCT,
    HOLE_RADIUS_MIN_PCT,
    LEASH_PLUG_CENTER_DEFAULT_MM,
    LEASH_PLUG_CENTER_MAX_MM,
    LEASH_PLUG_CENTER_MIN_MM,
    LEASH_PLUG_DEPTH_DEFAULT_MM,
    LEASH_PLUG_DEPTH_MAX_MM,
    LEASH_PLUG_DEPTH_MIN_MM,
    LEASH_PLUG_DIAMETER_DEFAULT_MM,
    LEASH_PLUG_DIAMETER_MAX_MM,
    LEASH_PLUG_DIAMETER_MIN_MM,
    LEASH_PLUG_POSITION_DEFAULT_MM,
    LEASH_PLUG_POSITION_MAX_MM,
    LEASH_PLUG_POSITION_MIN_MM,
    PIECE_RADIUS_DEFAULT_MM,
    PIECE_RADIUS_MAX_MM,
    PIECE_RADIUS_MIN_MM,
    STRINGER_WIDTH_DEFAULT_MM,
    STRINGER_WIDTH_MAX_MM,
    STRINGER_WIDTH_MIN_MM,
    TOP_WIDTH_DEFAULT_MM,
    TOP_WIDTH_MAX_MM,
    TOP_WIDTH_MIN_MM,
    WALL_WIDTH_DEFAULT_MM,
    WALL_WIDTH_MAX_MM,
    WALL_WIDTH_MIN_MM,
)

PIECE_LABELS = {"stringer": "Stringer", "a": "Side A", "b": "Side B"}
CUTLAP_LABELS = {"a": "Cutlap A", "b": "Cutlap B"}

GROUP_HINT = "Select a piece from the board core to enable actions."
STRINGER_HINT = (
    "No actions available for this piece. Select a piece from the board core."
)
CUTLAP_HINT = (
    "No actions available for cutlap pieces. Select a piece from the board core."
)


class AccordionSection(QWidget):
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.toggle_button.toggled.connect(self._on_toggled)
        layout.addWidget(self.toggle_button)

        self.content = content
        self.content.setVisible(False)
        layout.addWidget(self.content)

    def _on_toggled(self, checked):
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self.content.setVisible(checked)

    def set_expanded(self, expanded):
        self.toggle_button.setChecked(expanded)

    def set_enabled(self, enabled):
        self.toggle_button.setEnabled(enabled)
        if not enabled:
            self.set_expanded(False)


class LeashPlugPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Leash plug box", parent)
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.diameter_spin = self._add_field(
            top_row,
            "Diameter",
            LEASH_PLUG_DIAMETER_MIN_MM,
            LEASH_PLUG_DIAMETER_MAX_MM,
            LEASH_PLUG_DIAMETER_DEFAULT_MM,
        )
        self.depth_spin = self._add_field(
            top_row,
            "Deep",
            LEASH_PLUG_DEPTH_MIN_MM,
            LEASH_PLUG_DEPTH_MAX_MM,
            LEASH_PLUG_DEPTH_DEFAULT_MM,
        )
        layout.addLayout(top_row)

        bottom_row = QHBoxLayout()
        self.position_spin = self._add_field(
            bottom_row,
            "Position",
            LEASH_PLUG_POSITION_MIN_MM,
            LEASH_PLUG_POSITION_MAX_MM,
            LEASH_PLUG_POSITION_DEFAULT_MM,
        )
        self.center_spin = self._add_field(
            bottom_row,
            "Center",
            LEASH_PLUG_CENTER_MIN_MM,
            LEASH_PLUG_CENTER_MAX_MM,
            LEASH_PLUG_CENTER_DEFAULT_MM,
        )
        layout.addLayout(bottom_row)

    def _add_field(self, layout, title, minimum, maximum, initial):
        layout.addWidget(QLabel(title))
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(initial)
        # Room for up to 4 digits (plus a sign / spin arrows).
        spin.setMinimumWidth(70)
        layout.addWidget(spin)
        layout.addWidget(QLabel("mm"))
        return spin


class PlugsSetupPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.leash_plug_panel = LeashPlugPanel()
        layout.addWidget(self.leash_plug_panel)

        self.continue_button = QPushButton("Continue")
        layout.addWidget(self.continue_button)


class SplitterParametrizationPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Split polygon"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["Hexagon", "Triangle"])
        layout.addWidget(self.shape_combo)

        self.piece_radius_slider = self._add_slider(
            layout,
            "Circumscribed radius",
            PIECE_RADIUS_MIN_MM,
            PIECE_RADIUS_MAX_MM,
            PIECE_RADIUS_DEFAULT_MM,
            unit=" mm",
        )
        self.stringer_width_slider = self._add_slider(
            layout,
            "Stringer width",
            STRINGER_WIDTH_MIN_MM,
            STRINGER_WIDTH_MAX_MM,
            STRINGER_WIDTH_DEFAULT_MM,
            unit=" mm",
        )
        self.cutlap_width_slider = self._add_slider(
            layout,
            "Cutlap width",
            CUTLAP_WIDTH_MIN_MM,
            CUTLAP_WIDTH_MAX_MM,
            CUTLAP_WIDTH_DEFAULT_MM,
            unit=" mm",
        )

        self.execute_button = QPushButton("Split base polygons")
        layout.addWidget(self.execute_button)

    def _add_slider(self, layout, title, minimum, maximum, initial, unit=""):
        label = QLabel(f"{title}: {initial}{unit}")
        layout.addWidget(label)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(initial)
        slider.valueChanged.connect(
            lambda value: label.setText(f"{title}: {value}{unit}")
        )
        layout.addWidget(slider)

        return slider


class PiecesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(
            lambda current, _previous: self._update_actions(current)
        )
        layout.addWidget(self.tree)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.piece_actions = QGroupBox("Polygon hollowing actions")
        actions_layout = QVBoxLayout(self.piece_actions)
        self.wall_width_slider = self._add_slider(
            actions_layout,
            "Wall width",
            WALL_WIDTH_MIN_MM,
            WALL_WIDTH_MAX_MM,
            WALL_WIDTH_DEFAULT_MM,
            unit=" mm",
            decimals=1,
        )
        self.top_width_slider = self._add_slider(
            actions_layout,
            "Top width",
            TOP_WIDTH_MIN_MM,
            TOP_WIDTH_MAX_MM,
            TOP_WIDTH_DEFAULT_MM,
            unit=" mm",
            decimals=1,
        )
        self.bottom_width_slider = self._add_slider(
            actions_layout,
            "Bottom width",
            BOTTOM_WIDTH_MIN_MM,
            BOTTOM_WIDTH_MAX_MM,
            BOTTOM_WIDTH_DEFAULT_MM,
            unit=" mm",
            decimals=1,
        )
        self.hole_radius_slider = self._add_slider(
            actions_layout,
            "Hole radius",
            HOLE_RADIUS_MIN_PCT,
            HOLE_RADIUS_MAX_PCT,
            HOLE_RADIUS_DEFAULT_PCT,
            unit=" %",
        )
        self.apply_button = QPushButton("Preview hollowing")
        self.export_button = QPushButton("Export Hollowing")
        self.export_button.setEnabled(False)
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.apply_button)
        buttons_layout.addWidget(self.export_button)
        actions_layout.addLayout(buttons_layout)
        layout.addWidget(self.piece_actions)

        for slider in (self.top_width_slider, self.bottom_width_slider):
            slider.setEnabled(False)
            slider.value_label.setEnabled(False)

        # Any change to the hollow parameters invalidates the current preview,
        # so the export must be re-generated from a fresh preview.
        for slider in (
            self.wall_width_slider,
            self.top_width_slider,
            self.bottom_width_slider,
            self.hole_radius_slider,
        ):
            slider.valueChanged.connect(
                lambda _value: self.export_button.setEnabled(False)
            )

        self.reset()
        self._update_actions(None)

    def _add_slider(
        self, layout, title, minimum, maximum, initial, unit="", decimals=0
    ):
        factor = 10**decimals
        label = QLabel()
        layout.addWidget(label)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(round(minimum * factor), round(maximum * factor))
        slider.setValue(round(initial * factor))

        def refresh(raw):
            value = raw / factor
            shown = f"{value:.{decimals}f}" if decimals else f"{int(value)}"
            label.setText(f"{title}: {shown}{unit}")

        slider.valueChanged.connect(refresh)
        refresh(slider.value())
        layout.addWidget(slider)

        slider.value_label = label
        return slider

    @staticmethod
    def _classify(key):
        if not key:
            return "none"
        if key == ("all",):
            return "group"
        if key == ("stringer",):
            return "stringer"
        if len(key) == 1:
            return "group"
        if key[1] == "cutlap":
            return "cutlap_piece" if len(key) == 3 else "group"
        return "core"

    def _update_actions(self, item):
        key = item.data(0, Qt.UserRole) if item is not None else None
        category = self._classify(key)

        # Selecting a different piece invalidates the current preview, so the
        # export must be re-generated from a fresh preview.
        self.export_button.setEnabled(False)

        if category == "core":
            self.status_label.setVisible(False)
            self.piece_actions.setVisible(True)
            return

        self.piece_actions.setVisible(False)
        message = {
            "group": GROUP_HINT,
            "stringer": STRINGER_HINT,
            "cutlap_piece": CUTLAP_HINT,
        }.get(category, "")
        self.status_label.setText(message)
        self.status_label.setVisible(bool(message))

    def reset(self):
        self.tree.clear()
        placeholder = QTreeWidgetItem(
            ["No pieces yet - run Execute to split the board"]
        )
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self.tree.addTopLevelItem(placeholder)

    def populate(self, pieces):
        self.tree.clear()

        all_item = QTreeWidgetItem(["All"])
        all_item.setData(0, Qt.UserRole, ("all",))
        self.tree.addTopLevelItem(all_item)

        sides = {}
        for key in pieces:
            if len(key) == 1:
                label = PIECE_LABELS.get(key[0], key[0])
                leaf_item = QTreeWidgetItem([label])
                leaf_item.setData(0, Qt.UserRole, key)
                self.tree.addTopLevelItem(leaf_item)
                continue

            half = key[0]
            group = sides.setdefault(half, {"interior": [], "cutlap": []})
            if len(key) == 2:
                group["interior"].append(key)
            elif len(key) == 3 and key[1] == "cutlap":
                group["cutlap"].append(key)

        for half, group in sides.items():
            half_item = QTreeWidgetItem([PIECE_LABELS.get(half, half)])
            half_item.setData(0, Qt.UserRole, (half,))
            self.tree.addTopLevelItem(half_item)

            if group["cutlap"]:
                cutlap_item = QTreeWidgetItem([CUTLAP_LABELS.get(half, "Cutlap")])
                cutlap_item.setData(0, Qt.UserRole, (half, "cutlap"))
                half_item.addChild(cutlap_item)

                for index, key in enumerate(
                    sorted(group["cutlap"], key=lambda k: k[2])
                ):
                    split_item = QTreeWidgetItem([f"Cutlap split {index + 1}"])
                    split_item.setData(0, Qt.UserRole, key)
                    cutlap_item.addChild(split_item)

            for index, key in enumerate(sorted(group["interior"], key=lambda k: k[1])):
                split_item = QTreeWidgetItem([f"Main Split {index + 1}"])
                split_item.setData(0, Qt.UserRole, key)
                half_item.addChild(split_item)

        self.tree.expandAll()
        self.tree.setCurrentItem(all_item)


class ObjectStatsPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Object info", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.size_label = QLabel("Bounding box: -")
        layout.addWidget(self.size_label)

        self.volume_label = QLabel("Volume: -")
        layout.addWidget(self.volume_label)

    def update_stats(self, stats):
        x, y, z = stats["size_cm"]
        self.size_label.setText(f"Bounding box: {x:.1f} x {y:.1f} x {z:.1f} cm")
        self.volume_label.setText(
            f"Volume: {stats['volume_cm3']:.1f} cm³ ({stats['volume_liters']:.2f} L)"
        )

    def reset(self):
        self.size_label.setText("Bounding box: -")
        self.volume_label.setText("Volume: -")
