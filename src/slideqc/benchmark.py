"""Reproducible injected-blur experiments; originals are never ground-truth sharp labels."""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .coordinates import TileFootprint, iter_tiles, tissue_fraction, tissue_mask_for_tile
from .focus import focus_scores
from .segmentation import SegmentationConfig, segment_tissue

METRICS = ("laplacian", "tenengrad")
SIGMAS = (0.0, 1.0, 2.0, 4.0)


@dataclass
class Crop:
    slide_id: str
    source_id: str
    split: str
    x: int
    y: int
    level: int
    rgb: np.ndarray
    mask: np.ndarray
    downsample: float = 1.0
    reviewed: bool = False
    review_note: str = "Unreviewed original; sharpness is not established."

    @property
    def group_id(self) -> str:
        return f"{self.source_id}:{self.x}:{self.y}:{self.level}"


def source_identity(path: str | Path) -> str:
    """Known small-region/export variants must not masquerade as independent slides."""
    name = Path(path).stem
    if name.startswith("CMU-1"):
        return "CMU-1"
    if name.startswith("CMU-2"):
        return "CMU-2"
    if name.startswith("CMU-3"):
        return "CMU-3"
    return name


def roc_auc(labels: np.ndarray | list, risk: np.ndarray | list) -> float | None:
    """Mann-Whitney AUC with average ranks for ties; higher risk means blur."""
    labels = np.asarray(labels, dtype=bool)
    risk = np.asarray(risk, dtype=float)
    positive_count = int(labels.sum())
    negative_count = len(labels) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None
    order = np.argsort(risk, kind="stable")
    ranks = np.empty(len(risk), dtype=float)
    start = 0
    while start < len(order):
        stop = start + 1
        while stop < len(order) and risk[order[stop]] == risk[order[start]]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2
        start = stop
    rank_sum = float(ranks[labels].sum())
    return (rank_sum - positive_count * (positive_count + 1) / 2) / (positive_count * negative_count)


def choose_threshold(scores: list[float], labels: list[bool], max_fpr: float = .10) -> float:
    """Maximize balanced accuracy on calibration only, subject to original FPR <=10%."""
    values = np.asarray(scores, dtype=float)
    blurred = np.asarray(labels, dtype=bool)
    if not np.isfinite(values).all() or not blurred.any() or blurred.all():
        raise ValueError("Threshold selection needs finite calibration scores for originals and blur.")
    unique = np.unique(values)
    candidates = np.r_[max(0.0, np.nextafter(unique[0], -np.inf)),
                       unique[:-1] / 2 + unique[1:] / 2,
                       np.nextafter(unique[-1], np.inf)]
    best = None
    for threshold in candidates:
        flagged = values < threshold
        sensitivity = float(flagged[blurred].mean())
        fpr = float(flagged[~blurred].mean())
        if fpr > max_fpr + 1e-12:
            continue
        key = ((sensitivity + 1 - fpr) / 2, sensitivity, -fpr, -float(threshold))
        if best is None or key > best[0]:
            best = (key, float(threshold))
    return best[1]


def summarize_metric(records: list[dict], metric: str, threshold: float) -> dict:
    selected = [r for r in records if r[metric] is not None]
    originals = [r for r in selected if r["sigma"] == 0]
    blurred = [r for r in selected if r["sigma"] > 0]
    by_sigma = []
    for sigma in SIGMAS:
        rows = [r for r in selected if r["sigma"] == sigma]
        by_sigma.append({"sigma": sigma, "variant_count": len(rows),
                         "flagged_count": sum(r[metric] < threshold for r in rows),
                         "flagged_fraction": sum(r[metric] < threshold for r in rows) / len(rows) if rows else None})
    return {"original_tile_count": len(originals), "blurred_variant_count": len(blurred),
            "sensitivity_to_injected_blur": sum(r[metric] < threshold for r in blurred) / len(blurred) if blurred else None,
            "false_positive_rate_on_originals": sum(r[metric] < threshold for r in originals) / len(originals) if originals else None,
            "roc_auc": roc_auc([r["sigma"] > 0 for r in selected], [-r[metric] for r in selected]),
            "by_sigma": by_sigma}


