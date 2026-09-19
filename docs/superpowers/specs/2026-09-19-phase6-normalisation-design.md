# Phase 6: gentler, configurable normalisation — design

Date: 2026-09-19. Branch: `feat/phase6-normalisation`. Roadmap phase 6
([roadmap](../plans/2026-09-11-rpi4-imx708-roadmap.md),
[progress](../plans/2026-09-13-rpi4-imx708-progress.md)). Approved in
conversation on 2026-09-19; this document is the record the plan argues from.

## Problem, as measured

From the 108-shot IMX708 pilot (`source_imx708/2026-09-19/captures.jsonl`,
Pi 4, bundled starter):

- `levels.gamma` (the luma tone exponent; `< 1` brightens) has a median of
  0.75; 55 of 108 shots got a strong lift (`< 0.75`). Outdoor-ish scenes
  (`Lux > 1500`, n=31) got a median of **0.57**; dim scenes (n=77) 0.76.
- 89 of 108 shots already had their highlights at the ceiling
  (`levels.high >= 1.0`), and **53 of those were lifted anyway** — pushed
  further into clipping.
- `exposure_gain` is 1.0 on every shot, so the brightening is entirely the
  tone gamma.
- Grey-world white balance runs on frames the ISP's AWB has already balanced
  (colour temperature 4100–5100 K). It adds up to **1.60× blue** on
  foliage/yellow-dominated scenes. The two shots the user judged worst are the
  two strongest pushes: `172404` (γ 0.59, blue 1.51) and `172258` (γ 0.64,
  blue 1.60).
- `171656`: centre-weighted AE metered the shaded foreground (`Lux` 723,
  24.8 ms exposure) and blew the bright house and sky **in the original**,
  before any processing.

Indoor frames — even, low-contrast light — got γ ≈ 0.9–1.0 and mild WB, and
the user judges them very good. That is the behaviour to preserve.

Two mechanisms, therefore: the normaliser lifts already-clipped frames, and
it white-balances twice. A third, smaller one is capture-side metering.

## Goals

1. Never lift a frame into clipping; keep the full lift for genuinely dark
   frames.
2. No second white balance on frames the ISP has already balanced.
3. Capture-side highlight protection available for strong-light scenes.
4. Parameters chosen on the pilot set by measurement, then frozen, so Phase 5
   fits the LUT once against a stable normalisation.
5. Exact Pi/trainer parity preserved: the Pi applies precisely what the LUT
   was fitted on.

## Non-goals

Retraining (Phase 5); grading resolution or grain (Phase 7); scene statistics
(Phase 8); any change to the LUT or the LUT fit; per-frame or runtime
overrides of a trained artifact's normalisation.

## D1. Clipping-aware lift

Where: `compute_gains()` in `pifilm/normalize.py`, levels path. This is the
single implementation both runtimes call — `normalize_u8` (Pi) and
`normalize_float` (trainer) each consume its `Gains.levels` unchanged — so
parity is automatic.

**New parameter.** `NormalizeParams.levels_lift_highlight_ref: float | None
= None`. Validation in `__post_init__`: `None`, or `0 < x <= 1`. `None` means
the behaviour is bit-for-bit today's.

**New constant.** `LEVELS_HIGHLIGHT_LIN = 0.97`: a linear luminance at or
above this (≈ sRGB 254/255) counts as "at the ceiling". Not a parameter.

**Algorithm.** After the existing stretch, median and `raw_gamma`:

```
highlight_frac = mean(lum_b >= LEVELS_HIGHLIGHT_LIN)     # see note
if ref is None:
    damped = raw_gamma
elif raw_gamma < 1.0:                                     # a lift
    weight = clip(1 - highlight_frac / ref, 0.0, 1.0)
    damped = 1.0 - (1.0 - raw_gamma) * weight
else:                                                     # darkening: untouched
    damped = raw_gamma
gamma = clip(damped, levels_gamma_min, levels_gamma_max)
```

Note on `highlight_frac`: it is computed over **all** white-balanced,
pre-stretch pixels (`lum_b`), **not** the statistics mask. The mask excludes
luminance above 0.90, so it can never see the ceiling — that exclusion is
exactly why a bright frame reads as "dark" to the median and gets lifted.

`clamped["levels"]` tests the *damped* value against the gamma bounds (that
is the value being clamped), plus the existing stretch check.

**Recorded diagnostics.** `Gains.levels` gains three keys, always present on
the levels path: `raw_gamma`, `highlight_frac`, `lift_weight` (1.0 when no
damping applied, including when `ref` is `None`). They flow into
`captures.jsonl` through the existing generic serialisation and appear in
`pifilm-process` diagnostics. Existing keys are unchanged.

