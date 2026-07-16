"""Placement of the board plugs and their preview markers.

Builds trimesh solids positioned on the board so the GUI can render them as
green markers. Every marker is the real cavity shape from
``plug_subtraction_geometries`` (leash plug from the deck, fin boxes from the
hull), laid flat on the rockered surface and protruding a hair so the drill zone
shows. Nothing is subtracted from the board here — this only decides placement.
"""

from app.core.plug_subtraction_geometries import (
    futures_fin_cavity_side,
    leash_plug_cavity,
    single_fin_cavity,
)

# Markers stick out this little above the surface, so the green footprint of the
# zone to be drilled is visible without hiding the board.
MARKER_PROTRUSION_MM = 0.1
# When the cavities are subtracted for real, they poke this far past the surface
# so the boolean cuts cleanly through it.
SUBTRACTION_MARGIN_MM = 1.0


def leash_plug_markers(
    mesh,
    tail_distance_mm,
    center_offset_mm,
    diameter_mm,
    depth_mm,
    above_mm=MARKER_PROTRUSION_MM,
):
    """Leash plug cavity, on the deck (top)."""
    return [
        leash_plug_cavity(
            mesh,
            tail_distance_mm,
            center_offset_mm,
            diameter_mm,
            depth_mm,
            above_mm=above_mm,
        )
    ]


def single_fin_markers(
    mesh,
    tail_distance_mm,
    box_long_mm,
    box_width_mm,
    box_depth_mm,
    above_mm=MARKER_PROTRUSION_MM,
):
    """Single fin box cavity, on the hull (bottom)."""
    return [
        single_fin_cavity(
            mesh,
            tail_distance_mm,
            box_long_mm,
            box_width_mm,
            box_depth_mm,
            above_mm=above_mm,
        )
    ]


def twin_fin_markers(
    mesh,
    tail_distance_mm,
    center_distance_mm,
    angle_deg,
    above_mm=MARKER_PROTRUSION_MM,
):
    """Two side Futures box cavities (deep), toed toward the centreline, on the hull."""
    half = center_distance_mm / 2.0
    return [
        futures_fin_cavity_side(
            mesh, tail_distance_mm, -half, angle_deg, above_mm=above_mm
        ),
        futures_fin_cavity_side(
            mesh, tail_distance_mm, half, angle_deg, above_mm=above_mm
        ),
    ]
