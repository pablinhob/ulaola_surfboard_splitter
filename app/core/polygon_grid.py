import numpy as np
import trimesh
from shapely.geometry import Polygon


def generate_grid_centers(min_2d, max_2d, radius):
    horiz_spacing = radius * np.sqrt(3)
    vert_spacing = radius * 1.5
    margin = radius

    row_start = int(np.floor((min_2d[1] - margin) / vert_spacing)) - 1
    row_end = int(np.ceil((max_2d[1] + margin) / vert_spacing)) + 1
    col_start = int(np.floor((min_2d[0] - margin) / horiz_spacing)) - 1
    col_end = int(np.ceil((max_2d[0] + margin) / horiz_spacing)) + 1

    centers = {}
    for row in range(row_start, row_end + 1):
        y = row * vert_spacing
        x_offset = horiz_spacing / 2 if row % 2 else 0
        for col in range(col_start, col_end + 1):
            x = col * horiz_spacing + x_offset
            centers[(row, col)] = (x, y)
    return centers


def to_3d(point_2d, length_axis, width_axis):
    point = np.zeros(3)
    point[length_axis] = point_2d[0]
    point[width_axis] = point_2d[1]
    return point


def edge_key(v1, v2, precision=3):
    p1 = (round(v1[0], precision), round(v1[1], precision))
    p2 = (round(v2[0], precision), round(v2[1], precision))
    return frozenset((p1, p2))


def outward_edge_normal(v1, v2, center):
    edge_vec = np.array(v2) - np.array(v1)
    normal = np.array([edge_vec[1], -edge_vec[0]])
    normal = normal / np.linalg.norm(normal)
    if np.dot(normal, np.array(center) - np.array(v1)) > 0:
        normal = -normal
    return normal


def build_prism(
    verts_2d,
    length_axis,
    width_axis,
    thickness_axis,
    min_thickness,
    max_thickness,
    margin=1.0,
):
    height = (max_thickness - min_thickness) + 2 * margin
    prism = trimesh.creation.extrude_polygon(Polygon(verts_2d), height=height)

    remapped = np.zeros_like(prism.vertices)
    remapped[:, length_axis] = prism.vertices[:, 0]
    remapped[:, width_axis] = prism.vertices[:, 1]
    remapped[:, thickness_axis] = prism.vertices[:, 2] + (min_thickness - margin)
    prism.vertices = remapped
    return prism


def cap_face_outline(mesh, plane_origin, plane_normal, tolerance=1e-4):
    distances = np.dot(mesh.vertices - plane_origin, plane_normal)
    on_plane = np.abs(distances) < tolerance
    face_mask = on_plane[mesh.faces].all(axis=1)
    if not face_mask.any():
        return None

    face_indices = np.nonzero(face_mask)[0]
    try:
        submesh = mesh.submesh([face_indices], append=True)
        return submesh.outline()
    except Exception:
        return None


def split_into_cells(mesh, cell_vertices, length_axis, width_axis):
    thickness_axis = 3 - length_axis - width_axis
    min_bounds, max_bounds = mesh.bounds

    centers = {
        key: tuple(np.mean(verts, axis=0)) for key, verts in cell_vertices.items()
    }

    edge_owners = {}
    for key, verts in cell_vertices.items():
        n = len(verts)
        for i in range(n):
            v1, v2 = verts[i], verts[(i + 1) % n]
            edge_owners.setdefault(edge_key(v1, v2), []).append((key, v1, v2))

    cell_meshes = {}
    for key, verts in cell_vertices.items():
        prism = build_prism(
            verts,
            length_axis,
            width_axis,
            thickness_axis,
            min_bounds[thickness_axis],
            max_bounds[thickness_axis],
        )
        try:
            piece = mesh.intersection(prism)
        except Exception:
            piece = None
        if piece is not None and len(piece.faces) > 0:
            cell_meshes[key] = piece

    ordered_keys = sorted(cell_meshes.keys())
    key_to_index = {key: idx for idx, key in enumerate(ordered_keys)}
    segments = [cell_meshes[key] for key in ordered_keys]

    outlines = []
    for owners in edge_owners.values():
        if len(owners) != 2:
            continue

        (key_a, v1, v2), (key_b, _, _) = owners
        if key_a not in key_to_index or key_b not in key_to_index:
            continue

        outward = outward_edge_normal(v1, v2, centers[key_a])
        plane_normal = to_3d(outward, length_axis, width_axis)
        plane_origin = to_3d(v1, length_axis, width_axis)

        outline_path = cap_face_outline(cell_meshes[key_a], plane_origin, plane_normal)
        outlines.append(
            {
                "outline": outline_path,
                "borders": [key_to_index[key_a], key_to_index[key_b]],
            }
        )

    return segments, outlines
