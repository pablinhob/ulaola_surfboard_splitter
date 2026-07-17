import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor

from app.config import (
    BOARD_COLOR,
    BOUNDING_BOX_EDGE_COLOR,
    CUTLAP_COLOR,
    PLUG_SUPPORT_COLOR,
    SPLIT_EDGE_COLOR,
    STRINGER_COLOR,
    VIEWER_BACKGROUND_COLOR,
)

CORNER_BRACKET_FRACTION = 0.12
GHOST_COLOR = "gray"
GHOST_OPACITY = 0.1


def _trimesh_to_pyvista(mesh):
    faces = np.hstack([np.full((len(mesh.faces), 1), 3), mesh.faces]).astype(np.int64)
    return pv.PolyData(mesh.vertices, faces)


def _build_corner_brackets(bounds, fraction=CORNER_BRACKET_FRACTION):
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    arm_x = (xmax - xmin) * fraction
    arm_y = (ymax - ymin) * fraction
    arm_z = (zmax - zmin) * fraction

    points = []
    line_cells = []
    for x, x_sign in ((xmin, 1), (xmax, -1)):
        for y, y_sign in ((ymin, 1), (ymax, -1)):
            for z, z_sign in ((zmin, 1), (zmax, -1)):
                corner = np.array([x, y, z])
                arms = (
                    corner + np.array([x_sign * arm_x, 0, 0]),
                    corner + np.array([0, y_sign * arm_y, 0]),
                    corner + np.array([0, 0, z_sign * arm_z]),
                )
                for tip in arms:
                    start_idx = len(points)
                    points.append(corner)
                    points.append(tip)
                    line_cells.append([2, start_idx, start_idx + 1])

    lines = np.hstack(line_cells).astype(np.int64)
    return pv.PolyData(np.array(points), lines=lines)


def _build_cut_outline(cut_path):
    if cut_path is None or len(cut_path.discrete) == 0:
        return None

    points = []
    line_cells = []
    for loop in cut_path.discrete:
        start_idx = len(points)
        points.extend(loop)
        loop_len = len(loop)
        for i in range(loop_len):
            a = start_idx + i
            b = start_idx + (i + 1) % loop_len
            line_cells.append([2, a, b])

    lines = np.hstack(line_cells).astype(np.int64)
    return pv.PolyData(np.array(points), lines=lines)


def _merge_bounds(bounds_a, bounds_b):
    merged = []
    for i in range(0, 6, 2):
        merged.append(min(bounds_a[i], bounds_b[i]))
        merged.append(max(bounds_a[i + 1], bounds_b[i + 1]))
    return tuple(merged)


class MeshViewer(QtInteractor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_background(VIEWER_BACKGROUND_COLOR)
        self._piece_actors = {}
        self._piece_edge_actors = {}
        self._piece_bounds = {}
        self._outline_actors = []
        self._ghost_actor = None
        self._marker_actors = []

    def show_mesh(self, pv_mesh, color=BOARD_COLOR):
        self.clear()
        self.set_background(VIEWER_BACKGROUND_COLOR)
        self._piece_actors = {}
        self._marker_actors = []
        self.add_mesh(pv_mesh, color=color)
        self._add_corner_brackets(pv_mesh.bounds)
        self.reset_camera()

    def set_plug_markers(self, solids, color="green"):
        """Draw (replacing any previous) a set of plug marker solids."""
        for actor in self._marker_actors:
            self.remove_actor(actor)
        self._marker_actors = []
        for solid in solids:
            self._marker_actors.append(
                self.add_mesh(_trimesh_to_pyvista(solid), color=color)
            )

    def show_trimesh(self, mesh, color=BOARD_COLOR):
        self.show_mesh(_trimesh_to_pyvista(mesh), color=color)

    def show_pieces(
        self, pieces, cut_outlines=None, original_mesh=None, selection=("all",)
    ):
        self.clear()
        self.set_background(VIEWER_BACKGROUND_COLOR)

        self._piece_actors = {}
        self._piece_edge_actors = {}
        self._piece_bounds = {}
        self._marker_actors = []
        combined_bounds = None
        for key, segment_mesh in pieces.items():
            if key[0] == "support":
                piece_color = PLUG_SUPPORT_COLOR
            elif key[0] == "stringer":
                piece_color = STRINGER_COLOR
            elif len(key) == 3 and key[1] == "cutlap":
                piece_color = CUTLAP_COLOR
            else:
                piece_color = BOARD_COLOR
            pv_mesh = _trimesh_to_pyvista(segment_mesh)
            self._piece_actors[key] = self.add_mesh(pv_mesh, color=piece_color)
            self._piece_bounds[key] = pv_mesh.bounds

            edges = pv_mesh.extract_feature_edges()
            if edges.n_cells:
                self._piece_edge_actors[key] = self.add_mesh(
                    edges, color=SPLIT_EDGE_COLOR, line_width=1.5
                )

            combined_bounds = (
                pv_mesh.bounds
                if combined_bounds is None
                else _merge_bounds(combined_bounds, pv_mesh.bounds)
            )

        self._outline_actors = []
        for entry in cut_outlines or []:
            outline_mesh = _build_cut_outline(entry["outline"])
            if outline_mesh is None:
                continue
            actor = self.add_mesh(outline_mesh, color=SPLIT_EDGE_COLOR, line_width=1.5)
            self._outline_actors.append((entry["borders"], actor))

        self._ghost_actor = None
        if original_mesh is not None:
            self._ghost_actor = self.add_mesh(
                _trimesh_to_pyvista(original_mesh),
                color=GHOST_COLOR,
                opacity=GHOST_OPACITY,
            )

        if combined_bounds is not None:
            self._add_corner_brackets(combined_bounds)
        self.reset_camera()
        self.set_piece_selection(selection)

    def set_piece_selection(self, selection):
        selected_bounds = None
        for key, actor in self._piece_actors.items():
            is_selected = self._matches_selection(selection, key)
            actor.visibility = is_selected
            edge_actor = self._piece_edge_actors.get(key)
            if edge_actor is not None:
                edge_actor.visibility = is_selected
            if is_selected:
                bounds = self._piece_bounds[key]
                selected_bounds = (
                    bounds
                    if selected_bounds is None
                    else _merge_bounds(selected_bounds, bounds)
                )

        for borders, actor in self._outline_actors:
            actor.visibility = any(
                self._matches_selection(selection, key) for key in borders
            )

        if self._ghost_actor is not None:
            self._ghost_actor.visibility = selection != ("all",)

        if selected_bounds is not None:
            self.reset_camera(bounds=selected_bounds)

    @staticmethod
    def _matches_selection(selection, piece_key):
        if selection == ("all",):
            return True
        return piece_key[: len(selection)] == selection

    def _add_corner_brackets(self, bounds):
        brackets = _build_corner_brackets(bounds)
        self.add_mesh(brackets, color=BOUNDING_BOX_EDGE_COLOR, line_width=2)
