# Executed validation

Date: 2026-11-19. Workspace: `C:\Projects\Tissue_Rescan`. Windows, Python 3.13.1,
CPU only. Commands below ran from the workspace. Versions are recorded in
`requirements-lock.txt`; runtime dependencies passed `pip check`.

| Command | Actual outcome |
|---|---|
| `python -m venv .venv` | Created local environment |
| `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | Installed project, OpenCV, NumPy, Streamlit, OpenSlide Python and native OpenSlide wheel, pytest |
| `.\.venv\Scripts\python.exe scripts/fetch_samples.py --sample all` | Both official slides downloaded, SHA-256 verified, opened with OpenSlide |
| `.\.venv\Scripts\python.exe -m pytest -q` | **32 passed**, final run 10.57 s; fixtures require no slides or network |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements found |
| `.\.venv\Scripts\python.exe -m slideqc.benchmark --synthetic --max-tiles 16 --output outputs/synthetic` | Executed generated-fixture experiment: both metrics blur sensitivity 1, original flag rate 0, AUC 1; not real-slide evidence |
| `.\.venv\Scripts\python.exe -m slideqc.benchmark --calibration data/CMU-1-Small-Region.svs --evaluation data/JP2K-33003-1.svs --max-tiles 16 --review-manifest examples/original_review.json --output outputs/benchmark` | Executed held-out experiment: Laplacian threshold 6127.6787, blur sensitivity 1, original FPR proxy 0, AUC 1; Tenengrad threshold 24902.9303, sensitivity 1, original FPR proxy .875, AUC 1 |
| `.\.venv\Scripts\python.exe -m slideqc.evaluation --slide data/CMU-1-Small-Region.svs --output outputs/segmentation` | Saved RGB/HSV visual comparison; quantitative status **pending**, no human masks supplied |
| `.\.venv\Scripts\python.exe -m slideqc.cli data/CMU-1-Small-Region.svs --max-tiles 0 --metric tenengrad --threshold 24902.930314160512 --output outputs/demo` | 108/108 grid, 50 tissue, 2 candidates, flagged fraction .04, no read failures, 0.488385 s pipeline |
| `.\.venv\Scripts\python.exe -m slideqc.cli data/JP2K-33003-1.svs --level 1 --max-tiles 0 --output outputs/heldout_level1` | 288/288 grid, 64 tissue, no read failures, 0.997 s pipeline; threshold 100 explicitly experimental at this level |
| `.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501` | Server launched and served real slide workflow; see [browser validation](browser_validation.md) for interaction checks |

The real demo thumbnail was 898×1200 for a 2220×2967 source, so independent x/y
mapping was exercised. The held-out level-1 test used actual noninteger
downsample 4.0003745252 and a last edge tile of 3×22 analysis pixels with
level-0 rectangle `(15361,17409,13,88)`. Its overlay was visually inspected.
Unit tests independently check fractional coordinates and transparent padding.

Corrections encountered during implementation:

- The initial sandbox network denied package/download sockets. Retried with the
  environment's approved network escalation; both installations and downloads
  succeeded. An early editable install before `src/` existed failed, then passed
  after scaffolding was written.
- The first UI fixture test selected a sidebar control instead of the tile
  dropdown. Its selector now locates the control by label and the test passes.
- Browser testing caught a stale imported calibration signature while source was
  being edited under Streamlit hot reload. Restarting the server loaded the
  current implementation. Fresh-start validation is used for final interaction
  checks.
- An extra browser persistence assertion found that changing Gaussian sigma could
  restore a stale tile selection. The tile dropdown now has a stable key, and
  dropdown/table callbacks update shared selection before rendering. The new
  generated-fixture regression checks that changing sigma preserves the crop.

The measured reports retain source IDs, split groups, settings, raw per-variant
scores, review provenance and source physical resolution. Human tissue-mask
IoU/Dice and real scanner-defocus performance remain unmeasured. Annotation-code
tests use generated truth and do not substitute for human pathology labels.
No data-access or native-library blocker remains on the tested Windows system.
Other operating systems, clinical scanner hardware and actual rescans were not
tested. Pipeline runtime is wall-clock analysis time, not scanner time.

## Repository organization validation

The project was subsequently reorganized on 2026-11-19 for easier reading and
interview explanation. The root `app.py` now starts the dashboard in
`src/slideqc/ui/`; controls and display sections have separate modules. The
original 16 core cases were split into topic-based test files without changing
their assertions. Documentation is grouped into guides, references, and reports.

Checks after the reorganization:

- `.\.venv\Scripts\python.exe -m pytest -q`: **32 passed in 2.65 s**.
- `.\.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `.\.venv\Scripts\python.exe -m compileall -q src app.py scripts tests`: passed.
- All **25 local Markdown links** in the root README and documentation resolved.
- `.\.venv\Scripts\python.exe -m slideqc.cli data/CMU-1-Small-Region.svs --max-tiles 0 --metric tenengrad --threshold 24902.930314160512 --output outputs/organized_project_check`:
  108 grid visits, 50 scored tissue tiles, 2 candidates (4%), no read failures,
  full coverage, measured runtime **0.771389 s**.
- The freshly restarted Streamlit app passed the same **10 real-slide browser
  checks**. Selection, blur controls, and CSV geometry still agree; see the
  browser validation report in this folder.

The earlier timing and benchmark measurements above remain historical executed
results. This organization change does not change the image-processing methods.
