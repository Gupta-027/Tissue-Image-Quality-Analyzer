"""Pipeline checks: safe summaries, real edge footprints, failures, and CSV export."""

import csv
from io import StringIO

import numpy as np
import pytest

from slideqc.analysis import AnalysisConfig, analyze_slide, export_candidates_csv, reclassify_result
from slideqc.segmentation import SegmentationConfig


@pytest.mark.parametrize("method", ["rgb", "hsv"])
def test_background_only_has_no_tissue_or_scores_and_safe_percentages(method, fake_slide):
    slide = fake_slide(np.full((31, 45, 3), 255, np.uint8))
    config = AnalysisConfig(tile_size=16, segmentation=SegmentationConfig(method=method))
    result = analyze_slide(slide, config)
    assert not result.mask.any()
    assert result.summary["analyzed_tissue_tiles"] == 0
    assert result.summary["flagged_fraction"] == 0
    assert result.summary["coverage_fraction"] == 1
    assert result.summary["complete"]
    assert slide.requests == []
    assert list(csv.DictReader(StringIO(export_candidates_csv(result)))) == []
    assert "slide_id,tile_id,x,y,width,height" in export_candidates_csv(result)


def test_partial_edge_tiles_are_read_at_actual_dimensions(fake_slide, stained_texture):
    slide = fake_slide(stained_texture(45, 31))
    result = analyze_slide(slide, AnalysisConfig(tile_size=16, max_tiles=None, threshold=0))
    last = result.tiles[-1]
    assert (last["x"], last["y"], last["width"], last["height"]) == (32, 16, 13, 15)
    assert slide.requests[-1] == (32, 16, 0, 13, 15)
    assert last["eligible_pixels"] == 11 * 13
    assert result.summary["coverage_fraction"] == 1


def test_no_valid_pixels_produces_unevaluated_tissue_tiles(fake_slide, stained_texture):
    slide = fake_slide(stained_texture(32, 32), alpha=np.zeros((32, 32), np.uint8))
    result = analyze_slide(slide, AnalysisConfig(tile_size=32))
    assert result.tiles[0]["status"] == "unevaluated"
    assert "valid tissue pixels" in result.tiles[0]["reason"]
    assert result.summary["flagged_fraction"] == 0
    assert result.summary["failed_tiles"] == 0


def test_failed_reads_are_reported_without_becoming_rescan_candidates(fake_slide, stained_texture):
    slide = fake_slide(stained_texture(64, 64), fail=True)
    result = analyze_slide(slide, AnalysisConfig(tile_size=32))
    assert result.summary["failed_tiles"] == 4
    assert all(t["status"] == "unevaluated" for t in result.tiles)
    assert all("generated read failure" in t["reason"] for t in result.tiles)
    assert result.summary["analyzed_tissue_tiles"] == 0
    assert list(csv.DictReader(StringIO(export_candidates_csv(result)))) == []


def test_grid_limit_reports_partial_coverage(fake_slide, stained_texture):
    slide = fake_slide(stained_texture(64, 64))
    result = analyze_slide(slide, AnalysisConfig(tile_size=32, max_tiles=2))
    assert result.summary["visited_tiles"] == 2
    assert result.summary["grid_tiles"] == 4
    assert result.summary["coverage_fraction"] == 0.5
    assert not result.summary["complete"]
    assert len(slide.requests) == 2


def test_rescan_csv_coordinates_match_analysis_and_reclassification(fake_slide, stained_texture):
    slide = fake_slide(stained_texture(45, 31))
    result = analyze_slide(slide, AnalysisConfig(tile_size=16, max_tiles=None, threshold=1e12))
    rows = list(csv.DictReader(StringIO(export_candidates_csv(result))))
    assert len(rows) == result.summary["analyzed_tissue_tiles"] == 6
    for exported, analyzed in zip(rows, result.tiles):
        for key in ("x", "y", "width", "height", "level"):
            assert int(exported[key]) == analyzed[key]
        assert exported["slide_id"] == "generated"
        assert exported["status"] == "rescan"
    acceptable = reclassify_result(result, "tenengrad", 0)
    assert acceptable.summary["flagged_tissue_tiles"] == 0
    assert acceptable.summary["analyzed_tissue_tiles"] == 6
    assert result.summary["flagged_tissue_tiles"] == 6  # original is unchanged


def test_invalid_analysis_parameters_are_rejected(fake_slide, stained_texture):
    slide = fake_slide(stained_texture())
    for config in [AnalysisConfig(max_tiles=0), AnalysisConfig(level=2),
                   AnalysisConfig(min_tissue_fraction=1.1), AnalysisConfig(threshold=float("nan"))]:
        with pytest.raises(ValueError):
            analyze_slide(slide, config)
