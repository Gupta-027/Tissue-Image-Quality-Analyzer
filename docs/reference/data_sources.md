# Sample data and provenance

The data come from the [official OpenSlide Aperio sample directory](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/).
The downloader verifies the SHA-256 hashes published in the directory's
[index.yaml](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/index.yaml), retrieved 2026-11-19.

| Role | File | Directory size | Source | License |
|---|---|---:|---|---|
| Interactive demo / calibration | CMU-1-Small-Region.svs | 1.85 MB | Exported region of CMU-1, brightfield JPEG; only one pyramid level | CC0-1.0 |
| Distinct held-out slide | JP2K-33003-1.svs | 60.89 MB | Aorta tissue, brightfield JPEG 2000, YCbCr | Free to use and distribute, with or without modification |

Exact downloads:

- [CMU-1-Small-Region.svs](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1-Small-Region.svs)
- [JP2K-33003-1.svs](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/JP2K-33003-1.svs)

```powershell
python scripts/fetch_samples.py --sample demo
python scripts/fetch_samples.py --sample heldout
# Or download both:
python scripts/fetch_samples.py --sample all
```

Run from the repository root. Downloads stream in 1 MiB chunks, use socket timeouts,
retry up to three times, and only rename a `.part` file after verifying its hash.
Verified existing files are reused. `data/download_manifest.json` records source URLs,
actual byte counts and SHA-256 hashes. Downloaded slides are ignored by Git.
For restricted networks, download the linked files in a browser and put them in `data/`;
rerun the command to verify them. The automated tests need no slide downloads.

The larger CMU-1.svs and CMU-1-JP2K-33005.svs files share source tissue with the demo;
they are unsuitable as independent held-out slides. The chosen aorta file is a
different source, although two sample slides do not establish clinical generalization.
Compression and scanner/tissue differences can also shift score distributions.

Verified locally on 2026-11-19 with Python 3.13 and OpenSlide:

| File | Actual bytes | Level dimensions (width × height) | Reported downsample |
|---|---:|---|---|
| CMU-1-Small-Region.svs | 1,938,955 | 2220 × 2967 | 1.0 |
| JP2K-33003-1.svs | 63,847,265 | 15374 × 17497; 3843 × 4374; 1921 × 2187 | 1.0; 4.0003745252; 8.0017903103 |

Both files matched the published SHA-256, opened with the native OpenSlide library,
and yielded thumbnails and original tiles. `examples/original_review.json` records
the 16 original crops from each slide inspected by Codex at native crop size.
The reviewer is an AI agent, not a pathologist; these are visually plausible
reference originals, without independent scanner focus truth. The low-texture
aorta crops were retained, which exposes threshold transfer failures between slides.

Human tissue-mask annotation and clinical scanner-defocus labels are not supplied
by this dataset. Any algorithm-generated tissue mask is an estimate, not human truth.
