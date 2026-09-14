# Picamera2 Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture native 4608 × 2592 IMX708 RGB frames through the existing camera protocol, preserving USB/fake capture and recording negotiated stream information.

**Architecture:** Keep `Frame` and `Camera` unchanged. Add a lazily imported Picamera2 backend in its own module, with request ownership entirely inside `read()`. Extend `StreamInfo` with optional sensor fields and integrate backend selection into the existing CLI. The existing session saves `_ungraded.jpg` and `_parr.jpg`; original JPEG/DNG ownership belongs to Phase 3.

**Tech Stack:** Python, NumPy, pytest, Ruff; Picamera2/libcamera supplied by Raspberry Pi OS apt packages, never added to pip dependencies.

**Spec:** `docs/superpowers/plans/2026-09-11-rpi4-imx708-roadmap.md`, Phase 1 and source-data gates. User approved proceeding after camera delivery on 2026-09-14. Track work in `2026-09-13-rpi4-imx708-progress.md` separately.

## Global Constraints

- Native main size `(4608, 2592)`, `RGB888` format, native raw stream, two buffers, continuous still configuration. `RGB888` arrays contain BGR bytes; reverse channels into an owned, contiguous RGB uint8 array.
- Use `queue=False` so a previous queued frame is not presented as a fresh capture. Release every acquired request in `finally`, including conversion/metadata failures.
- Optional dependency stays lazy: importing the project, explicit V4L2, and `--fake` must work without Picamera2 or libcamera.
- No DNG save, autofocus cycle, manual AE/AWB, normalization, LUT, grain, remote API or firmware changes.
- Explicit tuning filename, initially the roadmap's `imx708_wide.json`, overridable for the delivered lens variant. Hardware variant must be confirmed before deployment; receipt alone does not establish Wide vs standard.
- Record actual configured sensor/raw mode and bit depth. Never assume 12-bit Bayer or a fixed 14 fps. FPS may be zero (not yet measured) until request metadata supplies a positive `FrameDuration`.
- Preserve existing five-field `StreamInfo.to_dict()` output when optional fields are absent.
- Convert setup/read failures to actionable `CameraError`; clean up partially started cameras. Close is idempotent and calls close even if stop fails. Do not silently fall back to USB after Picamera2 acquisition fails.
- Work on current feature branch, preserving pending roadmap/progress edits. Controller handles commits after review, so workers do not stall on Git metadata approval.

## Verified API references

Checked 2026-09-14 against upstream; hardware acceptance must also record the installed versions:

