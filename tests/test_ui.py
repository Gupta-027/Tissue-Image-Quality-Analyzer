"""UI state tests use a generated slide adapter; no downloaded slide is needed."""
from pathlib import Path

import numpy as np
from PIL import Image
from streamlit.testing.v1 import AppTest

from slideqc import slide_io


class GeneratedSlide:
    def __init__(self, path):
        self.slide_id = Path(path).stem
        self.dimensions = (512, 256)
        self.level_dimensions = ((512, 256),)
        self.level_downsamples = (1.,)
        self.properties = {}
        rng = np.random.default_rng(24)
        gray = rng.integers(30, 160, (256, 512), dtype=np.uint8)
        self.rgb = np.stack([gray+50, gray, gray+30], axis=-1)
    def thumbnail(self, max_size=1200):
        image = Image.fromarray(self.rgb)
        image.thumbnail((max_size,max_size))
        return np.asarray(image)
    def read_tile(self, x, y, level, width, height):
        rgb = self.rgb[y:y+height,x:x+width]
        return np.dstack([rgb,np.full(rgb.shape[:2],255,np.uint8)])
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return None


def test_generated_slide_main_workflow(tmp_path, monkeypatch):
    (tmp_path / "fixture.svs").touch()
    monkeypatch.setenv("SLIDEQC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SLIDEQC_BENCHMARK_DIR", str(tmp_path / "no_benchmark"))
    monkeypatch.setattr(slide_io, "Slide", GeneratedSlide)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    assert not at.exception
    assert [m.value for m in at.metric[:3]] == ["2", "0", "0.0%"]
    assert len(at.get("download_button")) == 1
    # Same image support and geometry survive segmentation / metric switches.
    at.sidebar.selectbox[1].select("rgb").run()
    assert not at.exception
    at.sidebar.selectbox[2].select("tenengrad").run()
    assert not at.exception
    # First number_input is grid cap, last is focus threshold.
    at.sidebar.number_input[-1].set_value(10000000.).run()
    assert not at.exception
    assert at.metric[1].value == "2"
    at.checkbox[0].check().run()
    next(widget for widget in at.selectbox if widget.label == "Select a visited tile").select_index(1).run()
    assert not at.exception
    assert "x=256" in at.code[0].value
    at.select_slider[0].set_value(4.).run()
    assert not at.exception
    assert "x=256" in at.code[0].value


def test_no_sample_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDEQC_DATA_DIR", str(tmp_path))
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not at.exception
    assert any("fetch_samples.py" in item.value for item in at.info)
