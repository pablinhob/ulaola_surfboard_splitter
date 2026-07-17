import logging

import numpy as np
import pymeshfix
import trimesh
from trimesh.intersections import slice_mesh_plane

from app.config import PIECE_RADIUS_DEFAULT_MM
from app.core.cutlap import split_cutlap, touches_boundary
from app.core.hex_grid import split_into_hexagons
from app.core.triangle_grid import split_into_triangles

MM_PER_CM = 10
CM3_PER_LITER = 1000

SPLIT_PATTERNS = {
    "hexagon": split_into_hexagons,
    "triangle": split_into_triangles,
}


def load_stl(path):
    return ensure_watertight(trimesh.load(path, force="mesh"))


def ensure_watertight(mesh):
    """Repair a non-watertight mesh so downstream booleans (split, hollow, plug
    subtraction) work on every piece — the stringer especially, which is a raw
    slice of the input and inherits any holes it has.
    """
    if mesh.is_watertight:
        return mesh

    vertices, faces = pymeshfix.clean_from_arrays(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int32),
    )
    repaired = trimesh.Trimesh(vertices, faces, process=False)
    if repaired.is_watertight:
        logging.info(
            "Input mesh was not watertight; repaired it "
            f"({len(mesh.faces)} -> {len(repaired.faces)} faces)."
        )
    else:
        logging.warning("Input mesh could not be fully repaired to watertight.")
    return repaired


def _detect_axes(mesh):
    min_bounds, max_bounds = mesh.bounds
    sizes = max_bounds - min_bounds

    length_axis = int(np.argmax(sizes))
    thickness_axis = int(np.argmin(sizes))
    width_axis = 3 - length_axis - thickness_axis

    return length_axis, width_axis, thickness_axis


def detect_thickness_axis(mesh):
    return _detect_axes(mesh)[2]


def board_axes(mesh):
    """(length, width, thickness) axis indices, ordered by extent."""
    return _detect_axes(mesh)


def surface_height(mesh, thickness_axis, point):
    """Top-surface coordinate along the thickness axis at ``point`` (in-plane)."""
    origin = np.array(point, dtype=float)
    origin[thickness_axis] = mesh.bounds[0][thickness_axis] - 1.0
    direction = np.zeros(3)
    direction[thickness_axis] = 1.0
    hits = mesh.ray.intersects_location([origin], [direction])[0]
    if len(hits):
        return hits[:, thickness_axis].max()
    return (mesh.bounds[0][thickness_axis] + mesh.bounds[1][thickness_axis]) / 2


def _surface_hit(
    mesh, length_axis, width_axis, thickness_axis, length_pos, width_pos, bottom
):
    """Location where a vertical ray meets the top (or bottom) surface."""
    origin = np.zeros(3)
    origin[length_axis] = length_pos
    origin[width_axis] = width_pos
    origin[thickness_axis] = mesh.bounds[0][thickness_axis] - 1.0
    direction = np.zeros(3)
    direction[thickness_axis] = 1.0

    hits = mesh.ray.intersects_location([origin], [direction])[0]
    if len(hits) == 0:
        return None
    column = hits[:, thickness_axis]
    index = int(np.argmin(column) if bottom else np.argmax(column))
    return np.array(hits[index], dtype=float)


