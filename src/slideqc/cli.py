"""Analyze a real SVS using exactly the same pipeline as the interactive app."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path
import sys

from PIL import Image

from .analysis import AnalysisConfig, analyze_slide, export_candidates_csv
from .rendering import render_overlay
from .segmentation import SegmentationConfig
from .slide_io import Slide, SlideError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slide", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/analysis"))
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument("--tile-size", type=int, default=256)
    parser.add_argument("--max-tiles", type=int, default=500, help="Grid visits including background; 0 means whole slide")
    parser.add_argument("--min-tissue", type=float, default=0.2)
    parser.add_argument("--segmentation", choices=["hsv", "rgb"], default="hsv")
    parser.add_argument("--metric", choices=["laplacian", "tenengrad"], default="laplacian")
    parser.add_argument("--threshold", type=float, default=100, help="Experimental unless supplied from a compatible benchmark")
    args = parser.parse_args(argv)
    config = AnalysisConfig(level=args.level, tile_size=args.tile_size, max_tiles=args.max_tiles or None,
                            min_tissue_fraction=args.min_tissue, metric=args.metric, threshold=args.threshold,
                            segmentation=SegmentationConfig(method=args.segmentation))
    try:
        with Slide(args.slide) as slide:
            result = analyze_slide(slide, config)
            metadata = {"path": str(args.slide.resolve()), "level_dimensions": slide.level_dimensions,
                        "level_downsamples": slide.level_downsamples,
                        "objective_power": slide.properties.get("openslide.objective-power"),
                        "mpp_x": slide.properties.get("openslide.mpp-x"),
                        "mpp_y": slide.properties.get("openslide.mpp-y")}
    except (SlideError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "candidates.csv").write_text(export_candidates_csv(result), encoding="utf-8")
    with (args.output / "tiles.csv").open("w", newline="", encoding="utf-8") as handle:
        if result.tiles:
            writer = csv.DictWriter(handle, fieldnames=list(result.tiles[0]))
            writer.writeheader()
            writer.writerows(result.tiles)
    report = {"summary": result.summary, "config": asdict(config), "slide": metadata,
              "threshold_provenance": "User-supplied or experimental CLI threshold; see benchmark/thresholds.json",
              "segmentation_evaluation": "pending: human masks required"}
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render_overlay(result.thumbnail, result.mask, result.tiles, tuple(result.summary["dimensions"])).save(args.output / "overlay.png")
    Image.fromarray(result.thumbnail).save(args.output / "thumbnail.png")
    Image.fromarray(result.mask.astype("uint8") * 255).save(args.output / "tissue_mask.png")
    print(json.dumps(result.summary, indent=2))
    print(f"Saved candidates, all tile records, report, thumbnail, mask and overlay to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
