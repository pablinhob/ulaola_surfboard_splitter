import numpy as np
import trimesh
from shapely.geometry import Point
from trimesh.intersections import slice_mesh_plane

FACE_HOLE_SECTIONS = 48
DRILL_OUTER_MARGIN_MM = 1.0
DRILL_INNER_MARGIN_MM = 5.0
COLLINEAR_TOLERANCE_MM = 0.1


def _thickness_axis(mesh):
    return int(np.argmin(mesh.extents))


def hollow_piece(
    mesh,
    wall_width_mm,
    top_width_mm,
    bottom_width_mm,
    hole_radius_pct,
):
    """Hollow a core piece and drill a lightening hole in each lateral face.

    The interior is emptied leaving lateral walls of ``wall_width_mm``, a top
    skin of ``top_width_mm`` and a bottom skin of ``bottom_width_mm`` (a skin of
    0 leaves that face open). Each lateral face additionally gets a circular
    hole at its centre whose diameter is ``hole_radius_pct`` percent of the
    piece height at that location.
    """
    thickness_axis = _thickness_axis(mesh)
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

    tools = []

    cavity = _build_cavity(
        planar,
        to_3d,
        normal,
        thickness_axis,
        wall_width_mm,
        z_min,
        z_max,
        top_width_mm,
        bottom_width_mm,
    )
    if cavity is not None:
        tools.append(cavity)

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


def _build_cavity(
    planar,
    to_3d,
    normal,
    thickness_axis,
    wall_width_mm,
    z_min,
    z_max,
    top_width_mm,
    bottom_width_mm,
):
    cavity_bottom = z_min + bottom_width_mm
    cavity_top = z_max - top_width_mm
    if cavity_top - cavity_bottom <= 0:
        return None

    tall = (z_max - z_min) + 4.0
    lift = np.eye(4)
    lift[2, 3] = -tall / 2

    solids = []
    for polygon in planar.polygons_full:
        inner = polygon.buffer(-wall_width_mm)
        if inner.is_empty:
            continue
        for geometry in getattr(inner, "geoms", [inner]):
            solid = trimesh.creation.extrude_polygon(geometry, height=tall)
            solid.apply_transform(lift)
            solid.apply_transform(to_3d)
            solids.append(solid)

    if not solids:
        return None

    cavity = trimesh.util.concatenate(solids)

    lo = np.zeros(3)
    lo[thickness_axis] = cavity_bottom
    hi = np.zeros(3)
    hi[thickness_axis] = cavity_top
    cavity = slice_mesh_plane(cavity, normal, lo, cap=True)
    cavity = slice_mesh_plane(cavity, -normal, hi, cap=True)
    return cavity


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
    height = wall_width_mm + DRILL_OUTER_MARGIN_MM + DRILL_INNER_MARGIN_MM
    axis_offset = (DRILL_INNER_MARGIN_MM - DRILL_OUTER_MARGIN_MM) / 2

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
            if not polygon.contains(Point(*(midpoint + inward * 1e-6))):
                inward = -inward

            base = to_3d @ np.array([midpoint[0], midpoint[1], 0.0, 1.0])
            base = base[:3]
            top_z, bottom_z = _local_height(mesh, base, normal, thickness_axis, z_min)
            local_height = top_z - bottom_z
            radius = fraction * local_height / 2
            if radius <= 0 or edge_length < 2 * radius:
                continue

            inward_3d = rotation @ np.array([inward[0], inward[1], 0.0])
            norm = np.linalg.norm(inward_3d)
            if norm == 0:
                continue
            inward_3d = inward_3d / norm

            center = base.copy()
            center[thickness_axis] = (top_z + bottom_z) / 2
            center = center + inward_3d * axis_offset

            transform = np.eye(4)
            transform[:3, :3] = trimesh.geometry.align_vectors([0, 0, 1], inward_3d)[
                :3, :3
            ]
            transform[:3, 3] = center

            cylinders.append(
                trimesh.creation.cylinder(
                    radius=radius,
                    height=height,
                    sections=FACE_HOLE_SECTIONS,
                    transform=transform,
                )
            )

    return cylinders


def _local_height(mesh, point_xy, normal, thickness_axis, z_min):
    origin = point_xy.copy()
    origin[thickness_axis] = z_min - 1.0
    locations = mesh.ray.intersects_location([origin], [normal])[0]
    if len(locations) == 0:
        return mesh.bounds[1][thickness_axis], mesh.bounds[0][thickness_axis]
    zs = locations[:, thickness_axis]
    return float(zs.max()), float(zs.min())
