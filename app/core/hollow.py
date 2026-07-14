import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

FACE_HOLE_SECTIONS = 48
DRILL_OUTER_MARGIN_MM = 1.0
DRILL_INNER_MARGIN_MM = 5.0
COLLINEAR_TOLERANCE_MM = 0.1
HEIGHT_SAMPLE_INSET_MM = 1.0
# The footprint comes from unioning the piece's triangles, so its boundary has
# many tiny/near-collinear segments; simplifying it keeps the extruded cavity a
# clean watertight volume (extrude_polygon chokes on the jagged raw boundary).
FOOTPRINT_SIMPLIFY_MM = 0.1


def hollow_piece(
    mesh,
    wall_width_mm,
    top_width_mm,
    bottom_width_mm,
    hole_radius_pct,
    thickness_axis,
):
    """Hollow a core piece and drill a lightening hole in each lateral face.

    The interior is emptied leaving lateral walls of ``wall_width_mm``, a top
    skin of ``top_width_mm`` and a bottom skin of ``bottom_width_mm`` (a skin of
    0 leaves that face open). Each lateral face additionally gets a circular
    hole at its centre whose diameter is ``hole_radius_pct`` percent of the
    piece height at that location.

    ``thickness_axis`` is the board's thickness axis (the lateral faces are the
    ones parallel to it). It is supplied by the caller rather than detected
    per piece, because a piece can be taller than it is wide, which would make
    a per-piece smallest-extent guess pick the wrong axis.
    """
    normal = np.zeros(3)
    normal[thickness_axis] = 1.0

    z_min = mesh.bounds[0][thickness_axis]
    z_max = mesh.bounds[1][thickness_axis]
    z_mid = (z_min + z_max) / 2

    origin = mesh.bounds[0].copy()
    origin[thickness_axis] = z_mid
    section = mesh.section(plane_origin=origin, plane_normal=normal)
    if section is None:
        return mesh

    planar, to_3d = section.to_planar()

    tools = _build_cavity(
        mesh,
        normal,
        thickness_axis,
        wall_width_mm,
        z_min,
        z_max,
        top_width_mm,
        bottom_width_mm,
    )

    if hole_radius_pct > 0:
        tools.extend(
            _build_face_holes(
                mesh,
                planar,
                to_3d,
                normal,
                thickness_axis,
                wall_width_mm,
                hole_radius_pct,
                z_min,
            )
        )

    if not tools:
        return mesh

    return trimesh.boolean.difference([mesh, *tools])


def _piece_footprint(mesh, thickness_axis):
    """The piece's shadow along the thickness axis (union of all its sections).

    Using the full footprint - rather than a single mid-height cross-section -
    means the cavity covers pieces whose faces tilt or curve across the
    thickness (rockered nose/tail, rounded rails). A mid-height slice only
    captures a diagonal sliver of such pieces, which left large solid bands.
    """
    in_axes = [a for a in range(3) if a != thickness_axis]
    triangles = mesh.triangles[:, :, in_axes]
    polygons = [Polygon(tri) for tri in triangles]
    footprint = unary_union([p for p in polygons if p.is_valid and p.area > 0])
    # buffer(0) heals any slivers left by the union into a clean polygon.
    return footprint.buffer(0)


def _build_cavity(
    mesh,
    normal,
    thickness_axis,
    wall_width_mm,
    z_min,
    z_max,
    top_width_mm,
    bottom_width_mm,
):
    """Build the cavity as a single prism from the piece's footprint.

    The footprint is inset by ``wall_width_mm`` and extruded through the
    hollowable thickness range. Returns a list of solid meshes (the difference
    tools), possibly empty.
    """
    cavity_bottom = z_min + bottom_width_mm
    cavity_top = z_max - top_width_mm
    span = cavity_top - cavity_bottom
    if span <= 0:
        return []

    footprint = _piece_footprint(mesh, thickness_axis)
    if footprint.is_empty:
        return []
    inner = footprint.buffer(-wall_width_mm)
    if inner.is_empty:
        return []

    in_axes = [a for a in range(3) if a != thickness_axis]
    solids = []
    for geometry in getattr(inner, "geoms", [inner]):
        geometry = geometry.simplify(FOOTPRINT_SIMPLIFY_MM)
        if geometry.is_empty:
            continue
        prism = trimesh.creation.extrude_polygon(geometry, height=span)
        remapped = np.zeros_like(prism.vertices)
        remapped[:, in_axes[0]] = prism.vertices[:, 0]
        remapped[:, in_axes[1]] = prism.vertices[:, 1]
        remapped[:, thickness_axis] = prism.vertices[:, 2] + cavity_bottom
        prism.vertices = remapped
        solids.append(prism)

    return solids


