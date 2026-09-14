# Pi 4 / IMX708 roadmap progress

Roadmap: [2026-09-11-rpi4-imx708-roadmap.md](2026-09-11-rpi4-imx708-roadmap.md).
Dependency review: 2026-09-13, following highlight-protection commits
`d349fec` and `d44c08d` on `plan/rpi4-imx708-camera`.

## Phase status

| Phase | Status | Next prerequisite |
| --- | --- | --- |
| 1: Picamera2 acquisition | Implementation in progress | Task-by-task plan; fake-request tests can start without photos. Hardware required for acceptance. |
| 2: capture controls and metadata | Implemented; fake-backed tests pass | Hardware acceptance: autofocus (`LensPosition`, `AfState`) and metadata verified on the sensor. |
| 3: original / DNG / graded output | Implemented; fake-backed tests pass | Hardware acceptance: DNG opens correctly in darktable/RawTherapee. |
| 4: benchmark | Not recorded for this roadmap | Synthetic benchmark can start now; real Pi 4 capture and DNG timings follow 1–3. |
| F: lighting experiment | Not recorded for IMX708 | Stable originals, pilot captures and paired lighting test. |
| 6: gentler normalisation | Not implemented | Code can start independently; choose parameters on IMX708 pilot photos before fitting. |
| 5: IMX708 retraining | Not performed | Stable capture/lighting policy, frozen normalisation, source corpus and scene-grouped training route. |
| 7: grain | Not implemented | Phase 4 timing/resolution decision; independent of colour-LUT fitting. |
| 8: scene statistics | Not implemented | Acquisition metadata for full integration; not a blocker for the first retrain. |
| 9: baked highlight protection | Implemented and tested | Select the IMX708 value in Phase 5; current default remains zero. |
| 9: runtime blend | Not implemented; optional | Evidence of need and Phase 8 adaptive inputs. |
| 10: classifier | Not implemented; conditional | Labelled data and evidence simple scene rules are insufficient. |
| F′: final flash | Not recorded | Prototype decision; collect final flash corpus after final lighting is established. |

## Dependency review completed

- Removed the dependency of baked highlight protection on scene statistics.
- Moved highlight-value selection into the first IMX708 training workflow;
  old-camera results do not select a new-camera default.
- Preserved separate controls for normalisation, LUT strength and highlights.
- Identified the scene-grouped CLI gap: `parr/experiments/train.py` accepts a
  `FitConfig` through its Python API but its CLI only exposes `--neutral-cap`.
  `parr-train` exposes highlights but partitions automatically by image.
- Added an explicit source/runtime parity requirement: pre-JPEG pixels and
  decoded saved-JPEG pixels are not identical inputs for exact replay.
- Clarified that new normalisation requires a refit, but suitable originals
  can be reused; DNG development is not needed for the current JPEG trainer.
- Corrected the assumption that 512-px training sampling makes all capture
  modes and pre-LUT resizing paths interchangeable.
- Moved final lighting establishment before the production flash corpus, or
  required a later recollection/refit if the light changes.

## Photo milestones

1. **Implementation can start now without a corpus.** Real shots are needed
   to accept acquisition, metadata and saved-file behaviour on hardware.
2. **First useful handoff: after Phases 1–3.** Target 20–30 pilot originals
   across 8–10 scenes, with capture logs and scene IDs. Include ten matched
   flash/ambient pairs if testing a light. Use these for F/6 decisions.
3. **Production collection: after capture and lighting are stable.** At least
   100 development originals over 25 scenes, plus 3–5 separate final-test
   scenes. Collection may overlap Phase 6 implementation; normalisation must
   be fixed before fitting. Prepare at least 200 coherent references separately.
4. **First production fit: Phase 5.** Use scene-held-out development data to
   select the fit and highlights; inspect the untouched final scenes only
   after settings are fixed. No IMX708 quality claim exists yet.

## Next implementation unit

