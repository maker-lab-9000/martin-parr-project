# Training on Kodak Ektar 100 (2026-09-07)

Replaces the scraped Artnet/Pinterest reference sets with 346 freely licensed
Kodak Ektar 100 scans from Wikimedia Commons (181 CC0; every file, author and
licence in `ektar100-attribution.md`). Ektar is the saturated colour-negative
stock in the family the project is aiming at.

## What was run

399 proxy source photographs (USDA, public domain) against the 346 Ektar
scans, two variants differing only in how target scans are normalised:

| variant | target normalisation | held-out distance | gates |
|---|---|---|---|
| `ektar-asym` | exposure match only (the inherited default) | 0.03715 → 0.01455 | 5/5 |
| `ektar-sym` | levels, same as the source | 0.03187 → 0.01213 | 5/5 |

Both clear every gate by a wide margin — a 61% and 62% reduction against a
noise bar of 0.0035 and 0.0019 — on 79 held-out source and 69 held-out
target images. For contrast, the previous artifacts were trained on 12 and
56 scraped images.

**`--target-levels` measures better, and the default is left alone.**
Source frames are stretched to a pinned white point while target scans get
only an exposure gain — structurally the same asymmetric-normaliser fault
diagnosed in `kodachrome-film` on 2026-09-04, with the flag on the other
side. Passing `--target-levels` improves the held-out distance by 17% and
restores contrast (std L 0.230 → 0.259) and highlights (p95 0.857 → 0.917).

But the asymmetry here is deliberate: `ORIGIN.md` records it as "exposure
matching by default without stretching black and white points" and
`test_training_skips_reference_levels_stretch_by_default` pins it. That is a
look decision about preserving the references' own tonality, not an
oversight, so the default is unchanged and the evidence is recorded here for
whoever owns that call. Both variants are trained above; `--target-levels`
is one flag away.

## The result is more muted than the handcrafted starter

Measured on the author's 26 captures of 2026-09-07, grain off, against the
reference corpora sampled through the same statistics:

| | p5 L | median | p95 | std L | chroma | colours | >0.12 | neutral |
|---|---|---|---|---|---|---|---|---|
| ungraded | 0.197 | 0.619 | 0.846 | 0.201 | 0.0212 | 0.0825 | 0.8% | 0.0038 |
| starter preset | 0.132 | 0.625 | 0.924 | 0.259 | **0.0253** | 0.0880 | 1.4% | 0.0043 |
| trained v3 (56 scraped) | 0.127 | 0.625 | 0.856 | 0.233 | 0.0235 | 0.0862 | 0.9% | 0.0042 |
| `ektar-asym` | 0.146 | 0.571 | 0.857 | 0.230 | 0.0229 | 0.0819 | 0.6% | 0.0037 |
| `ektar-sym` | 0.107 | 0.594 | 0.917 | 0.259 | 0.0224 | 0.0818 | 0.5% | 0.0039 |
| *Ektar 100 reference* | 0.187 | 0.542 | 0.908 | 0.246 | 0.0364 | 0.0863 | 2.6% | 0.0074 |
| *Velvia reference* | 0.183 | 0.475 | 0.850 | 0.219 | 0.0497 | 0.0920 | 7.3% | 0.0100 |

The trained artifacts match the reference *distribution* far better than
anything before them and are **less saturated than the handcrafted preset**,
on both mean chroma and the chroma of already-colourful pixels. The gates
are satisfied and the look is more muted. Both statements are true because
they measure different things.

## Why the saturation gap is not the grade's to close

Share of pixels by input chroma:

| chroma band | these captures | Ektar | Velvia |
|---|---|---|---|
| 0.00–0.02 | 64.4% | 36.8% | 27.4% |
| 0.02–0.06 | 28.6% | 47.5% | 42.5% |
| 0.06–0.13 | 6.5% | 14.6% | 25.8% |
| 0.13+ | 0.5% | 1.2% | 4.3% |

Two thirds of an indoor frame of white walls and grey floor is near-neutral;
in the reference corpora, photographed by people pointing cameras at flowers
and landscapes, it is a quarter to a third. The camera's *already colourful*
pixels are already about as saturated as the film's (0.0825 against 0.0863).
What differs is how much of the frame is colourful, and that is subject
matter. A distribution match cannot and should not invent it — the same
conclusion `kodachrome-film` reached on 2026-09-04 from the opposite
direction.

Getting the remembered Parr vividness therefore needs an **explicit
stylistic chroma lift**, weighted toward low input chroma, declared as a
look rather than learned from a reference. That is the honest place for it.

