# Image-processing and evaluation methods

The core modules live directly in `src/slideqc/`. They do not import Streamlit.
Both the dashboard and command-line analysis call `analyze_slide` in `analysis.py`.

## Slide loading and tissue masks

OpenSlide reads slide dimensions, pyramid dimensions, downsample factors, and
individual regions. The thumbnail's longest side is at most 1200 pixels. Its
actual rounded dimensions are used throughout the pipeline.

`segment_tissue` implements two configurable binary masks:

| Method | Default tissue rule |
|---|---|
| RGB baseline | Arithmetic mean of the three RGB channels <235 |
| HSV | OpenCV saturation >=20 and value <=245, both on a 0-255 scale |

Both methods apply a 3x3 elliptical opening then closing. Opening removes isolated
pixels; closing fills small holes. Kernel sizes 0 and 1 disable morphology.
The same cleanup makes the two algorithms comparable. Pale or thin tissue can
be missed at thumbnail resolution; neither mask is a human reference label.

## Tiles, coverage, and coordinate mapping

The default analysis uses level 0 and 256x256 analysis pixels. An area-weighted
thumbnail mask estimates the tissue fraction in each tile footprint. Tiles below
0.20 are background; eligible tissue tiles are read and scored. Partial edge tiles
use smaller reads rather than artificial image padding.

All canonical rectangles use half-open level-0 bounds:
`[x,x+width) x [y,y+height)`. In `coordinates.py`:

- Read origin = `floor(analysis_origin * reported_downsample)`.
- Adjacent canonical footprints share boundaries; the last reaches the true slide edge.
- OpenSlide receives a level-0 origin and analysis-level read width/height.
- Tissue labels are sampled at the actual read pixel centers using the floating downsample.
- `x_thumb = x0 * actual_thumbnail_width / level0_width`; y uses its own ratio.
  The inverse uses those same actual dimensions.

Separate thumbnail x/y ratios preserve alignment when resizing rounds the image.
Rendered outlines enclose each footprint; click hit-testing uses floating
half-open bounds. The overview, crop reader, and CSV refer to the same canonical
rectangle. A CSV row also records its analysis level and read dimensions.

The pipeline retains a thumbnail, masks, metadata rows, and one decoded tile.
The default cap includes **500 grid visits**, in row-major order, including
background. Coverage is visited slide area/grid tiles, not estimated tissue recall.
Unvisited regions have no tile outlines. A large slide's first rows may be blank;
increase the cap or choose a lower resolution level.

Tiles have four separate statuses: `background`, `acceptable`, `rescan`, and
`unevaluated`. Failed reads and insufficient valid tissue are unevaluated, with
reasons. They do not enter the flagged denominator. With zero scored tissue,
the fraction is 0 and the UI explains the empty result.

## Exact focus formulas

Convert uint8 RGB to grayscale using `cv2.COLOR_RGB2GRAY` on the 0-255 scale,
then float64. Exclude alpha values other than 255. Erode the eligible tissue mask
by one pixel, including the tile perimeter, so every scored derivative has valid
tissue neighbors. Let `E` be the supported pixels:

- **Variance of Laplacian** = population variance over `E` of
  `cv2.Laplacian(gray, CV_64F, ksize=3)`.
- **Tenengrad** = mean over `E` of `Gx**2 + Gy**2`, with 3x3 `cv2.Sobel`
  derivatives, `scale=1`, no gradient cutoff, and no normalization.

Fewer than two supported pixels gives no score. OpenCV's default reflected
derivative border is immaterial because perimeter scores are excluded.
Both raw scores are saved. A score **strictly below** the active threshold is
a rescan candidate; equality is acceptable.

These are edge-energy measures, so sharp tissue with little texture may score
low. Resolution, magnification, stain, compression, and tissue type shift the
score distribution. A universal threshold is not assumed.

## Calibration and held-out evaluation

The measured experiment uses 16 reference originals from each of two source
slides, with injected Gaussian blur at sigma 1, 2, and 4 **analysis pixels**.
OpenCV chooses the `(0,0)` kernel from sigma and uses `BORDER_REFLECT_101`.
Each metric scores the same original-derived tissue support for every copy;
benchmark crops containing transparent padding are excluded.

