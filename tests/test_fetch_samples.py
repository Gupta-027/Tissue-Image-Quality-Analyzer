"""The downloader must never promote a corrupt/partial file to a usable slide."""

from io import BytesIO
import hashlib
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "fetch_samples", Path(__file__).parents[1] / "scripts" / "fetch_samples.py"
)
fetch_samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_samples)


class Response(BytesIO):
    def __init__(self, content: bytes, length: int | None = None):
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content) if length is None else length)}


def sample(monkeypatch, content: bytes):
    monkeypatch.setitem(fetch_samples.SAMPLES, "test", {
        "filename": "fixture.svs", "sha256": hashlib.sha256(content).hexdigest(),
        "license": "test", "source_slide": "generated",
    })


def test_verified_download_is_promoted_and_reused(tmp_path, monkeypatch):
    content = b"small generated fixture"
    sample(monkeypatch, content)
    monkeypatch.setattr(fetch_samples.urllib.request, "urlopen", lambda *a, **k: Response(content))
    metadata = fetch_samples.fetch_sample("test", tmp_path, retries=1)
    assert metadata["bytes"] == len(content)
    assert (tmp_path / "fixture.svs").read_bytes() == content
    assert not (tmp_path / "fixture.svs.part").exists()
    monkeypatch.setattr(fetch_samples.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network called for verified file"))
    assert fetch_samples.fetch_sample("test", tmp_path)["sha256"] == metadata["sha256"]


@pytest.mark.parametrize("content,length", [(b"corrupt", None), (b"good", 99)])
def test_invalid_download_is_never_promoted(tmp_path, monkeypatch, content, length):
    sample(monkeypatch, b"good")
    monkeypatch.setattr(fetch_samples.urllib.request, "urlopen", lambda *a, **k: Response(content, length))
    with pytest.raises(RuntimeError):
        fetch_samples.fetch_sample("test", tmp_path, retries=1)
    assert not (tmp_path / "fixture.svs").exists()
    assert not (tmp_path / "fixture.svs.part").exists()
