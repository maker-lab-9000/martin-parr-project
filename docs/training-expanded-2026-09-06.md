# Expanded reference collection and training — 2026-09-06

Attempted all five requested sources. Downloaded **49 new image candidates**,
selected **44**, and combined them with the 12-image first pilot: **56 targets**.
The new LUT finished training but **failed held-out improvement** (exit code 3).
The bundled preset and the first pilot are unchanged. Nothing was pushed.

## Source coverage

| Source | Downloaded | Selected | Notes |
|---|---:|---:|---|
| [AnOther / Benidorm 1997](https://www.anothermag.com/art-photography/gallery/11814/benidorm-by-martin-parr/0) | 6 | 6 | Caption credits Martin Parr/Magnum. |
| [ROSEGALLERY / The Cost of Living](https://rosegallery.net/artists/52-martin-parr/series/the-cost-of-living/) | 22 | 22 | Gallery-attributed series; files approximately 550 × 450 pixels. |
| [ROCKET / Food](https://rocketgalleryshop.com/collections/food-photographs) | 10 | 9 | Product pages retained. Excluded Teacup, dated 2010; selected 1994–95 Food works and Teacakes (1999). |
| [ROCKET on Artsy / Common Sense](https://www.artsy.net/viewing-room/rocket-martin-parr-common-sense/artworks) | 11 | 7 | HTML requests returned 403; public browser listing exposed working CDN image links. Four photographed Xerox prints with visible paper borders excluded. |
| [NGV / Common Sense](https://www.ngv.vic.gov.au/essay/martin-parrs-common-sense/) | 0 | 0 | Direct HTML and publicly linked Common sense 7 image requests returned 403. No access-control workaround attempted. |
| Earlier Artnet/Pinterest pilot | 12 existing | 12 | 1 Artnet + 11 Pinterest; provisional secondary attribution remains flagged. |

Each selected image retains its URL, source page, attribution, original bytes,
and SHA-256 checksum. Reviewed all new images in contact sheets. Screened all
56 selected images with a 63-bit perceptual hash (Hamming distance ≤12 for
manual review); no further near-duplicate candidates were found. This is not a
guarantee of scene independence. Existing pilot duplicate exclusions remain.
No AI image editing, recoloring, or reconstruction was used.

Original reproduction differences, JPEG compression, uncertain inherited pin
dates and mixed series remain limitations. This collection is not an open
dataset; no redistribution or commercial-training permission was established.
Images and generated models remain local and gitignored.

## Locations and reproduction

- Curated corpus: `data/references-expanded-2026-09-06/`
- Source pages, raw candidates, scripts and review sheets:
  `data/reference-collection-expanded-2026-09-06/`
- Model and report: `artifacts/expanded-five-sources-2026-09-06/`
- Exact dependency versions, command, corpus hashes and settings: model `params.json`

From the project root, with training dependencies installed:

```sh
parr-train --source ../kodachrome-film/data/proxy-large \
  --target data/references-expanded-2026-09-06 \
  --out artifacts/expanded-five-sources-2026-09-06 \
  --proxy-source --allow-small
```

The actual run used the sibling Kodachrome virtual environment with this project
on `PYTHONPATH`. The source is explicitly a proxy, not Raspberry Pi captures.
399 source images: 320 training / 79 validation. 56 target images: 45 training /
11 validation. Seed 0, 40 transfer rounds, 33³ LUT, unchanged regularization;
source levels normalization and target exposure matching only.

Collection scripts are bounded records of this run, not full-site crawlers.
They operate on explicitly exposed public URLs, and `curate.py` requires a fresh
output directory. The archived collection includes a copy of the curated corpus;
the separate top-level corpus is the one used by the recorded training command.

## Evaluation

| Metric / gate | Result |
|---|---|
| Held-out color-distribution distance (lower is better) | 0.02597 → 0.04437 |
| Evaluation seed spread | 0.00156 |
| Training-pool distance | 0.03558 → 0.00618 |
| Improvement exceeds noise | FAIL |
| Neutral luminance monotonicity | PASS |
| Channel monotonicity | PASS |
| Neutral-axis chroma | PASS (0.00567) |
| Clipped interior volume | PASS (0.0) |

The fit improves its training-pool distance but worsens the held-out distance.
This is consistent with overfitting or a distribution mismatch; it does not
establish which cause dominates. Baseline distances are not directly comparable
with the first pilot because the target corpus and held-out reference set changed.
The report contact sheet was inspected; it illustrates stronger color/contrast,
but visual changes alone do not override the failed evaluation gate.

No thresholds were relaxed and no validation-driven retuning was performed.
Next work should establish coherent series-balanced training/validation sets and
real ungraded camera sources before another fit. A global color LUT cannot learn
Parr's flash lighting, composition, or subject choices.
