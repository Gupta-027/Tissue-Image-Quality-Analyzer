"""Small, named page sections for inspecting one analysis result.

These functions display pipeline outputs. They do not decide which tiles to flag.
"""
import base64
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

import cv2
import streamlit as st
import streamlit.components.v1 as components

import slideqc
from slideqc import slide_io
from slideqc.analysis import export_candidates_csv
from slideqc.coordinates import TileFootprint, level0_to_thumbnail, tissue_mask_for_tile
from slideqc.focus import focus_scores
from slideqc.rendering import render_overlay, rgba_on_white
from slideqc.segmentation import SegmentationConfig, segment_tissue
from .sidebar import read_json

# The bundled component sends a thumbnail click back to Python; no remote service.
picker = components.declare_component(
    "slideqc_tile_picker", path=str(Path(slideqc.__file__).parent / "tile_picker")
)


def image_url(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def percent(value):
    return "pending" if value is None else f"{value:.1%}"


def select_tile_changed(selection_key):
    """Widget callbacks run before the next render, keeping one selection source."""
    st.session_state.selected_tile = st.session_state[selection_key]


def table_tile_changed(table_key, selection_key, tile_ids):
    """Apply a table selection before the page is redrawn, like the dropdown."""
    rows = st.session_state[table_key]["selection"]["rows"]
    if rows:
        tile_id = tile_ids[rows[0]]
        st.session_state.selected_tile = tile_id
        st.session_state[selection_key] = tile_id


def show_summary(result, settings):
    """Explain the measured counts, runtime and visited slide coverage."""
    info = settings.metadata
    path = settings.path
    summary = result.summary
    analyzed, flagged = summary["analyzed_tissue_tiles"], summary["flagged_tissue_tiles"]
    tissue_column, candidates_column, fraction_column, runtime_column = st.columns(4)
    tissue_column.metric("Analyzed tissue tiles", analyzed)
    candidates_column.metric("Rescan candidates", flagged)
    fraction_column.metric("Flagged tissue fraction", percent(summary["flagged_fraction"]))
    runtime_column.metric("Pipeline runtime", f"{summary['runtime_seconds']:.2f} s")
    st.caption(f"{path.name} · level 0: {info['dimensions'][0]:,} × {info['dimensions'][1]:,} px · "
               f"objective {info['objective']}× · MPP {info['mpp']} · coordinates use level-0 pixels")
    coverage = (f"Visited {summary['visited_tiles']:,}/{summary['grid_tiles']:,} grid tiles "
                f"({summary['grid_coverage_fraction']:.1%} of grid; {summary['coverage_fraction']:.1%} of slide area), "
                f"in row-major order. {summary['background_tiles']} background; "
                f"{summary['unevaluated_tissue_tiles']} unevaluated; {summary['failed_tiles']} read failures.")
    if summary["complete"]:
        st.caption(coverage)
    else:
        st.warning("Partial slide coverage. " + coverage + " Unoutlined regions were not visited.")
    if not summary["tissue_detected"]:
        st.info("No tissue detected. Inspect both segmentation masks or adjust the thresholds.")
    elif not analyzed:
        st.info("No eligible tissue tiles were scored in this area. Increase the grid limit or inspect segmentation and unevaluated reasons.")
    st.write(f"Tile-count comparison over the same analyzed area: **{flagged} targeted visits versus {analyzed} full-area tissue visits**. "
             "This does not measure scanner time or clinical benefit.")


def show_overview(result, settings, signature, selection_key, ids):
    """Draw visited footprints and keep thumbnail clicks tied to the selected tile."""
    info = settings.metadata
    st.subheader("Slide overview")
    show_mask = st.checkbox("Show tissue segmentation mask", value=False)
    overlay = render_overlay(result.thumbnail, result.mask, result.tiles, info["dimensions"],
                             show_mask=show_mask, selected_id=st.session_state.selected_tile)
    boxes = []
    thumb_dims = (result.thumbnail.shape[1], result.thumbnail.shape[0])
    for row in result.tiles:
        x0, y0 = level0_to_thumbnail(row["x"], row["y"], info["dimensions"], thumb_dims)
        x1, y1 = level0_to_thumbnail(
            row["x"] + row["width"], row["y"] + row["height"], info["dimensions"], thumb_dims
        )
        boxes.append(dict(id=row["tile_id"], x0=x0, y0=y0, x1=x1, y1=y1))
    clicked = picker(image=image_url(overlay), tiles=boxes, default=None, key=f"picker_{signature}")
    # A component retains its last value on other widget reruns. Consume each
    # changed click once so a subsequent table/dropdown selection can prevail.
    click_key = f"last_click_{signature}"
    if isinstance(clicked, dict) and clicked.get("tile_id") in ids and clicked != st.session_state.get(click_key):
        st.session_state[click_key] = clicked
        st.session_state.selected_tile = clicked["tile_id"]
        st.session_state[selection_key] = clicked["tile_id"]
        st.rerun()
    st.caption("✓ Green outline: acceptable · × Orange hatching: candidate · ? Gray: unevaluated · plain gray: background. "
               "Black border: selected. Blue tint: segmentation when enabled.")


def show_tile_inspector(result, settings, selection_key, ids):
    """Read the selected crop and compare it with a labeled injected-blur variant."""
    info = settings.metadata
    path = settings.path
    config = settings.config
    level, tile_size = config.level, config.tile_size
    st.subheader("Tile inspector")
    if ids:
        selected = st.selectbox("Select a visited tile", ids, key=selection_key,
                                on_change=select_tile_changed, args=(selection_key,))
        row = next(t for t in result.tiles if t["tile_id"] == selected)
        st.write(f"**{row['status'].capitalize()}** · {row['reason']}")
        st.code(f"x={row['x']}  y={row['y']}\nwidth={row['width']}  height={row['height']}\nlevel={row['level']}  tissue={row['tissue_fraction']:.1%}", language=None)
        st.write(f"Laplacian: **{row['laplacian'] if row['laplacian'] is not None else 'unevaluated'}**  \n"
                 f"Tenengrad: **{row['tenengrad'] if row['tenengrad'] is not None else 'unevaluated'}**")
        try:
            with slide_io.Slide(path) as slide:
                rgba = slide.read_tile(row["x"], row["y"], row["level"], row["analysis_width"], row["analysis_height"])
            rgb = rgba_on_white(rgba)
            st.image(rgb, caption="Selected source crop at the analysis level", width=min(400, tile_size))
            st.write("**Injected-blur experiment**")
            sigma = st.select_slider("Gaussian sigma (analysis pixels)", options=[1., 2., 4.], value=2.)
            blurred = cv2.GaussianBlur(rgb, (0, 0), sigmaX=sigma, sigmaY=sigma, borderType=cv2.BORDER_REFLECT_101)
            original_col, blur_col = st.columns(2)
            original_col.image(rgb, caption="Original input", width="stretch")
            blur_col.image(blurred, caption=f"Injected blur: σ={sigma:g}", width="stretch")
            footprint = TileFootprint(**{k: row[k] for k in TileFootprint.__dataclass_fields__})
            eligible = tissue_mask_for_tile(result.mask, footprint, info["dimensions"], info["level_downsamples"][level])
            if rgba.shape[2] == 4:
                eligible &= rgba[:, :, 3] == 255
            st.caption(f"Same fixed tissue support. Blur scores: {focus_scores(blurred, eligible)}. "
                       "This experiment does not change the source tile or the rescan CSV.")
        except (slide_io.SlideError, ValueError) as exc:
            st.error(str(exc))


def show_tile_records(result, settings, signature, selection_key, ids):
    """Provide table selection and a candidate-only coordinate download."""
    path = settings.path
    metric, threshold = settings.metric, settings.threshold
    st.subheader("Visited tile records")
    st.caption("Select a row to inspect its crop. Tile coordinates and footprints are in level-0 pixels.")
    columns = [
        "tile_id", "status", "x", "y", "width", "height", "level",
        "tissue_fraction", "laplacian", "tenengrad", "threshold", "reason",
    ]
    table_key = f"records_{signature}_{metric}_{threshold}"
    st.dataframe([{key: tile[key] for key in columns} for tile in result.tiles], hide_index=True,
                 selection_mode="single-row", on_select=lambda: table_tile_changed(table_key, selection_key, ids),
                 key=table_key, width="stretch", height=260)
    st.download_button("Download rescan candidates CSV", export_candidates_csv(result),
                       file_name=f"{path.stem}_rescan.csv", mime="text/csv")


def show_segmentation_comparison(result, settings):
    """Compare both algorithms visually while human-mask metrics are pending."""
    info = settings.metadata
    segmentation = settings.config.segmentation
    with st.expander("Compare RGB and HSV segmentation"):
        rgb_column, hsv_column = st.columns(2)
        for method_name, column in [("rgb", rgb_column), ("hsv", hsv_column)]:
            mask = segment_tissue(result.thumbnail, SegmentationConfig(**dict(asdict(segmentation), method=method_name)))
            column.image(render_overlay(result.thumbnail, mask, [], info["dimensions"], show_mask=True),
                         caption=f"{method_name.upper()} mask overlay", width="stretch")
        st.caption("Quantitative tissue IoU and Dice are pending until human binary reference masks are supplied. "
                   "See examples/annotations.example.json and the manual evaluation command in the README.")


def show_benchmark(report_path):
    """Display saved experiments without recalibrating on the selected slide."""
    st.subheader("Benchmark evidence")
    report = read_json(report_path)
    if not report:
        st.info("Benchmark pending. Run the README benchmark command to calibrate both metrics and show results here.")
        return
    st.caption(f"{report.get('mode', 'experiment')} · {report_path}")
    rows = []
    for name, item in report.get("metrics", {}).items():
        stats = item.get("evaluation", {})
        rows.append({"Metric": name, "Threshold": item.get("threshold"),
                     "Blur sensitivity": percent(stats.get("sensitivity_to_injected_blur")),
                     "Original flag rate (FPR proxy)": percent(stats.get("false_positive_rate_on_originals")),
                     "ROC AUC": stats.get("roc_auc"), "Original tiles": stats.get("original_tile_count"),
                     "Blur variants": stats.get("blurred_variant_count")})
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("Injected Gaussian blur experiment. Original crops are reference inputs, not clinical sharpness labels. "
               "Full provenance, split assignments and per-strength results are in report.json and records.csv.")
    with st.expander("Results by blur strength"):
        for name, item in report.get("metrics", {}).items():
            st.write(name)
            st.dataframe(item.get("evaluation", {}).get("by_sigma", []), hide_index=True)
    measured = report_path.parent / "reviewed_original_flagged.png"
    if measured.is_file():
        st.image(str(measured), caption="Measured example: an original reviewed crop flagged at the transferred threshold. "
                 "Possible texture or resolution failure; scanner focus truth is unavailable.")
    failure = report_path.parent / "low_texture_failure.png"
    if failure.is_file():
        st.image(str(failure), caption="Separate generated failure example: sharp, low-texture tissue can have a low edge score.")
