# Parr refinement: September 7 experiment results

## Outcome

All four requested experiment steps were executed. The production starter is
unchanged. No experimental artifact was deployed or promoted.

The most promising isolated change is **highlight protection**. It retains more
colour in bright surfaces without adding saturation everywhere. The combined
candidate adds useful colour to objects and outdoor scenes, but also increases
warm skin saturation and some channel clipping. It is not a universal replacement.

All three camera-trained pilots are **rejected**: each worsens the held-out
distribution distance and fails the neutral-grey monotonicity gate. Increasing
the neutral cap alone does not fix this result. These artifacts are retained as
evidence, not recommended for photography.

## 1. Frozen regression set

- Snapshot: `data/refinement-2026-09-07/regression/`.
- 26 ungraded/starter/v3 triplets: 78 photographs plus capture log and two
  baseline artifact files = **81 checksum-verified files**.
- Full SHA256 manifest: [regression-manifest.json](regression-manifest.json).
- Starter LUT identity: `fa89d3b2075f2d3ebaf6cd3c080e5fcaf5683bca`.
- Original photos, original references, `parr/data/parr.cube` and
  `parr/data/params.json` were verified unchanged after the runs.

These scenes were already reviewed and used to guide the design. They are a
regression/development set, **not an untouched final test**. The frozen v3 JPEGs
are retained as observed outputs; their folder name does not identify their LUT.

The capture log's grain seed is reused for each candidate. Candidate comparisons
use the same JPEG input, runtime normalization and grain settings. Reprocessing
a saved ungraded JPEG is not a promise of bit-identical reproduction of the
original camera-decoded frame, so reports distinguish recorded starter JPEGs
from the freshly processed `starter-control`.

## 2. Starter-derived candidates

Artifact parent: `artifacts/refinement-2026-09-07/starter-derived/`.

| Candidate | Controls | Mean chroma | Mean within-image std L | Mean p95 L | Channel-boundary pixels |
|---|---|---:|---:|---:|---:|
| starter-control | unchanged starter | 0.02508 | 0.25943 | 0.92341 | 12.44% |
| colour-only | colour 0.25 | 0.02680 | 0.25944 | 0.92339 | 13.19% |
| highlights-only | highlights 0.60 | 0.02515 | 0.25382 | 0.90360 | 11.95% |
| shadows-only | shadows 0.60 | 0.02526 | 0.25855 | 0.92341 | 12.27% |
| combined | all three above | 0.02713 | 0.25295 | 0.90358 | 12.62% |

Measurements are arithmetic means of per-image, grain-free runtime results,
sampled every fourth pixel in each dimension. They differ from pooled raw-JPEG
statistics in the earlier discussion. Channel-boundary pixels have at least one
channel at <=1 or >=254; this includes pre-existing capture clipping and does not
by itself prove all detail was lost.

The colour control boosts restrained chroma, tapers off at true neutral and high
chroma, and reduces its action on skin-like colours. Hue-preserving gamut
compression retains red/orange ordering on test swatches. Highlight protection
reduces the starter's upper tone lift. Shadow protection reduces tone darkening
in a skin-like colour range; it is not face segmentation and also affects similarly
coloured wood/objects. Grain remains at the starter setting, strength 0.004.

## 3. Visual review and selection

Reports: `data/refinement-2026-09-07/starter-comparison/`.
There are seven contact-sheet pages, 130 full-resolution candidate/control JPEGs,
and a `metrics.json` with per-image and input-defined colour/lightness regions.

- **124829, orange notebook:** highlight protection increases mean chroma in
  the frame's coloured-highlight mask from 0.04599 to 0.05913 while reducing
  channel-boundary occupancy from 82.27% to 76.54%. The mask is not a hand-selected
  notebook crop. Colour-only goes the wrong direction for boundary occupancy.
- **124940, portrait:** shadow-only raises the shaded-skin proxy's mean L from
  0.33218 to 0.35123, but also raises its chroma. The combined render still looks
  too warm in shaded skin. A colour-range mask does not solve mixed lighting.
- **125223, books:** stronger cyan, green, red and yellow are useful, but the
  combined candidate raises coloured-highlight boundary occupancy above the
  starter. Highlight-only is the safer individual improvement here.
- **125912, street:** colour-only/combined strengthen restrained building and
  foliage colours; highlight-only retains a quieter, more restrained result.

Selection: **shortlist highlights-only for the next user comparison**; retain
combined as a colour-direction experiment, not a production recommendation.
Do not promote any candidate based on global chroma alone.

### Safety caveat

The original handcrafted starter and all four derived variants fail the trainer's
generic channel-monotonicity and full-cube boundary gates. The starter's interior
boundary occupancy is about 70.3%; the derived range is 68.3–76.0%. This uniform
colour-cube probe is different from clipping measured in actual photos. Grey
ramps remain monotone and effectively neutral. Thresholds were not relaxed;
these failures are visible in `metrics.json`. Production safety remediation is
not claimed by this experiment, and the existing starter was not modified.

## 4. Scene-separated camera retraining

Inputs: `data/refinement-2026-09-07/training-inputs/`.