- [Picamera2 manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf): RGB888 byte ordering and OS packages.
- [Picamera2 source](https://github.com/raspberrypi/picamera2/blob/main/picamera2/picamera2.py): load_tuning_file, create_still_configuration, camera_configuration, capture_request.
- [CompletedRequest source](https://github.com/raspberrypi/picamera2/blob/main/picamera2/request.py): make_array, get_metadata, release.

## Task 1: backend and stream metadata

**Files:** create `parr/capture/picamera.py`, `tests/test_picamera.py`; modify `parr/capture/camera.py` and `tests/test_camera.py`.

**Interfaces:**

```python
# Additional StreamInfo fields; omit None values from to_dict().
sensor_mode: str | None = None
bit_depth: int | None = None
tuning_file: str | None = None

# parr.capture.picamera
DEFAULT_TUNING_FILE = "imx708_wide.json"
class Picamera2Camera:
    def __init__(self, tuning_file: str = DEFAULT_TUNING_FILE): ...
    @property
    def stream_info(self) -> StreamInfo: ...
    def read(self) -> Frame: ...
    def close(self) -> None: ...
```

- [ ] Write fake Picamera2 module/request tests first. Inject via monkeypatch/sys.modules; no camera packages needed. Fake returns configured native main/raw stream and sensor bit depth. Cover missing dependency, tuning failure, configure/start failure cleanup, negotiated size/format mismatch rejection, actual metadata serialization, uint8/shape validation, read after close, idempotent close, and request release on success and errors.

```python
# Fake request owns a BGR array; mutate it during release to expose aliasing.
frame = camera.read()
assert frame.rgb.dtype == np.uint8
assert frame.rgb.flags.c_contiguous
assert frame.jpeg is None
assert frame.source == "picamera2"
assert frame.rgb[0, 0].tolist() == [230, 40, 10]  # request BGR [10, 40, 230]
assert request.release_count == 1
```

Use small negotiated dimensions only when testing helper logic; the backend must reject non-native capture configuration. A full native test array is about 36 MB; release fixtures promptly. Assert old stream-info serialization remains exactly unchanged.

- [ ] Run `.venv/bin/python -m pytest tests/test_picamera.py tests/test_camera.py -q`; confirm failures name absent backend/fields.
- [ ] Implement the backend with lazy `from picamera2 import Picamera2` inside construction. Load explicit tuning, configure and inspect the actual configuration before starting:

```python
config = camera.create_still_configuration(
    main={"size": (4608, 2592), "format": "RGB888"},
    raw={"size": (4608, 2592)}, buffer_count=2, queue=False,
)
camera.configure(config)
actual = camera.camera_configuration()
# Validate native main/raw dimensions and RGB888 main format.
# Derive bit_depth from actual["sensor"]["bit_depth"], not a constant.
camera.start()
```

Represent `sensor_mode` as actual raw dimensions and format, e.g. `4608x2592 SBGGR10_CSI2P`. Read ownership:

```python
request = camera.capture_request()
try:
    bgr = request.make_array("main")
    # Reject wrong dtype/shape before conversion.
    rgb = np.array(bgr[..., ::-1], dtype=np.uint8, order="C", copy=True)
    metadata = request.get_metadata()
    # Positive finite FrameDuration is microseconds; fps = 1_000_000 / duration.
    return Frame(rgb=rgb, jpeg=None, source="picamera2")
finally:
    request.release()
```

- [ ] Run focused tests and `.venv/bin/ruff check parr tests`. Report RED/GREEN and exact changes; controller reviews before Task 2.
- [ ] Controller commit: `Add native Picamera2 acquisition backend` after review (may batch Git approval with Task 2).

## Task 2: CLI selection, end-to-end fake acceptance and setup

**Files:** modify `parr/capture/app.py`, `tests/test_app.py`, `tests/test_picamera.py`, `docs/setup.md`, `README.md`. Reuse the backend fake fixture in `tests/test_picamera.py` for the native session/thumbnail integration test rather than duplicating it in app tests.

**Interfaces:** `--camera {v4l2,picamera2}` and `--tuning-file NAME_OR_PATH`. Existing `--device` remains V4L2-specific. Preserve `--fake` as a hardware bypass.

- [ ] Add failing CLI tests using backend doubles and the existing simulated terminal loop: explicit V4L2 must not import Picamera2; explicit Picamera2 receives the tuning filename; missing dependency/setup error returns 2; fake bypasses hardware; `--device` implies V4L2 when no camera choice is supplied; explicit Picamera2 plus `--device` is an argparse error; tuning override plus V4L2 is an argparse error.
- [ ] Default selection: explicit `--camera` wins; otherwise `--device` selects V4L2; otherwise prefer Picamera2 if its module imports successfully, as the roadmap specifies, falling back to V4L2 only if unavailable. Keep selection after the fake bypass. Test both default branches without installed hardware libraries.

```python
parser.add_argument("--camera", choices=("v4l2", "picamera2"))
parser.add_argument("--tuning-file", help="Picamera2 tuning filename or absolute path")
```

- [ ] Run `.venv/bin/python -m pytest tests/test_app.py -q` and observe the new selection tests fail before wiring.
- [ ] Wire selection into the current camera-construction try/except and keep cleanup/controller ownership unchanged. Rename USB-only parser description. Do not change the existing capture/remote loops.
- [ ] Add a fake-backed CaptureSession test in `tests/test_picamera.py` exercising the real new backend: load a tiny LUT, capture native RGB, assert saved `_ungraded.jpg` and `_parr.jpg` have native dimensions and JSONL contains actual sensor fields; verify a 240 × 135 bounded thumbnail through the existing thumbnail function. No JPEG/DNG claims in Phase 1.
- [ ] Update setup and README with a concise link to `docs/picamera2-bringup.md` and apt Picamera2, system-site-packages venv, explicit backend/tuning command, `rpicam-hello --list-cameras`, coloured-patch check, saved dimensions/metadata verification, and USB/fake commands. Warn that an installed Picamera2 changes default selection; the USB service should explicitly use `--camera v4l2` until migrated. No deployment or service edits on a remote host without knowing the correct host and hardware.
- [ ] Run camera/app/thumbnail/controller focused tests and Ruff. Controller runs full suite once, reviews, updates separate progress and commits `Select Picamera2 capture from CLI and document bring-up`.

## Hardware acceptance gate

On the identified Pi 4, first inspect OS, model, installed Picamera2/libcamera versions and camera enumeration. Confirm the delivered lens/tuning variant. Once setup and service ownership are understood, use `parr-capture --camera picamera2 --no-preview` with explicit tuning and a new output directory. Take coloured-patch and ordinary frames; verify native dimensions, correct RGB order, recorded mode/bit depth/tuning, no repeated buffer exhaustion, and remote thumbnail behaviour. Record measured outcomes in progress; tests using fakes do not complete this gate.

## Self-review

Both tasks preserve Frame/Camera and existing capture lifetime, so autofocus and retained RAW requests are deliberately deferred. Task 1 supplies the class and optional fields Task 2 consumes. Tests cover resource ownership, selection and real session serialization. Hardware-only observations stay pending until the identified Pi is available. Highlight code and its zero defaults are not changed.
