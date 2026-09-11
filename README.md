# Introduction
This entire idea took shape from trying to find a kid friendly camera for my son, which is a little more than potato quality, is made of decent plastic, modular and cheap.

The prototype is still in progress but I'm aiming at a handheld point and shoot with the M5Stack Stick S3 used as the viewfinder along the Raspberry Pi3 and the Innomaker low light camera module for start.

Once the prototype is working as expected, additional parts would include a proper 3D printed case, and potential upgrade to the Raspi high quality camera module and external battery HAT.


# Martin Parr Look

A color-grading experiment inspired by Martin Parr's saturated,
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

## Hardware
- Raspberry Pi 3B, 1GB RAM
- M5Stack StickS3 (display, trigger)
- 64GB SD Card
- Innomaker 1080P USB2.0 UVC Camera, 121° Lens, PS5268 Sensor

## Getting started

Follow [the setup guide](docs/setup.md). It is ordered by dependency and says,
for every step, which machine it runs on and why:

1. **Mac** — clone, venv, `pip install -e '.[train,dev,deploy]'`, PlatformIO, tests.
2. **The one `.env` file** — every credential and address, read by the deploy
   script, the hotspot script and the firmware build.
3. **Pi, OS and network** — Trixie, hostname `parr`, Ethernet administration,
   then the Pi's own Wi-Fi hotspot that the Stick joins.
4. **Pi, application and service** — venv with system OpenCV, choice of look,
   token file, systemd unit, reboot test.
5. **Stick** — build and flash with the credentials baked in, read the serial log.
6. **Training, optional** — only if you want to replace the bundled starter.

Two supporting documents go deeper: [the network and deployment guide](docs/sticks3-remote.md)
for the hotspot, Ethernet, service and rollback details, and
[the firmware README](firmware/sticks3/README.md) for the Stick's build, its
serial debug log and how to prove the displayed photo is the graded one.

| Last captured photo | Ready to capture |
| --- | --- |
| <img src="docs/images/sticks3-ready.jpg" alt="M5Stack StickS3 showing TV colour bars and the READY prompt" height="280"> | <img src="docs/images/sticks3-captured-photo.jpg" alt="M5Stack StickS3 displaying a captured room photo" height="280"> |

Never put a real token, Wi-Fi password, or Pi SSH password in a command,
source file, or commit; `.env` is gitignored for that reason.

## From button press to displayed photo

The Raspberry Pi does the capture, grading and storage. The M5Stack StickS3 is
the wireless shutter button and **last-capture display**, not a live viewfinder.
The Pi runs its own Wi-Fi hotspot and the Stick joins it directly, so no home
network is needed in the field; the two talk over a token-authenticated HTTP API.
SSH over an Ethernet cable is used for deployment/administration and photo
transfer, not for each shutter press. No cloud service is involved.

```text
Stick joins the Pi's hotspot → checks Pi readiness → displays READY
    ↓ primary button press
Capture request → Pi accepts → Stick sounds shutter acknowledgement
    ↓ TV colour bars while waiting
Pi acquires one camera frame → normalizes → applies LUT → adds grain
    ↓
Pi saves original + graded JPEG + capture log → marks job complete
    ├─ Optional Pi screen displays the saved graded photo
    └─ Stick polls completion → downloads graded thumbnail → decodes → displays
```

1. **Connect and become ready.** The Pi capture app must be running with its
   remote listener enabled. The Stick joins the Pi's hotspot and checks the
   Pi's status before showing that it is ready for another capture.
2. **Request one snapshot.** A debounced primary-button press creates a unique
   request ID and sends `POST /v1/captures`. The Pi accepts only one active
   capture at a time; additional requests can be rejected as busy. The Stick's
   shutter tone acknowledges an accepted request—it does not mean grading or
   saving has finished.
3. **Show processing feedback.** The Stick shows TV colour bars while submitting,
   processing and downloading. It polls `GET /v1/captures/{id}` for that same
   capture, rather than taking another photo while waiting. In two-screen mode,
   the Pi also shows processing colour bars during capture and grading.
4. **Capture and grade on the Pi.** One newly acquired USB-camera frame supplies
   both the original and the graded output. The pipeline applies configured
   white-balance and exposure/levels normalization, the selected 3D LUT, then
   optional fine grain. The bundled starter is the default; `--artifacts DIR`
   explicitly selects another LUT and its associated normalization/grain settings.
5. **Save locally before declaring completion.** By default, the Pi writes to
   `~/Pictures/parr/YYYY-MM-DD/`: the original camera JPEG as `*_original.jpg`
   when available, otherwise an encoded `*_ungraded.jpg`; the full-resolution
   graded `*_parr.jpg`; and an entry in `captures.jsonl`. The log records file
   names, timestamp, LUT hash, normalization gains, grain seed, camera stream
   settings and processing timings. The job is marked complete after these writes
   succeed.
