"""Coordinate conversions; all exported footprints are level-0 pixel rectangles.

Rectangles use half-open bounds [x, x + width), like NumPy slices. OpenSlide's
reported downsample determines read origins. Actual thumbnail dimensions determine
thumbnail conversion independently on each axis, avoiding resize-rounding drift.
"""

from dataclasses import asdict, dataclass
import math
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class TileFootprint:
    tile_id: str
    x: int
    y: int
    width: int
    height: int
    analysis_width: int
    analysis_height: int
    level: int
    row: int
    col: int

    def to_dict(self) -> dict:
        return asdict(self)


def level0_to_thumbnail(x, y, dimensions, thumbnail_dimensions):
    """Return floating thumbnail coordinates (width, height tuple convention)."""
    return x * thumbnail_dimensions[0] / dimensions[0], y * thumbnail_dimensions[1] / dimensions[1]


def thumbnail_to_level0(x, y, dimensions, thumbnail_dimensions):
    """Invert the actual per-axis thumbnail transform; do not assume one scale."""
    return x * dimensions[0] / thumbnail_dimensions[0], y * dimensions[1] / thumbnail_dimensions[1]


def thumbnail_bounds(footprint, dimensions, thumbnail_dimensions):
    """Enclosing thumbnail pixel bounds, clipped to the thumbnail."""
    get = footprint.get if isinstance(footprint, dict) else lambda key: getattr(footprint, key)
    x0, y0 = level0_to_thumbnail(get("x"), get("y"), dimensions, thumbnail_dimensions)
    x1, y1 = level0_to_thumbnail(get("x") + get("width"), get("y") + get("height"), dimensions, thumbnail_dimensions)
    return (max(0, math.floor(x0)), max(0, math.floor(y0)),
            min(thumbnail_dimensions[0], math.ceil(x1)), min(thumbnail_dimensions[1], math.ceil(y1)))


def iter_tiles(dimensions, level_dimensions, downsample, level=0, tile_size=256) -> Iterator[TileFootprint]:
    """Yield row-major tiles, including smaller edge reads with no artificial pad.

    level_dimensions is the (width, height) of the selected analysis level. A
    noninteger downsample is rounded down only at canonical read origins. Adjacent
    footprints share boundaries; the last ends at the actual level-0 edge.
    """
    if tile_size <= 0 or downsample <= 0 or any(v <= 0 for v in (*dimensions, *level_dimensions)):
        raise ValueError("Dimensions, downsample and tile_size must be positive.")
    width, height = level_dimensions
    for row, ay in enumerate(range(0, height, tile_size)):
        ah = min(tile_size, height - ay)
        y0 = min(dimensions[1], math.floor(ay * downsample))
        y1 = dimensions[1] if ay + ah == height else min(dimensions[1], math.floor((ay + ah) * downsample))
        for col, ax in enumerate(range(0, width, tile_size)):
            aw = min(tile_size, width - ax)
            x0 = min(dimensions[0], math.floor(ax * downsample))
            x1 = dimensions[0] if ax + aw == width else min(dimensions[0], math.floor((ax + aw) * downsample))
            if x1 > x0 and y1 > y0:
                yield TileFootprint(f"r{row:05d}_c{col:05d}", x0, y0, x1 - x0, y1 - y0, aw, ah, level, row, col)


def tissue_fraction(mask, footprint, dimensions):
    """Area-weight a binary thumbnail mask over a fractional tile rectangle.

    Weighting boundary pixels avoids making tiny full-resolution tiles depend on
    whichever enclosing thumbnail rectangle happened to be rounded outwards.
    """
    th, tw = mask.shape
    x0, y0 = level0_to_thumbnail(footprint.x, footprint.y, dimensions, (tw, th))
    x1, y1 = level0_to_thumbnail(footprint.x + footprint.width, footprint.y + footprint.height, dimensions, (tw, th))
    ix0, iy0, ix1, iy1 = thumbnail_bounds(footprint, dimensions, (tw, th))
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    wx = np.maximum(0, np.minimum(np.arange(ix0, ix1) + 1, x1) - np.maximum(np.arange(ix0, ix1), x0))
    wy = np.maximum(0, np.minimum(np.arange(iy0, iy1) + 1, y1) - np.maximum(np.arange(iy0, iy1), y0))
    area = (x1 - x0) * (y1 - y0)
    return float(wy @ mask[iy0:iy1, ix0:ix1].astype(float) @ wx / area) if area > 0 else 0.0


def tissue_mask_for_tile(mask, footprint, dimensions, downsample):
    """Nearest-neighbor tissue labels at the actual OpenSlide read pixel centers."""
    th, tw = mask.shape
    xs0 = footprint.x + (np.arange(footprint.analysis_width) + 0.5) * downsample
    ys0 = footprint.y + (np.arange(footprint.analysis_height) + 0.5) * downsample
    xs = np.clip(np.floor(xs0 * tw / dimensions[0]).astype(int), 0, tw - 1)
    ys = np.clip(np.floor(ys0 * th / dimensions[1]).astype(int), 0, th - 1)
    result = mask[np.ix_(ys, xs)].copy()
    result &= (ys0[:, None] < dimensions[1]) & (xs0[None, :] < dimensions[0])
    return result