def surface_frame(
    mesh, axes, length_pos, width_pos, length_span, width_span, bottom=False
):
    """Contact point and averaged outward normal of the top/bottom surface.

    The inclination is estimated from the surface heights at the extremes of a
    length-wise and a width-wise centre line spanning ``length_span`` x
    ``width_span`` around ``(length_pos, width_pos)``, so it reflects the overall
    tilt of the region the plug rests on rather than a single noisy triangle.
    The normal points outward from the chosen face (down when ``bottom``).
    """
    length_axis, width_axis, thickness_axis = axes

    def hit(length, width):
        return _surface_hit(
            mesh, length_axis, width_axis, thickness_axis, length, width, bottom
        )

    center = hit(length_pos, width_pos)
    if center is None:
        point = np.zeros(3)
        point[length_axis] = length_pos
        point[width_axis] = width_pos
        point[thickness_axis] = (
            mesh.bounds[0][thickness_axis] + mesh.bounds[1][thickness_axis]
        ) / 2
        normal = np.zeros(3)
        normal[thickness_axis] = -1.0 if bottom else 1.0
        return point, normal

    half_length = length_span / 2.0
    half_width = width_span / 2.0
    front = hit(length_pos + half_length, width_pos)
    back = hit(length_pos - half_length, width_pos)
    right = hit(length_pos, width_pos + half_width)
    left = hit(length_pos, width_pos - half_width)
    front = center if front is None else front
    back = center if back is None else back
    right = center if right is None else right
    left = center if left is None else left

    normal = np.cross(front - back, right - left)
    magnitude = np.linalg.norm(normal)
    if magnitude < 1e-9:
        normal = np.zeros(3)
        normal[thickness_axis] = 1.0
    else:
        normal = normal / magnitude
    if (normal[thickness_axis] > 0) == bottom:
        normal = -normal
    return center, normal


def split_lengthwise(mesh, stringer_width_mm=0.0):
    min_bounds, max_bounds = mesh.bounds
    _, width_axis, _ = _detect_axes(mesh)

    center = (min_bounds + max_bounds) / 2
    normal = np.zeros(3)
    normal[width_axis] = 1.0

    half_width = stringer_width_mm / 2
    origin_pos = center.copy()
    origin_pos[width_axis] += half_width
    origin_neg = center.copy()
    origin_neg[width_axis] -= half_width

    side_a = slice_mesh_plane(mesh, normal, origin_pos, cap=True)
    side_b = slice_mesh_plane(mesh, -normal, origin_neg, cap=True)
    outline_pos = mesh.section(plane_origin=origin_pos, plane_normal=normal)

    stringer = None
    outline_neg = None
    if stringer_width_mm > 0:
        below_pos = slice_mesh_plane(mesh, -normal, origin_pos, cap=True)
        stringer = slice_mesh_plane(below_pos, normal, origin_neg, cap=True)
        outline_neg = mesh.section(plane_origin=origin_neg, plane_normal=normal)

    return side_a, side_b, stringer, outline_pos, outline_neg


def _split_or_empty(split_fn, mesh, piece_radius_mm, length_axis, width_axis):
    if mesh is None:
        return [], []
    return split_fn(mesh, piece_radius_mm, length_axis, width_axis)