| Corpus | Fitting | Validation/development |
|---|---|---|
| Camera | 15 September 6 images, one bedroom | 10 September 7 images: dining room, bathroom, street |
| Parr references | 19 images | 4 images in two related-scene groups |

All 15 approved September 6 images are from one room. A random image split would
have put neighbouring shots on both sides. Instead, all are one training group.
The other 16 September 7 regression shots overlap that room and are explicitly
**in-domain**, not scene-held-out. None of the 26 September 7 files is fitted.

References were selected from the existing curated corpus: six Benidorm images
from Another, one Artnet Last Resort image, seven Artsy images, and nine Rocket
Gallery images. The two sunbather close-ups and two decorated-cake images are
validation groups. One file per existing duplicate group is enforced. Publisher/
gallery attribution is preserved; no licence or training permission is inferred.
Ektar, Velvia, Pinterest and provisionally attributed personal images were not used
in this pilot. All 150 prior reference records have a selection/exclusion decision.

Versioned metadata: [camera-partition.json](camera-partition.json),
[reference-partition.json](reference-partition.json),
[selection.json](selection.json), [exclusions.json](exclusions.json).
Images and full generated artifacts remain gitignored.

The fits share the same pools, scene partitions, normalization, seed 0, 33-cubed
LUT, 40 transfer rounds, strength 1, smoothness 0.01 and identity regularization 1.
Only the requested neutral cap varies.

| Requested neutral cap | Before distance | After distance (lower better) | Actual max neutral chroma | Decision |
|---|---:|---:|---:|---|
| 0.005 | 0.056739 | 0.082814 | 0.013630 | Reject |
| 0.0075 | 0.056739 | 0.082693 | 0.015118 | Reject |
| 0.010 | 0.056739 | 0.082593 | 0.017507 | Reject |

All three fail `improvement_exceeds_noise` and `grey_axis_monotone`. The other
three existing gates pass. **The requested cap is not an achieved hard bound:**
the final LUT's measured neutral chroma exceeds it. The legacy fitter applies
neutral correction before subsequent constraint projections; these runs expose
that the overall result does not jointly meet the requested properties. No solver
or gate was changed to disguise the failure.

Visually the trained candidates warm skin/wood and lift some scenes, while the
street result looks flatter than the starter. Differences between cap settings
are much smaller than the shared shortcomings.

Artifacts are in `artifacts/refinement-2026-09-07/trained/cap-005`, `cap-0075`,
and `cap-010`, each with its own report and recorded code hashes. Their runtime
comparison is `data/refinement-2026-09-07/trained-comparison/`: seven contact-sheet
pages and 104 full-resolution trained/control JPEGs.

### Limits and next useful work

Fifteen neighbouring captures from one room cannot establish broad camera
generalization; four reference validation images also give a fragile estimate.
This pilot tests the requested direction, not an adequate final training corpus.
It does not prove all camera-trained models are worse or that more photographs
alone will fix the fitting method.

Before another production candidate: correct and test the fitter's joint
neutral/monotonic constraints; collect diverse camera scenes including people,
coloured objects and outdoor lighting; reserve new whole scenes before looking at
results; expand the coherent, attributed reference subset. Keep fresh final-test
scenes out of both fitting and candidate selection. Preserve the starter meanwhile.

## Reproduce

Run from the project root with the project's virtual environment and training
dependencies. Destinations must be new; the commands below name the existing run
for documentation, so use a fresh dated directory to rerun.

```sh
.venv/bin/python -m parr.experiments.regression \
  --source /Users/george.babanau/2026-09-07 \
  --graded /Users/george.babanau/2026-09-07-trained-comparison-v3 \
  --out data/refinement-2026-09-07/regression

.venv/bin/python -m parr.experiments.candidates \
  --baseline data/refinement-2026-09-07/regression/baseline \
  --out artifacts/refinement-2026-09-07/starter-derived

.venv/bin/python scripts/prepare_refinement.py \
  --camera /Users/george.babanau/2026-09-06 \
  --references data/references-personal-01-curated-v1 \
  --snapshot data/refinement-2026-09-07/regression \
  --out data/refinement-2026-09-07/training-inputs

.venv/bin/python -m parr.experiments.train \
  --inputs data/refinement-2026-09-07/training-inputs \
  --out artifacts/refinement-2026-09-07/trained/cap-005 --neutral-cap 0.005
# Repeat with separate destinations for --neutral-cap 0.0075 and 0.010.
# Exit status 3 means artifact retained but acceptance gates failed.

.venv/bin/python -m parr.experiments.evaluate \
  --snapshot data/refinement-2026-09-07/regression \
  --artifacts artifacts/refinement-2026-09-07/starter-derived \
  --out data/refinement-2026-09-07/starter-comparison
# Repeat with --artifacts artifacts/refinement-2026-09-07/trained
# and a separate comparison output directory.
```

## Verification

- Full suite including packaging and local HTTP tests: **362 passed**.
- New experiment modules, curation script and tests: Ruff clean.
- Snapshot: 81 checksums verified; original images/reference inputs unchanged.
- Packaged starter cube and parameters unchanged byte-for-byte.
- Independent code review: path handling, fitting-pool separation, publication
  protection and source-code provenance reviewed; substantive findings resolved.
- No Pi deployment, firmware change, remote push or new image download.