The crops in `examples/original_review.json` were visually inspected by Codex
without using focus scores to select them. They are plausible reference originals,
not pathologist labels or independently verified scanner-focus truth. The report
preserves the reviewer and review notes. Original flag rate is therefore an
**FPR proxy**, not measured specificity against confirmed sharp tissue.

All copies of a source crop stay in the same split. Thresholds maximize calibration
balanced accuracy subject to original flag rate <=10%, with deterministic tie
handling. Evaluation data never fit a threshold. ROC AUC uses negative raw score
as blur risk and average ranks for ties. Results include per-strength counts.

Calibration is `CMU-1-Small-Region.svs`; evaluation is the distinct aorta slide
`JP2K-33003-1.svs`. The small CMU-1 file is a region of CMU-1, so other CMU-1
exports are not independent held-out slides. With no evaluation slide, or a
known same-source export, the command uses nonoverlapping left/right regions
of the calibration file and labels the result a within-slide spatial experiment.
Unreviewed tissue crops are reservoir-sampled across the grid using seed 42.

The source physical sampling differs: CMU is 20x, 0.499 micrometers/pixel; JP2K
is 40x, 0.2498 micrometers/pixel. Tissue, stain, and resolution are confounded.
The UI uses a calibrated starting threshold only when level, downsample, tile
size, segmentation, and known MPP match (MPP within 2%). Other settings use labeled
experimental defaults. Calibration selected crops with >=50% thumbnail tissue;
the demo additionally analyzes tiles down to 20%.

Recorded held-out measurements are in
[benchmark_results.json](../reports/benchmark_results.json):

| Metric | Threshold | Blur sensitivity (48 copies) | Original FPR proxy (16 crops) | AUC |
|---|---:|---:|---:|---:|
| Laplacian | 6127.6787 | 100% | 0% | 1.000 |
| Tenengrad | 24902.9303 | 100% | 87.5% | 1.000 |

Both flagged all 16 variants at each blur strength. On calibration, Laplacian
sensitivity was 100% and original flag rate 0%; Tenengrad sensitivity was 95.83%
and original flag rate 6.25%. AUC measures ranking over possible thresholds:
perfect held-out ranking can coexist with a poorly transferred fixed threshold.

## Human tissue-mask evaluation

Quantitative segmentation IoU and Dice remain pending without human masks.
`evaluation.py` accepts binary PNGs paired with level-0 rectangles in a manifest.
Both methods run at the reference-mask resolution with identical morphology;
invalid slide padding is excluded. Microaggregated valid-pixel scores are:

- IoU = `intersection / union`.
- Dice = `2 * intersection / (predicted_tissue + reference_tissue)`.

Empty/empty masks score 1; no valid pixels scores null. A mask must cover the
manifest rectangle, even if downsampled. Paths resolve relative to the manifest.
The user records the human annotator; software cannot establish that provenance.
Region-resolution metrics may differ from full-thumbnail results.

## Interpretation and limitations

The full demo proposed 2 targeted visits versus 50 tissue-tile visits over the
same analyzed area. This is a **tile-count comparison**, not a measured scanner
speedup. Pipeline runtime is measured separately from UI drawing and downloads.

One reviewed original at `(5120,3840)`, size 256x256, has resolved nuclei/fibers
but Tenengrad 16745.918 falls below its threshold 24902.930. Laplacian 12730.947
exceeds its threshold 6127.679. This is a possible texture/resolution false alarm,
not an established scanner diagnosis. The generated low-texture patch is a
separately labeled illustration and does not enter the measured benchmark.

Gaussian blur approximates one aspect of defocus. Only two convenience slides and
correlated crop variants were tested; no clinical or patient-level performance is
established. Dust, folds, necrosis, compression, and tissue texture can confound
scores. Further verification needs human tissue masks, expert focus labels,
independent slides at controlled physical resolution, scanner defocus/z-stack
data, and outcomes from actual rescans.
