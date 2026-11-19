"""Small OpenSlide adapter. Importing SlideQC itself needs no native library."""

from pathlib import Path

import numpy as np


class SlideError(RuntimeError):
    """An actionable slide-open/read failure suitable for the CLI and UI."""


class Slide:
    def __init__(self, path):
        self.path = Path(path)
        self.slide_id = self.path.stem
        if not self.path.is_file():
            raise SlideError(f"Slide not found: {self.path}. Run python scripts/fetch_samples.py first, or select an existing .svs file.")
        if self.path.suffix.lower() != ".svs":
            raise SlideError(f"Unsupported file extension {self.path.suffix!r}; select an Aperio .svs slide.")
        try:
            import openslide
        except (ImportError, OSError) as exc:
            raise SlideError("OpenSlide is unavailable. Install openslide-python and openslide-bin in this Python environment; see the README native-library steps.") from exc
        try:
            self._slide = openslide.OpenSlide(str(self.path))
        except Exception as exc:
            raise SlideError(f"Cannot open {self.path.name} with OpenSlide: {exc}. Confirm the download completed and the file is supported.") from exc
        self.dimensions = tuple(self._slide.dimensions)
        self.level_dimensions = tuple(tuple(d) for d in self._slide.level_dimensions)
        self.level_downsamples = tuple(float(d) for d in self._slide.level_downsamples)
        self.properties = dict(self._slide.properties)

    def thumbnail(self, max_size=1200):
        if max_size < 1:
            raise ValueError("Thumbnail maximum size must be positive.")
        try:
            return np.asarray(self._slide.get_thumbnail((max_size, max_size)).convert("RGB"))
        except Exception as exc:
            raise SlideError(f"Unable to read the thumbnail for {self.path.name}: {exc}. Reopen the file; check for an incomplete or corrupt download.") from exc

    def read_tile(self, x0, y0, level, width, height):
        if not 0 <= level < len(self.level_dimensions):
            raise ValueError(f"Analysis level must be between 0 and {len(self.level_dimensions) - 1}.")
        if width <= 0 or height <= 0:
            raise ValueError("Read dimensions must be positive.")
        try:
            return np.asarray(self._slide.read_region((int(x0), int(y0)), int(level), (int(width), int(height))).convert("RGBA"))
        except Exception as exc:
            # OpenSlide errors latch on the handle. Report every subsequent failed
            # read too; do not silently return blank tiles or misclassify padding.
            raise SlideError(f"Tile read failed at level-0 ({x0}, {y0}), level {level}: {exc}. Reopen the slide and check file integrity.") from exc

    def close(self):
        self._slide.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