def score_crops(crops: list[Crop]) -> list[dict]:
    records = []
    for crop in crops:
        for sigma in SIGMAS:
            # OpenCV chooses a kernel from sigma; BORDER_REFLECT_101 is explicit.
            variant = crop.rgb if sigma == 0 else cv2.GaussianBlur(
                crop.rgb, (0, 0), sigmaX=sigma, sigmaY=sigma, borderType=cv2.BORDER_REFLECT_101)
            scores = focus_scores(variant, crop.mask)
            records.append({"slide_id": crop.slide_id, "source_id": crop.source_id,
                            "group_id": crop.group_id, "split": crop.split,
                            "x": crop.x, "y": crop.y, "level": crop.level,
                            "analysis_width": crop.rgb.shape[1], "analysis_height": crop.rgb.shape[0],
                            "downsample": crop.downsample, "sigma": sigma,
                            "reviewed_original": crop.reviewed, "review_note": crop.review_note,
                            **{key: scores[key] for key in (*METRICS, "eligible_pixels")}})
    return records


def evaluate_records(records: list[dict]) -> dict:
    calibration = [r for r in records if r["split"] == "calibration"]
    evaluation = [r for r in records if r["split"] == "evaluation"]
    if not calibration or not evaluation:
        raise ValueError("Both calibration and evaluation need eligible original crops. Increase --max-tiles or review tissue regions.")
    calibration_groups = {r["group_id"] for r in calibration}
    evaluation_groups = {r["group_id"] for r in evaluation}
    if calibration_groups & evaluation_groups:
        raise ValueError("A source crop appears in both splits; all blur variants must remain together.")
    metrics = {}
    for metric in METRICS:
        valid = [r for r in calibration if r[metric] is not None]
        threshold = choose_threshold([r[metric] for r in valid], [r["sigma"] > 0 for r in valid])
        metrics[metric] = {"threshold": threshold,
                           "calibration": summarize_metric(calibration, metric, threshold),
                           "evaluation": summarize_metric(evaluation, metric, threshold)}
    return metrics


