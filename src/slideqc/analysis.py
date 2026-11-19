"""Incremental, bounded-memory tissue screening and simulated rescan export."""

import csv
from dataclasses import dataclass, field, replace
from io import StringIO
import math
from time import perf_counter

import numpy as np

from .coordinates import iter_tiles, tissue_fraction, tissue_mask_for_tile
from .focus import focus_scores
from .segmentation import SegmentationConfig, segment_tissue


@dataclass(frozen=True)
class AnalysisConfig:
    level: int = 0
    tile_size: int = 256
    min_tissue_fraction: float = 0.2
    max_tiles: int | None = 500
    metric: str = "laplacian"
    threshold: float = 100.0
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    thumbnail_size: int = 1200


@dataclass
class AnalysisResult:
    thumbnail: np.ndarray
    mask: np.ndarray
    tiles: list[dict]
    summary: dict
    config: AnalysisConfig


def _validate(config, slide):
    if not 0 <= config.level < len(slide.level_dimensions):
        raise ValueError(f"Analysis level must be between 0 and {len(slide.level_dimensions) - 1}.")
    if config.tile_size <= 0 or config.thumbnail_size <= 0:
        raise ValueError("Tile and thumbnail sizes must be positive.")
    if not 0 <= config.min_tissue_fraction <= 1:
        raise ValueError("Minimum tissue fraction must be between 0 and 1.")
    if config.max_tiles is not None and config.max_tiles <= 0:
        raise ValueError("max_tiles must be positive, or None for a complete slide.")
    if config.metric not in ("laplacian", "tenengrad"):
        raise ValueError("Focus metric must be 'laplacian' or 'tenengrad'.")
    if not math.isfinite(config.threshold) or config.threshold < 0:
        raise ValueError("Focus threshold must be a finite, nonnegative number.")


def _summarize(tiles, dimensions, grid_tiles, runtime):
    analyzed = sum(t["status"] in ("acceptable", "rescan") for t in tiles)
    flagged = sum(t["status"] == "rescan" for t in tiles)
    visited_area = sum(t["width"] * t["height"] for t in tiles)
    return {
        "grid_tiles": grid_tiles,
        "visited_tiles": len(tiles),
        "analyzed_tissue_tiles": analyzed,
        "flagged_tissue_tiles": flagged,
        "flagged_fraction": flagged / analyzed if analyzed else 0.0,
        "failed_tiles": sum(bool(t.get("read_failed")) for t in tiles),
        "unevaluated_tissue_tiles": sum(t["status"] == "unevaluated" for t in tiles),
        "background_tiles": sum(t["status"] == "background" for t in tiles),
        "coverage_fraction": visited_area / (dimensions[0] * dimensions[1]),
        "grid_coverage_fraction": len(tiles) / grid_tiles if grid_tiles else 0.0,
        "runtime_seconds": runtime,
        "complete": len(tiles) == grid_tiles,
        "dimensions": list(dimensions),
    }


def analyze_slide(slide, config=None):
    """Analyze a row-major prefix of the grid, recording all visited backgrounds.

    The cap includes background tiles, making work and coverage predictable. Only
    thumbnail, mask, metadata rows, and one full-resolution tile stay in memory.
    """
    started = perf_counter()
    config = config or AnalysisConfig()
    _validate(config, slide)
    thumb = slide.thumbnail(config.thumbnail_size)
    mask = segment_tissue(thumb, config.segmentation)
    level_dimensions = slide.level_dimensions[config.level]
    downsample = slide.level_downsamples[config.level]
    grid_tiles = math.ceil(level_dimensions[0] / config.tile_size) * math.ceil(level_dimensions[1] / config.tile_size)
    rows = []
    for tile in iter_tiles(slide.dimensions, level_dimensions, downsample, config.level, config.tile_size):
        if config.max_tiles is not None and len(rows) >= config.max_tiles:
            break
        fraction = tissue_fraction(mask, tile, slide.dimensions)
        record = {**tile.to_dict(), "slide_id": slide.slide_id,
                  "tissue_fraction": fraction, "laplacian": None, "tenengrad": None,
                  "eligible_pixels": 0, "metric": config.metric, "threshold": config.threshold,
                  "status": "background", "reason": "Thumbnail tissue fraction below minimum.", "read_failed": False}
        if fraction <= 0 or fraction < config.min_tissue_fraction:
            rows.append(record)
            continue
        try:
            image = np.asarray(slide.read_tile(tile.x, tile.y, tile.level, tile.analysis_width, tile.analysis_height))
            if image.ndim != 3 or image.shape[:2] != (tile.analysis_height, tile.analysis_width) or image.shape[2] not in (3, 4):
                raise ValueError("Slide reader returned an unexpected tile shape.")
            eligible = tissue_mask_for_tile(mask, tile, slide.dimensions, downsample)
            if image.shape[2] == 4:
                eligible &= image[..., 3] == 255
            record.update(focus_scores(image[..., :3], eligible))
            score = record[config.metric]
            if score is None:
                record.update(status="unevaluated", reason="Too few valid tissue pixels after excluding padding and mask boundaries.")
            elif score < config.threshold:
                record.update(status="rescan", reason=f"{config.metric} score {score:.3g} is below threshold {config.threshold:.3g}.")
            else:
                record.update(status="acceptable", reason=f"{config.metric} score {score:.3g} meets threshold {config.threshold:.3g}.")
        except Exception as exc:
            record.update(status="unevaluated", reason=f"Tile read/scoring failed: {exc}", read_failed=True)
        rows.append(record)
    summary = _summarize(rows, slide.dimensions, grid_tiles, perf_counter() - started)
    summary.update(slide_id=slide.slide_id, analysis_level=config.level, downsample=downsample,
                   thumbnail_dimensions=[thumb.shape[1], thumb.shape[0]],
                   tissue_detected=bool(mask.any()), min_tissue_fraction=config.min_tissue_fraction)
    return AnalysisResult(thumb, mask, rows, summary, config)


def reclassify_result(result, metric, threshold):
    """Reclassify cached raw scores without reading the slide again."""
    if metric not in ("laplacian", "tenengrad") or not math.isfinite(threshold) or threshold < 0:
        raise ValueError("Choose a valid focus metric and a finite nonnegative threshold.")
    rows = []
    for original in result.tiles:
        row = dict(original, metric=metric, threshold=float(threshold))
        score = row[metric]
        if row["status"] in ("acceptable", "rescan") and score is not None:
            row["status"] = "rescan" if score < threshold else "acceptable"
            row["reason"] = f"{metric} score {score:.3g} {'is below' if score < threshold else 'meets'} threshold {threshold:.3g}."
        rows.append(row)
    summary = dict(result.summary)
    summary.update(_summarize(rows, summary["dimensions"], summary["grid_tiles"], summary["runtime_seconds"]))
    return AnalysisResult(result.thumbnail, result.mask, rows, summary, replace(result.config, metric=metric, threshold=threshold))


CSV_FIELDS = ["slide_id", "tile_id", "x", "y", "width", "height", "level", "analysis_width", "analysis_height",
              "tissue_fraction", "laplacian", "tenengrad", "eligible_pixels", "metric", "threshold", "status", "reason"]


def export_candidates_csv(result_or_tiles):
    """CSV of candidates only, with a header even when there are no candidates."""
    rows = result_or_tiles.tiles if isinstance(result_or_tiles, AnalysisResult) else result_or_tiles
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(row for row in rows if row["status"] == "rescan")
    return buffer.getvalue()
