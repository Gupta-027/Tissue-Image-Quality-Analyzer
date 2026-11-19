"""Focus scores should react to blur, not transparent padding or mask edges."""

import cv2
import numpy as np

from slideqc.focus import focus_scores


def test_focus_metrics_decrease_for_injected_blur(stained_texture):
    original = stained_texture(128, 128)
    blurred = cv2.GaussianBlur(original, (0, 0), sigmaX=2.0, sigmaY=2.0)
    sharp_scores = focus_scores(original)
    blur_scores = focus_scores(blurred)
    assert sharp_scores["eligible_pixels"] == 126 * 126
    for metric in ("laplacian", "tenengrad"):
        assert sharp_scores[metric] > 5 * blur_scores[metric] > 0


def test_padding_and_mask_boundaries_do_not_inflate_focus_scores():
    rgba = np.full((32, 32, 4), 255, np.uint8)
    rgba[..., 3] = 0
    rgba[6:26, 6:26, :3] = 100
    rgba[6:26, 6:26, 3] = 255
    scores = focus_scores(rgba)
    assert scores["eligible_pixels"] == 18 * 18
    assert scores["laplacian"] == 0
    assert scores["tenengrad"] == 0
    sparse = np.zeros((32, 32), bool)
    sparse[16, 16] = True
    assert focus_scores(rgba, sparse)["laplacian"] is None
