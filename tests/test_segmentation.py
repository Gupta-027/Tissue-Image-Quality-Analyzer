"""Both tissue methods must produce clean boolean masks using the same cleanup."""

import numpy as np
import pytest

from slideqc.segmentation import SegmentationConfig, segment_tissue


@pytest.mark.parametrize("method", ["rgb", "hsv"])
def test_segmenters_use_same_cleanup_and_produce_boolean_masks(method):
    rgb = np.full((32, 32, 3), 255, np.uint8)
    rgb[5:25, 5:25] = [180, 70, 150]
    rgb[1, 1] = [180, 70, 150]
    mask = segment_tissue(rgb, SegmentationConfig(method=method, morphology_size=3))
    assert mask.dtype == bool
    assert mask[10, 10]
    assert not mask[1, 1]
    assert not mask[0, 0]
