"""Solids to subtract from the board to fit each plug / insert type.

One builder per insert design (leash plug, Futures fin box, single fin box, and
more to come). Each returns a trimesh solid laid flat against the board surface
at the requested spot, oriented to the local (rockered) surface normal. The same
solids double as the green preview markers, with a tiny protrusion above the
surface; nothing is subtracted here.

Placement (tail distance, center offset, toe, which face) is passed in; the
routing shape of each insert lives here because some are non-trivial.
"""

import numpy as np
import trimesh
from shapely.geometry import LineString, Point, box

from app.core.mesh_ops import board_axes, surface_frame

# Extra gap added all around every cavity for the insert + glue.
PLUG_GLUE_CLEARANCE_MM = 0.2

# --- Futures single fin box: APPROXIMATE routing dimensions ---------------
# Best-effort values; verify against the official Futures routing template
# before cutting real boards. Plan = "stadium" (rectangle + semicircular ends).
FUTURES_BOX_LENGTH_MM = 122.0  # overall slot length, tip to tip
FUTURES_BOX_WIDTH_MM = 11.0  # slot width (= diameter of the rounded ends)
FUTURES_DEPTH_SIDE_MM = 16.0  # deep version (side fins)
FUTURES_DEPTH_CENTER_MM = 12.0  # shallower version (center fin)

# Single fin box: vertical edges rounded with this radius.
SINGLE_FIN_CORNER_RADIUS_MM = 6.0

_ARC_RESOLUTION = 24  # segments per rounded arc


def _stadium_polygon(length_mm, width_mm):
    """Stadium (rectangle + semicircular ends), centred, long axis along X."""
    radius = width_mm / 2.0
    half_straight = max(length_mm / 2.0 - radius, 0.0)
    spine = LineString([(-half_straight, 0.0), (half_straight, 0.0)])
    return spine.buffer(radius, resolution=_ARC_RESOLUTION)


def _rounded_rectangle(length_mm, width_mm, radius_mm):
    """Rectangle ``length_mm`` x ``width_mm`` with rounded corners, centred,
    long axis along X. The radius is clamped so it never exceeds half a side."""
    radius = min(radius_mm, length_mm / 2.0, width_mm / 2.0)
    inner = box(
        -(length_mm / 2.0 - radius),
        -(width_mm / 2.0 - radius),
        length_mm / 2.0 - radius,
        width_mm / 2.0 - radius,
    )
    return inner.buffer(radius, resolution=_ARC_RESOLUTION)


def _extrude_pocket(footprint, depth_mm, above_mm):
    """Extrude a 2D footprint into a pocket solid with ``z = 0`` on the surface,
    top at ``+above_mm`` (protrusion) and bottom at ``-depth_mm`` (into board)."""
    solid = trimesh.creation.extrude_polygon(footprint, height=depth_mm + above_mm)
    verts = solid.vertices.copy()
    verts[:, 2] -= depth_mm
    solid.vertices = verts
    return solid


def _place_on_surface(
    mesh, solid_local, length_pos, width_pos, length_span, width_span, toe_deg, bottom
):
    """Lay ``solid_local`` flat against the board surface at (length_pos, width_pos).

    The solid's +Z is aligned to the surface normal (averaged over the plug's
    extent, so it follows the rocker), its +X to the board length projected onto
    the surface, then toed by ``toe_deg`` about the normal. ``z = 0`` lands on
    the contact point. ``bottom`` picks the hull side (fins) vs the deck (leash).
    """
    axes = board_axes(mesh)
    length_axis, width_axis, thickness_axis = axes
    point, normal = surface_frame(
        mesh, axes, length_pos, width_pos, length_span, width_span, bottom
    )

    long_dir = np.zeros(3)
    long_dir[length_axis] = 1.0
    long_dir = long_dir - np.dot(long_dir, normal) * normal
    if np.linalg.norm(long_dir) < 1e-9:
        long_dir = np.zeros(3)
        long_dir[width_axis] = 1.0
        long_dir = long_dir - np.dot(long_dir, normal) * normal
    long_dir = long_dir / np.linalg.norm(long_dir)
    width_dir = np.cross(normal, long_dir)

    frame = np.column_stack([long_dir, width_dir, normal])
    toe = trimesh.transformations.rotation_matrix(np.radians(toe_deg), normal)[:3, :3]
    frame = toe @ frame

    transform = np.eye(4)
    transform[:3, :3] = frame
    transform[:3, 3] = point

    placed = solid_local.copy()
    placed.apply_transform(transform)
    return placed