def _build_face_holes(
    mesh,
    planar,
    to_3d,
    normal,
    thickness_axis,
    wall_width_mm,
    hole_radius_pct,
    z_min,
):
    rotation = to_3d[:3, :3]
    fraction = hole_radius_pct / 100.0

    cylinders = []
    for polygon in planar.polygons_full:
        merged = polygon.simplify(COLLINEAR_TOLERANCE_MM, preserve_topology=True)
        coords = np.asarray(merged.exterior.coords)
        for start, end in zip(coords[:-1], coords[1:]):
            edge = end - start
            edge_length = np.linalg.norm(edge)
            if edge_length == 0:
                continue

            midpoint = (start + end) / 2
            inward = np.array([-edge[1], edge[0]]) / edge_length
            if not merged.contains(Point(*(midpoint + inward * 1e-6))):
                inward = -inward

            inward_3d = rotation @ np.array([inward[0], inward[1], 0.0])
            norm = np.linalg.norm(inward_3d)
            if norm == 0:
                continue
            inward_3d = inward_3d / norm

            # The face-centre height fixes a uniform hole size for this face.
            center_pt = to_3d @ np.array([midpoint[0], midpoint[1], 0.0, 1.0])
            span = _local_height(
                mesh,
                center_pt[:3] + inward_3d * HEIGHT_SAMPLE_INSET_MM,
                normal,
                thickness_axis,
                z_min,
            )
            if span is None:
                continue
            radius = fraction * (span[0] - span[1]) / 2
            # Gap between holes and clearance to top/bottom edges are both this
            # margin, so holes never overlap nor touch the deck/hull.
            margin = (1 - fraction) * (span[0] - span[1]) / 2
            if radius <= 0 or edge_length < 2 * radius:
                continue

            count = max(1, int((edge_length - margin) // (2 * radius + margin)))
            span_used = count * 2 * radius + (count - 1) * margin
            end_margin = (edge_length - span_used) / 2

            for i in range(count):
                distance = end_margin + radius + i * (2 * radius + margin)
                point2d = start + (distance / edge_length) * edge
                cylinder = _hole_cylinder(
                    mesh,
                    to_3d,
                    inward_3d,
                    point2d,
                    radius,
                    fraction,
                    normal,
                    thickness_axis,
                    z_min,
                    wall_width_mm,
                )
                if cylinder is not None:
                    cylinders.append(cylinder)

    return cylinders


def _hole_cylinder(
    mesh,
    to_3d,
    inward_3d,
    point2d,
    radius,
    fraction,
    normal,
    thickness_axis,
    z_min,
    wall_width_mm,
):
    base = (to_3d @ np.array([point2d[0], point2d[1], 0.0, 1.0]))[:3]
    span = _local_height(
        mesh, base + inward_3d * HEIGHT_SAMPLE_INSET_MM, normal, thickness_axis, z_min
    )
    if span is None:
        return None

    top_z, bottom_z = span
    # Follow the deck/hull drift vertically and never let a hole exceed the
    # local height (shorter spots shrink the hole rather than poke through).
    local_radius = min(radius, fraction * (top_z - bottom_z) / 2)
    if local_radius <= 0:
        return None

    height = wall_width_mm + DRILL_OUTER_MARGIN_MM + DRILL_INNER_MARGIN_MM
    axis_offset = (DRILL_INNER_MARGIN_MM - DRILL_OUTER_MARGIN_MM) / 2

    center = base.copy()
    center[thickness_axis] = (top_z + bottom_z) / 2
    center = center + inward_3d * axis_offset

    transform = np.eye(4)
    transform[:3, :3] = trimesh.geometry.align_vectors([0, 0, 1], inward_3d)[:3, :3]
    transform[:3, 3] = center

    return trimesh.creation.cylinder(
        radius=local_radius,
        height=height,
        sections=FACE_HOLE_SECTIONS,
        transform=transform,
    )


def _local_height(mesh, point_xy, normal, thickness_axis, z_min):
    origin = point_xy.copy()
    origin[thickness_axis] = z_min - 1.0
    locations = mesh.ray.intersects_location([origin], [normal])[0]
    if len(locations) < 2:
        return None
    zs = locations[:, thickness_axis]
    top, bottom = float(zs.max()), float(zs.min())
    if top - bottom <= 0:
        return None
    return top, bottom
