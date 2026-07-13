import numpy as np

from app.core.polygon_grid import split_into_cells


def _lattice_point(i, j, side_length):
    height = side_length * np.sqrt(3) / 2
    return (i * side_length + j * side_length / 2, j * height)


def _generate_triangle_cells(min_2d, max_2d, radius):
    side_length = radius * np.sqrt(3)
    height = side_length * np.sqrt(3) / 2
    margin = radius

    j_min = int(np.floor((min_2d[1] - margin) / height)) - 1
    j_max = int(np.ceil((max_2d[1] + margin) / height)) + 1

    cells = {}
    for j in range(j_min, j_max + 1):
        row_offset = j * side_length / 2
        i_min = int(np.floor((min_2d[0] - margin - row_offset) / side_length)) - 1
        i_max = int(np.ceil((max_2d[0] + margin - row_offset) / side_length)) + 1
        for i in range(i_min, i_max + 1):
            p00 = _lattice_point(i, j, side_length)
            p10 = _lattice_point(i + 1, j, side_length)
            p01 = _lattice_point(i, j + 1, side_length)
            p11 = _lattice_point(i + 1, j + 1, side_length)
            cells[(i, j, "a")] = [p00, p10, p01]
            cells[(i, j, "b")] = [p10, p11, p01]
    return cells


def split_into_triangles(mesh, radius_mm, length_axis, width_axis):
    min_bounds, max_bounds = mesh.bounds
    min_2d = (min_bounds[length_axis], min_bounds[width_axis])
    max_2d = (max_bounds[length_axis], max_bounds[width_axis])

    cell_vertices = _generate_triangle_cells(min_2d, max_2d, radius_mm)

    return split_into_cells(mesh, cell_vertices, length_axis, width_axis)
