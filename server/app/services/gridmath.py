"""Grid/parcel overlap maths shared by the ET and ERA5 services.

A 20 ha parcel can straddle four 0.25° cells, so every grid lookup weights the
cells by the actual overlapping area instead of sampling one point.
"""

from __future__ import annotations

import numpy as np

from . import geo


def clip(poly: list[tuple[float, float]], edge: int, bound: float) -> list[tuple[float, float]]:
    """Sutherland–Hodgman clip against one axis-aligned edge (0=W,1=E,2=S,3=N)."""
    if not poly:
        return []
    inside = {
        0: lambda p: p[0] >= bound,
        1: lambda p: p[0] <= bound,
        2: lambda p: p[1] >= bound,
        3: lambda p: p[1] <= bound,
    }[edge]
    out: list[tuple[float, float]] = []
    count = len(poly)
    for i in range(count):
        current = poly[i]
        previous = poly[i - 1]
        current_in, previous_in = inside(current), inside(previous)
        if current_in != previous_in:
            if edge in (0, 1):
                t = (bound - previous[0]) / (current[0] - previous[0])
                out.append((bound, previous[1] + t * (current[1] - previous[1])))
            else:
                t = (bound - previous[1]) / (current[1] - previous[1])
                out.append((previous[0] + t * (current[0] - previous[0]), bound))
        if current_in:
            out.append(current)
    return out


def planar_area(poly: list[tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    total = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def overlap_weights(
    ring: geo.Ring, lon: np.ndarray, lat: np.ndarray
) -> list[tuple[int, int, float]]:
    """Fractional overlap of a parcel with each grid cell: ``[(row, col, weight)]``.

    ``lat`` must be descending (north first), which is how both ERA5 and
    ETMonitor files are laid out.
    """
    if len(ring) < 3 or len(lon) < 2 or len(lat) < 2:
        return []
    cell = float(lon[1] - lon[0])
    half = cell / 2.0
    min_lon, min_lat, max_lon, max_lat = geo.bbox_of_points(ring)

    def col_index(value: float) -> int:
        return int(np.clip(np.abs(lon - value).argmin(), 0, len(lon) - 1))

    def row_index(value: float) -> int:
        return int(np.clip(np.abs(lat - value).argmin(), 0, len(lat) - 1))

    c0, c1 = sorted((col_index(min_lon), col_index(max_lon)))
    r0, r1 = sorted((row_index(min_lat), row_index(max_lat)))

    poly = [(float(x), float(y)) for x, y in ring]
    total_poly = planar_area(poly)
    if total_poly <= 0:
        return []

    weights: list[tuple[int, int, float]] = []
    for row in range(r0, r1 + 1):
        for col in range(c0, c1 + 1):
            clon, clat = float(lon[col]), float(lat[row])
            clipped = clip(poly, 0, clon - half)
            clipped = clip(clipped, 1, clon + half)
            clipped = clip(clipped, 2, clat - half)
            clipped = clip(clipped, 3, clat + half)
            if len(clipped) < 3:
                continue
            share = planar_area(clipped) / total_poly
            if share > 1e-9:
                weights.append((row, col, share))
    total = sum(w for _, _, w in weights)
    if total <= 0:
        return []
    return [(r, c, w / total) for r, c, w in weights]


def weighted_value(
    field: np.ndarray, weights: list[tuple[int, int, float]], min_cover: float = 0.2
) -> float | None:
    """Area-weighted mean of one 2-D slice, ignoring missing cells."""
    if not weights:
        return None
    accumulator, cover = 0.0, 0.0
    for row, col, weight in weights:
        value = float(field[row, col])
        if np.isfinite(value):
            accumulator += value * weight
            cover += weight
    if cover < min_cover:
        return None
    return accumulator / cover
