import numpy as np
import trimesh
from shapely.geometry import Point
from trimesh.path.polygons import projected


def _axis_normal(axis):
    normal = np.zeros(3)
    normal[axis] = 1.0
    return normal


def _extrude_prism(
    polygon,
    length_axis,
    width_axis,
    thickness_axis,
    min_thickness,
    max_thickness,
    margin=1.0,
):
    height = (max_thickness - min_thickness) + 2 * margin
    prism = trimesh.creation.extrude_polygon(polygon, height=height)

    remapped = np.zeros_like(prism.vertices)
    remapped[:, length_axis] = prism.vertices[:, 0]
    remapped[:, width_axis] = prism.vertices[:, 1]
    remapped[:, thickness_axis] = prism.vertices[:, 2] + (min_thickness - margin)
    prism.vertices = remapped
    return prism


def _boundary_outline(piece_mesh, polygon, length_axis, width_axis, tolerance=1e-2):
    boundary = polygon.exterior
    centroids = piece_mesh.triangles_center
    points_2d = centroids[:, [length_axis, width_axis]]
    distances = np.array([boundary.distance(Point(p)) for p in points_2d])
    face_mask = distances < tolerance
    if not face_mask.any():
        return None

    face_indices = np.nonzero(face_mask)[0]
    try:
        submesh = piece_mesh.submesh([face_indices], append=True)
        return submesh.outline()
    except Exception:
        return None


def touches_boundary(piece_mesh, polygon, length_axis, width_axis, tolerance=1e-2):
    boundary = polygon.exterior
    points_2d = piece_mesh.vertices[:, [length_axis, width_axis]]
    return any(boundary.distance(Point(p)) < tolerance for p in points_2d)


def split_cutlap(
    mesh, side_mesh, cutlap_width_mm, length_axis, width_axis, thickness_axis
):
    if cutlap_width_mm <= 0:
        return None, side_mesh, None, None

    footprint = projected(mesh, normal=_axis_normal(thickness_axis))
    inner_polygon = footprint.buffer(-cutlap_width_mm)

    if inner_polygon.is_empty:
        return side_mesh, None, None, None

    if inner_polygon.geom_type == "MultiPolygon":
        inner_polygon = max(inner_polygon.geoms, key=lambda p: p.area)

    min_bounds, max_bounds = mesh.bounds
    prism = _extrude_prism(
        inner_polygon,
        length_axis,
        width_axis,
        thickness_axis,
        min_bounds[thickness_axis],
        max_bounds[thickness_axis],
    )

    interior = side_mesh.intersection(prism)
    cutlap = side_mesh.difference(prism)

    if interior is None or len(interior.faces) == 0:
        interior = None
    if cutlap is None or len(cutlap.faces) == 0:
        cutlap = None

    outline = None
    if cutlap is not None:
        outline = _boundary_outline(cutlap, inner_polygon, length_axis, width_axis)

    return cutlap, interior, outline, inner_polygon