6. **Transfer a graded preview to the Stick.** After completion, the Stick requests
   `GET /v1/captures/{id}/image.jpg`. The Pi reads that job's saved **`*_parr.jpg`**
   and generates an aspect-preserving **240 × 135 JPEG**, with black padding if
   needed and a **64 KiB** transfer limit. This is a download initiated by the
   Stick, not a push/upload of the full-resolution file. Grading is not repeated
   on the Stick, and the ungraded file is not used for this endpoint.
7. **Display until the next snapshot.** The Stick decodes the JPEG and displays
   it from memory. In normal operation it stays visible until the next capture
   starts. The full-resolution files remain on the Pi; the Stick display is not
   the photo archive. Network or capture failures show a status/error instead of
   being treated as a successful new photo.

For battery-powered **headless use**, the systemd service runs with
`--no-preview` and the remote listener and no `--show-captures`. The Stick
still receives the graded preview; the Pi needs no monitor. For **two-screen
use**, add `--show-captures` in a working Pi desktop session. See the
[deployment guide](docs/sticks3-remote.md) for the complete configuration and
service commands.

## Using the tools directly

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

## Training a reference-derived look

Training is optional; the camera works with the bundled starter.
[The training guide](docs/training.md) is the step-by-step procedure: how a run
works, collecting camera frames, curating references, training, reading the
report gate by gate, iterating without fooling yourself, deploying to the Pi and
writing the run down. [The setup guide, section 6](docs/setup.md#6-training-a-look-optional)
has the short outline. The policy that applies to every reference photograph:

Use photographs credited to Martin Parr from the supplied Magnum and Aperture
sources, his official site, Foundation and publishers. Fan-submission Flickr
groups are excluded. See [the reference guide](docs/reference-sources.md) for
additional sources, curation notes and the difference between visual research
and training files. Use reference files you have permission to use. The project
takes local image folders; it does not scrape Parr's website or assume that
photos *of* Parr are photos *by* him. The optional `parr-fetch --category
'Category:...'` command downloads an explicitly chosen Wikimedia Commons
category, retaining licence metadata; that is a generic corpus utility, not a
ready-made Parr reference set.

Training fits a 33³ RGB lookup table via color-distribution transfer and smooth
least squares. It splits by image, evaluates held-out data, and produces
`parr.cube`, `params.json`, and a report with contact sheets, tone ramps, metrics
and quality gates. A LUT models global color and tone, not subjects,
composition, focus or lighting geometry. The dated reports in `docs/` record
what past runs produced; `todo.md` section 1 records what is needed for better
results.

## How the colour model works

There is no neural network in this project. The "model" is a 33 × 33 × 33
colour lookup table, the same `.cube` format that DaVinci Resolve or Photoshop
would open, fitted with classical colour statistics: distribution matching,
regularised least squares and a handful of safety checks. That choice is
deliberate. The training data is a few hundred images with no pairs between
camera frames and reference photographs, and the result has to run on a
Raspberry Pi 3B with no machine-learning runtime installed.

### At capture time, on the Pi

Every graded frame goes through three steps, in a fixed order, in
`parr/pipeline.py`:

1. **Normalisation** (`parr/normalize.py`). Per-frame white balance and an
   exposure or levels correction, computed in linear light and applied to
   the luma channel only, so contrast changes do not inflate saturation. It
   compiles into three 256-entry tables plus one for tone, applied with
   OpenCV's `LUT` and two `cvtColor` calls: about 100 ms for 1080p on the Pi.
   The same code, in floating point, prepared every training image, so the LUT
   sees the input distribution it was fitted on.
2. **The 3D LUT** (`parr/lut.py`). Trilinear interpolation over the 35,937
   nodes, executed by Pillow's `ImageFilter.Color3DLUT` in C with 16-bit fixed
   point. A NumPy reference implementation exists for tests and the trainer.
3. **Grain** (`parr/grain.py`). Gaussian noise on luminance only, blurred by
   `blur_sigma` so it clumps like film rather than looking like sensor noise,
   scaled by `4Y(1 − Y)` so it vanishes in deep shadow and blown highlights.
   The seed is recorded per capture, so any graded file can be regenerated
   from its original.

### At training time, on the Mac

`parr-train` (`parr/train/`) turns two folders of images into that LUT:

1. **Corpus building** (`dataset.py`). Each corpus is split **by image**
   before any pixel is sampled, 20 % held out. Every image is oriented from
   EXIF, colour-managed to sRGB from its embedded ICC profile, cropped 6 % per
   edge, downscaled to 512 px, normalised, and sampled: 3000 pixels per image,
   capped at 400,000 per pool, kept only where Oklab lightness lies in
   (0.02, 0.98).
2. **Oklab** (`color.py`). All statistics are computed in Oklab, Björn
   Ottosson's perceptual space, so "match the distribution" means "match what
   the eye sees" and hue angles behave in the blues.
3. **Hue reweighting** (`transport.py`). The two corpora show different
   subjects. Target pixels are reweighted across 24 hue bins so the target's
   hue histogram matches the source's, which removes the largest content bias.
   Weights are clipped to 0.2 to 5, so this is a heuristic, and the residual
   is published in the report.
4. **Iterative Distribution Transfer** (Pitié, Kokaram and Dahyot, 2005).
   Forty rounds of: pick a random 3D rotation, project both pixel clouds onto
   its axes, match the source's marginal to the weighted target's along each
   axis by quantile mapping, rotate back. Each source pixel ends up with a
   partner colour in the target distribution. `--strength` blends between the
   original and the moved colour, and may extrapolate up to 2.
5. **LUT fit** (`lutfit.py`). A trilinear LUT is linear in its node values, so
   fitting is ordinary least squares with a sparse design matrix of eight
   non-zeros per pixel. Two regularisers are added: a second-difference
   smoothness term along all three grid axes, and an identity term that holds
   nodes no source pixel ever touched in place (71 % of the cube, in the first
   real fit). The normal equations are solved with SciPy's conjugate-gradient
   solver and a Jacobi preconditioner. A neutral-axis cap limits tint on greys,
   and monotonicity is then enforced exactly with SciPy's isotonic regression.
6. **Evaluation** (`evaluate.py`). The headline metric is a **sliced
   Wasserstein distance** from the graded held-out source pixels to the target
   cloud, using 256 fixed random projections and fixed samples so "before" and
   "after" differ only by the LUT. It is repeated over five seeds and the
   spread reported, so an improvement can be compared against noise. Five
   gates then pass or fail with thresholds fixed before any tuning:
   improvement above three times the seed spread, grey axis monotone, each
   channel monotone, neutral input staying neutral, and the cube interior off
   the gamut boundary.
7. **Report and publish** (`report.py`, `artifacts.py`). Contact sheets of
   held-out frames, tone ramps, normalisation diagnostics and `metrics.json`,
   then an atomic swap of the finished artifact into place so a crash can never
   leave a new LUT beside old parameters.

The full procedure, from an empty `data/` folder to a verified deployment, is
[the training guide](docs/training.md).

### Libraries

| Library | Where | What it does here |
|---|---|---|
| NumPy | everywhere | All array maths: colour conversions, sampling, transport, evaluation |
| Pillow | runtime and trainer | Image I/O, EXIF orientation, ICC conversion (`ImageCms`), the `Color3DLUT` filter, `.cube` round-trips, contact sheets |
| OpenCV (`cv2`) | runtime and trainer | Colour-space conversions, the 256-entry `LUT` tables, Gaussian blur for grain, resizing, and V4L2 camera capture on the Pi |
| SciPy | trainer only | Sparse matrices, the conjugate-gradient solver, isotonic regression |
| requests, tqdm | `parr-fetch` only | Wikimedia Commons downloads with licence checks |
| smbus2, gpiozero | Pi only, `--ups x728` | Reading the UPS fuel gauge over I2C and the power-loss pin |
| Paramiko | Mac only, deploy script | SSH to the Pi with a reject-unknown-hosts policy |
| pytest, ruff, build | development | Tests, lint, wheel build |

Not used: PyTorch, TensorFlow, scikit-learn, or any GPU. Nothing is downloaded
at runtime and no data leaves the machine.

### Dependencies by role

`pyproject.toml` keeps the base install small and puts the rest behind extras:

| Install | Pulls in | Who needs it |
|---|---|---|
| `pip install -e .` | NumPy, Pillow | The Pi, which gets OpenCV from apt |
| `.[opencv]` | + `opencv-python` | Any non-Pi machine that runs the pipeline |
| `.[train]` | + SciPy, requests, tqdm, `opencv-python` | The Mac, for `parr-train` and `parr-fetch` |
| `.[deploy]` | + Paramiko | The Mac, for `scripts/deploy_remote.py` |
| `.[dev]` | + pytest, ruff, build, `opencv-python` | Anyone running the tests |

On the Pi, `python3-opencv`, `python3-numpy` and `python3-pil` come from apt
and the venv is created with `--system-site-packages`, because the apt OpenCV
is built with GTK for the two-screen mode and the pip wheel is not; `smbus2`
and `gpiozero` are preinstalled on Raspberry Pi OS. OpenCV is imported through
one guard, `parr/_cv2.py`, which explains the right fix when it is missing.

### What a LUT cannot do

It maps each input colour to one output colour, everywhere in the frame. It
cannot add flash lighting, local contrast, sharpness or depth, and it cannot
invent colour: an unlit grey room comes out grey through every LUT, as measured
in `todo.md` section 1. Those limits, and the roadmap for better fits, are the
subject of the next section and of the training guide.

## The look and its limits

Parr's [own FAQ](https://martinparr.com/faq/) describes consumer films including
Agfa Ultra and Fuji 100 with ring flash, and Fuji 400 in medium format. This
project's low-ISO, fine-grain target is an aesthetic choice, not a claim that all
his work used one film or ISO. His saturated color depends partly on flash:
capture with direct or ring flash and appropriate exposure when possible.
A LUT cannot add the corresponding highlights, shadows or depth cues afterward.

See [ORIGIN.md](ORIGIN.md) for the code's starting point and what is independent.
