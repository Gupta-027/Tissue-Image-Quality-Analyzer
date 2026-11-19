"""Compare RGB/HSV masks with explicitly supplied human binary region labels."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .segmentation import SegmentationConfig, segment_tissue


def binary_overlap(prediction: np.ndarray, reference: np.ndarray,
                   valid: np.ndarray | None = None) -> dict:
    """IoU/Dice on valid pixels; two empty masks score 1, no valid pixels is pending."""
    prediction = np.asarray(prediction, dtype=bool)
    reference = np.asarray(reference, dtype=bool)
    if prediction.shape != reference.shape:
        raise ValueError("Prediction and human reference mask must have the same shape.")
    valid = np.ones(reference.shape, bool) if valid is None else np.asarray(valid, dtype=bool)
    if valid.shape != reference.shape:
        raise ValueError("Validity mask must have the reference dimensions.")
    prediction = prediction & valid
    reference = reference & valid
    intersection = int((prediction & reference).sum())
    union = int((prediction | reference).sum())
    pred_count, ref_count = int(prediction.sum()), int(reference.sum())
    denominator = pred_count + ref_count
    return {"iou": intersection / union if union else (1.0 if valid.any() else None),
            "dice": 2 * intersection / denominator if denominator else (1.0 if valid.any() else None),
            "intersection": intersection, "union": union,
            "predicted_tissue_pixels": pred_count, "reference_tissue_pixels": ref_count,
            "valid_pixels": int(valid.sum())}


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _sample_region(slide, region: dict, shape: tuple[int, int], level: int) -> tuple[np.ndarray, np.ndarray]:
    x, y, width, height = (int(region[key]) for key in ("x", "y", "width", "height"))
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > slide.dimensions[0] or y + height > slide.dimensions[1]:
        raise ValueError("Annotated region must lie fully inside the slide in level-0 pixels.")
    if not 0 <= level < len(slide.level_dimensions):
        raise ValueError(f"Invalid annotation read level {level}.")
    ds = float(slide.level_downsamples[level])
    aw, ah = math.ceil(width / ds), math.ceil(height / ds)
    if aw * ah > 4096 * 4096:
        raise ValueError("Annotation read exceeds 4096x4096 pixels. Use smaller regions or a coarser read level.")
    rgba = np.asarray(slide.read_tile(x, y, level, aw, ah))
    mh, mw = shape
    # Read starts at exact level-0 x/y. Map target pixel centers over the exact
    # annotated rectangle, retaining the fractional final analysis pixel.
    xs = ((np.arange(mw, dtype=np.float32) + .5) * width / mw / ds - .5)
    ys = ((np.arange(mh, dtype=np.float32) + .5) * height / mh / ds - .5)
    map_x, map_y = np.meshgrid(xs, ys)
    rgb = cv2.remap(rgba[..., :3], map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    alpha = rgba[..., 3] if rgba.shape[2] == 4 else np.full(rgba.shape[:2], 255, np.uint8)
    valid = cv2.remap(alpha, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_REPLICATE) == 255
    return rgb, valid


def _save_region_comparison(rgb: np.ndarray, reference: np.ndarray, predictions: dict,
                            path: Path) -> None:
    images = [("Image", rgb), ("Human reference", np.repeat((reference.astype(np.uint8) * 255)[..., None], 3, axis=2))]
    for name, mask in predictions.items():
        overlay = rgb.copy()
        overlay[mask] = (.5 * overlay[mask] + .5 * np.array([0, 170, 150])).astype(np.uint8)
        images.append((name.upper(), overlay))
    canvas = Image.new("RGB", (len(images) * 320, 360), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (label, pixels) in enumerate(images):
        image = Image.fromarray(pixels)
        image.thumbnail((320, 320))
        canvas.paste(image, (index * 320, 32))
        draw.text((index * 320 + 5, 8), label, fill="black")
    canvas.save(path)


def evaluate_manifest(manifest_path: str | Path, output: str | Path) -> dict:
    from .slide_io import Slide
    manifest_path, output = Path(manifest_path), Path(output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("reference_type") != "human":
        raise ValueError("Manifest must explicitly set reference_type='human'. Algorithm masks are not human labels.")
    annotations = manifest.get("annotations", [])
    if not annotations:
        raise ValueError("No human mask annotations were supplied.")
    output.mkdir(parents=True, exist_ok=True)
    config = SegmentationConfig(**manifest.get("segmentation", {}))
    regions = []
    for index, item in enumerate(annotations):
        mask_path = _resolve(manifest_path.parent, item["mask"])
        with Image.open(mask_path) as image:
            if image.format != "PNG":
                raise ValueError("Human reference masks must be binary PNG files.")
            reference_pixels = np.array(image.convert("L"))
        if not set(np.unique(reference_pixels).tolist()) <= {0, 1, 255}:
            raise ValueError(f"Mask {mask_path} has non-binary values; export black background and white tissue without antialiasing.")
        reference = reference_pixels > 0
        slide_path = _resolve(manifest_path.parent, item["slide"])
        with Slide(slide_path) as slide:
            rgb, valid = _sample_region(slide, item["region"], reference.shape, int(item.get("level", 0)))
            methods = {}
            predictions = {}
            for method in ("rgb", "hsv"):
                options = asdict(config)
                options["method"] = method
                predictions[method] = segment_tissue(rgb, SegmentationConfig(**options)) & valid
                methods[method] = binary_overlap(predictions[method], reference, valid)
            regions.append({"slide_id": slide.slide_id, "slide": str(slide_path), "mask": str(mask_path),
                            "region": item["region"], "read_level": int(item.get("level", 0)),
                            "reference_dimensions": [reference.shape[1], reference.shape[0]], "methods": methods})
            _save_region_comparison(rgb, reference, predictions, output / f"region_{index:03d}.png")
    aggregate = {}
    for method in ("rgb", "hsv"):
        totals = {key: sum(r["methods"][method][key] for r in regions)
                  for key in ("intersection", "union", "predicted_tissue_pixels", "reference_tissue_pixels", "valid_pixels")}
        denominator = totals["predicted_tissue_pixels"] + totals["reference_tissue_pixels"]
        totals.update(iou=totals["intersection"] / totals["union"] if totals["union"] else (1.0 if totals["valid_pixels"] else None),
                      dice=2 * totals["intersection"] / denominator if denominator else (1.0 if totals["valid_pixels"] else None))
        aggregate[method] = totals
    report = {"schema_version": 1, "status": "measured_against_supplied_human_masks",
              "annotator": manifest.get("annotator", "Not recorded"), "manifest": str(manifest_path),
              "segmentation": asdict(config), "regions": regions, "aggregate": aggregate,
              "convention": "Region bounds are level-0 half-open coordinates. Both algorithms operate at reference-mask resolution using identical morphology; scores are micro-aggregated over valid pixels. Empty/empty masks score 1.",
              "limits": "Human labels are supplied by the user; this program cannot verify their annotation provenance. Crop-resolution metrics need not equal whole-thumbnail metrics."}
    (output / "segmentation_report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def visual_comparison(slide_path: str | Path, output: str | Path) -> dict:
    from .benchmark import save_segmentation_comparison
    from .slide_io import Slide
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with Slide(slide_path) as slide:
        save_segmentation_comparison([(slide.slide_id, slide.thumbnail(max_size=1200))],
                                     output / "segmentation_comparison.png", SegmentationConfig())
    report = {"schema_version": 1, "status": "pending", "reason": "No human reference masks supplied; visual comparison only, no IoU or Dice claimed."}
    (output / "segmentation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Human annotation JSON; paths resolve relative to this file.")
    parser.add_argument("--slide", help="Without labels, generate a visual comparison and pending quantitative report.")
    parser.add_argument("--output", default="outputs/segmentation")
    args = parser.parse_args(argv)
    try:
        if args.manifest:
            report = evaluate_manifest(args.manifest, args.output)
        elif args.slide:
            report = visual_comparison(args.slide, args.output)
        else:
            parser.error("Provide --manifest with human masks, or --slide for visual comparison only.")
    except (ValueError, OSError, RuntimeError, ImportError, KeyError) as exc:
        parser.exit(2, f"Segmentation evaluation failed: {exc}\n")
    print(json.dumps({key: report[key] for key in ("status", "aggregate") if key in report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