**Properties.** Monotone in `highlight_frac`. An indoor frame (≈0 % at the
ceiling) keeps its full lift. A frame with at least `ref` of its pixels at the
ceiling gets no lift. Darkening is unaffected. A second pass over a normalised
image has median ≈ target, so `raw_gamma ≈ 1` and the lift is ≈ 0 — the
"second pass is mild" invariant holds. With `levels=False` the path is
untouched.

## D2. White balance: per artifact, trust the ISP

No new normalisation code: `NormalizeParams.white_balance` already exists.

- **Trainer.** `pifilm-train --no-source-white-balance` (argparse
  `dest="source_white_balance", action="store_false"`, mirroring the existing
  `--no-source-levels`), threaded through `fit()` into the source
  `NormalizeParams`. Also `--source-lift-highlight-ref FLOAT` (default: the
  `NormalizeParams` default) so Phase 5 trains with, and records, the same
  damping the Pi applies. Both are recorded in `params.json` through the
  existing `normalize.to_dict()`.
- **Bundled starter.** The starter's normalisation is defined in one place,
  `pifilm/preset.py` (`write_starter`). Set `white_balance=False` and
  `levels_lift_highlight_ref=<the value D4 selects>` there and regenerate
  `pifilm/data/params.json` from it: run `write_starter` into a temporary
  directory, copy only its `params.json` over the bundled one, and assert the
  regenerated `.cube` is byte-identical to `pifilm/data/pifilm.cube`
  (`starter_lut()` is deterministic, so `lut_sha1` must not change).
- **Why not a runtime flag.** The pipeline does not know a frame's backend and
  must not learn it: a `--no-white-balance` on `pifilm-capture` would let a
  flag silently break parity on a trained artifact. Per-artifact is the
  parity-correct lever, and it is how `levels` already works.
- **Trade-off, stated.** This is per artifact, not per camera. The bundled
  starter now targets the IMX708, the default mount. The V4L2/USB path has no
  ISP AWB; a USB user regenerates a starter with `pifilm-preset` and
  re-enables white balance in their artifact. Document this in the README's
  camera-backends section and in `docs/how-it-works.md`.

## D3. Capture-side AE controls

Verified on the Pi (libcamera 0.7.2, 2026-09-19): `AeConstraintModeEnum`
{`Normal`, `Highlight`, `Shadows`, `Custom`}, `AeMeteringModeEnum`
{`CentreWeighted`, `Spot`, `Matrix`, `Custom`} and the `ExposureValue`
control all exist. Today none is set, so libcamera's defaults apply:
centre-weighted metering, normal constraint, EV 0.

- `Picamera2Camera(..., ae_constraint="normal", ae_metering="centre",
  ev=0.0)`. Validation, raising `CameraError` like `autofocus` does:
  `ae_constraint ∈ {normal, highlight, shadows}`, `ae_metering ∈ {centre,
  spot, matrix}`, `-8.0 <= ev <= 8.0`.
- `_apply_camera_controls` sets `AeConstraintMode`, `AeMeteringMode` and
  `ExposureValue` (always, 0.0 being neutral, for determinism). Each enum
  lookup uses the same `try/except AttributeError` guard as
  `NoiseReductionMode`, skipping and recording "unset" on an older libcamera.
- `pifilm-capture` flags: `--ae-constraint {normal,highlight,shadows}`
  (default `normal`), `--ae-metering {centre,spot,matrix}` (default
  `centre`), `--ev FLOAT` (default `0`). All three join the existing
  Picamera2-only rejection list so V4L2, `--device` and `--fake` reject them.
- Defaults reproduce today's behaviour exactly. The effect of non-default
  values shows in the already-recorded `ExposureTime` and `Lux`.
- Docs: the README camera-backends flag table and `docs/picamera2-bringup.md`
  gain the three flags; the bring-up checklist gains a follow-up to shoot a
  171656-type scene with `--ae-constraint highlight` and confirm the original
  keeps its highlights.

## D4. Evaluation on the pilot set

New module `pifilm/experiments/normalisation.py`, following the experiments
convention (argparse `main()`, run as
`python -m pifilm.experiments.normalisation`, never changes production
defaults).

**Inputs.** `--source DIR` (a capture folder of `*_original.jpg`);
`--artifacts DIR` (default: the bundled starter); `--refs 0.02,0.05,0.10`
(candidate `levels_lift_highlight_ref` values — the current behaviour,
`None`, is always evaluated too); `--no-wb` (also evaluate every candidate
with `white_balance=False`); `--shots 171656,172012,...` (stems always
included in the contact sheet); `--sample N` (extra random shots, fixed
seed); `--out DIR` (gitignored).

