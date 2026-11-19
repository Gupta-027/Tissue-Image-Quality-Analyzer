# Setup and commands

Run commands from the repository root. The verified environment is Windows,
Python 3.13.1, and CPU only. Python 3.10+ is declared; other operating systems
have not been executed in this validation.

## Install

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`pyproject.toml` declares the six runtime dependencies and the optional pytest
dependency. You do not need to activate the environment when using its Python
executable explicitly. `requirements-lock.txt` records the exact Windows test
environment, including optional browser tools; it is a version snapshot rather
than a portable lockfile.

The dependencies include both `openslide-python` and `openslide-bin`. The second
package provides native OpenSlide on supported platforms. This combination worked
here without manual DLL configuration. If a binary wheel is unavailable, install
native OpenSlide using your OS package manager following the [official
instructions](https://openslide.org/api/python/#installing). Install NumPy,
opencv-python-headless, openslide-python, Pillow, Streamlit, and pytest manually,
then run `pip install -e . --no-deps` in that environment.

For macOS/Linux, use `python3 -m venv .venv`, activate with
`source .venv/bin/activate`, and replace the Windows executable below with `python`.
Keep the OpenSlide wrapper and native library in a compatible environment.

## Download slides

```powershell
.\.venv\Scripts\python.exe scripts/fetch_samples.py --sample demo
.\.venv\Scripts\python.exe scripts/fetch_samples.py --sample all
```

Choose one command: `demo` downloads the 1.85 MiB interactive sample; `all` adds
the 60.89 MiB distinct evaluation slide. Downloads stream to disk, verify published
SHA-256 hashes, and record `data/download_manifest.json`. On a restricted network,
download the [linked samples](data_sources.md) in a browser, place them in `data/`,
and rerun the command to verify them. Tests need no downloaded slides.

## Run the application

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://localhost:8501. The sidebar selects a local `.svs`, processing
settings, and benchmark folder. The default folders are `data/` and
`outputs/benchmark/`; environment variables `SLIDEQC_DATA_DIR` and
`SLIDEQC_BENCHMARK_DIR` can override them. `app.py` starts the dashboard in
`src/slideqc/ui/`.

## Run analysis without the UI

```powershell
.\.venv\Scripts\python.exe -m slideqc.cli data/CMU-1-Small-Region.svs --max-tiles 0 --metric tenengrad --threshold 24902.930314160512 --output outputs/demo
```

`--max-tiles 0` means the whole grid; the default cap is 500, including background.
This command explicitly supplies a calibrated Tenengrad threshold. The CLI default
100 is experimental. Use `--help` to see level, tile-size, segmentation, and other
options. The output folder contains `tiles.csv`, `candidates.csv`, `report.json`,
`thumbnail.png`, `tissue_mask.png`, and `overlay.png`.

## Reproduce focus experiments

```powershell
.\.venv\Scripts\python.exe -m slideqc.benchmark --calibration data/CMU-1-Small-Region.svs --evaluation data/JP2K-33003-1.svs --max-tiles 16 --review-manifest examples/original_review.json --output outputs/benchmark
```

This uses the recorded reference crops and seed 42. It writes thresholds, measured
results, raw per-variant records, original/blur comparisons, segmentation panels,
and failure examples. The app reads compatible thresholds from this output folder.
For new data, omit the review manifest, inspect the generated contact sheet and
`review_candidates.json`, and rerun with a manifest of reviewed originals. Without
review, the report explicitly calls the original crops unreviewed.

An offline generated-fixture experiment is also available:

```powershell
.\.venv\Scripts\python.exe -m slideqc.benchmark --synthetic --max-tiles 16 --output outputs/synthetic
```

Those results are a software demonstration, separate from real-slide measurements.

## Compare tissue segmentation

```powershell
.\.venv\Scripts\python.exe -m slideqc.evaluation --slide data/CMU-1-Small-Region.svs --output outputs/segmentation
```

Without human masks this produces a visual comparison and marks IoU/Dice pending.
To measure overlap, create the binary PNG named by
`examples/annotations.example.json`, record the actual human annotator, then run:

```powershell
.\.venv\Scripts\python.exe -m slideqc.evaluation --manifest examples/annotations.example.json --output outputs/manual_segmentation
```

The mask must cover the manifest's level-0 rectangle, with 0 for background and
255 for tissue. It may be smaller than the rectangle if it depicts the same field
of view. Paths resolve relative to the manifest. Details are in [Methods](methods.md).

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

The optional [browser smoke test](../reports/browser_validation.md) requires
Playwright, the real sample files, a running server, and benchmark outputs.
The regular pytest suite uses generated fixtures and does not require a browser.

Missing slides, unsupported files, missing native dependencies, and failed reads
produce actionable errors. If no tissue is scored, inspect the mask and coverage:
a large slide's first rows may be background. Increase the tile cap or use a lower
resolution pyramid level. Restart Streamlit after changing imported modules if
development hot reload retains an older function signature.
