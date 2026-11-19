import json

import numpy as np
import pytest
from PIL import Image

from slideqc.benchmark import (choose_threshold, evaluate_records, roc_auc,
                               run_benchmark, source_identity)
from slideqc.evaluation import _sample_region, binary_overlap, evaluate_manifest


def test_auc_ties_and_single_class():
    assert roc_auc([False, True], [0, 1]) == 1
    assert roc_auc([False, True], [1, 1]) == .5
    assert roc_auc([False, False], [0, 1]) is None


def test_threshold_convention_zero_and_fpr_budget():
    assert choose_threshold([0, 0], [False, True]) == 0
    scores = [100, 110, 120, 130, 1, 2, 3, 4]
    labels = [False] * 4 + [True] * 4
    threshold = choose_threshold(scores, labels)
    assert 4 < threshold < 100


def _records(evaluation_scores=(80., 5.)):
    rows = []
    for split, scores in (("calibration", (100., 10.)), ("evaluation", evaluation_scores)):
        for sigma, score in zip((0., 1.), scores):
            rows.append({"split": split, "group_id": split, "sigma": sigma,
                         "laplacian": score, "tenengrad": score * 2})
    return rows


def test_evaluation_cannot_change_calibrated_threshold():
    first = evaluate_records(_records())
    changed = evaluate_records(_records((.1, 50000.)))
    assert first["laplacian"]["threshold"] == changed["laplacian"]["threshold"]
    assert first["tenengrad"]["threshold"] == changed["tenengrad"]["threshold"]
    assert changed["laplacian"]["evaluation"]["false_positive_rate_on_originals"] == 1


def test_blur_variants_cannot_leak_across_splits():
    records = _records()
    records[-1]["group_id"] = "calibration"
    with pytest.raises(ValueError, match="both splits"):
        evaluate_records(records)


def test_known_same_source_is_not_a_distinct_slide():
    assert source_identity("CMU-1-Small-Region.svs") == source_identity("CMU-1.svs")
    assert source_identity("CMU-1.svs") != source_identity("JP2K-33003-1.svs")


def test_generated_benchmark_reproducible_and_separate_from_real(tmp_path):
    first = run_benchmark(calibration=None, evaluation=None, output=tmp_path / "first",
                          synthetic=True, max_tiles=3, tile_size=64, seed=9)
    second = run_benchmark(calibration=None, evaluation=None, output=tmp_path / "second",
                           synthetic=True, max_tiles=3, tile_size=64, seed=9)
    assert first["metrics"] == second["metrics"]
    assert first["mode"] == "generated_fixture_experiment"
    assert not set(first["splits"]["calibration"]["group_ids"]) & set(first["splits"]["evaluation"]["group_ids"])
    thresholds = json.loads((tmp_path / "first" / "thresholds.json").read_text())
    assert thresholds["usable_for_real_slides"] is False
    assert (tmp_path / "first" / "records.csv").exists()


def test_manual_overlap_uses_human_label_and_validity():
    prediction = np.array([[1, 1], [0, 0]], bool)
    human = np.array([[1, 0], [1, 0]], bool)
    score = binary_overlap(prediction, human)
    assert score["iou"] == pytest.approx(1 / 3)
    assert score["dice"] == .5
    valid = np.array([[1, 0], [1, 0]], bool)
    assert binary_overlap(prediction, human, valid)["iou"] == .5
    assert binary_overlap(np.zeros((2, 2)), np.zeros((2, 2)))["dice"] == 1
    assert binary_overlap(prediction, human, np.zeros((2, 2)))["iou"] is None


def test_algorithm_reference_cannot_be_reported_as_human(tmp_path):
    path = tmp_path / "algorithm_labels.json"
    path.write_text(json.dumps({"reference_type": "algorithm", "annotations": []}))
    with pytest.raises(ValueError, match="human"):
        evaluate_manifest(path, tmp_path / "result")


def test_manual_manifest_workflow_on_generated_fixture(tmp_path, monkeypatch):
    """Tests the annotation plumbing; this fixture is not reported as real-slide IoU."""
    import slideqc.slide_io

    class FakeSlide:
        dimensions = (20, 20)
        level_dimensions = [(20, 20)]
        level_downsamples = [1.0]
        slide_id = "generated_fixture"

        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read_tile(self, x, y, level, width, height):
            assert (x, y, width, height) == (2, 4, 8, 8)
            rgba = np.full((height, width, 4), 255, np.uint8)
            rgba[4:, :, :3] = (180, 90, 150)
            return rgba

    monkeypatch.setattr(slideqc.slide_io, "Slide", FakeSlide)
    reference = np.zeros((8, 8), np.uint8)
    reference[4:] = 255
    Image.fromarray(reference).save(tmp_path / "mask.png")
    manifest = {"reference_type": "human", "annotator": "TEST FIXTURE ONLY",
                "segmentation": {"morphology_size": 0},
                "annotations": [{"slide": "fixture.svs", "mask": "mask.png",
                                 "region": {"x": 2, "y": 4, "width": 8, "height": 8}}]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    result = evaluate_manifest(tmp_path / "manifest.json", tmp_path / "output")
    assert result["aggregate"]["hsv"]["iou"] == 1
    assert result["aggregate"]["rgb"]["dice"] == 1
    assert result["regions"][0]["reference_dimensions"] == [8, 8]


def test_annotation_region_mapping_with_fractional_downsample():
    class GradientSlide:
        dimensions = (100, 100)
        level_dimensions = [(100, 100), (40, 40)]
        level_downsamples = [1., 2.5]

        def read_tile(self, x, y, level, width, height):
            assert (x, y, level, width, height) == (7, 11, 1, 4, 2)
            rgba = np.full((height, width, 4), 255, np.uint8)
            rgba[..., :3] = (np.arange(width) * 40)[None, :, None]
            return rgba

    # Exact 10x5 level-0 ROI at ds2.5 -> 4x2 source, mapped to an 8x4 mask.
    image, valid = _sample_region(GradientSlide(),
                                {"x": 7, "y": 11, "width": 10, "height": 5}, (4, 8), 1)
    assert image[1, :, 0].tolist() == [0, 10, 30, 50, 70, 90, 110, 120]
    assert valid.all()
