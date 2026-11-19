"""Orchestrate the Streamlit page using the same pipeline as the command line.

Read this module after analysis.py: sidebar settings enter the pipeline, and the
result is handed to named display sections. No focus formulas live in the UI.
"""
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from slideqc import slide_io
from slideqc.analysis import analyze_slide, reclassify_result
from .sidebar import show_sidebar
from .panels import (
    show_benchmark,
    show_overview,
    show_segmentation_comparison,
    show_summary,
    show_tile_inspector,
    show_tile_records,
)


@st.cache_data(max_entries=3, show_spinner=False)
def run_analysis(path, modified, config):
    with slide_io.Slide(path) as slide:
        return analyze_slide(slide, config)


def initialize_selection(result, settings):
    """Keep one selected tile until the analysis geometry or slide changes."""
    signature = str((settings.path.resolve(), settings.modified, asdict(settings.config)))
    selection_key = f"selected_tile_{signature}"
    ids = [tile["tile_id"] for tile in result.tiles]
    if st.session_state.get("analysis_signature") != signature:
        st.session_state.analysis_signature = signature
        first_tissue = next(
            (tile["tile_id"] for tile in result.tiles if tile["status"] == "acceptable"),
            ids[0] if ids else None,
        )
        st.session_state.selected_tile = next(
            (tile["tile_id"] for tile in result.tiles if tile["status"] == "rescan"),
            first_tissue,
        )
        st.session_state[selection_key] = st.session_state.selected_tile
    return signature, selection_key, ids


def main(project_root=None):
    """Run the local page: controls, analysis, selection and inspection panels."""
    st.set_page_config(page_title="SlideQC | Focus & rescan", page_icon="🔬", layout="wide")
    st.title("SlideQC")
    st.write("Whole-slide focus quality and targeted rescan simulator")
    st.caption("Local CPU analysis · level-0 coordinate export · research demonstration")
    project_root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[3]
    settings = show_sidebar(project_root)
    try:
        with st.spinner("Screening the slide one tile at a time\u2026"):
            raw = run_analysis(str(settings.path.resolve()), settings.modified, settings.config)
        result = reclassify_result(raw, settings.metric, settings.threshold)
    except (slide_io.SlideError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    show_summary(result, settings)
    signature, selection_key, ids = initialize_selection(result, settings)
    left, right = st.columns([1.45, 1], gap="large")
    with left:
        show_overview(result, settings, signature, selection_key, ids)
    with right:
        show_tile_inspector(result, settings, selection_key, ids)
    show_tile_records(result, settings, signature, selection_key, ids)
    show_segmentation_comparison(result, settings)
    show_benchmark(settings.benchmark_dir / "report.json")
