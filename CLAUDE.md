# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Martin Parr-inspired colour-grading pipeline (saturated colour-negative look) with two runtimes:
a Mac side that trains 3D LUTs from reference photographs, and a Raspberry Pi side that captures
from a USB camera, grades, and saves. An M5Stack StickS3 acts as a wireless shutter button and
last-capture display, talking to the Pi over a token-authenticated HTTP API.

Forked from the user's `kodachrome-film` project (see `ORIGIN.md`). Package is `parr`, distribution is
`martin-parr-project`, commands are `parr-*`. The bundled LUT in `parr/data/` is a handcrafted,
untrained starter preset (`trained: false`). Trained artifacts, training data, `data/`, `artifacts/`,
`ektar100/`, `velvia/` are all gitignored and not in a clone.

## Commands

Python 3.11+ required (the venv is 3.12). Always use `.venv/bin/...`.

```bash
# Setup (Mac)
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[train,dev]'     # add ,deploy for scripts/deploy_remote.py

# Tests: use `python -m pytest`, NOT bare `pytest`.
# tests/test_config.py and tests/test_deployment.py import `firmware.sticks3.scripts.generate_config`
# and `scripts.deploy_remote` as namespace packages from the repo root; only `python -m pytest`
# puts the CWD on sys.path. Bare `.venv/bin/pytest` fails collection on those two files.
.venv/bin/python -m pytest -q -m 'not slow'           # ~40s, 361 tests
.venv/bin/python -m pytest -q tests/test_lut.py       # one file
.venv/bin/python -m pytest -q tests/test_lut.py -k identity   # one test by name
.venv/bin/python -m pytest -q -m slow                 # builds a wheel, installs into a temp venv, runs parr-process

# Lint (ruff: E, F, I, B, UP; line length 100)
.venv/bin/ruff check .

# CLI entry points (pyproject [project.scripts])
.venv/bin/parr-preset --out artifacts/starter-v1                 # regenerate the untrained starter
.venv/bin/parr-process IN_DIR OUT_DIR [--artifacts DIR]          # batch regrade
.venv/bin/parr-capture --fake --no-preview                       # capture loop w/o hardware
.venv/bin/parr-train --source data/source --target data/references --out artifacts/parr-v1
.venv/bin/parr-fetch --category 'Category:...'                   # Wikimedia Commons corpus fetch

# Experiments have no console scripts; run as modules from the repo root
.venv/bin/python -m parr.experiments.{regression,candidates,train,evaluate} ...

# StickS3 firmware (PlatformIO; reads repo-root .env via pre-build script)
pio run -d firmware/sticks3                # build
pio run -d firmware/sticks3 -t upload      # flash
pio test -d firmware/sticks3 -e native     # host-side Unity tests of the state machine only
python3 firmware/sticks3/scripts/generate_config.py --env .env   # validate .env w/o printing secrets

# Pi deployment (needs [deploy] extra, .env, and the Pi host key already in known_hosts)
.venv/bin/python scripts/deploy_remote.py --env .env             # inspect only
.venv/bin/python scripts/deploy_remote.py --env .env --restart   # guarded systemd restart

# Pi hotspot (run ON the Pi, over Ethernet; dry run prints the redacted keyfile)
.venv/bin/python scripts/pi_hotspot.py --env .env
sudo .venv/bin/python scripts/pi_hotspot.py --env .env --apply
```

`parr-train` exit code 3 means an artifact was written but a quality gate failed.

## Architecture

### Processing core (`parr/`, runs on the Pi; NumPy + Pillow + OpenCV only)

`Pipeline.process()` in `pipeline.py` is the single grading path for captures, previews, and batch:
**normalize → LUT → grain**, in that fixed order. Normalization runs first because the LUT was
fitted on normalized input; grain runs last because it models developed film.

- `normalize.py`: per-image white balance and exposure/levels normalization. The trainer applies the
  identical maths in float (`normalize_float`); the Pi uses 256-entry lookup tables (`normalize_u8`).
  Tone is applied to luma only by default to avoid per-channel gamma inflating saturation.
  Normalizing an image twice is unsupported.
- `lut.py`: `LUT3D` with `apply_numpy` (reference, used in tests/trainer) and `apply_pillow`
  (C fast path, used on the Pi). Both `.cube` and Pillow order the flat table red-fastest.
  `sha1_hex` is the LUT content identity.
- `artifacts.py`: an artifact is `parr.cube` + `params.json`. Loading verifies `lut_sha1` matches the
  cube on disk so a half-written pair cannot load. `publish()` stages then swaps the directory with
  `os.replace`. `Artifacts.default()` resolves the packaged `parr/data/`; `--artifacts DIR` overrides.
- `color.py`: sRGB ↔ linear ↔ Oklab/Oklch. All trainer statistics are computed in Oklab.
- `imageio.py`: the only place pixels enter. Applies EXIF orientation and converts embedded ICC
  profiles to sRGB. Do not load images elsewhere with raw `Image.open`.
- `_cv2.py`: the single `cv2` import site. Use `require_cv2()`; never `import cv2` directly.
  OpenCV is deliberately not a base dependency (Pi uses apt `python3-opencv` for GTK).

### Capture (`parr/capture/`)

- `camera.py`: V4L2 UVC camera forcing MJPEG at 1920×1080. Grabs the raw compressed buffer so the
  saved `*_original.jpg` is the camera's own bytes; falls back to decoded mode (file becomes
  `*_ungraded.jpg`) if raw mode fails. `FakeCamera` for tests and `--fake`.
