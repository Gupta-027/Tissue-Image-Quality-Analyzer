"""Raw edge-energy metrics: lower scores suggest less high-frequency texture."""

import cv2
import numpy as np


def focus_scores(rgb, eligible_mask=None):
    """Score only pixels whose full 3×3 derivative support is eligible.

    Gray is cv2.COLOR_RGB2GRAY on uint8 (0–255), then converted to float64.
    Laplacian = population variance of cv2.Laplacian(gray, CV_64F, ksize=3).
    Tenengrad = mean(Sobel_x**2 + Sobel_y**2), 3×3 kernels, scale=1.
    The eligibility mask is eroded by one pixel including the image perimeter.
    No post-hoc normalization, gradient cutoff, or score standardization is used.
    """
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("Focus scoring requires an RGB or RGBA image.")
    eligible = np.ones(image.shape[:2], dtype=bool) if eligible_mask is None else np.asarray(eligible_mask, dtype=bool)
    if eligible.shape != image.shape[:2]:
        raise ValueError("Focus eligibility mask must match the image dimensions.")
    if image.shape[2] == 4:
        eligible = eligible & (image[..., 3] == 255)
    support = cv2.erode(eligible.astype(np.uint8), np.ones((3, 3), np.uint8),
                        borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    count = int(support.sum())
    if count < 2:
        return {"laplacian": None, "tenengrad": None, "eligible_pixels": count}
    gray = cv2.cvtColor(image[..., :3].astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float64)
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return {"laplacian": float(np.var(lap[support])),
            "tenengrad": float(np.mean((gx * gx + gy * gy)[support])),
            "eligible_pixels": count}