## A hypothesis that was wrong

`neutral_axis_cap` was raised 0.005 → 0.010 on the reasoning that the film
tints its neutrals (0.0074 and 0.0100 measured) while the grades carried
0.0042, so the cap was throwing the cast away. It changed nothing: the
fitted artifacts land at 0.0037–0.0039, well under either ceiling. The cap
was never the binding constraint. The wider value is kept because it does
not belong at a Kodachrome-era setting here, but it buys nothing today.

## The stylistic lift (`--vividness`)

Added because the reference cannot supply it. `chroma_gain` follows a power
curve in chroma, unity at 0.15 and rising as chroma falls, so weak colour
gains more than strong colour. `vividness=0` reproduces the original
constant-gain look exactly.

An exponential decay was tried first and measured too weak — mean chroma
0.0251 → 0.0270 across its whole range. The power curve reaches 0.0284 and,
more to the point, matches the reference's *distribution shape*:

| | mean chroma | chroma of colours | >0.06 | >0.12 |
|---|---|---|---|---|
| ungraded | 0.0212 | 0.0825 | 6.5% | 0.8% |
| `vividness 0` (original) | 0.0251 | 0.0878 | 10.6% | 1.4% |
| **`vividness 1`** | **0.0284** | **0.0948** | **14.8%** | **2.4%** |
| `vividness 1.5` | 0.0303 | 0.0998 | 16.2% | 3.8% |
| *Ektar 100 reference* | 0.0364 | 0.0863 | **14.6%** | **2.6%** |
| *Velvia reference* | 0.0497 | 0.0920 | 25.8% | 7.3% |

`vividness=1` is therefore calibrated, not chosen by eye: it puts the same
share of the frame above chroma 0.06 and 0.12 as Ektar 100 does. 1.5 leans
toward Velvia. Mean chroma stays well below either reference on purpose —
two thirds of these frames are white wall and grey floor, and colouring
those would be wrong rather than vivid.

**Near-neutral surfaces are not tinted.** Output chroma by input band, mean
over the 26 captures:

| input chroma | share | v=0 | v=1 | v=1.5 |
|---|---|---|---|---|
| 0.00–0.01 | 37.2% | 0.0055 | 0.0055 | 0.0055 |
| 0.01–0.02 | 26.7% | 0.0165 | 0.0168 | 0.0170 |
| 0.02–0.04 | 21.3% | 0.0333 | 0.0392 | 0.0429 |
| 0.04–0.08 | 12.1% | 0.0666 | 0.0801 | 0.0871 |

The lift lands in 0.02–0.08 and leaves the bottom two bands alone, because
the existing grey-diagonal blend protects them. A first visual read of these
frames suggested walls were picking up a cyan cast; the measurement says
otherwise — what changes is slightly-blue daylight at chroma 0.02–0.04,
lifted 29%, which is the control working as intended.

## `enforce_monotone` now also runs on the handcrafted preset

The preset is built by `starter_lut`, not `fit_lut`, so the monotone
projection the fitted path applies had never touched it. It needed it: the
per-node gamut search and neutral blend left **53 steps where a channel falls
as its own input rises, the worst reversing by 0.15 — 38 of 255 levels**,
which is the banding hazard. The projection fixes all of them, moves nodes by
a mean of 0.00003, and changes mean chroma by 0.0%. It is free.

`parr.preset` imports it lazily. `parr/train/lutfit.py` imports SciPy at
module scope and SciPy is only in the `[train]` extra, so a top-level import
would have turned `parr-preset` on a bare Pi install into a
`ModuleNotFoundError` for a command that previously worked. Importing
`parr.preset` with SciPy blocked now succeeds, and calling `starter_lut`
raises a message naming the extra.

## The bundled artifact was regenerated

`parr/data/` now carries the `vividness=1` preset (`preset_version: 2`), so
`git pull` on the Pi is enough — `parr-capture` and `parr-process` pick it up
with no extra step. `parr-preset` is only needed to *make* a different look,
and it needs the `[train]` extra for SciPy.

Verified by inspecting the built wheel: `parr/data/parr.cube` (970,373 bytes)
and `params.json` travel inside it, and all five console scripts are in
`entry_points.txt`.

Note `tests/test_packaging.py` fails on this machine — the console script is
absent from the temporary venv it builds. It fails identically at
`origin/main`, so it is environmental and pre-existing, not a regression from
this branch. The wheel itself is correct by direct inspection.
