# Explain SlideQC in an interview

Use the wording below as a starting point, then explain it in your own words.
Keep the code and measured outputs available so you can support each claim.

## A 90-second explanation and demo

| Time | Show | Explain |
|---|---|---|
| 0–15 s | Small CMU slide and summary | The aim is to suggest tissue regions for review; the rescan is a coordinate simulation |
| 15–30 s | HSV and RGB mask comparison | Tissue filtering avoids spending tile reads and focus measurements on slide background |
| 30–50 s | Tenengrad candidates and one selected crop | The outline, crop and exported rectangle all use one level-0 coordinate system |
| 50–65 s | Original beside injected blur | Gaussian blur reduces high-frequency detail; both metrics are measured on identical tissue support |
| 65–80 s | Candidate CSV | On the recorded complete demo, 2 candidates compare with 50 analyzed tissue-tile visits |
| 80–90 s | Held-out results and failure crop | A threshold can fail to transfer even when ranking remains strong |

For this walkthrough use CMU-1-Small-Region, HSV, level 0, tile size 256, minimum
tissue fraction 0.20, and calibrated Tenengrad threshold **24902.9303**. The
recorded run has 108 grid tiles, 50 analyzed tissue tiles and 2 candidates.
Changing settings can change those counts.

## A five-minute code tour

1. **Minute 1 — `analysis.py`:** Show `AnalysisConfig`, `AnalysisResult`, and the
   `analyze_slide()` loop. Explain its inputs, tile records and summary.
2. **Minute 2 — `segmentation.py` and `focus.py`:** Show the two tissue conditions
   and the two derivative formulas. Explain grayscale conversion and valid support.
3. **Minute 3 — `coordinates.py`:** Trace a tile from analysis pixels to level 0
   and then to the actual thumbnail dimensions. Mention smaller edge tiles.
4. **Minute 4 — `benchmark.py`:** Show grouped source crops, calibration-only
   threshold selection, and the independent slide used for evaluation.
5. **Minute 5 — UI and tests:** Show the small launcher and UI modules, then a
   coordinate or padding test. Explain why processing also runs through the CLI.

## Questions you should be ready to answer

### 1. What problem does the project solve?

It screens likely tissue regions for low edge-energy scores and exports where
those tiles lie on the original slide. It helps demonstrate a possible targeted
review workflow. It does not prove that a region needs a physical rescan.

### 2. Why use classical methods instead of deep learning?

The weekend scope and lack of labeled scanner-defocus data favor a transparent
baseline. Thresholds and derivatives are fast on a CPU and easy to inspect.
A learned method would require suitable labels and independent validation to
justify its added complexity.

### 3. Why segment tissue before measuring focus?

Blank glass also has very little texture, which would produce low focus scores.
The thumbnail mask filters those regions cheaply before full tile reads. Its
mistakes can still affect focus results, especially for pale or thin tissue.

### 4. How do the two focus scores work?

Variance of Laplacian measures variation in a second-derivative response.
Tenengrad averages squared horizontal and vertical Sobel gradients. Both detect
high-frequency structure, so Gaussian blur usually lowers their scores. They
measure image texture as well as focus, which is a central limitation.

### 5. Why exclude mask boundaries and padding?

A sudden tissue-to-background or valid-to-transparent transition can create an
artificial edge. Eroding eligible pixels by one pixel ensures each scored 3×3
derivative neighborhood contains valid tissue. Partial edge tiles use actual
read sizes; invalid alpha pixels do not contribute.

### 6. How do you know the CSV refers to the displayed region?

Every tile has a level-0 rectangle created by the shared coordinate module.
Drawing converts that rectangle to thumbnail space, and preview reads use its
original location. Unit tests check rounding and edge cases; the real browser
check matched an overlay selection, crop and CSV rectangle `(1024,768,256,256)`.

### 7. How were thresholds selected without leaking evaluation data?

Each metric selects its own threshold using only calibration records: maximize
balanced accuracy while keeping original-crop flag rate at most 10%. All copies
of an original remain in one split. CMU-1-Small-Region is used for calibration;
the distinct JP2K aorta slide is used for evaluation.

### 8. How can AUC be 1.0 while Tenengrad flags 87.5% of originals?

AUC measures the ordering of scores across all possible thresholds. A fixed
threshold measures one operating point. The held-out blurred copies ranked
below the originals, but many originals also fell below the threshold selected
on CMU tissue. A good ranking did not give a useful transferred cutoff.

### 9. What is a concrete failure example?

The held-out original at `(5120,3840)` has visible sparse nuclei or fiber
boundaries. Tenengrad **16745.918** is below **24902.930**, so it is flagged;
Laplacian **12730.947** is above **6127.679**. Texture and physical resolution
may contribute, but scanner truth is unavailable, so the cause is unconfirmed.

### 10. What do the reported numbers establish?

With 16 originals and 48 blurred copies on the held-out slide, both metrics
detected all injected blur. Original-crop flag rates were 0% for Laplacian and
87.5% for Tenengrad. Originals were AI visually reviewed, not clinically labeled;
these rates are proxies. CMU is 0.499 µm/px and JP2K is 0.2498 µm/px, so tissue,
stain and resolution differences are confounded in this small experiment.

### 11. How does the project handle large slides and failures?

OpenSlide reads one analysis tile at a time. A configurable grid-visit cap bounds
demo work and the UI reports partial coverage. Background, acceptable, candidate
and unevaluated are separate states. Failed reads stay visible in the report and
never become candidates just because scoring failed.

### 12. What would you improve next?

Collect human tissue masks and expert/scanner focus labels, then evaluate across
more independent slides at controlled physical resolution. Compare additional
failure types and measure whether actual rescanning improves the image. The
current 2-versus-50 count is not a measured scanner-time saving.

For the data flow and vocabulary, return to the [project guide](project_guide.md).