- `app.py`: `CaptureSession` owns camera + pipeline + output dir. Three loops: live preview,
  captures-only display (`--show-captures`, shows TV colour bars while processing), and headless
  terminal. Output: `~/Pictures/parr/YYYY-MM-DD/HHMMSS_{original|ungraded,parr}.jpg` plus an audit
  line in `captures.jsonl` (grain seed + LUT hash allow regenerating the graded file).
- `controller.py`: `CaptureController` serializes captures on one worker thread, one active job at
  a time, idempotent by `request_id`. Shared by the local SPACE key and the remote API.
- `remote.py`: `RemoteCaptureServer`, a stdlib `http.server` with bearer-token auth
  (`PARR_REMOTE_TOKEN`). Endpoints: `GET /v1/status`, `POST /v1/captures` (`{"request_id": uuid}`,
  409 when busy), `GET /v1/captures/{id}`, `GET /v1/captures/{id}/image.jpg`. Only jobs submitted
  through this server instance are visible; `instance_id` changes on restart.
- `thumbnail.py`: 240×135 letterboxed JPEG, ≤64 KiB, served to the Stick.
- `batch.py`: `parr-process`. Skips `*_parr.*`, defaults to only `_original`/`_ungraded` files in a
  capture folder, refuses an output dir equal to or inside the input.

### Trainer (`parr/train/`, Mac only; needs `[train]` extra: SciPy, requests)

`fit.py` sequence: `dataset.build_corpus` (split **by image** before pixel sampling, then normalize
and sample in Oklab) → `transport.hue_weights` (reweight target hues toward source to reduce content
bias) → `transport.iterative_distribution_transfer` (Pitié IDT; gives every source pixel a target
partner) → `lutfit.fit_lut` (sparse regularised least squares with smoothness + identity terms,
solved by CG, then monotone projection) → `evaluate.evaluate` + `check_gates` (paired SWD metrics on
held-out images, plus safety gates: grey-axis monotone, neutral tint cap, channel monotone, gamut
clip) → `report.write_report` → `artifacts.publish`. `FitConfig` defaults are the single source of
truth for CLI defaults. Targets default to no white balance and no levels stretch (exposure match
only); sources get the same normalization the Pi applies.

`fetch.py` (`parr-fetch`) downloads a Wikimedia Commons category with per-file licence checks and a
`manifest.json`; it is a generic corpus utility, not a Parr reference set.

### Experiments (`parr/experiments/`)

Offline grading experiments that never change production defaults. `partitions.py` enforces
checksum-verified, scene-grouped train/validation splits; `regression.py` freezes immutable
snapshots of ungraded/graded triplets; `candidates.py` bakes starter-derived controls into
deployable LUTs; `train.py`/`evaluate.py` run pilots and paired comparisons. Results are written up
in `docs/experiments/`. `scripts/prepare_refinement.py` is a dated curation recipe for one run.

### StickS3 firmware (`firmware/sticks3/`, PlatformIO, ESP32-S3, M5Unified)

`capture_client.{h,cpp}` is a pure state machine (Connecting → Ready → Requesting → Processing →
Downloading → Photo/Error) with no Arduino/Wi-Fi/display dependency so it can run under the `native`
Unity test env. `main.cpp` runs networking in a FreeRTOS task and the UI loop on the main task;
`display.cpp` draws colour bars, status, and the decoded JPEG. Config enters only as four
`STICKS3_*` compile defines appended by `scripts/generate_config.py` from `.env`; empty defaults on a
clean clone leave the device unable to join a network. Build outputs contain credentials.

### Deployment (`scripts/deploy_remote.py`, `deploy/parr-capture.service.example`)

Topology: the Pi runs its own WPA2 hotspot (`scripts/pi_hotspot.py`, a NetworkManager keyfile
generated from `.env`) and the Stick joins it directly; SSH and photo transfer go over Ethernet
(`parr.local` via avahi). `WIFI_SSID`/`WIFI_PASSWORD` in `.env` are therefore the hotspot's
credentials, `PARR_REMOTE_URL`'s host is the hotspot address, `PI_HOST` is the SSH address, and
`PARR_LISTEN` (default `0.0.0.0:8765`) is where `parr-capture` binds.

`deploy_remote.py` uses Paramiko with system known_hosts and `RejectPolicy`; it inspects the Pi
(project dir, artifact, running `parr-capture`, `/dev/video*` owners, desktop sessions) and refuses
to restart when a foreign process owns the camera. The systemd unit is the headless Stick-only mode
and reads `PARR_REMOTE_TOKEN` from `/etc/parr-capture.env`. Two-screen mode (`--show-captures`) must
be launched from the Pi's desktop session, not over SSH. Full guide: `docs/sticks3-remote.md`.

## Conventions and constraints

- `.env` holds Pi/Wi-Fi/token secrets and is gitignored. `.env.example` documents keys. Scripts parse
  it as `KEY=VALUE` data only; never source it or echo values. Never put the token, Wi-Fi password,
  or SSH password into a command line, source file, service unit, or commit.
- `params.json` `version` is currently 2 (`PARAMS_VERSION`). `lut_sha1` is required.
- Module docstrings carry the design rationale (why an order is fixed, why a check exists). Read them
  before changing behaviour; many encode failures found on real hardware.
- Reference photographs must be credited to Martin Parr from primary sources with permission;
  fan-submission groups are excluded. See `docs/reference-sources.md`. Training reports live in
  `docs/training-*.md`.
- `ektar100/` and `velvia/` are downloaded film-reference corpora (gitignored); `velvia-attribution.md`
  records their licences.
- Agent scratch space (`.superpowers/`) is gitignored; implementation plans are committed under
  `docs/superpowers/plans/`.
