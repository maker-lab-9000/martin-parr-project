# martin-parr-project

A separate color-grading experiment inspired by Martin Parr's saturated,
flash-lit color-negative photographs: vivid reds, yellows and blues, crisp
contrast, neutral whites, and fine grain. Runs on a Mac for training and a
Raspberry Pi for capture, using the learned 3D-LUT approach from `kodachrome-film`.

The bundled look is a **handcrafted, untrained starter preset**; no reference
photographs were used to train that preset. Separately, the local
`artifacts/personal-collection-01-v1/` model was trained on 150 curated references
and passed all five numerical validation gates. See the
[personal-collection training report](docs/training-personal-collection-01-v1.md).
It remains experimental and proxy-trained, not calibrated to the Raspberry Pi
camera. Artifacts and training data are gitignored and are not included in a clone.

To test this trained model after installing the package, explicitly select it:

```bash
parr-process /path/to/ungraded-photos /path/to/results \
  --artifacts artifacts/personal-collection-01-v1
```

Without `--artifacts`, commands continue to use the untrained starter preset.

## Setup

Mac (Python 3.11 or newer):

```bash
cd ../martin-parr-project
python3 -m venv .venv
.venv/bin/pip install -e '.[train,dev]'
.venv/bin/pytest -q -m 'not slow'
```

Raspberry Pi OS with a desktop:

```bash
sudo apt install python3-venv python3-opencv python3-numpy python3-pil
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .
```

Use the Pi's system OpenCV for its GTK display support. Training additionally
needs the `train` dependencies; normally train on the Mac and copy the artifact
folder to the Pi.

## Try the starter look

```bash
.venv/bin/parr-process /path/to/originals /path/to/parr-results
.venv/bin/parr-capture --no-preview --show-captures
```

`SPACE` shows TV color bars while a snapshot is captured and processed, then
displays the graded photo until the next capture. `Q` or Escape exits. Fullscreen
display fits the image without cropping or stretching. Plain `--no-preview`
uses terminal controls without a window; `--fake` uses synthetic camera frames.

Captures go to `~/Pictures/parr/YYYY-MM-DD/`: the camera JPEG is saved verbatim
as `*_original.jpg` when available, otherwise `*_ungraded.jpg`, alongside
`*_parr.jpg` and `captures.jsonl`. These commands and outputs are separate from
the Kodachrome project. Capture currently requests a 1920 × 1080 MJPEG stream at
30 fps, inherited from that project; display resolution does not change capture
resolution. Use `--device` to select the camera.

The preset increases midtone color and contrast with a smooth tone curve,
compresses out-of-gamut chroma, and adds subtle grain (`0.004`). Rebuild it with:

```bash
.venv/bin/parr-preset --out artifacts/starter-v1
```

## Train a reference-derived look

Create `data/source/` for ungraded camera photos and `data/references/` for the
finished reference photographs. Aim for at least 30 source images (50+ is better)
and 200 references spanning skin, food, signage, beaches, interiors and neutrals.
Use one coherent visual period; mixing early monochrome, muted scans and later
digital work gives the trainer contradictory targets. Avoid duplicates and
near-duplicates across the held-out split.

Use photographs credited to Martin Parr from the supplied Magnum and Aperture
sources, his official site, Foundation and publishers. Fan-submission Flickr
groups are excluded. See [the reference guide](docs/reference-sources.md) for
additional sources, curation notes and the difference between visual research
and training files.

Use reference files you have permission to use. The project takes local image
folders; it does not scrape Parr's website or assume that photos *of* Parr are
photos *by* him. The optional `parr-fetch --category 'Category:...'` command
downloads an explicitly chosen Wikimedia Commons category, retaining licence
metadata. It defaults to public-domain files; that is a generic corpus utility,
not a ready-made Parr reference set.

```bash
.venv/bin/parr-train --source data/source --target data/references --out artifacts/parr-v1
.venv/bin/parr-process /path/to/test-originals /path/to/test-results --artifacts artifacts/parr-v1
.venv/bin/parr-capture --no-preview --show-captures --artifacts artifacts/parr-v1
```

Training fits a 33³ RGB lookup table via color-distribution transfer and smooth
least squares. It splits by image, evaluates held-out data, and produces
`parr.cube`, `params.json`, and a report with contact sheets, tone ramps, metrics
and quality gates. Exit code 3 means an artifact was written but a gate failed;
inspect `report/summary.txt` before using it. A LUT models global color and tone,
not subjects, composition, focus or lighting geometry.

Target white balance and levels stretching are off by default; exposure matching
still aligns reference brightness. Camera inputs receive the same normalization
in training and capture. `--target-levels` opts into reference levels stretching.
`--strength 0.8` weakens a learned grade; `--grain-strength 0` disables added grain.
`--allow-small` permits exploratory small-corpus fits and marks unavailable
held-out evaluation; `--proxy-source` records stand-in photos instead of actual
camera samples. A small test run does not establish a successful visual match.

## The look and its limits

Parr's [own FAQ](https://martinparr.com/faq/) describes consumer films including
Agfa Ultra and Fuji 100 with ring flash, and Fuji 400 in medium format. This
project's low-ISO, fine-grain target is an aesthetic choice, not a claim that all
his work used one film or ISO. His saturated color depends partly on flash:
capture with direct or ring flash and appropriate exposure when possible.
A LUT cannot add the corresponding highlights, shadows or depth cues afterward.

See [ORIGIN.md](ORIGIN.md) for the code's starting point and what is independent.
