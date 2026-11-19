"""Small deterministic image fixtures shared by the core tests.

The fake slide records tile requests and can simulate transparency or read errors.
It lets us test WSI behavior without downloading a real pathology image.
"""

import cv2
import numpy as np
import pytest


def _stained_texture(width=96, height=64):
    rng = np.random.default_rng(711)
    texture = rng.integers(30, 190, (height, width), dtype=np.uint8)
    return np.stack((texture, texture // 3, np.minimum(texture.astype(int) + 35, 230).astype(np.uint8)), axis=2)


class FakeSlide:
    def __init__(self, rgb, downsample=1.0, fail=False, alpha=None):
        self.rgb = rgb
        self.dimensions = (rgb.shape[1], rgb.shape[0])
        self.level_dimensions = (self.dimensions,)
        self.level_downsamples = (downsample,)
        self.slide_id = "generated"
        self.fail = fail
        self.alpha = alpha
        self.requests = []

    def thumbnail(self, max_size=1200):
        scale = min(1, max_size / max(self.dimensions))
        size = tuple(max(1, round(v * scale)) for v in self.dimensions)
        return cv2.resize(self.rgb, size, interpolation=cv2.INTER_AREA)

    def read_tile(self, x0, y0, level, width, height):
        self.requests.append((x0, y0, level, width, height))
        if self.fail:
            raise OSError("generated read failure")
        rgb = self.rgb[y0:y0 + height, x0:x0 + width]
        alpha = np.full(rgb.shape[:2], 255, dtype=np.uint8) if self.alpha is None else self.alpha[y0:y0 + height, x0:x0 + width]
        return np.dstack((rgb, alpha))


@pytest.fixture
def stained_texture():
    """Return a factory so each test chooses its image dimensions."""
    return _stained_texture


@pytest.fixture
def fake_slide():
    """Return a factory so each test chooses normal or failing slide behavior."""
    return FakeSlide
