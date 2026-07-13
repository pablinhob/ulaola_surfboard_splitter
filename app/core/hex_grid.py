import numpy as np

from app.core.polygon_grid import generate_grid_centers, split_into_cells

POINTY_TOP_ANGLES_DEG = np.arange(6) * 60 - 30


def _hex_vertices_2d(center, radius):
    angles = np.radians(POINTY_TOP_ANGLES_DEG)
    return [
        (center[0] + radius * np.cos(a), center[1] + radius * np.sin(a)) for a in angles
    ]


def split_into_hexagons(mesh, radius_mm, length_axis, width_axis):
    min_bounds, max_bounds = mesh.bounds
    min_2d = (min_bounds[length_axis], min_bounds[width_axis])
    max_2d = (max_bounds[length_axis], max_bounds[width_axis])

    centers = generate_grid_centers(min_2d, max_2d, radius_mm)
    cell_vertices = {
        key: _hex_vertices_2d(center, radius_mm) for key, center in centers.items()
    }

    return split_into_cells(mesh, cell_vertices, length_axis, width_axis)
