# IMX708 Autofocus, Metadata and Original/DNG Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record per-shot camera metadata and a controlled, neutrally-rendered autofocus capture on the IMX708, and save a true original JPEG plus a DNG alongside the graded output, so captures become a trustworthy, re-developable training corpus.

**Architecture:** Keep the `Camera` protocol. Extend `Frame` with optional `metadata` and `dng` fields that the Picamera2 backend fills from the same request that produced the RGB, released inside `read()` as now. Add neutral-ISP and autofocus controls to `Picamera2Camera` and their CLI flags. Extend `CaptureSession.capture()` to name the Pi original `_original.jpg`, write the DNG, and record the metadata. V4L2 and Fake paths are unchanged.

**Tech Stack:** Python, NumPy, Pillow, pytest, Ruff; Picamera2/libcamera from Raspberry Pi OS apt (0.3.37 / 0.7.2 confirmed on the Pi 4), never pip.

**Spec:** `docs/superpowers/plans/2026-09-11-rpi4-imx708-roadmap.md`, Phases 2 and 3. Phase 1 is merged (PR #12). **Decision (2026-09-14): no flash in the long run.** Therefore exposure and white balance stay auto by default to match how the camera is used, and there is no flash mode; AE/AWB locks and fixed colour gains exist only for optional controlled shoots.

## Global Constraints

- Picamera2 and libcamera come from apt; the venv uses `--system-site-packages`. Never add them to `pyproject.toml`.
- The optional dependency stays lazy: importing the project, `--camera v4l2`, and `--fake` must work with no Picamera2/libcamera present. All new Picamera2 control/enum imports are inside the backend, never at module top level of anything the USB/fake path imports.
- One request per capture, released in `finally` in `read()`, including on conversion, metadata or DNG-extraction failure. Metadata and DNG are extracted from that request before release; nothing holds a live request past `read()`.
- `Frame` gains `metadata: dict | None = None` and `dng: bytes | None = None`, both defaulting to `None`, so V4L2/Fake frames are unaffected and existing `Frame(...)` positional calls keep working.
- Recorded metadata is JSON-serialisable: numbers, or short lists of numbers. Filter to a fixed key set; drop anything absent or non-serialisable rather than raising.
- The Pi original is the ISP's own 8-bit RGB rendering, saved once as `_original.jpg`; there is no separate camera JPEG. `_ungraded.jpg` is only used when no original and no DNG exist (never for this backend).
- `--no-dng` skips the DNG (storage), still saving `_original.jpg` and `_graded.jpg`.
- Preserve the five-field `StreamInfo.to_dict()` for absent optional fields, and the existing `captures.jsonl` keys; new keys are additive.
- Ruff clean (`E, F, I, B, UP`, line length 100). Firmware untouched. Branch cut from `main` at the PR #12 merge.

## Hardware / API verification (do before Task 2, and record on the Pi)

These Picamera2 0.3.37 / libcamera 0.7.2 facts must be checked on the Pi (`192.168.178.87`, account `george`, checkout on this branch) and written into `docs/superpowers/plans/2026-09-13-rpi4-imx708-progress.md`. Development uses fakes; hardware acceptance is separate.

- `CompletedRequest.get_metadata()` key names actually present for this sensor: confirm `ExposureTime`, `AnalogueGain`, `DigitalGain`, `ColourGains`, `ColourTemperature`, `Lux`, `LensPosition`, `AfState`, `FocusFoM`, `FrameDuration`, `SensorTimestamp`. Record which exist; the code keeps whichever are present.
- `CompletedRequest.save_dng(path)` exists and writes a valid DNG that opens in darktable/RawTherapee. Confirm whether it also accepts a file object; if not, the backend writes a temporary file and reads it back (see Task 2).
- Autofocus controls: `libcamera.controls.AfModeEnum` (`Continuous`, `Auto`, `Manual`), `AfRangeEnum` (`Normal`, `Macro`, `Full`), and `Picamera2.autofocus_cycle()`. Confirm the Wide module reports `AfState` and moves `LensPosition`.
- `NoiseReductionMode`: confirm the enum path (`libcamera.controls.draft.NoiseReductionModeEnum.HighQuality`); if absent, skip it and record that only Sharpness/Contrast/Saturation were neutralised.

---

## Task 1: Frame metadata/DNG fields and session output

**Files:** modify `pifilm/capture/camera.py` (`Frame`), `pifilm/capture/app.py` (`CaptureSession.capture`), `tests/test_app.py`.

**Interfaces:**
- Produces: `Frame(rgb, jpeg, source, metadata: dict | None = None, dng: bytes | None = None)`. `CaptureSession.capture()` writes `_original.jpg` when `frame.jpeg` or `frame.dng` is present, writes `<stem>.dng` when `frame.dng` is present and `save_dng` is enabled, and records `camera_metadata` and `dng` in the JSONL. `CaptureSession(..., save_dng: bool = True)`.

- [ ] **Step 1: Write the failing tests** (extend `tests/test_app.py`)

```python
def test_capture_writes_original_and_dng_and_records_metadata(tmp_path):
    import numpy as np
    from pifilm.capture.app import CaptureSession
    from pifilm.capture.camera import Frame, StreamInfo
    from pifilm.artifacts import Artifacts
    from pifilm.pipeline import Pipeline

    class MetaCamera:
        stream_info = StreamInfo(4608, 2592, 14.35, "RGB888", False,
                                 sensor_mode="4608x2592 SBGGR10_CSI2P", bit_depth=10,
                                 tuning_file="imx708_wide.json")
        def read(self):
            rgb = np.zeros((8, 8, 3), dtype=np.uint8)
            return Frame(rgb=rgb, jpeg=None, source="picamera2",
                         metadata={"ExposureTime": 9995, "AnalogueGain": 2.0, "Lux": 120.0},
                         dng=b"II*\x00fake-dng-bytes")
        def close(self): ...

    sess = CaptureSession(MetaCamera(), Pipeline(Artifacts.default()), tmp_path,
                          seed_rng=np.random.default_rng(0))
    result = sess.capture()
    day = result.pifilm.parent
    assert result.original.name.endswith("_original.jpg")
    dng = day / (result.original.name.replace("_original.jpg", ".dng"))
    assert dng.read_bytes() == b"II*\x00fake-dng-bytes"
    assert result.record["camera_metadata"] == {"ExposureTime": 9995, "AnalogueGain": 2.0, "Lux": 120.0}
    assert result.record["dng"] == dng.name


def test_capture_skips_dng_when_disabled(tmp_path):
    import numpy as np
    from pifilm.capture.app import CaptureSession
    from pifilm.capture.camera import Frame, StreamInfo
    from pifilm.artifacts import Artifacts
    from pifilm.pipeline import Pipeline

    class C:
        stream_info = StreamInfo(8, 8, 0.0, "RGB888", False)
        def read(self):
            return Frame(np.zeros((8, 8, 3), np.uint8), None, "picamera2", dng=b"raw")
        def close(self): ...

    sess = CaptureSession(C(), Pipeline(Artifacts.default()), tmp_path,
                          seed_rng=np.random.default_rng(0), save_dng=False)
    result = sess.capture()
    assert not list(result.pifilm.parent.glob("*.dng"))
    assert "dng" not in result.record
    assert result.original.name.endswith("_original.jpg")


def test_v4l2_style_frame_without_metadata_is_unchanged(tmp_path):
    import numpy as np
    from pifilm.capture.app import CaptureSession
    from pifilm.capture.camera import Frame, StreamInfo
    from pifilm.artifacts import Artifacts
    from pifilm.pipeline import Pipeline

    class Usb:
        stream_info = StreamInfo(1920, 1080, 30.0, "MJPG", True)
        def read(self):
            return Frame(np.zeros((8, 8, 3), np.uint8), b"\xff\xd8jpg\xff\xd9", "raw-mjpeg")
        def close(self): ...

    result = CaptureSession(Usb(), Pipeline(Artifacts.default()), tmp_path,
                            seed_rng=np.random.default_rng(0)).capture()
    assert result.original.name.endswith("_original.jpg")   # jpeg present -> original
    assert "camera_metadata" not in result.record
    assert "dng" not in result.record
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest -q tests/test_app.py -k "metadata or dng or v4l2_style"`
Expected: FAIL — `Frame` has no `metadata`/`dng`; `capture()` writes `_ungraded`, records no metadata.

- [ ] **Step 3: Implement**

In `pifilm/capture/camera.py`, extend `Frame`:

```python
@dataclass
class Frame:
    rgb: np.ndarray
    jpeg: bytes | None
    source: str  # "raw-mjpeg", "decoded", or "picamera2"
    metadata: dict | None = None  # per-shot camera metadata (picamera2)
    dng: bytes | None = None      # in-memory DNG for this frame (picamera2)
```

In `CaptureSession.__init__`, add `save_dng: bool = True` and store `self._save_dng = save_dng`. In `capture()`, replace the suffix/original block and record:

```python
        has_original = frame.jpeg is not None or frame.dng is not None
        suffix = "original" if has_original else "ungraded"
        day_dir, stem, t = self._allocate(suffix)
        original = day_dir / f"{stem}_{suffix}.jpg"
        if frame.jpeg is not None:
            original.write_bytes(frame.jpeg)
        else:
            save_jpeg(frame.rgb, original)
        dng_name = None
        if frame.dng is not None and self._save_dng:
            dng_path = day_dir / f"{stem}.dng"
            dng_path.write_bytes(frame.dng)
            dng_name = dng_path.name
        pifilm = save_jpeg(graded, day_dir / f"{stem}_graded.jpg")
```

and in the `record` dict, after `"frame_source": frame.source,` add:

```python
            **({"camera_metadata": frame.metadata} if frame.metadata else {}),
            **({"dng": dng_name} if dng_name else {}),
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q tests/test_app.py && .venv/bin/ruff check pifilm tests`
Expected: pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add pifilm/capture/camera.py pifilm/capture/app.py tests/test_app.py
git commit -m "Carry per-shot metadata and DNG on Frame; save original and DNG"
```

---

## Task 2: Backend fills metadata and DNG from the request

**Files:** modify `pifilm/capture/picamera.py`, `tests/test_picamera.py`.

**Interfaces:**
- Consumes: `Frame.metadata`, `Frame.dng` (Task 1).
- Produces: `Picamera2Camera(tuning_file=..., save_dng: bool = True)`; `read()` returns a `Frame` with `metadata` (filtered subset) and, when `save_dng`, `dng` bytes. Module constant `METADATA_KEYS: tuple[str, ...]`; helper `serialisable_metadata(raw: dict) -> dict`.

- [ ] **Step 1: Write the failing tests** using the existing fake Picamera2 request. Extend the fake request in `tests/test_picamera.py` to carry a `get_metadata()` dict and a `save_dng(path)` that writes known bytes. Assert:

```python
def test_read_populates_serialisable_metadata_subset():
    # fake get_metadata returns extra + non-serialisable keys; only the known,
    # serialisable subset survives, with ColourGains coerced to a list.
    frame = camera.read()
    assert frame.metadata["ExposureTime"] == 9995
    assert frame.metadata["ColourGains"] == [1.8, 2.1]
    assert "ScalerCrop" not in frame.metadata   # dropped: not in METADATA_KEYS

def test_read_includes_dng_bytes_when_enabled():
    frame = camera.read()
    assert frame.dng[:4] == b"II*\x00"   # fake save_dng wrote a TIFF/DNG magic
    assert request.release_count == 1     # request still released exactly once

def test_read_omits_dng_when_disabled():
    # Picamera2Camera(..., save_dng=False): save_dng never called, frame.dng is None
    assert frame.dng is None
    assert fake_request.save_dng_calls == 0

def test_dng_extraction_failure_still_releases_the_request():
    # fake save_dng raises; read() raises CameraError and release_count == 1
    ...
```

Write the fake so `save_dng(path)` writes `b"II*\x00...bytes"` to the path; the backend reads it back. Keep native-size arrays but small DNG payloads.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_picamera.py -q`
Expected: FAIL — metadata not on the frame; no `save_dng`; no `save_dng` constructor arg.

- [ ] **Step 3: Implement.** Add the subset and a serialiser, thread `save_dng` through the constructor, and in `read()` extract metadata and (optionally) the DNG before `request.release()`:

```python
METADATA_KEYS = (
    "ExposureTime", "AnalogueGain", "DigitalGain", "ColourGains", "ColourTemperature",
    "Lux", "LensPosition", "AfState", "FocusFoM", "FrameDuration", "SensorTimestamp",
)

def serialisable_metadata(raw: dict) -> dict:
    out: dict = {}
    for key in METADATA_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, (tuple, list)) and all(isinstance(v, (int, float)) for v in value):
            out[key] = [float(v) for v in value]
        else:
            try:
                out[key] = int(value)          # libcamera enums (e.g. AfState) are int-like
            except (TypeError, ValueError):
                pass
    return out
```

In `__init__`, accept `save_dng: bool = True` and store `self._save_dng`. In `read()`, inside the existing `try`, after building `rgb`:

```python
                metadata = serialisable_metadata(request.get_metadata())
                self._update_fps({"FrameDuration": metadata.get("FrameDuration", 0)})
                dng = None
                if self._save_dng:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".dng", delete=True) as tmp:
                        request.save_dng(tmp.name)
                        tmp.seek(0)
                        dng = tmp.read()
                return Frame(rgb=rgb, jpeg=None, source="picamera2", metadata=metadata, dng=dng)
```

Keep the existing `finally: request.release()` and its error precedence. During hardware bring-up, verify whether `save_dng` accepts a file object; if it does, prefer `io.BytesIO` over the temp file and note it in the progress doc.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_picamera.py tests/test_camera.py -q && .venv/bin/ruff check pifilm tests`
Expected: pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add pifilm/capture/picamera.py tests/test_picamera.py
git commit -m "Extract per-shot metadata and DNG bytes from the Picamera2 request"
```

---

## Task 3: Neutral ISP rendering, autofocus, and controlled-shoot controls

**Files:** modify `pifilm/capture/picamera.py`, `pifilm/capture/app.py`, `tests/test_picamera.py`, `tests/test_app.py`.

**Interfaces:**
- Produces: `Picamera2Camera(tuning_file=..., save_dng=True, autofocus="continuous", af_range="normal", ae_lock=False, awb_lock=False, colour_gains: tuple[float, float] | None = None)`. CLI: `--autofocus {continuous,auto,manual}` (default continuous), `--af-range {normal,macro,full}` (default normal), `--ae-lock`, `--awb-lock`, `--colour-gains R,B` — all Picamera2-only, argparse errors if combined with `--camera v4l2` — plus `--no-dng`, which toggles the session/backend DNG output independently of backend choice and is deliberately *accepted* on `--camera v4l2` too.

- [ ] **Step 1: Write failing tests.** Backend tests assert the control dict applied at start (via the fake camera recording `set_controls`/`configure` controls): neutral `Sharpness=Contrast=Saturation=1.0`; `AfMode` continuous maps to the continuous enum; `af_range` maps correctly; `colour_gains` sets `ColourGains` and disables AWB; `autofocus="auto"` triggers one `autofocus_cycle()` per `read()` (assert call count == reads); `autofocus="manual"` never cycles. CLI tests: each flag reaches the backend; `--colour-gains 1.8,2.1` parses to `(1.8, 2.1)`; a malformed value is an argparse error; every Picamera2-only flag with `--camera v4l2` is an argparse error; `--no-dng` sets `save_dng=False`; defaults leave AE/AWB auto (no lock controls set).

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_picamera.py tests/test_app.py -q`
Expected: FAIL — no such constructor args/flags.

- [ ] **Step 3: Implement.** In the backend, import the libcamera control enums lazily inside `__init__` (never at module top), build a controls dict, and apply it. Neutral tone plus autofocus:

```python
        from libcamera import controls as _lc
        cam_controls = {"Sharpness": 1.0, "Contrast": 1.0, "Saturation": 1.0}
        try:
            cam_controls["NoiseReductionMode"] = _lc.draft.NoiseReductionModeEnum.HighQuality
        except AttributeError:
            pass  # older libcamera: leave NR at its default, recorded as unset
        af_modes = {"continuous": _lc.AfModeEnum.Continuous,
                    "auto": _lc.AfModeEnum.Auto, "manual": _lc.AfModeEnum.Manual}
        af_ranges = {"normal": _lc.AfRangeEnum.Normal,
                     "macro": _lc.AfRangeEnum.Macro, "full": _lc.AfRangeEnum.Full}
        cam_controls["AfMode"] = af_modes[autofocus]
        cam_controls["AfRange"] = af_ranges[af_range]
        if colour_gains is not None:
            cam_controls["AwbEnable"] = False
            cam_controls["ColourGains"] = tuple(colour_gains)
        elif awb_lock:
            cam_controls["AwbEnable"] = False
        if ae_lock:
            cam_controls["AeEnable"] = False
```

Validate `autofocus`/`af_range` against the known keys and raise `CameraError` on an unknown value (so a bad value fails fast with a clear message rather than a `KeyError`). Apply the controls with `camera.set_controls(cam_controls)` after `configure` and before or right after `start()` per the manual; verify ordering on hardware. Store `self._autofocus = autofocus`. In `read()`, before `capture_request()`:

```python
        if self._autofocus == "auto":
            try:
                camera.autofocus_cycle()
            except Exception as exc:
                raise CameraError(f"Autofocus cycle failed: {exc}") from exc
```

In `app.py`, add the flags near `--camera`/`--tuning-file`, parse `--colour-gains` with a small `_colour_gains(value)` type function returning `(r, b)` and raising `argparse.ArgumentTypeError` on malformed input, guard each Picamera2-only flag against `--camera v4l2` (extend the existing guard block), and pass them into `Picamera2Camera(...)`. Pass `save_dng=not args.no_dng` into `CaptureSession(...)`.

Default behaviour with no flags: continuous AF, normal range, AE and AWB auto, DNG on. This matches "shoot the way the camera will be used," per the no-flash decision.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -q -m 'not slow' && .venv/bin/ruff check .`
Expected: full suite passes; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add pifilm/capture/picamera.py pifilm/capture/app.py tests/test_picamera.py tests/test_app.py
git commit -m "Add neutral ISP rendering, autofocus and controlled-shoot controls"
```

---

## Task 4: Fake-backed integration test and documentation

**Files:** modify `tests/test_picamera.py`, `docs/picamera2-bringup.md`, `docs/setup.md`, `README.md`, `docs/superpowers/plans/2026-09-13-rpi4-imx708-progress.md`.

- [ ] **Step 1: Write a failing fake-backed `CaptureSession` test** in `tests/test_picamera.py` that drives the real `Picamera2Camera` with the injected fake module and a tiny artifact: capture once and assert the day folder holds `*_original.jpg`, `*.dng` and `*_graded.jpg`, all present; `captures.jsonl`'s last record has `frame_source == "picamera2"`, a `camera_metadata` object, a `dng` filename, and the sensor fields; and a 240 × 135 thumbnail comes back through `fitted_jpeg` on the graded file. Add a second case with `save_dng=False` asserting no `.dng` and no `dng` key.

- [ ] **Step 2: Run to verify it fails**, then rely on Tasks 1–3 already implementing the behaviour; if the test passes immediately because the pieces exist, tighten it until it exercises a path not already asserted (the end-to-end folder contents), per TDD honesty.

- [ ] **Step 3: Documentation.**
  - `docs/picamera2-bringup.md`: add a Phase 2/3 section — the capture now writes `_original.jpg` + `.dng` + `_graded.jpg`; `captures.jsonl` carries `camera_metadata` and `dng`; verify the DNG opens in darktable/RawTherapee with correct colour; note `--no-dng` for long sessions and the storage figure (about 28 MB per shot); note AE/AWB stay auto (no flash), with `--ae-lock`/`--awb-lock`/`--colour-gains` for controlled reference-matching shoots; confirm autofocus moves `LensPosition` and records `AfState`.
  - `docs/setup.md` and `README.md`: extend the camera-backend text with the new flags and the three output files.
  - `docs/superpowers/plans/2026-09-13-rpi4-imx708-progress.md`: mark Phases 2 and 3 implemented (tests) and list the hardware acceptance still pending (DNG opens correctly; autofocus and metadata verified on the sensor; the API-verification checklist above).

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q -m 'not slow'` and `.venv/bin/ruff check .`; controller reviews and commits.

```bash
git add tests/test_picamera.py docs/picamera2-bringup.md docs/setup.md README.md docs/superpowers/plans/2026-09-13-rpi4-imx708-progress.md
git commit -m "Integration test and docs for IMX708 metadata and original/DNG output"
```

---

## Hardware acceptance (manual, on the Pi 4, after the suite is green)

Deploy the branch to the Pi, stop the service, and capture a few frames with real objects at different distances:

```sh
.venv/bin/pifilm-capture --camera picamera2 --tuning-file imx708_wide.json --no-preview \
  --out ~/Pictures/pifilm-imx708-phase23
```

Confirm: `_original.jpg`, `.dng` and `_graded.jpg` per shot at 4608 × 2592; the DNG opens in darktable/RawTherapee with correct colour; `captures.jsonl` records `camera_metadata` with a plausible `ExposureTime`, `AnalogueGain`, `Lux` and a `LensPosition` that changes with distance; and repeated captures do not stall. Then restore the service (its unit already selects the Picamera2 backend). Record results in the progress document; passing fake-backed tests are not hardware acceptance.

After this lands, the pilot corpus can begin: 20–30 originals across 8–10 scenes with capture logs and scene IDs, per the roadmap, then the production corpus once normalisation (Phase 6) is chosen.

## Self-review

- **Spec coverage.** Phase 2 (autofocus control, AE/AWB control, metadata): Tasks 2 and 3. Phase 3 (original + DNG + graded): Tasks 1 and 2. No-flash decision honoured: no flash mode; AE/AWB auto by default with optional locks. Out of roadmap scope and excluded: normalisation changes (Phase 6), the LUT retrain (Phase 5), scene statistics (Phase 8), the runtime highlight blend.
- **Placeholder scan.** Each code step carries real code; the libcamera enum paths and `save_dng` buffer behaviour are marked for on-hardware verification (they depend on the installed version), not left as logic gaps.
- **Type consistency.** `Frame(rgb, jpeg, source, metadata=None, dng=None)` defined in Task 1 and populated in Task 2. `CaptureSession(..., save_dng=True)` defined in Task 1, set from `--no-dng` in Task 3. `serialisable_metadata`/`METADATA_KEYS` defined and used in Task 2. `Picamera2Camera` keyword set is consistent across Tasks 2 and 3 and the CLI.
