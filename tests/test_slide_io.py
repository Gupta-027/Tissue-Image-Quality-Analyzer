"""Slide-open failures should explain how the user can fix the input."""

import pytest

from slideqc.slide_io import Slide, SlideError


def test_missing_and_unsupported_files_have_actionable_errors(tmp_path):
    with pytest.raises(SlideError, match="Slide not found"):
        Slide(tmp_path / "missing.svs")
    path = tmp_path / "image.png"
    path.write_bytes(b"not a slide")
    with pytest.raises(SlideError, match="Unsupported file extension"):
        Slide(path)
