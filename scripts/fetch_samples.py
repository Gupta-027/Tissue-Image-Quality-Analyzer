"""Stream verified OpenSlide Aperio samples without loading the files into memory.

Usage: python scripts/fetch_samples.py --sample all
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


BASE_URL = "https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/"
# Published hashes: BASE_URL + "index.yaml" (retrieved 2026-11-19).
SAMPLES = {
    "demo": {
        "filename": "CMU-1-Small-Region.svs",
        "sha256": "ed92d5a9f2e86df67640d6f92ce3e231419ce127131697fbbce42ad5e002c8a7",
        "license": "CC0-1.0",
        "source_slide": "CMU-1",
    },
    "heldout": {
        "filename": "JP2K-33003-1.svs",
        "sha256": "6205ccf75a8fa6c32df7c5c04b7377398971a490fb6b320d50d91f7ba6a0e6fd",
        "license": "Free to use and distribute, with or without modification",
        "source_slide": "JP2K-33003-1",
    },
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_sample(name: str, destination: Path, retries: int = 3) -> dict:
    sample = SAMPLES[name]
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / sample["filename"]
    url = BASE_URL + sample["filename"]
    if target.exists():
        if file_sha256(target) == sample["sha256"]:
            print(f"Verified existing {target} ({target.stat().st_size:,} bytes)", flush=True)
            return {**sample, "url": url, "bytes": target.stat().st_size}
        raise ValueError(f"Existing {target} has the wrong SHA-256. Rename it before retrying.")
    partial = target.with_suffix(target.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"Downloading {url} (attempt {attempt}/{retries})", flush=True)
            request = urllib.request.Request(url, headers={"User-Agent": "SlideQC/0.1"})
            digest = hashlib.sha256()
            received = 0
            last_progress = time.monotonic()
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as handle:
                expected_length = response.headers.get("Content-Length")
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if time.monotonic() - last_progress >= 5:
                        print(f"  {received / (1024 * 1024):.1f} MiB received", flush=True)
                        last_progress = time.monotonic()
            if expected_length is not None and received != int(expected_length):
                raise ValueError(f"Truncated download: {received} bytes; expected {expected_length}")
            if digest.hexdigest() != sample["sha256"]:
                raise ValueError(f"SHA-256 mismatch for {sample['filename']}; downloaded file is unusable")
            partial.replace(target)
            print(f"Saved {target}: {received:,} bytes; SHA-256 verified", flush=True)
            return {**sample, "url": url, "bytes": received}
        except (OSError, urllib.error.URLError, ValueError) as exc:
            last_error = exc
            print(f"  Download failed: {exc}", flush=True)
            if partial.exists():
                partial.unlink()
            if attempt < retries:
                time.sleep(attempt)
    raise RuntimeError(f"Could not fetch {url}. Check internet/proxy access, or download it manually to {target}. Last error: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", choices=["demo", "heldout", "all"], default="demo")
    parser.add_argument("--destination", type=Path, default=Path("data"))
    args = parser.parse_args()
    names = list(SAMPLES) if args.sample == "all" else [args.sample]
    try:
        records = [fetch_sample(name, args.destination) for name in names]
    except (RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    manifest = args.destination / "download_manifest.json"
    existing = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    merged = {item["filename"]: item for item in existing + records}
    manifest.write_text(json.dumps(list(merged.values()), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
