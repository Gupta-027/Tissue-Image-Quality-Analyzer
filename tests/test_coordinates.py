"""Coordinate checks: thumbnail rounding, fractional downsamples, and tile edges."""

import numpy as np
import pytest

from slideqc.coordinates import (
    TileFootprint,
    iter_tiles,
    level0_to_thumbnail,
    thumbnail_bounds,
    thumbnail_to_level0,
    tissue_fraction,
    tissue_mask_for_tile,
)


def test_thumbnail_coordinate_roundtrip_uses_actual_axis_dimensions():
    dims, thumb = (10003, 7061), (1200, 847)
    for x, y in [(0, 0), (10003, 7061), (7123.125, 3158.75)]:
        mapped = level0_to_thumbnail(x, y, dims, thumb)
        assert thumbnail_to_level0(*mapped, dims, thumb) == pytest.approx((x, y))
    assert level0_to_thumbnail(*dims, dims, thumb) == thumb
    tile = TileFootprint("edge", 9900, 7000, 103, 61, 103, 61, 0, 0, 0)
    assert thumbnail_bounds(tile, dims, thumb)[2:] == thumb


def test_noninteger_downsample_tiles_partition_actual_level0_rectangle():
    dims, level_dims, ds = (1003, 707), (251, 177), 3.998
    tiles = list(iter_tiles(dims, level_dims, ds, level=1, tile_size=64))
    assert len(tiles) == 12
    assert sum(t.width * t.height for t in tiles) == dims[0] * dims[1]
    for row in range(3):
        same_row = [t for t in tiles if t.row == row]
        assert same_row[0].x == 0
        assert same_row[-1].x + same_row[-1].width == dims[0]
        assert all(a.x + a.width == b.x for a, b in zip(same_row, same_row[1:]))
    assert tiles[-1].analysis_width == 59
    assert tiles[-1].analysis_height == 49
    assert tiles[-1].y + tiles[-1].height == dims[1]


def test_fractional_mask_footprint_is_area_weighted():
    mask = np.array([[False, True]], dtype=bool)
    tile = TileFootprint("a", 25, 0, 50, 10, 50, 10, 0, 0, 0)
    assert tissue_fraction(mask, tile, (100, 10)) == pytest.approx(0.5)
    pixels = tissue_mask_for_tile(mask, tile, (100, 10), 1.0)
    assert pixels.shape == (10, 50)
    assert not pixels[:, :25].any()
    assert pixels[:, 25:].all()