def _plug_cavity(
    mesh,
    base_polygon,
    depth_mm,
    tail_distance_mm,
    center_offset_mm,
    toe_deg,
    above_mm,
    bottom,
    clearance_mm=PLUG_GLUE_CLEARANCE_MM,
):
    """Position a cavity (given its 2D footprint) on the board surface."""
    footprint = base_polygon.buffer(clearance_mm) if clearance_mm > 0 else base_polygon
    local = _extrude_pocket(footprint, depth_mm + clearance_mm, above_mm)

    length_axis, width_axis, thickness_axis = board_axes(mesh)
    min_bounds, max_bounds = mesh.bounds
    length_pos = min_bounds[length_axis] + tail_distance_mm
    width_pos = (min_bounds[width_axis] + max_bounds[width_axis]) / 2 + center_offset_mm

    min_x, min_y, max_x, max_y = footprint.bounds
    return _place_on_surface(
        mesh,
        local,
        length_pos,
        width_pos,
        max_x - min_x,
        max_y - min_y,
        toe_deg,
        bottom,
    )


def leash_plug_cavity(
    mesh, tail_distance_mm, center_offset_mm, diameter_mm, depth_mm, above_mm=1.0
):
    """Cylindrical leash-plug cavity, routed from the deck (top surface)."""
    base = Point(0.0, 0.0).buffer(diameter_mm / 2.0, resolution=_ARC_RESOLUTION)
    return _plug_cavity(
        mesh,
        base,
        depth_mm,
        tail_distance_mm,
        center_offset_mm,
        0.0,
        above_mm,
        bottom=False,
    )


def single_fin_cavity(
    mesh, tail_distance_mm, box_long_mm, box_width_mm, box_depth_mm, above_mm=1.0
):
    """Single fin box cavity (rounded vertical edges), routed from the hull."""
    base = _rounded_rectangle(box_long_mm, box_width_mm, SINGLE_FIN_CORNER_RADIUS_MM)
    return _plug_cavity(
        mesh, base, box_depth_mm, tail_distance_mm, 0.0, 0.0, above_mm, bottom=True
    )


def _futures_fin_cavity(
    mesh, tail_distance_mm, center_offset_mm, angle_deg, depth_mm, above_mm
):
    base = _stadium_polygon(FUTURES_BOX_LENGTH_MM, FUTURES_BOX_WIDTH_MM)
    # Toe toward the centreline; the side is given by which half we are on.
    side = 1.0 if center_offset_mm >= 0 else -1.0
    return _plug_cavity(
        mesh,
        base,
        depth_mm,
        tail_distance_mm,
        center_offset_mm,
        side * angle_deg,
        above_mm,
        bottom=True,  # fin boxes are routed from the hull (underside)
    )


def futures_fin_cavity_side(
    mesh, tail_distance_mm, center_offset_mm, angle_deg=0.0, above_mm=1.0
):
    """Deep Futures cavity, for the side fins."""
    return _futures_fin_cavity(
        mesh,
        tail_distance_mm,
        center_offset_mm,
        angle_deg,
        FUTURES_DEPTH_SIDE_MM,
        above_mm,
    )


def futures_fin_cavity_center(
    mesh, tail_distance_mm, center_offset_mm=0.0, angle_deg=0.0, above_mm=1.0
):
    """Shallower Futures cavity, for the center fin."""
    return _futures_fin_cavity(
        mesh,
        tail_distance_mm,
        center_offset_mm,
        angle_deg,
        FUTURES_DEPTH_CENTER_MM,
        above_mm,
    )
