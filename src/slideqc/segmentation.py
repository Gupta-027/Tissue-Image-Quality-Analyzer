"""Two simple, comparable classical tissue/background segmenters."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SegmentationConfig:
    method: str = "hsv"
    rgb_threshold: float = 235
    saturation_threshold: int = 20
    value_threshold: int = 245
    morphology_size: int = 3


def segment_tissue(rgb, config=None):
    """Return bool mask; OpenCV HSV S and V both have the range 0–255.

    Both methods get identical opening then closing with an elliptical kernel.
    Opening removes isolated pixels; closing fills small holes. Set size=0 or 1
    to disable morphology. RGB baseline uses arithmetic channel mean.
    """
    config = config or SegmentationConfig()
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("Segmentation requires an RGB image of shape (H, W, 3).")
    image = image[..., :3].astype(np.uint8)
    if config.method == "rgb":
        mask = image.mean(axis=2) < config.rgb_threshold
    elif config.method == "hsv":
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        mask = (hsv[..., 1] >= config.saturation_threshold) & (hsv[..., 2] <= config.value_threshold)
    else:
        raise ValueError("Segmentation method must be 'rgb' or 'hsv'.")
    size = config.morphology_size
    if size < 0 or (size > 1 and size % 2 == 0):
        raise ValueError("Morphology size must be 0, 1, or a positive odd integer.")
    if size > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask.astype(bool)