Prepare the Phase 1 task-by-task plan against `parr/capture/camera.py`,
`parr/capture/app.py` and the existing fake-camera tests. Include how request
ownership can support Phase 3 without prematurely releasing saved-image data,
and preserve the V4L2/FakeCamera paths and Stick thumbnail behaviour.
Photo collection is not a blocker for writing or testing that software plan.
The remaining hardware/API assumptions in the roadmap must be checked against
the installed Picamera2/libcamera versions during that planning and bring-up.

## Validation of the September 13 roadmap review

Reviewed current highlight/config/provenance code, capture frame/session code,
normalisation and dataset handling, scene-partition training, training guide,
and the completed highlight experiment/progress records. Roadmap-relative
Markdown file links resolve and `git diff --check` passes. That review changed
documentation only; implementation progress is recorded below.

## 2026-09-14 — camera delivered; Phase 1 started

User reports the IMX708 autofocus camera has arrived. Connection to the Pi 4, SSH address, installed stack and exact lens variant are not yet confirmed.

Implementation plan: [Picamera2 acquisition](2026-09-14-picamera2-acquisition.md). Baseline camera/app/controller tests: 85 passed. Use fake Picamera2 requests for development; hardware acceptance remains separate. Preserve the prior roadmap review edits.

- Backend implemented: optional stream metadata, native BGR-to-RGB copy, measured FPS, request/close cleanup and lazy OS dependency. Focused camera tests: **50 passed**; Ruff and diff checks clean. Scoped spec and quality review passed; CLI integration in progress.

- Hardware checklist: [Picamera2 bring-up](../../picamera2-bringup.md). Hardware identity, SSH access and native capture acceptance remain pending. Existing deploy script/service examples omit backend selection; migration must set the intended backend/tuning explicitly.

- CLI selection checks: **63 app tests passed**. Explicit backend/tuning, automatic selection, fake bypass and dependency/conflict errors verified. Native session/thumbnail acceptance test and final suite remain in progress.

## 2026-09-14 — Phase 1 hardware acceptance on the Pi 4 (192.168.178.87)

Hardware confirmed and Phase 1 accepted on the real board.

- **Board / stack:** Raspberry Pi 4 Model B Rev 1.4, 8 GB, Raspberry Pi OS Trixie,
  kernel 6.18; Picamera2 0.3.37, libcamera 0.7.2 from apt.
- **Camera:** `imx708_wide` — the Wide variant, so `imx708_wide.json` is correct.
  Native 4608 × 2592, 10-bit `SBGGR10_CSI2P` (not 12-bit; the backend reads bit
  depth from the live config). `config.txt` already carries `dtoverlay=imx708`
  with `imx477` commented; RTC overlay and I2C present.
- **Capture test:** a direct `Picamera2Camera` + `CaptureSession` run saved two
  native 4608 × 2592 frames. `captures.jsonl` recorded `frame_source=picamera2`,
  `sensor_mode=4608x2592 SBGGR10_CSI2P`, `bit_depth=10`, `tuning_file`, and a
  measured `fps` of 14.35 from `FrameDuration`. The graded JPEG was pulled back
  and inspected: correct colour, red/blue not swapped, sharp, starter look
  applied. Colour management (BGR→RGB) verified on real pixels.
- **Phase 4 signal (informal):** at full 4608 × 2592 the pipeline took about
  3.4 s per frame and shutter-to-saved about 4.5 s on the Pi 4. This informs the
  Phase 4 full-res-versus-binned decision; a formal benchmark is still separate.

### Branch-lineage fix

`plan/rpi4-imx708-camera` was cut from `main` before the UPS battery work merged
(PR #9/#11), so it had the Picamera2 backend but not the `--ups` flag. The
installed unit (from the UPS deployment) passes `--ups x728`, so the first deploy
crash-looped with `unrecognized arguments: --ups x728`. Fixed by merging
`origin/main` into the branch (one import conflict in `parr/capture/app.py`,
resolved to keep both the `--camera` and `--ups` wiring). Full suite 475 passed,
ruff clean.

### Service state

The installed unit now runs `... --ups x728 --camera picamera2 --tuning-file
imx708_wide.json`. After the merge was pulled and the service restarted:
`active/running`, `NRestarts=0`, listening on `0.0.0.0:8765`, `/v1/status`
returns `ready:true` with `pi_battery` present and 401 without the token. The Pi
is on branch `plan/rpi4-imx708-camera`; it should return to `main` once this
branch merges.

### Still pending (manual / next)

- End-to-end Stick capture over the Pi's hotspot (this Pi was reached on the home
  network; the hotspot path was not exercised here).
