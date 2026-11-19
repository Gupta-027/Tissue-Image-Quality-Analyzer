# SlideQC

**Whole-Slide Focus Quality and Targeted Rescan Simulator**

A computer vision portfolio project that opens real pathology slides, separates
tissue from background, finds tiles with low focus scores, and exports their
coordinates for a simulated rescan. Everything runs locally on a CPU.

## Start here

1. Read the [project guide](docs/guides/project_guide.md) for the file map, reading order, and a tile-by-tile explanation.
2. Run the app with the commands below.
3. Practice the [interview guide](docs/guides/interview_guide.md): short pitch, code tour, and technical questions.

## Run the project

Verified on Windows with Python 3.13.1. Run from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts/fetch_samples.py --sample all
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://localhost:8501**. `--sample demo` downloads only the small interactive
slide; `all` adds the held-out slide. The dependencies include `openslide-bin` for
the native library. No GPU or API key is needed. [Setup and commands](docs/reference/setup.md)
covers native installation alternatives, macOS/Linux instructions, and CLI usage.

## Folder structure

```text
SlideQC/
├── app.py                    # Small Streamlit launcher
├── pyproject.toml            # Dependencies and package configuration
├── requirements-lock.txt     # Exact tested environment snapshot
├── src/slideqc/
│   ├── slide_io.py           # OpenSlide file and tile reading
│   ├── coordinates.py        # Tile grid and coordinate conversions
│   ├── segmentation.py       # RGB and HSV tissue masks
│   ├── focus.py              # Laplacian and Tenengrad scores
│   ├── analysis.py           # Pipeline, tile status, and CSV export
│   ├── calibration.py        # Threshold compatibility checks
│   ├── rendering.py          # Mask and tile overlay drawing
│   ├── cli.py                # Analysis without the UI
│   ├── benchmark.py          # Calibration and blur experiments
│   ├── evaluation.py         # Human tissue-mask evaluation
│   ├── ui/
│   │   ├── dashboard.py      # Page flow and shared selection state
│   │   ├── sidebar.py        # Slide selection and analysis controls
│   │   └── panels.py         # Overview, inspector, records, and results
│   └── tile_picker/          # Small HTML thumbnail-click component
├── tests/                    # Tests grouped by processing topic
├── scripts/                  # Data download and optional browser check
├── examples/                 # Annotation and crop-review manifests
├── docs/
│   ├── guides/               # Learning path and interview preparation
│   ├── reference/            # Setup, methods, data, and interface notes
│   └── reports/              # Executed validation and recorded results
├── data/                     # Downloaded slides; ignored by Git
└── outputs/                  # Generated CSVs, reports, and images; ignored
```

The processing modules do not import Streamlit. Both app and CLI call the same
`analyze_slide` function. Read `segmentation.py`, `focus.py`, then `analysis.py`
first; the project guide explains the remaining files in order.

## How it works

```text
SVS slide -> thumbnail -> tissue mask -> tissue tiles -> focus scores
                                                            |
                                                   candidates + overlay
                                                            |
                                                    level-0 CSV export
```

The default is 256x256 analysis pixels at pyramid level 0, with at least 20%
thumbnail tissue. RGB segmentation uses mean intensity <235; HSV uses saturation
>=20 and value <=245. Both use the same 3x3 elliptical opening and closing.

Focus converts uint8 RGB to OpenCV grayscale (0-255), then float64:

- **Laplacian:** population variance of `cv2.Laplacian(gray, CV_64F, ksize=3)` over eligible pixels.
- **Tenengrad:** mean of `Gx**2 + Gy**2` over the same support, using 3x3 Sobel kernels, scale 1, without normalization or a gradient cutoff.

Transparent padding is excluded and eligible tissue is eroded by one pixel so
derivative neighbors are valid. Fewer than two supported pixels gives no score.
Scores strictly below the active threshold are candidates. All rectangles use
**level-0 pixels**; thumbnail x/y ratios use actual resized dimensions. Edge tiles
use smaller reads. The 500-grid-visit cap includes background, and partial coverage
and read failures are explicit. [Methods](docs/reference/methods.md) gives the exact conventions.

## Benchmark and tests

```powershell
.\.venv\Scripts\python.exe -m slideqc.benchmark --calibration data/CMU-1-Small-Region.svs --evaluation data/JP2K-33003-1.svs --max-tiles 16 --review-manifest examples/original_review.json --output outputs/benchmark
.\.venv\Scripts\python.exe -m pytest -q
```

Run calibration before the app to load compatible calibrated defaults. Otherwise
the app labels its defaults experimental. All Gaussian-blurred copies (sigma
1, 2, 4 analysis pixels) stay with their original crop in the same split.
Thresholds are fitted on the calibration slide, then tested on the distinct slide.

Measured held-out results: 16 original crops and 48 blur variants.

| Metric | Threshold | Blur sensitivity | Original flag rate / FPR proxy | ROC AUC |
|---|---:|---:|---:|---:|
| Laplacian | 6127.6787 | 100% | 0% | 1.000 |
| Tenengrad | 24902.9303 | 100% | 87.5% | 1.000 |

Both metrics flagged every variant at each blur strength. Original crops were
visually reviewed by Codex, not labeled by a pathologist or verified with scanner
focus truth. The slides differ in tissue and physical resolution. AUC measures
ranking, so high AUC can coexist with a poorly transferred fixed threshold.

The complete demo scored **50 tissue tiles**, flagged **2 with Tenengrad (4%)**,
covered all 108 grid tiles, and had zero read failures. One CLI run took **0.488 s**.
This compares **2 targeted versus 50 tissue-tile visits** over the same area,
not scanner-time savings. Runtime varies with machine and cache.

The recorded validation passed **32 tests and 10 real-slide browser checks**.
Tests use generated fixtures and need no downloads. See the
[validation log](docs/reports/validation.md) and [recorded results](docs/reports/benchmark_results.json).

## 90-second demo

1. Open the small CMU slide at level 0 and 256-pixel tiles; explain coverage and tissue counts.
2. Enable the tissue mask and switch HSV -> RGB -> HSV.
3. Select Tenengrad with its calibrated threshold; click a hatched tile or its table row.
4. Show the crop, level-0 rectangle, both scores, and the status reason.
5. Compare the original with injected blur, then download the candidate CSV.
6. Show the held-out results and explain the Tenengrad threshold-transfer failure.

One failure example is original `(5120,3840)`, size 256x256: Tenengrad
**16745.918 <24902.930** flags it despite visible nuclei/fibers; Laplacian
**12730.947 >6127.679** accepts it. Texture and resolution can cause false alarms.
This is a possible failure, not a confirmed scanner diagnosis.

## Data and limits

The [official Aperio samples](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/) are
[CMU-1-Small-Region.svs](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1-Small-Region.svs)
(1.85 MiB, demo/calibration) and
[JP2K-33003-1.svs](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/JP2K-33003-1.svs)
(60.89 MiB, distinct evaluation). Published SHA-256 hashes are verified.
Other CMU-1 exports share source tissue and are not independent evaluation slides.

Gaussian blur covers one aspect of defocus. Human-mask IoU/Dice remain pending;
the annotation-manifest workflow is in [setup](docs/reference/setup.md). Clinical
accuracy needs human tissue/focus labels, more independent slides, controlled
resolution, and real scanner-defocus and rescan data. The generated low-texture
example is labeled separately as a demonstration.

The [documentation index](docs/README.md) links the full learning path,
data provenance, method details, and recorded evidence.
