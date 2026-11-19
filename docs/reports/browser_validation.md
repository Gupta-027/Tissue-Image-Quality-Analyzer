# Live browser validation

Executed on 2026-11-19 against the real Streamlit server at
`http://127.0.0.1:8501`, using Python 3.13, Playwright 1.65.2 and cached Chromium
1243. The browser ran headlessly; no visible windows were launched.

Playwright is an optional development check, not an application dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
# If no compatible browser is already installed:
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m streamlit run app.py --server.headless true
```

In another terminal, the exact successful command on the validation machine was:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_browser.py --browser C:/Users/HP/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe
```

Omit `--browser` to use Playwright's default installed Chromium. Run from the
repository root with the documented sample slides and reviewed benchmark outputs
present; the assertions intentionally expect this reproducible demonstration.

The final browser run passed all ten workflow checks:

1. Opened `CMU-1-Small-Region.svs`: 50 analyzed tissue tiles, 108/108 visited grid
   tiles, 100% coverage, zero read failures, zero candidates at calibrated
   Laplacian threshold 6127.6787; calibration provenance was visible.
2. Clicked thumbnail position corresponding to level-0 `(1152,896)`. Inspector
   selected `r00003_c00004`, footprint `(1024,768,256,256)`.
3. Selected `(1024,1024)` through the dropdown, then clicked the same earlier
   overlay tile; the inspector returned to `(1024,768)`.
4. Clicked the first visited-record table row checkbox. Inspector selected `(0,0)`.
   Clicking the overlay restored the selected tissue region.
5. Enabled the tissue mask, switched HSV to RGB and back. RGB defaults were
   correctly labeled experimental; HSV returned to the calibrated configuration.
6. Selected Tenengrad. Its calibrated threshold 24902.93031 produced two demo
   candidates.
7. Applied an explicit exploratory threshold of `1e9`, which flagged all 50 eligible
   tissue tiles. This override exercises candidate inspection and CSV export; it
   is not a measured focus result or a recommended threshold.
8. Changed injected Gaussian blur sigma to four analysis pixels. Original and blur
   images were visible, and the selected tile stayed `(1024,768)` after the rerun.
9. Downloaded the rescan CSV: exactly 50 candidate rows. The selected overlay and
   inspector region matched the CSV row's slide ID, status and
   `(x,y,width,height)=(1024,768,256,256)`.
10. Rendered at desktop and 800-pixel viewport widths. No browser page exceptions
    or Streamlit exception elements appeared. Screenshots were visually inspected.

Artifacts, ignored by Git, are `outputs/ui_smoke.png`, `outputs/ui_narrow.png`,
`outputs/ui_rescan.csv` and `outputs/browser_results.json`. The desktop screenshot
deliberately shows the exploratory threshold and all candidates; the measured
benchmark results remain unchanged.

Browser verification found and helped fix a real selection-state bug: changing the
blur slider could restore an older dropdown selection. The final application uses
stable selection keys and callbacks, and both the browser check and AppTest now
verify selection persistence. A temporary stale module error during development
was resolved by restarting the Streamlit process after a function signature changed.

This checks the local demonstration, not clinical validity or exhaustive browser
compatibility. Automated small-fixture tests remain independent of browser and
slide downloads.

## Reorganization validation

On 2026-11-19, the same browser command above was rerun after moving the page
implementation into `src/slideqc/ui/dashboard.py`, `sidebar.py` and `panels.py`,
with `app.py` as the launcher. The server was restarted before this check.
The command exited successfully: **all 10 real-slide workflow checks passed**,
including repeated overlay selection, table selection, selection persistence
after changing blur strength, and CSV coordinates matching the inspector.
No JavaScript page errors or Streamlit exceptions were reported. The screenshots
and `outputs/browser_results.json` were refreshed by this run.
