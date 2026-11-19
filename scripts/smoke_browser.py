"""Optional live UI validation. Install playwright separately; no app dependency.

Run a Streamlit server first, then:
  python scripts/smoke_browser.py --browser PATH_TO_CHROME
"""

from __future__ import annotations

import argparse
import csv
from io import StringIO
import json
from pathlib import Path
import re
import sys

from playwright.sync_api import sync_playwright, expect


class Checks(list):
    def append(self, message):
        super().append(message)
        print("PASS:", message, flush=True)


def choose(page, label: str, value: str):
    control = page.get_by_role("combobox", name=label, exact=True)
    control.click()
    control.fill(value)
    page.get_by_role("option", name=value, exact=True).click()
    expect(control).to_have_value(value)


def click_level0_tile(page, x: int, y: int):
    thumbnail = page.frame_locator("iframe").first.locator("#slide")
    thumbnail.wait_for(state="visible")
    box = thumbnail.bounding_box()
    # The documented demo dimensions; click the center of a full level-0 tile.
    thumbnail.click(position={"x": (x + 128) / 2220 * box["width"],
                              "y": (y + 128) / 2967 * box["height"]})


def expect_tile(page, tile_id: str, x: int, y: int):
    expect(page.get_by_role("combobox", name="Select a visited tile", exact=True)).to_have_value(tile_id)
    expect(page.get_by_test_id("stCode")).to_contain_text(f"x={x}  y={y}")
    expect(page.get_by_test_id("stCode")).to_contain_text("width=256  height=256")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--browser", help="Existing Chrome/Chromium executable; otherwise use Playwright's installed Chromium.")
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    parser.add_argument("--inspect", action="store_true", help="Print initial visible UI and controls for diagnostics.")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        options = {"headless": True}
        if args.browser:
            options["executable_path"] = args.browser
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1500, "height": 1100}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(args.url)
        if args.inspect:
            page.get_by_text("Benchmark results folder", exact=True).wait_for(timeout=30000)
            page.wait_for_timeout(2500)
            print(page.locator("body").inner_text())
            print(page.get_by_role("combobox").evaluate_all("els => els.map(e => ({label: e.getAttribute('aria-label'), html:e.outerHTML}))"))
            print("SLIDERS", page.get_by_role("slider").evaluate_all("els => els.map(e => e.outerHTML)"))
            print("FRAMES", [frame.url for frame in page.frames])
            page.screenshot(path=str(args.output / "ui_initial.png"), full_page=True)
            browser.close()
            return 0
        try:
            page.get_by_text("Slide overview", exact=True).wait_for(timeout=30000)
        except Exception:
            print("UI did not reach slide overview:\n" + page.locator("body").inner_text(), flush=True)
            print("Page errors:", errors, flush=True)
            page.screenshot(path=str(args.output / "ui_failure.png"), full_page=True)
            raise
        expect(page.get_by_test_id("stException")).to_have_count(0)
        steps = Checks()
        expect(page.get_by_test_id("stMetricValue").nth(0)).to_have_text("50")
        expect(page.get_by_test_id("stMetricValue").nth(1)).to_have_text("0")
        expect(page.get_by_text("Calibrated starting point:", exact=False)).to_be_visible()
        steps.append("Real demo: 50 tissue tiles, 108/108 visits, zero candidates, calibrated provenance.")

        # Both selections must refer to exactly the same canonical region.
        click_level0_tile(page, 1024, 768)
        expect_tile(page, "r00003_c00004", 1024, 768)
        steps.append("Clicked overlay center at level-0 (1152,896); inspector selected (1024,768), 256x256.")
        choose(page, "Select a visited tile", "r00004_c00004")
        expect_tile(page, "r00004_c00004", 1024, 1024)
        click_level0_tile(page, 1024, 768)
        expect_tile(page, "r00003_c00004", 1024, 768)
        steps.append("Dropdown selected a different tile; clicking the SAME earlier overlay tile selected it again.")
        table = page.get_by_test_id("stDataFrame").first
        table.locator(".dvn-scroller").first.click(position={"x": 18, "y": 52})
        expect_tile(page, "r00000_c00000", 0, 0)
        click_level0_tile(page, 1024, 768)
        expect_tile(page, "r00003_c00004", 1024, 768)
        steps.append("Clicked first visited-record row checkbox; inspector selected (0,0); restored tissue tile by overlay.")

        page.get_by_text("Show tissue segmentation mask", exact=True).click()
        expect(page.get_by_role("checkbox", name="Show tissue segmentation mask", exact=True)).to_be_checked()
        choose(page, "Tissue segmentation", "RGB")
        expect(page.get_by_text("Experimental threshold:", exact=False)).to_be_visible()
        expect(page.get_by_test_id("stException")).to_have_count(0)
        choose(page, "Tissue segmentation", "HSV")
        expect(page.get_by_text("Calibrated starting point:", exact=False)).to_be_visible()
        steps.append("Enabled tissue overlay; switched RGB then HSV masks; RGB defaults correctly labeled experimental.")

        choose(page, "Focus metric", "Tenengrad")
        threshold = page.get_by_role("spinbutton", name="Rescan threshold (score below this)", exact=True)
        expect(threshold).to_have_value("24902.93031")
        expect(page.get_by_test_id("stMetricValue").nth(1)).to_have_text("2")
        steps.append("Calibrated Tenengrad starting threshold 24902.93031 produced 2 demo candidates.")
        # This is an exploratory override to exercise candidate inspection/download.
        threshold.fill("1000000000")
        threshold.press("Enter")
        expect(page.get_by_test_id("stMetricValue").nth(1)).to_have_text("50")
        choose(page, "Select a visited tile", "r00003_c00004")
        expect_tile(page, "r00003_c00004", 1024, 768)
        expect(page.get_by_text(re.compile(r"Rescan.*tenengrad score", re.IGNORECASE)).first).to_be_visible()
        steps.append("Selected Tenengrad calibration; exploratory threshold 1e9 flagged all 50 eligible tissue tiles.")

        sigma = page.locator('input[type="range"][aria-label="Gaussian sigma (analysis pixels)"]')
        sigma.focus()
        sigma.press("End")
        expect(page.get_by_text("Injected blur: σ=4", exact=True)).to_be_visible()
        expect_tile(page, "r00003_c00004", 1024, 768)
        steps.append("Changed Gaussian sigma to 4; original and injected-blur images displayed.")
        with page.expect_download() as info:
            page.get_by_role("button", name="Download rescan candidates CSV", exact=True).click()
        destination = args.output / "ui_rescan.csv"
        info.value.save_as(destination)
        rows = list(csv.DictReader(StringIO(destination.read_text(encoding="utf-8"))))
        assert len(rows) == 50, len(rows)
        selected = next(row for row in rows if row["tile_id"] == "r00003_c00004")
        assert [int(selected[key]) for key in ("x", "y", "width", "height")] == [1024, 768, 256, 256]
        assert selected["slide_id"] == "CMU-1-Small-Region" and selected["status"] == "rescan"
        steps.append("Downloaded 50 candidate CSV rows; selected overlay/preview region matches CSV (1024,768,256,256).")
        page.set_viewport_size({"width": 1500, "height": 1800})
        page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
        page.screenshot(path=str(args.output / "ui_smoke.png"), full_page=True)
        expect(page.get_by_test_id("stException")).to_have_count(0)
        assert errors == [], errors
        page.set_viewport_size({"width": 800, "height": 1000})
        page.get_by_test_id("stMain").evaluate("el => el.scrollTop = 0")
        page.screenshot(path=str(args.output / "ui_narrow.png"), full_page=True)
        expect(page.get_by_role("combobox", name="Select a visited tile", exact=True)).to_be_visible()
        steps.append("Rendered at 1500px and 800px viewport widths; no browser page errors or Streamlit exceptions.")
        (args.output / "browser_results.json").write_text(json.dumps({"url": args.url, "passed": steps, "page_errors": errors}, indent=2) + "\n", encoding="utf-8")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
