"""Collect the page settings and choose a compatible focus threshold.

The returned SidebarSettings is the interface between controls and the dashboard.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path

import streamlit as st

from slideqc import slide_io
from slideqc.analysis import AnalysisConfig
from slideqc.calibration import compatible_thresholds
from slideqc.segmentation import SegmentationConfig


@dataclass(frozen=True)
class SidebarSettings:
    """Everything needed to analyze the selected local slide."""
    path: Path
    modified: int
    metadata: dict
    config: AnalysisConfig
    metric: str
    threshold: float
    benchmark_dir: Path


@st.cache_data(max_entries=8, show_spinner=False)
def load_slide_metadata(path, modified):
    # File modification time participates in the cache key after a replacement.
    with slide_io.Slide(path) as slide:
        return {"dimensions": slide.dimensions, "level_dimensions": slide.level_dimensions,
                "level_downsamples": slide.level_downsamples,
                "objective": slide.properties.get("openslide.objective-power", "unknown"),
                "mpp": slide.properties.get("openslide.mpp-x", "unknown"),
                "mpp_y": slide.properties.get("openslide.mpp-y", "unknown")}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def show_sidebar(project_root: Path) -> SidebarSettings:
    """Return user controls without running the image-processing pipeline."""
    with st.sidebar:
        st.header("Analysis controls")
        data_dir = Path(st.text_input("Local slide folder", os.environ.get("SLIDEQC_DATA_DIR", str(project_root / "data")))).expanduser()
        paths = sorted(data_dir.glob("*.svs")) if data_dir.is_dir() else []
        custom = st.text_input("Or enter a local .svs path", "")
        if custom:
            path = Path(custom).expanduser()
        elif paths:
            path = st.selectbox("Sample slide", paths, format_func=lambda slide_path: slide_path.name)
        else:
            st.info("Fetch the demo: python scripts/fetch_samples.py --sample demo")
            st.stop()
        if not path.is_file():
            st.error(f"Slide not found: {path}. Check the path or fetch the sample.")
            st.stop()
        modified = path.stat().st_mtime_ns
        try:
            info = load_slide_metadata(str(path.resolve()), modified)
        except (slide_io.SlideError, ValueError) as exc:
            st.error(str(exc))
            st.stop()
        method = st.selectbox("Tissue segmentation", ["hsv", "rgb"], format_func=str.upper)
        metric = st.selectbox("Focus metric", ["laplacian", "tenengrad"],
                              format_func=lambda s:{"laplacian":"Variance of Laplacian", "tenengrad":"Tenengrad"}[s])
        level = st.selectbox("Analysis pyramid level", list(range(len(info["level_dimensions"]))),
                             format_func=lambda v:f"{v} · {info['level_dimensions'][v]} · {info['level_downsamples'][v]:.3g}× downsample")
        tile_size = st.selectbox("Tile edge at analysis level (pixels)", [128, 256, 512], index=1)
        minimum = st.slider("Minimum thumbnail tissue fraction", .0, 1., .2, .05)
        cap = int(st.number_input("Maximum grid tiles (includes background)", min_value=1, max_value=100000, value=500, step=100))
        with st.expander("Segmentation thresholds"):
            rgb_threshold = st.slider("RGB mean below", 0, 255, 235)
            saturation = st.slider("HSV saturation at least", 0, 255, 20)
            value = st.slider("HSV value at most", 0, 255, 245)
            morphology = st.selectbox("Opening + closing kernel (thumbnail pixels)", [0, 3, 5, 7], index=1)
        segmentation = SegmentationConfig(method=method, rgb_threshold=rgb_threshold,
                                           saturation_threshold=saturation, value_threshold=value,
                                           morphology_size=morphology)
        config = AnalysisConfig(level=level, tile_size=tile_size, max_tiles=cap,
                                min_tissue_fraction=minimum, segmentation=segmentation)
        benchmark_dir = Path(st.text_input("Benchmark results folder", os.environ.get("SLIDEQC_BENCHMARK_DIR", str(project_root / "outputs" / "benchmark"))))
        thresholds = read_json(benchmark_dir / "thresholds.json")
        calibrated = compatible_thresholds(thresholds, config, info["level_downsamples"][level], info["mpp"], info["mpp_y"])
        default = float(thresholds["metrics"][metric]) if calibrated else {"laplacian":100., "tenengrad":500.}[metric]
        threshold_key = f"threshold_{metric}_{default}_{hash(config.segmentation)}_{level}_{tile_size}_{minimum}"
        threshold = st.number_input("Rescan threshold (score below this)", min_value=0., value=default,
                                    format="%.5f", key=threshold_key)
        if calibrated:
            st.caption(f"Calibrated starting point: {thresholds.get('calibration_slide_id')}. "
                       "Changing the threshold is an exploratory override. Stain and resolution can still shift scores.")
        else:
            st.caption("Experimental threshold: compatible real-slide calibration was not found for these settings and physical pixel resolution.")
    return SidebarSettings(path, modified, info, config, metric, threshold, benchmark_dir)