**Method.** For every original × candidate parameter set: normalise with the
candidate `NormalizeParams`, apply the artifact's LUT, **no grain** — so only
normalisation differs between columns.

**Metrics** on the graded 8-bit output, per shot per candidate: `clip_pct`
(pixels with any channel ≥ 254), `p1_luma` and `p5_luma` (BT.709 luma
percentiles in [0, 1]; high means lifted, faded blacks), and the applied
`gamma`, `wb_blue`, `highlight_frac`, `lift_weight`. Aggregates per
candidate: mean and median `clip_pct`, count of shots with `clip_pct > 1 %`,
median `p1_luma`/`p5_luma`, and the gamma distribution (min, median, max),
split indoor/outdoor when `captures.jsonl` is present beside the originals
(outdoor = `camera_metadata.Lux > 1500`, the threshold used in the analysis
above; shots without a record are reported unsplit).

**Outputs** under `--out`: `report.json`, `report.md` (the tables), and
`contact_sheet.jpg` — rows are the named plus sampled shots, columns are
*original | current | each candidate*, tiles at most 480 px wide, JPEG
quality 85. Deterministic: fixed seed, grain off.

**Write-up.** `docs/experiments/2026-09-19-imx708-normalisation.md` with the
aggregate tables, the chosen values and their justification, and **one**
downscaled sheet (≤ 1 MB) committed under
`docs/experiments/imx708-normalisation/`. Raw outputs stay gitignored.

**Selection rule** (proposed; the user confirms on the sheet — this is a
call-in point): the smallest `ref` that brings outdoor `clip_pct` down to the
indoor level and moves the six named shots' `p5_luma` back toward their
originals', while leaving indoor gamma unchanged within 0.02. White balance
off is adopted for the IMX708 starter if it removes the blue push on the
named shots without shifting indoor neutrals.

## D5. Repository hygiene

`source_imx708/` — 325 files, roughly 2 GB of the user's pilot photos — is
untracked and **not** gitignored. Add `source_*/` (every sensor source
folder) to `.gitignore` with a comment, alongside `data/` and `artifacts/`,
before anything else on this branch. The evaluation takes the folder as an
argument and never commits it.

## Data formats

- `params.json` → `normalize` gains `levels_lift_highlight_ref` (nullable
  float). `PARAMS_VERSION` stays 2: the field is additive with a default, and
  `NormalizeParams.from_dict` ignores unknown keys, so old artifacts load
  unchanged.
- `captures.jsonl` → `levels` gains `raw_gamma`, `highlight_frac`,
  `lift_weight`.

## Testing

TDD throughout; full suite and ruff green at every task.

- `normalize`: `ref=None` reproduces today's `Gains` exactly on a fixture; a
  dark frame with 0 % at the ceiling gets `damped == raw_gamma`; a frame with
  at least `ref` at the ceiling gets no lift; a partial fraction gives the
  linear weight; darkening is untouched; `highlight_frac` is computed over
  all pixels, proven with a fixture whose ceiling pixels lie outside the
  stats mask; the diagnostics are recorded; validation and `to_dict` round
  trip; "second pass is mild" still holds with `ref` set; `normalize_u8` and
  `normalize_float` agree on gamma for the same image.
- Trainer: both flags thread into the source `NormalizeParams` and into
  `params.json`.
- Preset: the regenerated bundled `params.json` has white balance off and
  `ref` set, and `lut_sha1` is unchanged.
- Camera: with the fake libcamera, the controls dict carries the three
  controls with the right enums; defaults leave today's dict unchanged;
  invalid values raise `CameraError`; V4L2 and `--fake` reject the flags.
- Experiments: on synthetic images, `clip_pct` is higher for a blown frame
  than a normal one, the contact sheet and `report.json` are written, and the
  report schema is stable.

## Execution

Subagent-driven development; the controller orchestrates and does not
implement. Opus: D1, D2 (trainer and preset), D3, the D4 script. Sonnet: D5,
documentation, the write-up scaffold, the params regeneration check. Order:
D5 → D1 → D2 → D3 → D4 → run the evaluation → **user validates the sheet and
values** → freeze (preset + `params.json`) → docs and progress log → final
whole-branch review → PR.

User call-in points: (1) the evaluation sheet and the values to freeze;
(2) the final PR.

## Risks

- Changing the starter's normalisation changes output for anyone grading with
  it on a USB camera. Documented; the IMX708 is the default mount.
- The local, proxy-trained `personal-collection-01-v1` artifact keeps its own
  `params.json` (`ref` absent → `None`), so it is unaffected until the Phase 5
  retrain.
- The AE flags need one real shot to accept on hardware (a 171656-type scene
  with `--ae-constraint highlight`). Listed in the bring-up checklist; not a
  blocker for this phase.