def collect_slide_crops(path: str | Path, split: str, max_tiles: int, level: int,
                        tile_size: int, seed: int, segmentation: SegmentationConfig,
                        review_manifest: dict | None = None, spatial_half: str | None = None) -> tuple[list[Crop], dict, np.ndarray]:
    from .slide_io import Slide
    rng = np.random.default_rng(seed)
    failures = []
    with Slide(path) as slide:
        if not 0 <= level < len(slide.level_dimensions):
            raise ValueError(f"Slide {slide.slide_id} has {len(slide.level_dimensions)} levels; requested {level}.")
        thumbnail = slide.thumbnail(max_size=1200)
        mask = segment_tissue(thumbnail, segmentation)
        dimensions = tuple(slide.dimensions)
        ds = float(slide.level_downsamples[level])
        lw, lh = slide.level_dimensions[level]
        reviewed_by_position = {}
        if review_manifest is not None:
            rows = [r for r in review_manifest.get("tiles", []) if r.get("slide_id") == slide.slide_id
                    and r.get("appears_sharp") is True and int(r.get("level", level)) == level]
            positions = [(int(r["x"]), int(r["y"])) for r in rows]
            if len(set(positions)) != len(positions):
                raise ValueError(f"Review manifest repeats a source crop for {slide.slide_id}.")
            if any(int(r.get("analysis_width", tile_size)) != tile_size or
                   int(r.get("analysis_height", tile_size)) != tile_size for r in rows):
                raise ValueError("Reviewed crop dimensions must match --tile-size for comparable calibration.")
            candidates = [(int(r["x"]), int(r["y"]), int(r.get("analysis_width", tile_size)),
                           int(r.get("analysis_height", tile_size))) for r in rows]
            reviewed_by_position = {(int(r["x"]), int(r["y"])): r for r in rows}
            candidates = candidates[:max_tiles]
            eligible_grid_count = len(candidates)
        else:
            # Reservoir sample across the entire tissue grid, not the first slide rows.
            # Only max_tiles footprints and one decoded tile are retained in memory.
            candidates = []
            eligible_grid_count = 0
            for tile in iter_tiles(dimensions, (lw, lh), ds, level, tile_size):
                if spatial_half == "left" and tile.x + tile.width > dimensions[0] // 2:
                    continue
                if spatial_half == "right" and tile.x < dimensions[0] // 2:
                    continue
                # Full crops keep injected blur comparable; partial edges excluded here only.
                if tile.analysis_width < tile_size or tile.analysis_height < tile_size:
                    continue
                if tissue_fraction(mask, tile, dimensions) < .5:
                    continue
                eligible_grid_count += 1
                footprint = (tile.x, tile.y, tile.analysis_width, tile.analysis_height)
                if len(candidates) < max_tiles:
                    candidates.append(footprint)
                else:
                    replacement = int(rng.integers(0, eligible_grid_count))
                    if replacement < max_tiles:
                        candidates[replacement] = footprint
        crops = []
        for x, y, width, height in candidates:
            if x < 0 or y < 0 or width < 3 or height < 3 or x + width * ds > dimensions[0] + 1 or y + height * ds > dimensions[1] + 1:
                raise ValueError(f"Reviewed crop ({x},{y},{width},{height}) is outside slide bounds.")
            if spatial_half == "left" and x + width * ds > dimensions[0] // 2:
                continue
            if spatial_half == "right" and x < dimensions[0] // 2:
                continue
            try:
                rgba = np.asarray(slide.read_tile(x, y, level, width, height))
                rgb = np.ascontiguousarray(rgba[..., :3])
                valid = rgba[..., 3] == 255 if rgba.shape[2] == 4 else np.ones(rgb.shape[:2], bool)
                if not valid.all():
                    failures.append({"x": x, "y": y, "reason": "Benchmark excludes crops containing transparent slide padding before injecting blur."})
                    continue
                footprint = TileFootprint("benchmark", x, y, min(dimensions[0] - x, round(width * ds)),
                                          min(dimensions[1] - y, round(height * ds)), width, height, level, 0, 0)
                eligible = tissue_mask_for_tile(mask, footprint, dimensions, ds) & valid
                if int(eligible.sum()) < 64 or focus_scores(rgb, eligible)["laplacian"] is None:
                    failures.append({"x": x, "y": y, "reason": "Fewer than 64 eligible tissue pixels or no derivative support."})
                    continue
                review = reviewed_by_position.get((x, y))
                crops.append(Crop(slide.slide_id, source_identity(path), split, x, y, level,
                                  rgb, eligible, ds, review is not None,
                                  review.get("note", "Visually reviewed; no independent scanner focus label.") if review else
                                  "Unreviewed original; sharpness is not established."))
            except Exception as exc:
                failures.append({"x": x, "y": y, "reason": str(exc)})
        metadata = {"path": str(Path(path)), "slide_id": slide.slide_id, "source_id": source_identity(path),
                    "dimensions": list(dimensions), "level": level, "downsample": ds,
                    "objective_power": slide.properties.get("openslide.objective-power"),
                    "mpp_x": slide.properties.get("openslide.mpp-x"),
                    "mpp_y": slide.properties.get("openslide.mpp-y"),
                    "split": split, "spatial_half": spatial_half,
                    "eligible_grid_count": eligible_grid_count, "selected_originals": len(crops),
                    "failed_or_ineligible_reads": failures}
        return crops, metadata, thumbnail


def synthetic_crops(seed: int = 42, count: int = 16, tile_size: int = 256) -> list[Crop]:
    """Generated stained textures exercise the experiment; these are not pathology data."""
    rng = np.random.default_rng(seed)
    crops = []
    for split in ("calibration", "evaluation"):
        for index in range(count):
            rgb = np.full((tile_size, tile_size, 3), (235, 188, 214), np.uint8)
            noise = rng.normal(0, 5, rgb.shape[:2])
            rgb = np.clip(rgb.astype(float) + noise[..., None], 0, 255).astype(np.uint8)
            for _ in range(100):
                x, y = rng.integers(0, tile_size, size=2)
                radius = int(rng.integers(2, 8))
                color = tuple(int(v) for v in ((90, 40, 115) + rng.integers(-15, 15, size=3)))
                cv2.circle(rgb, (int(x), int(y)), radius, color, -1)
            crops.append(Crop(f"synthetic-{split}", f"synthetic-{split}", split,
                              index * tile_size, 0, 0, rgb, np.ones(rgb.shape[:2], bool),
                              reviewed=False, review_note="Generated texture, not a real slide or human sharpness label."))
    return crops