- Autofocus control, per-shot AE/AWB metadata and original/DNG output are Phases
  2–3, not in this backend.
- A dedicated Phase 4 benchmark, and the pilot corpus (20–30 originals) once
  Phases 2–3 land.

## 2026-09-14 — Phases 2 and 3 implemented (fake-backed tests only)

Plan: [IMX708 Autofocus, Metadata and Original/DNG Output](2026-09-14-imx708-af-metadata-dng.md),
Tasks 1–4 on `plan/imx708-af-metadata-dng`.

- **Phase 2 (autofocus, AE/AWB control, metadata):** `Picamera2Camera` neutralises
  Sharpness/Contrast/Saturation and noise reduction, defaults to continuous
  autofocus at normal range, and leaves AE/AWB auto (no flash, per the 2026-09-14
  decision recorded in the implementation plan); `--ae-lock`, `--awb-lock` and
  `--colour-gains R,B` are available for controlled shoots. Each `read()` filters
  the request's metadata to a fixed, JSON-serialisable key set
  (`ExposureTime`, `AnalogueGain`, `DigitalGain`, `ColourGains`,
  `ColourTemperature`, `Lux`, `LensPosition`, `AfState`, `FocusFoM`,
  `FrameDuration`, `SensorTimestamp`) and drops the rest.
- **Phase 3 (original / DNG / graded output):** `CaptureSession.capture()` names
  the Picamera2 original `_original.jpg` always — a Picamera2 frame is the
  camera's own full-quality rendering whether or not a DNG sidecar is also
  saved — writes a `<stem>.dng` sidecar from the same request when `save_dng`
  is enabled, and records `camera_metadata` and `dng` in `captures.jsonl`.
  `--no-dng` disables the sidecar on both the backend and the session; it only
  omits the `.dng` file and never changes the original's name.
- **Task 4 (this entry):** added an end-to-end fake-backed test in
  `tests/test_picamera.py` that drives the real `Picamera2Camera` (via the
  injected fake `picamera2`/`libcamera` modules and a fake capture request)
  through a real `CaptureSession`, asserting the day folder holds
  `*_original.jpg`, `*.dng` and `*_parr.jpg`; that the last `captures.jsonl`
  record carries `frame_source == "picamera2"`, `camera_metadata`, `dng` and the
  sensor fields; and that `fitted_jpeg` on the graded file returns a
  240 × 135 thumbnail. A second test drives `Picamera2Camera(save_dng=False)`
  (the `--no-dng` path) through the same session and confirms the original is
  still saved as `_original.jpg`, with no `.dng` file, no `dng` key, and zero
  calls to the fake request's `save_dng`. Full suite:
  522 passed, 1 deselected (`-m 'not slow'`); Ruff clean. Documentation updated:
  `docs/picamera2-bringup.md`, `docs/setup.md`, `README.md`.
- **Hardware acceptance still pending** (fake-backed tests are not hardware
  acceptance): the DNG opens correctly in darktable/RawTherapee with correct
  colour; autofocus moves `LensPosition` and `AfState` is verified across
  subject distances on the sensor; `ExposureTime`, `AnalogueGain` and `Lux` are
  plausible for the scene; and the API-verification checklist from the
  implementation plan — `get_metadata()` key names actually present on this
  sensor, whether `save_dng(path)` also accepts a file object, presence of
  `AfModeEnum`/`AfRangeEnum`/`autofocus_cycle()` and whether the Wide module
  reports `AfState` and moves `LensPosition`, and whether the
  `NoiseReductionMode` enum path exists on the installed libcamera (0.7.2) or
  must be skipped.
