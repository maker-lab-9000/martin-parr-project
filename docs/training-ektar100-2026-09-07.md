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