def split_board(
    mesh,
    piece_radius_mm=PIECE_RADIUS_DEFAULT_MM,
    stringer_width_mm=0.0,
    cutlap_width_mm=0.0,
    split_pattern="hexagon",
):
    split_fn = SPLIT_PATTERNS[split_pattern]

    side_a, side_b, stringer, outline_pos, outline_neg = split_lengthwise(
        mesh, stringer_width_mm
    )
    length_axis, width_axis, thickness_axis = _detect_axes(mesh)

    cutlap_a, interior_a, cutlap_outline_a, polygon_a = split_cutlap(
        mesh, side_a, cutlap_width_mm, length_axis, width_axis, thickness_axis
    )
    cutlap_b, interior_b, cutlap_outline_b, polygon_b = split_cutlap(
        mesh, side_b, cutlap_width_mm, length_axis, width_axis, thickness_axis
    )

    interior_segments_a, interior_outlines_a = _split_or_empty(
        split_fn, interior_a, piece_radius_mm, length_axis, width_axis
    )
    interior_segments_b, interior_outlines_b = _split_or_empty(
        split_fn, interior_b, piece_radius_mm, length_axis, width_axis
    )
    cutlap_segments_a, cutlap_hex_outlines_a = _split_or_empty(
        split_fn, cutlap_a, piece_radius_mm, length_axis, width_axis
    )
    cutlap_segments_b, cutlap_hex_outlines_b = _split_or_empty(
        split_fn, cutlap_b, piece_radius_mm, length_axis, width_axis
    )

    pieces = {}
    if stringer is not None:
        pieces[("stringer",)] = stringer

    for i, segment in enumerate(interior_segments_a):
        pieces[("a", i)] = segment
    for i, segment in enumerate(cutlap_segments_a):
        pieces[("a", "cutlap", i)] = segment

    for i, segment in enumerate(interior_segments_b):
        pieces[("b", i)] = segment
    for i, segment in enumerate(cutlap_segments_b):
        pieces[("b", "cutlap", i)] = segment

    tolerance = 1e-3
    a_min_width = side_a.bounds[0][width_axis]
    b_max_width = side_b.bounds[1][width_axis]

    a_border_keys = [
        ("a", i)
        for i, segment in enumerate(interior_segments_a)
        if abs(segment.bounds[0][width_axis] - a_min_width) < tolerance
    ]
    b_border_keys = [
        ("b", i)
        for i, segment in enumerate(interior_segments_b)
        if abs(segment.bounds[1][width_axis] - b_max_width) < tolerance
    ]
    other_side_keys = [("stringer",)] if stringer is not None else b_border_keys

    cut_outlines = [
        {"outline": outline_pos, "borders": a_border_keys + other_side_keys}
    ]
    if outline_neg is not None:
        cut_outlines.append(
            {"outline": outline_neg, "borders": [("stringer",)] + b_border_keys}
        )

    if cutlap_outline_a is not None:
        touching_interior = [
            ("a", i)
            for i, segment in enumerate(interior_segments_a)
            if touches_boundary(segment, polygon_a, length_axis, width_axis)
        ]
        touching_cutlap = [
            ("a", "cutlap", i)
            for i, segment in enumerate(cutlap_segments_a)
            if touches_boundary(segment, polygon_a, length_axis, width_axis)
        ]
        cut_outlines.append(
            {
                "outline": cutlap_outline_a,
                "borders": touching_interior + touching_cutlap,
            }
        )
    if cutlap_outline_b is not None:
        touching_interior = [
            ("b", i)
            for i, segment in enumerate(interior_segments_b)
            if touches_boundary(segment, polygon_b, length_axis, width_axis)
        ]
        touching_cutlap = [
            ("b", "cutlap", i)
            for i, segment in enumerate(cutlap_segments_b)
            if touches_boundary(segment, polygon_b, length_axis, width_axis)
        ]
        cut_outlines.append(
            {
                "outline": cutlap_outline_b,
                "borders": touching_interior + touching_cutlap,
            }
        )

    for entry in interior_outlines_a:
        i, j = entry["borders"]
        cut_outlines.append(
            {"outline": entry["outline"], "borders": [("a", i), ("a", j)]}
        )
    for entry in interior_outlines_b:
        i, j = entry["borders"]
        cut_outlines.append(
            {"outline": entry["outline"], "borders": [("b", i), ("b", j)]}
        )
    for entry in cutlap_hex_outlines_a:
        i, j = entry["borders"]
        cut_outlines.append(
            {
                "outline": entry["outline"],
                "borders": [("a", "cutlap", i), ("a", "cutlap", j)],
            }
        )
    for entry in cutlap_hex_outlines_b:
        i, j = entry["borders"]
        cut_outlines.append(
            {
                "outline": entry["outline"],
                "borders": [("b", "cutlap", i), ("b", "cutlap", j)],
            }
        )

    return pieces, cut_outlines


def compute_object_stats(mesh):
    min_bounds, max_bounds = mesh.bounds
    size_cm = (max_bounds - min_bounds) / MM_PER_CM

    volume_cm3 = abs(mesh.volume) / (MM_PER_CM**3)
    volume_liters = volume_cm3 / CM3_PER_LITER

    return {
        "size_cm": tuple(size_cm),
        "volume_cm3": volume_cm3,
        "volume_liters": volume_liters,
    }
