"""Use a benchmark threshold only in its documented processing domain."""
from dataclasses import asdict
import math


def compatible_thresholds(payload, config, downsample, mpp_x=None, mpp_y=None):
    if not payload.get("usable_for_real_slides", False):
        return False
    for axis, actual in (("x", mpp_x), ("y", mpp_y)):
        expected = payload.get(f"calibration_mpp_{axis}")
        if expected is not None:
            try:
                if not math.isclose(float(expected), float(actual), rel_tol=.02):
                    return False
            except (TypeError, ValueError):
                return False
    return (
        payload.get("level") == config.level
        and payload.get("tile_size") == config.tile_size
        and math.isclose(payload.get("calibration_downsample", -1), downsample, rel_tol=1e-6)
        and payload.get("segmentation") == asdict(config.segmentation)
        and payload.get("thumbnail_size", 1200) == config.thumbnail_size
        and math.isclose(payload.get("min_tissue_fraction", .2), config.min_tissue_fraction)
        and all(isinstance(payload.get("metrics", {}).get(m), (int, float))
                and math.isfinite(payload["metrics"][m]) and payload["metrics"][m] >= 0
                for m in ("laplacian", "tenengrad"))
    )