def save_contact_sheet(crops: list[Crop], path: Path, max_crops: int = 64) -> None:
    selected = crops[:max_crops]
    columns, cell_width, cell_height = 4, 270, 300
    rows = max(1, math.ceil(len(selected) / columns))
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, crop in enumerate(selected):
        x, y = (index % columns) * cell_width, (index // columns) * cell_height
        image = Image.fromarray(crop.rgb)
        image.thumbnail((256, 256))
        sheet.paste(image, (x + 6, y + 4))
        draw.text((x + 6, y + 262), f"{crop.slide_id}\n({crop.x}, {crop.y}) L{crop.level} {crop.split}", fill="black")
    sheet.save(path)


def save_blur_comparison(crop: Crop, path: Path) -> None:
    cell_width = 270
    sheet = Image.new("RGB", (cell_width * len(SIGMAS), 300), "white")
    draw = ImageDraw.Draw(sheet)
    for index, sigma in enumerate(SIGMAS):
        image = crop.rgb if sigma == 0 else cv2.GaussianBlur(crop.rgb, (0, 0), sigma, borderType=cv2.BORDER_REFLECT_101)
        display = Image.fromarray(image)
        display.thumbnail((256, 256))
        sheet.paste(display, (index * cell_width + 6, 4))
        label = "Original (review status in report)" if sigma == 0 else f"Injected Gaussian blur sigma={sigma:g}px"
        draw.text((index * cell_width + 6, 264), label, fill="black")
    sheet.save(path)


def low_texture_example(thresholds: dict[str, float], path: Path) -> dict:
    # A smooth, unblurred stain-colored area can have tiny edge energy while in focus.
    xx, yy = np.meshgrid(np.arange(256), np.arange(256))
    gray = 195 + 2 * np.sin(xx / 80) + 2 * np.sin(yy / 60)
    rgb = np.stack((gray + 20, gray - 25, gray + 10), axis=2).astype(np.uint8)
    scores = focus_scores(rgb, np.ones((256, 256), dtype=bool))
    Image.fromarray(rgb).save(path)
    return {"type": "generated_unblurred_low_texture_example", "measured_benchmark": False,
            "explanation": "No blur was applied; low texture alone yields low derivative energy. This illustrates a possible false alarm, not a measured clinical failure.",
            "scores": {metric: scores[metric] for metric in METRICS},
            "flagged": {metric: scores[metric] < thresholds[metric] for metric in METRICS}}


def save_segmentation_comparison(thumbnails: list[tuple[str, np.ndarray]], output: Path,
                                 config: SegmentationConfig) -> None:
    rows = []
    for slide_id, thumbnail in thumbnails:
        original = Image.fromarray(thumbnail)
        original.thumbnail((400, 400))
        rgb = np.asarray(thumbnail)
        panel = Image.new("RGB", (1200, original.height + 42), "white")
        draw = ImageDraw.Draw(panel)
        for index, method in enumerate(("original", "rgb", "hsv")):
            image = rgb.copy()
            if method != "original":
                options = asdict(config)
                options["method"] = method
                mask = segment_tissue(rgb, SegmentationConfig(**options))
                image[mask] = (.5 * image[mask] + .5 * np.array([0, 170, 150])).astype(np.uint8)
            display = Image.fromarray(image)
            display.thumbnail((400, 400))
            panel.paste(display, (400 * index, 30))
            draw.text((400 * index + 5, 6), f"{slide_id}: {method}", fill="black")
        rows.append(panel)
    if rows:
        canvas = Image.new("RGB", (1200, sum(row.height for row in rows)), "white")
        offset = 0
        for row in rows:
            canvas.paste(row, (0, offset))
            offset += row.height
        canvas.save(output)


def run_benchmark(*, calibration: str | None, evaluation: str | None, output: str | Path,
                  max_tiles: int = 24, level: int = 0, tile_size: int = 256, seed: int = 42,
                  synthetic: bool = False, review_manifest: str | None = None) -> dict:
    if max_tiles < 2 or tile_size < 16 or level < 0:
        raise ValueError("Use --max-tiles >=2, --tile-size >=16 and --level >=0.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    segmentation = SegmentationConfig()
    thumbnails = []
    sources = []
    review = json.loads(Path(review_manifest).read_text(encoding="utf-8")) if review_manifest else None
    if synthetic:
        crops = synthetic_crops(seed, max_tiles, tile_size)
        mode = "generated_fixture_experiment"
        split_description = "Separate generated source textures for calibration and evaluation; no real slides."
    else:
        if not calibration:
            raise ValueError("Provide --calibration SLIDE.svs or explicitly use --synthetic.")
        distinct = bool(evaluation and source_identity(calibration) != source_identity(evaluation))
        if distinct:
            cal_crops, source, thumb = collect_slide_crops(calibration, "calibration", max_tiles, level, tile_size, seed, segmentation, review)
            sources.append(source)
            thumbnails.append((source["slide_id"], thumb))
            eval_crops, source, thumb = collect_slide_crops(evaluation, "evaluation", max_tiles, level, tile_size, seed + 1, segmentation, review)
            sources.append(source)
            thumbnails.append((source["slide_id"], thumb))
            mode = "held_out_slide_experiment"
            split_description = "Calibration and evaluation are distinct source slides; all variants of an original remain in its split."
        else:
            # Reuse the calibration image itself when the requested evaluation is an export
            # of that same source; physical offsets between exports are not assumed known.
            cal_crops, source, thumb = collect_slide_crops(calibration, "calibration", max_tiles, level, tile_size, seed, segmentation, review, "left")
            sources.append(source)
            thumbnails.append((source["slide_id"], thumb))
            eval_crops, source, _ = collect_slide_crops(calibration, "evaluation", max_tiles, level, tile_size, seed + 1, segmentation, review, "right")
            sources.append(source)
            mode = "within_slide_spatial_experiment"
            split_description = "Calibration uses left-half source tiles; evaluation uses right-half source tiles. Crops crossing the midpoint are excluded. Same-source exports are not held-out slides."
        crops = cal_crops + eval_crops
    if not crops:
        raise ValueError("No eligible tissue crops; inspect segmentation or supply a review manifest.")
    records = score_crops(crops)
    metrics = evaluate_records(records)
    thresholds = {metric: metrics[metric]["threshold"] for metric in METRICS}
    failure = low_texture_example(thresholds, output / "low_texture_failure.png")
    measured_failure_examples = []
    for crop in crops:
        if crop.split != "evaluation" or not crop.reviewed:
            continue
        row = next(r for r in records if r["group_id"] == crop.group_id and r["sigma"] == 0)
        flagged_metrics = [metric for metric in METRICS if row[metric] is not None and row[metric] < thresholds[metric]]
        if flagged_metrics:
            Image.fromarray(crop.rgb).save(output / "reviewed_original_flagged.png")
            measured_failure_examples.append({"slide_id": crop.slide_id, "x": crop.x, "y": crop.y,
                                              "level": crop.level, "analysis_width": crop.rgb.shape[1],
                                              "analysis_height": crop.rgb.shape[0], "sigma": 0,
                                              "scores": {metric: row[metric] for metric in METRICS},
                                              "flagged_metrics": flagged_metrics,
                                              "image": "reviewed_original_flagged.png", "review_note": crop.review_note,
                                              "interpretation": "Reviewed original flagged without injected blur: possible false alarm from tissue texture or cross-slide sampling differences. No scanner focus truth establishes its cause."})
            break
    save_contact_sheet(crops, output / "originals_contact_sheet.png")
    save_blur_comparison(next((c for c in crops if c.split == "evaluation"), crops[0]), output / "blur_comparison.png")
    save_segmentation_comparison(thumbnails, output / "segmentation_comparison.png", segmentation)
    review_candidates = {"reviewer": "REPLACE with reviewer and review procedure; set appears_sharp only after visual inspection.",
                         "tiles": [{"slide_id": c.slide_id, "x": c.x, "y": c.y, "level": c.level,
                                    "analysis_width": c.rgb.shape[1], "analysis_height": c.rgb.shape[0],
                                    "appears_sharp": False, "note": "Pending visual review; inspect originals_contact_sheet.png and full-size crop."} for c in crops]}
    (output / "review_candidates.json").write_text(json.dumps(review_candidates, indent=2), encoding="utf-8")
    with (output / "records.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    reviewed = all(c.reviewed for c in crops)
    report = {"schema_version": 1, "mode": mode, "seed": seed,
              "split_description": split_description, "source_slides": sources,
              "splits": {split: {"original_tile_count": sum(c.split == split for c in crops),
                                 "group_ids": [c.group_id for c in crops if c.split == split]} for split in ("calibration", "evaluation")},
              "parameters": {"level": level, "tile_size": tile_size, "max_tiles_per_split": max_tiles,
                             "sigmas_analysis_pixels": list(SIGMAS), "border_mode": "BORDER_REFLECT_101",
                             "gaussian_kernel": "OpenCV automatic (0,0) from sigma", "segmentation": asdict(segmentation),
                             "minimum_thumbnail_tissue_fraction": .5,
                             "threshold_selection": "Maximum calibration balanced accuracy subject to original FPR <= 0.10; score < threshold is flagged."},
              "original_review": {"all_visually_reviewed": reviewed, "manifest": review_manifest,
                                  "reviewer": review.get("reviewer") if review else None,
                                  "procedure": review.get("procedure") if review else None,
                                  "status": "Visually selected reference originals; no scanner focus truth." if reviewed else "Unreviewed originals; FPR is a proxy, not specificity against confirmed sharp tissue."},
              "metrics": metrics, "failure_example": failure, "measured_failure_examples": measured_failure_examples,
              "segmentation_evaluation": {"status": "pending", "reason": "No human masks supplied to this command. Run slideqc.evaluation with an annotation manifest."},
              "limits": ["Gaussian blur approximates only one aspect of scanner defocus.",
                         "Reference originals have no independent scanner focus labels; visual review is not a clinical annotation.",
                         "Thresholds depend on analysis level/downsample, pixel resolution, stain, tissue texture, and mask settings.",
                         "Physical sampling is not normalized between slides; source metadata records objective power and microns per pixel. Different MPP can contribute to transfer failures.",
                         "Variants from one original are correlated; variant counts are not independent patient samples.",
                         "Small convenience sample supports an engineering demonstration, not clinical validation."]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    compatibility = {"schema_version": 1, "mode": mode,
                     "usable_for_real_slides": not synthetic,
                     "metrics": thresholds, "level": level, "tile_size": tile_size,
                     "thumbnail_size": 1200, "minimum_calibration_tissue_fraction": .5,
                     "segmentation": asdict(segmentation),
                     "calibration_slide_id": sources[0]["slide_id"] if sources else "synthetic-calibration",
                     "calibration_downsample": sources[0]["downsample"] if sources else 1.0,
                     "calibration_mpp_x": sources[0]["mpp_x"] if sources else None,
                     "calibration_mpp_y": sources[0]["mpp_y"] if sources else None,
                     "calibration_objective_power": sources[0]["objective_power"] if sources else None,
                     "report": str(output / "report.json")}
    (output / "thresholds.json").write_text(json.dumps(compatibility, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration", help="Calibration .svs slide; thresholds are selected here only.")
    parser.add_argument("--evaluation", help="A distinct source slide; same-source variants trigger within-slide split.")
    parser.add_argument("--output", default="outputs/benchmark")
    parser.add_argument("--max-tiles", type=int, default=24, help="Maximum original crops per split, sampled across tissue.")
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument("--tile-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--synthetic", action="store_true", help="Run generated fixtures only, explicitly separate from real-slide measurements.")
    parser.add_argument("--review-manifest", help="JSON listing visually reviewed original tile coordinates; only approved rows are included.")
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(**vars(args))
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        parser.exit(2, f"Benchmark failed: {exc}\n")
    print(f"Mode: {report['mode']}")
    print("metric       threshold       blur sensitivity   original FPR   ROC AUC   originals")
    for metric, result in report["metrics"].items():
        stats = result["evaluation"]
        print(f"{metric:12} {result['threshold']:12.4f} {stats['sensitivity_to_injected_blur']:16.3f} "
              f"{stats['false_positive_rate_on_originals']:14.3f} {stats['roc_auc']:9.3f} {stats['original_tile_count']:11}")
    print(report["original_review"]["status"])
    print(f"Artifacts: {Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
