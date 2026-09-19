# IMX708 normalisation candidates — 2026-09-19

This experiment picks the frozen normalisation for the bundled starter
(Phase 6 of the [IMX708 roadmap](../superpowers/plans/2026-09-11-rpi4-imx708-roadmap.md),
[design](../superpowers/specs/2026-09-19-phase6-normalisation-design.md)). It
measures, on real IMX708 pilot photos, whether the clipping-aware highlight
lift (`levels_lift_highlight_ref`) and turning source white balance off stop
the normaliser from lifting already-clipped frames further, and it selects
the values frozen into `pifilm/data/params.json`.

## Question

The 108-shot pilot showed two problems with the bundled starter's
normalisation on Picamera2/IMX708 frames (full numbers in the
[design doc](../superpowers/specs/2026-09-19-phase6-normalisation-design.md#problem-as-measured)):
outdoor shots got a strong tone lift (median gamma 0.577) while already
clipped, and a second, redundant grey-world white balance pushed blue up to
1.6x on frames the ISP's AWB had already balanced. Does capping the lift by
the fraction of pixels at the ceiling, and disabling the source-side white
balance, fix both without changing how good the indoor shots already look?

## Method

`pifilm/experiments/normalisation.py`, run against the 108-shot pilot capture
folder, evaluating the bundled starter's LUT with every combination of
candidate `levels_lift_highlight_ref` and white balance on/off:

```sh
.venv/bin/python -m pifilm.experiments.normalisation \
  --source source_imx708/2026-09-19 \
  --artifacts /tmp/pre-phase6 \
  --no-wb \
  --shots 171656,172012,172111,172144,172258,172404 \
  --out data/phase6-normalisation-eval
```

> **Since the freeze, `--artifacts` matters.** The `current` column is the
> given artifact's *own* normalisation, and the bundled starter now **is** the
> chosen candidate — so running this without `--artifacts` makes `current`
> identical to `ref=0.02+nowb`. To reproduce the tables, build the pre-Phase-6
> starter first and point at it:
>
> ```sh
> .venv/bin/python -c "
> from pifilm.artifacts import write_artifact
> from pifilm.preset import starter_lut
> from pifilm.normalize import NormalizeParams
> from pifilm.grain import GrainParams
> write_artifact('/tmp/pre-phase6', starter_lut(), NormalizeParams(levels=True), GrainParams())
> "
> ```
>
> That is the starter's normalisation as it stood before this phase (white
> balance on, no lift damping) with a byte-identical LUT
> (`lut_sha1 fa89d3b2075f2d3ebaf6cd3c080e5fcaf5683bca`).

`--refs` defaults to `0.02,0.05,0.10` (evaluated alongside the current,
undamped behaviour); `--no-wb` doubles every candidate with
`white_balance=False`; `--shots` pins the six shots discussed in the design
doc onto the contact sheet in addition to six random samples (`--sample 6`,
default). For every original x candidate, the pipeline normalises with that
candidate's `NormalizeParams`, applies the bundled starter's LUT, and never
applies grain, so only normalisation differs between columns; originals are
downscaled to 1536 px on the long side (`--max-side`, default) before
grading, for speed. Indoor/outdoor is split by `camera_metadata.Lux > 1500`
from `captures.jsonl` recorded alongside the originals.

Metrics, on the graded 8-bit output, per shot: `clip_pct` (pixels with any
channel >= 254), `p1_luma`/`p5_luma` (BT.709 luma percentiles), and the
applied `gamma`/`wb_blue`/`highlight_frac`/`lift_weight`. Aggregates: mean and
median `clip_pct`, count of shots with `clip_pct > 1%`, median
`p1_luma`/`p5_luma`, and the gamma distribution (min/median/max).

## Results

### Aggregate tables

All figures are medians unless noted; full output in `report.md` under the
gitignored `--out` directory (not committed).

| Candidate | Split (n) | Median gamma | Median clip% | Median p5 luma |
| --- | --- | ---: | ---: | ---: |
| current (today's behaviour) | all (108) | 0.750 | 4.566 | 0.0812 |
| current | outdoor (31) | 0.577 | 12.051 | 0.1704 |
| current | indoor (77) | 0.764 | 2.836 | 0.0779 |
| ref=0.02 | all (108) | 1.000 | 3.865 | 0.0326 |
| ref=0.02 | outdoor (31) | 1.000 | 9.469 | 0.0370 |
| ref=0.02 | indoor (77) | 0.976 | 2.551 | 0.0322 |
| ref=0.05 | all (108) | 0.873 | 4.144 | 0.0462 |
| ref=0.05 | outdoor (31) | 1.000 | 9.708 | 0.0415 |
| ref=0.05 | indoor (77) | 0.856 | 2.746 | 0.0468 |
| ref=0.10 | all (108) | 0.814 | 4.325 | 0.0605 |
| ref=0.10 | outdoor (31) | 0.845 | 11.012 | 0.0656 |
| ref=0.10 | indoor (77) | 0.810 | 2.799 | 0.0591 |
| current+nowb | all (108) | 0.753 | 3.696 | 0.0796 |
| current+nowb | outdoor (31) | 0.577 | 9.253 | 0.1700 |
| current+nowb | indoor (77) | 0.765 | 2.308 | 0.0779 |
| **ref=0.02+nowb (chosen)** | all (108) | 1.000 | 3.178 | 0.0323 |
| **ref=0.02+nowb (chosen)** | outdoor (31) | 1.000 | 8.167 | 0.0367 |
| **ref=0.02+nowb (chosen)** | indoor (77) | 0.975 | 2.079 | 0.0317 |
| ref=0.05+nowb | all (108) | 0.872 | 3.391 | 0.0459 |
| ref=0.05+nowb | outdoor (31) | 1.000 | 8.167 | 0.0417 |
| ref=0.05+nowb | indoor (77) | 0.856 | 2.203 | 0.0459 |
| ref=0.10+nowb | all (108) | 0.812 | 3.476 | 0.0593 |
| ref=0.10+nowb | outdoor (31) | 0.837 | 8.689 | 0.0659 |
| ref=0.10+nowb | indoor (77) | 0.811 | 2.254 | 0.0588 |

Current, undamped: 53 of 108 shots were lifted while already clipped (see the
design doc). With `ref=0.02+nowb`, outdoor median gamma goes from 0.577 to
1.00 (no lift) and outdoor median clip% roughly halves (12.05% -> 8.17%;
outdoor *mean* clip%, the statistic quoted in `pifilm/preset.py`, goes 13.31%
-> 9.54%). The indoor lift is also largely removed at `ref=0.02` — median gamma
goes from 0.764 to 0.975, i.e. most of the lift is gone, not a small change.
`ref=0.05` would have kept more of it (indoor median gamma 0.856) but damps the
problem shots only partially; the user chose 0.02 for those shots
(see Decision, below). Indoor clip% falls a little regardless, because
turning white balance off also removes some blue-channel clipping.

### Named shots (current -> chosen: `ref=0.02+nowb`)

Gamma / clip% / p5 luma:

| Shot | Current gamma/clip%/p5 | Chosen gamma/clip%/p5 |
| --- | --- | --- |
| 172404 | 0.59 / 10.8 / 0.204 | 1.00 / 6.9 / 0.055 |
| 172258 | 0.65 / 10.9 / 0.137 | 1.00 / 5.2 / 0.040 |
| 171656 | 0.70 / 10.4 / 0.093 | 1.00 / 5.4 / 0.028 |
| 172111 | 0.74 / 5.9 / 0.086 | 1.00 / 2.6 / 0.032 |
| 172012 | 0.92 / 11.7 / 0.055 | 1.00 / 10.2 / 0.039 |
| 172144 | 0.97 / 2.1 / 0.109 | 0.98 / 1.4 / 0.107 |

`172404` and `172258` were the two shots the user judged worst under the
current behaviour (design doc: the strongest gamma lift combined with the
strongest blue push, up to 1.6x). Both drop their tone lift to identity and
lose most of their extra clipping. `172144`, an already well-behaved indoor
shot, keeps almost the same gamma (0.97 -> 0.98) and clip% (2.1 -> 1.4),
which is the "leave good indoor shots alone" property working as intended —
in contrast to the indoor set as a whole, where the median lift is largely
removed (see above).

![Original, current starter and chosen (ref=0.02, white balance off) side by side for the six named shots](imx708-normalisation/named-shots.jpg)

Columns: original | current starter | chosen (`ref=0.02`, white balance off).

## Decision

**Frozen: `levels_lift_highlight_ref=0.02`, `white_balance=False`.** The two
serious candidates were `ref=0.02+nowb` and `ref=0.05+nowb`.

**On the aggregate outdoor medians they are indistinguishable.** Both give
outdoor median gamma **1.00** and outdoor median clip **8.167%** (table
above). Nothing in the outdoor aggregate separates the two candidates, so the
choice could not be made there.

**They differ on the specific problem shots** — those with a moderate fraction
of pixels already at the ceiling (roughly 2.5-4%, above `0.02` but well below
`0.05`). There `ref=0.05` only partially damps the lift while `ref=0.02`
removes it entirely (`report.json`, per-shot applied gamma):

| Shot | `ref=0.05+nowb` gamma | `ref=0.02+nowb` gamma |
| --- | ---: | ---: |
| 172404 | 0.86 | 1.00 |
| 172258 | 0.83 | 1.00 |
| 171656 | 0.93 | 1.00 |

`172404` and `172258` are the two shots the user judged worst; `171656` is the
blown-highlight scene. Under `ref=0.05` each keeps a residual lift on a frame
that is already clipped.

**The cost is indoor.** `ref=0.02` removes **more** of the indoor lift than
`ref=0.05` would: indoor median gamma goes 0.764 -> **0.975** at `ref=0.02`
versus 0.764 -> 0.856 at `ref=0.05`. The indoor frames are the ones the user
already judged good, so this is the price of the choice, and it was paid
knowingly.

**How the choice was actually made.** The design doc's proposed selection rule
— indoor gamma unchanged within 0.02 of current, and outdoor clip% brought down
to the indoor level — **was not satisfiable by any candidate on this set**. No
candidate brings outdoor clip% (8.2% at best) near the indoor level (~2%),
because most of the residual outdoor clipping is in-camera (see below); and the
only candidate leaving indoor gamma within 0.02 of current is `current+nowb`
(0.765), which is the undamped behaviour this phase exists to change. With the
rule inapplicable, the user chose on the contact sheet, preferring **the
outdoor problem shots fully corrected over keeping the indoor lift**.

White balance off removes the ISP-on-top-of-grey-world double correction
(D2 in the design doc) with no measurable cost to indoor neutrals in this
set.

## What this does not fix

Residual outdoor clipping under the chosen candidate (roughly 8-10% median)
is **in-camera**: it is present in the original before any normalisation runs
(`171656`'s centre-weighted AE metered the shaded foreground and blew the
bright house and sky in the original itself — see the design doc). The
normaliser can dampen a *lift into* clipping; it cannot un-clip pixels that
were already saturated at capture. That is what the new capture-side
`--ae-constraint highlight` flag targets (see the
[README](../../README.md#camera-backends) and
[picamera2-bringup.md](../picamera2-bringup.md), section 4):
a follow-up hardware shot of a 171656-type strong-light scene with
`--ae-constraint highlight` is still needed to confirm it protects the
original's highlights.

## Reproduce

```sh
.venv/bin/python -m pifilm.experiments.normalisation \
  --source source_imx708/2026-09-19 \
  --artifacts /tmp/pre-phase6 \
  --no-wb \
  --shots 171656,172012,172111,172144,172258,172404 \
  --out data/phase6-normalisation-eval
```

> **Since the freeze, `--artifacts` matters.** The `current` column is the
> given artifact's *own* normalisation, and the bundled starter now **is** the
> chosen candidate — so running this without `--artifacts` makes `current`
> identical to `ref=0.02+nowb`. To reproduce the tables, build the pre-Phase-6
> starter first and point at it:
>
> ```sh
> .venv/bin/python -c "
> from pifilm.artifacts import write_artifact
> from pifilm.preset import starter_lut
> from pifilm.normalize import NormalizeParams
> from pifilm.grain import GrainParams
> write_artifact('/tmp/pre-phase6', starter_lut(), NormalizeParams(levels=True), GrainParams())
> "
> ```
>
> That is the starter's normalisation as it stood before this phase (white
> balance on, no lift damping) with a byte-identical LUT
> (`lut_sha1 fa89d3b2075f2d3ebaf6cd3c080e5fcaf5683bca`).

`report.json`, `report.md` and `contact_sheet.jpg` land under `--out`, which
is gitignored (`source_*/` and `data/` are excluded from the repo; see
`.gitignore`). Only the one downscaled sheet used above is committed, under
`docs/experiments/imx708-normalisation/`.
