from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
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
    CUTLAP_WIDTH_DEFAULT_MM,
    CUTLAP_WIDTH_MAX_MM,
    CUTLAP_WIDTH_MIN_MM,
    PIECE_RADIUS_DEFAULT_MM,
    PIECE_RADIUS_MAX_MM,
    PIECE_RADIUS_MIN_MM,
    STRINGER_WIDTH_DEFAULT_MM,
    STRINGER_WIDTH_MAX_MM,
    STRINGER_WIDTH_MIN_MM,
)

PIECE_LABELS = {"stringer": "Stringer", "a": "Side A", "b": "Side B"}
CUTLAP_LABELS = {"a": "Cutlap A", "b": "Cutlap B"}


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

        self.execute_button = QPushButton("Split polygons")
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
        layout.addWidget(self.tree)

        self.reset()

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
