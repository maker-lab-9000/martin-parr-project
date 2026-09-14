# Finished-LUT highlight protection — 2026-09-12

This comparison evaluates the opt-in `--highlights 0.6` starter against the
frozen September 7 baseline and a newly written unprotected starter. It tests
the general finished-LUT operation from the September 11 implementation plan.
It does not change the bundled look or select a production default.

## Method

The existing snapshot at `data/refinement-2026-09-07/regression` contains 26
captures. Its manifest and image hashes passed `verify_snapshot`. This is a
reviewed regression set, not a blind final test. The older experiment note
referenced in the plan is absent from this branch.

The comparison uses `parr.experiments.evaluate.evaluate_candidates` with an
explicit mapping of candidate names to artifact paths. The equivalent CLI
expects the **parent** of the candidate artifact directories as `--artifacts`;
the plan's example passes a single artifact directory instead.

Normalization and grain settings match the frozen baseline. Region metrics
exclude grain, sample every fourth pixel, and define masks from normalized
input. Reported aggregate means weight each capture by its mask pixel count.
Shaded-skin measurements use the evaluator's colour-range proxy, not semantic
skin segmentation. A supplementary measurement applies the same Pillow LUT
path to the normalized sample and records mean Oklab a/b for that proxy.

The frozen LUT differs from the current in-memory starter by at most
5.066395e-07, consistent with six-decimal `.cube` serialization. The additional
current-unprotected control separates serialization from the new operation.

## Results

Snapshot manifest SHA-256:
`9e3db25a69dde1c174350dfbd117fa1a4610ed711a357438f2fa403f4a2b9d81`.
The frozen and newly written unprotected controls produced identical sampled
metrics and the same LUT SHA-1 (`fa89d3b2075f2d3ebaf6cd3c080e5fcaf5683bca`).
The protected artifact SHA-1 is `f69c797ee7b41cd9761278ac9376100a15d528a2`.

| Region / metric | Unprotected | Highlights 0.6 |
| --- | ---: | ---: |
| Coloured highlights: pixels | 149,102 | 149,102 |
| Mean Oklab L | 0.884109 | 0.857959 |
| Mean Oklab chroma | 0.056868 | 0.056877 |
| Channel-boundary occupancy | 42.7721% | 0.2180% |
| Shaded-skin proxy: pixels | 177,119 | 177,119 |
| Mean Oklab L | 0.404724 | 0.404381 |
| Mean Oklab chroma | 0.063541 | 0.063535 |
| Channel-boundary occupancy | 20.4569% | 20.4569% |
| Mean Oklab a | 0.03992191 | 0.03991400 |
| Mean Oklab b | 0.04617229 | 0.04617040 |

Boundary occupancy means at least one 8-bit channel is <= 1 or >= 254.
The aggregate directional acceptance criteria are met on this reviewed set:
highlight chroma rises, boundary occupancy falls, and mean shaded-skin a/b do
not increase. The chroma increase is only 0.00000946 (about 0.017%); this does
not establish a perceptible gain. The major measured change is reduced
highlight lightness and boundary occupancy. No blind visual assessment was
performed and no production value is promoted.

The LUT grey axis remains monotone. Both the frozen starter and the protected
starter fail the channel-monotonicity diagnostic; the starter has no trainer
projection. The LUT boundary-volume diagnostic falls from 0.703031 to
0.477393. Maximum grey-axis chroma is 3.73e-08 unprotected and 2.79e-06 after
protected artifact serialization. The trained path separately enforces its
existing monotone projection.

## Interpretation limits

The operation changes only positive lightness lift, preserving Oklab a/b
before conversion to sRGB. This differs from the old starter-specific
experiment, which adjusted its tone curve before its chroma gamut compression.
A finished LUT has already undergone that compression, so this operation
cannot recover chroma previously discarded there. Lowering L can also move
saturated colours outside the lower sRGB boundary; bounded conversion then
clips them and can change stored chroma and hue.

Unit measurements found maximum a/b change of 0.008486 on clipped requests,
versus 5.96e-08 in gamut. At full protection, clipping can leave residual stored
lightness lift up to 0.000827 on the tested starter. The trainer additionally
projects the protected result back to its monotonic constraints; that projection
can further change colour and lightness. These results concern the starter,
not a newly trained corpus.

## Reproduce the paired evaluation

Use new output directories if these already exist:

```sh
.venv/bin/parr-preset \
  --out data/refinement-2026-09-12-highlight-protection/artifacts/current-unprotected
.venv/bin/parr-preset --highlights 0.6 \
  --out data/refinement-2026-09-12-highlight-protection/artifacts/highlights-06
.venv/bin/python -m parr.experiments.evaluate \
  --snapshot data/refinement-2026-09-07/regression \
  --artifacts data/refinement-2026-09-12-highlight-protection/artifacts \
  --out data/refinement-2026-09-12-highlight-protection/comparison
```

The full per-capture metrics and rendered contact sheets are local, gitignored
outputs under the comparison directory. For each region and metric, the
aggregate is `sum(capture_metric * mask_pixels) / sum(mask_pixels)`, excluding
empty masks.
