# Artnet + Pinterest pilot — 2026-09-06

Completed an experimental 33³ color-LUT fit. **Not promoted to the app default:**
the held-out improvement gate failed. This is not a generative model, an
authenticated film-stock emulation, or a calibrated Raspberry Pi camera profile.

## References

- [Artnet artist page](https://www.artnet.com/artists/martin-parr/): direct HTML
  requests returned HTTP 403. One photograph explicitly linked from an accessible
  artwork listing downloaded successfully. No access controls were bypassed.
- [User-supplied Pinterest board](https://www.pinterest.com/jajaakk/martin-parr/):
  collected 23 candidates from its first public response, **not the entire board**.
- Selected 11 Pinterest images plus the Artnet photograph (12 distinct images).
  Removed an exact duplicate and a differently cropped/recolored copy of the
  Artnet photograph after contact-sheet review. Excluded ambiguous authors and
  identifiable later digital-period images. Some remaining pin attributions are
  provisional secondary claims, not independently authenticated authorship.
- Kept source URLs, image URLs, checksums, attribution evidence and exclusions
  in `data/references-pilot-2026-09-06/manifest.json`.
- Raw candidates, public board HTML, and collection/curation scripts are in
  `data/reference-collection-2026-09-06/`. The scripts are one-off collection
  records; curation should run into a fresh destination to avoid stale images.
- Rights were not established for redistribution/commercial training; these
  are not marked openly licensed. Reference images and model outputs remain
  gitignored. Nothing was uploaded or pushed.

## Training

Used the existing 399 `kodachrome-film/data/proxy-large` photographs as explicitly
marked stand-ins, **not Kodachrome-graded target images and not camera captures**.
Source split: 320 training / 79 validation. Target split: 10 training / 2 validation.
The corpus is far below the recommended 200 target images, so `--allow-small` was
explicitly enabled. Seed 0, 40 distribution-transfer rounds, 33³ LUT, default
regularization, source levels normalization, target exposure matching only.

Run from the project root (after installing this project's training extras):

```sh
parr-train --source ../kodachrome-film/data/proxy-large \
  --target data/references-pilot-2026-09-06 \
  --out artifacts/pilot-artnet-pinterest-2026-09-06 \
  --proxy-source --allow-small
```

The actual run used the sibling Kodachrome virtual environment's Python with
this project's directory on `PYTHONPATH`. Exact dependency versions and corpus
hashes are recorded in the generated `params.json`. The new repository still
has no commits, so its code revision is recorded as unknown.

## Results

Training completed and retained the artifact with exit code **3**:

| Check | Result |
|---|---|
| Held-out color-distribution distance | 0.03063 → 0.03253 (worse; lower is better) |
| Evaluation seed spread | 0.00102 |
| Training-pool distance | 0.01809 → 0.00524 |
| Improvement exceeds noise | FAIL |
| Neutral luminance and channel monotonicity | PASS |
| Neutral-axis chroma and gamut clipping | PASS |

The training/validation divergence is consistent with overfitting or reference
distribution mismatch, but two held-out target images are too few to diagnose
reliably. They are both Last Resort images; this small mixed-series corpus is
not a robust representation of the desired Common Sense saturated-negative look.
Do not tune against these two images until a gate happens to pass.

Artifacts: `artifacts/pilot-artnet-pinterest-2026-09-06/` contains `parr.cube`,
`params.json`, and `report/` with summary, metrics, before/after contact sheet,
ramps, and diagnostics. The bundled handcrafted preset is unchanged.

Next: expand and independently attribute a coherent color reference corpus,
deduplicate by scene before splitting, and use real ungraded camera captures as
source. Flash lighting and composition cannot be learned by a global color LUT.
