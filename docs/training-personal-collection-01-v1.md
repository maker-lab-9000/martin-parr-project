# Personal collection 01 — curated training run v1

The user supplied 135 photographs in `data/references-personal-collection-01/`.
All were readable. The original folder was left untouched; byte-level checksums
were verified again after curation.

## Curation

| Input / decision | Count |
|---|---:|
| Earlier expanded reference corpus | 56 |
| New personal collection files | 135 |
| New distinct references selected | 94 |
| New files excluded as duplicate copies | 27 |
| New files held for quality, attribution or period checks | 14 |
| Combined training/evaluation corpus | 150 |

All 135 new images were reviewed in contact sheets. Byte and decoded-pixel
checksums identified exact duplicates. A 63-bit perceptual hash with Hamming
distance ≤12 screened resized/re-encoded copies. SIFT descriptor matching and
RANSAC homography additionally screened crop differences; candidates were
visually reviewed, not accepted automatically. Two extra duplicate photographs
were confirmed (breakfast and seaside kiosk). A false match involving newspaper
details in unrelated photographs was rejected. One copy per confirmed group is
retained, preferring the existing attributed corpus, otherwise a suitable larger
reproduction. The kiosk's wider composition was preferred explicitly.

The 14 held files comprise three small images (short side below 250 pixels),
three watermarked images, one two-photo collage, three attribution questions,
and four period/date holds. Some held files are also duplicates; counts are
mutually exclusive according to the recorded decision precedence. No watermarks
were removed and no images were recolored, reconstructed, or cropped for training.
Originals and excluded files remain available for a later review.

Selected personal references are recorded as user-supplied, not independently
authenticated. Original filenames and checksums are retained; unknown source
URLs, dates, and series are not invented. Several file titles are misleading or
generic, so filenames alone are not treated as photographer verification. Source
links can be added to the manifest later. Existing attribution caveats remain.

## Reproducibility

- Original collection: `data/references-personal-collection-01/`
- Curated corpus: `data/references-personal-01-curated-v1/`
- Per-file decisions and attribution: curated corpus `manifest.json`
- Review sheets, audit records, crop-match results, and one-off scripts:
  `data/personal-collection-01-review-v1/`
- Trained artifact: `artifacts/personal-collection-01-v1/`

All data, review assets and trained artifacts are gitignored. No input images
were deleted, moved, modified or uploaded. Rights were not inferred from public
availability or user selection.

The fitting settings are unchanged: seed 0, 40 transfer rounds, 33³ LUT, strength
1, smoothness 0.01, identity regularization 1, neutral-axis cap 0.005, and 20%
held-out images. Sources receive levels normalization; targets receive exposure
matching without white balance or levels stretching. The 399 source photographs
remain marked as proxies, not Raspberry Pi camera captures. `--allow-small` is
still required because there are fewer than the recommended 200 references.

```sh
parr-train --source ../kodachrome-film/data/proxy-large \
  --target data/references-personal-01-curated-v1 \
  --out artifacts/personal-collection-01-v1 \
  --proxy-source --allow-small
```

The actual run uses the sibling Kodachrome virtual environment with this project
on `PYTHONPATH`. Exact versions, corpus hashes and the command are retained in
the artifact's `params.json`. Collection scripts are archived one-off tools;
their paths are local and curation requires a fresh destination.

## Evaluation

**Training completed successfully (exit code 0); all five gates passed.**
120 target images were used for fitting and 30 for validation; the source split
was 320 training / 79 validation. No model or threshold tuning was performed.

| Metric / gate | Result |
|---|---|
| Held-out distribution distance (lower is better) | 0.01799 → 0.00875 (about 51% reduction) |
| Evaluation seed spread | 0.00030 |
| Training-pool distance | 0.01903 → 0.00390 |
| Improvement exceeds noise | PASS |
| Neutral luminance monotonicity | PASS |
| Channel monotonicity | PASS |
| Neutral-axis chroma | PASS (0.00539) |
| Clipped interior volume | PASS (0.0) |

The held-out before/after sheet was inspected. The artifact loaded successfully
through the runtime loader and processed a full-resolution held-out source image
through the normalization/LUT/grain pipeline. Focused artifact, pipeline and batch
tests also passed: **49 tests**. All original and curated-file checksums matched.
Passing these numerical checks makes this a candidate for visual testing, not a
guarantee of photographer resemblance or camera calibration.

Results are recorded in the artifact's `report/summary.txt` and `metrics.json`.
The report includes held-out before/after contact sheets and color diagnostics.
Previous models and the bundled preset are preserved. Different corpus runs have
different target validation sets, so their raw distance values must not be ranked
as though they were measured against the same references. The within-run paired
before/after result is the acceptance check; no thresholds are relaxed to pass it.

## Testing from another project

Install this project's runtime, then copy `parr.cube` and `params.json` together
from the trained artifact folder. No training photos are needed for inference.

```sh
parr-process /path/to/ungraded-photos /path/to/personal-01-results \
  --artifacts /path/to/personal-collection-01-v1
```

Always pass `--artifacts` for this experiment; the package default is still the
handcrafted starter. A color LUT cannot recreate flash direction, composition,
or the photographer's subject choices, and proxy training is not camera calibration.
