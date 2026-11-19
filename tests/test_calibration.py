from dataclasses import asdict, replace

from slideqc.analysis import AnalysisConfig
from slideqc.calibration import compatible_thresholds


def test_threshold_domain_rejects_generated_and_changed_resolution():
    config = AnalysisConfig()
    payload = dict(usable_for_real_slides=True, level=0, tile_size=256,
                   calibration_downsample=1., segmentation=asdict(config.segmentation),
                   metrics=dict(laplacian=120.,tenengrad=500.))
    assert compatible_thresholds(payload, config, 1.)
    assert not compatible_thresholds(dict(payload, usable_for_real_slides=False), config, 1.)
    assert not compatible_thresholds(payload, config, 4.)
    assert not compatible_thresholds(payload, replace(config, tile_size=512), 1.)
    assert not compatible_thresholds(payload, replace(config, segmentation=replace(config.segmentation, method="rgb")), 1.)
    physical = dict(payload, calibration_mpp_x="0.499", calibration_mpp_y="0.499")
    assert compatible_thresholds(physical, config, 1., "0.499", "0.499")
    assert not compatible_thresholds(physical, config, 1., "0.2498", "0.2498")
    assert not compatible_thresholds(physical, config, 1.)
