"""Native Raspberry Pi camera acquisition through the optional Picamera2 package.

The camera is configured for the IMX708's full 4608x2592 still stream. Picamera2's
``RGB888`` arrays use BGR byte order, so each request is copied into an owned RGB
array before the request is released. Importing Picamera2 stays inside construction
so USB and fake-camera use do not require Raspberry Pi camera packages.
"""

from __future__ import annotations

import math
import tempfile
from typing import Any

import numpy as np

from .camera import CameraError, Frame, StreamInfo

DEFAULT_TUNING_FILE = "imx708_wide.json"
_NATIVE_SIZE = (4608, 2592)
_MAIN_FORMAT = "RGB888"
_AUTOFOCUS_MODES = ("continuous", "auto", "manual")
_AF_RANGES = ("normal", "macro", "full")

METADATA_KEYS = (
    "ExposureTime",
    "AnalogueGain",
    "DigitalGain",
    "ColourGains",
    "ColourTemperature",
    "Lux",
    "LensPosition",
    "AfState",
    "FocusFoM",
    "FrameDuration",
    "SensorTimestamp",
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
                out[key] = int(value)  # libcamera enums (e.g. AfState) are int-like
            except (TypeError, ValueError):
                pass
    return out


class Picamera2Camera:
    """Acquire full-sensor RGB frames from an IMX708 through Picamera2."""

    def __init__(
        self,
        tuning_file: str = DEFAULT_TUNING_FILE,
        save_dng: bool = True,
        autofocus: str = "continuous",
        af_range: str = "normal",
        ae_lock: bool = False,
        awb_lock: bool = False,
        colour_gains: tuple[float, float] | None = None,
    ) -> None:
        if autofocus not in _AUTOFOCUS_MODES:
            raise CameraError(
                f"Unknown autofocus mode {autofocus!r}; expected one of {_AUTOFOCUS_MODES}"
            )
        if af_range not in _AF_RANGES:
            raise CameraError(f"Unknown af_range {af_range!r}; expected one of {_AF_RANGES}")

        try:
            from picamera2 import Picamera2
        except (ImportError, OSError) as exc:
            raise CameraError(
                "Picamera2 is unavailable; install the Raspberry Pi OS python3-picamera2 package"
            ) from exc

        try:
            tuning = Picamera2.load_tuning_file(tuning_file)
        except Exception as exc:
            raise CameraError(
                f"Failed to load Picamera2 tuning file {tuning_file!r}: {exc}"
            ) from exc

        try:
            camera = Picamera2(tuning=tuning)
        except Exception as exc:
            raise CameraError(f"Failed to open Picamera2 camera: {exc}") from exc

        self._camera: Any | None = camera
        self._started = False
        self._save_dng = save_dng
        self._autofocus = autofocus
        start_attempted = False
        try:
            config = camera.create_still_configuration(
                main={"size": _NATIVE_SIZE, "format": _MAIN_FORMAT},
                raw={"size": _NATIVE_SIZE},
                buffer_count=2,
                queue=False,
            )
            camera.configure(config)
            actual = camera.camera_configuration()
            self._stream_info = _stream_info(actual, tuning_file)
            _apply_camera_controls(camera, autofocus, af_range, ae_lock, awb_lock, colour_gains)
            start_attempted = True
            camera.start()
            self._started = True
        except Exception as exc:
            _cleanup_camera(camera, stop=start_attempted)
            self._camera = None
            if isinstance(exc, CameraError):
                raise
            raise CameraError(f"Failed to configure or start Picamera2 camera: {exc}") from exc

    @property
    def stream_info(self) -> StreamInfo:
        return self._stream_info

    def read(self) -> Frame:
        camera = self._camera
        if camera is None:
            raise CameraError("Cannot read from a closed Picamera2 camera")

        if self._autofocus == "auto":
            try:
                camera.autofocus_cycle()
            except Exception as exc:
                raise CameraError(f"Autofocus cycle failed: {exc}") from exc

        try:
            request = camera.capture_request()
        except Exception as exc:
            raise CameraError(f"Picamera2 failed to capture a request: {exc}") from exc

        processing_failed = False
        try:
            try:
                bgr = request.make_array("main")
                expected_shape = (_NATIVE_SIZE[1], _NATIVE_SIZE[0], 3)
                if not isinstance(bgr, np.ndarray):
                    raise CameraError("Picamera2 main array is not a NumPy array")
                if bgr.dtype != np.uint8 or bgr.shape != expected_shape:
                    raise CameraError(
                        "Picamera2 main array must be "
                        f"uint8 with shape {expected_shape}, got {bgr.dtype} {bgr.shape}"
                    )
                rgb = np.array(bgr[..., ::-1], dtype=np.uint8, order="C", copy=True)
                metadata = serialisable_metadata(request.get_metadata())
                self._update_fps({"FrameDuration": metadata.get("FrameDuration", 0)})
                dng = None
                if self._save_dng:
                    with tempfile.NamedTemporaryFile(suffix=".dng", delete=True) as tmp:
                        request.save_dng(tmp.name)
                        tmp.seek(0)
                        dng = tmp.read()
                return Frame(rgb=rgb, jpeg=None, source="picamera2", metadata=metadata, dng=dng)
            except CameraError:
                processing_failed = True
                raise
            except Exception as exc:
                processing_failed = True
                raise CameraError(f"Picamera2 failed while reading a frame: {exc}") from exc
        finally:
            try:
                request.release()
            except Exception as exc:
                if not processing_failed:
                    raise CameraError(
                        f"Picamera2 failed to release a capture request: {exc}"
                    ) from exc

    def _update_fps(self, metadata: Any) -> None:
        try:
            duration = float(metadata.get("FrameDuration", 0))
        except (AttributeError, TypeError, ValueError):
            return
        if duration > 0 and math.isfinite(duration):
            self._stream_info.fps = 1_000_000.0 / duration

    def close(self) -> None:
        camera = self._camera
        if camera is None:
            return
        self._camera = None
        started = self._started
        self._started = False

        first_error: Exception | None = None
        if started:
            try:
                camera.stop()
            except Exception as exc:
                first_error = exc
        try:
            camera.close()
        except Exception as exc:
            if first_error is None:
                first_error = exc
        if first_error is not None:
            raise CameraError(f"Failed to close Picamera2 camera: {first_error}") from first_error


def _stream_info(actual: Any, tuning_file: str) -> StreamInfo:
    try:
        main_size = tuple(actual["main"]["size"])
        main_format = actual["main"]["format"]
        raw_size = tuple(actual["raw"]["size"])
        raw_format = actual["raw"]["format"]
        bit_depth = actual["sensor"]["bit_depth"]
    except (KeyError, TypeError) as exc:
        raise CameraError(
            f"Picamera2 returned an incomplete negotiated configuration: {actual!r}"
        ) from exc

    mismatches = []
    if main_size != _NATIVE_SIZE:
        mismatches.append(f"main size {main_size!r}")
    if main_format != _MAIN_FORMAT:
        mismatches.append(f"main format {main_format!r}")
    if raw_size != _NATIVE_SIZE:
        mismatches.append(f"raw size {raw_size!r}")
    if not isinstance(raw_format, str) or not raw_format:
        mismatches.append(f"raw format {raw_format!r}")
    if not isinstance(bit_depth, int) or isinstance(bit_depth, bool) or bit_depth <= 0:
        mismatches.append(f"sensor bit depth {bit_depth!r}")
    if mismatches:
        details = ", ".join(mismatches)
        raise CameraError(f"Picamera2 negotiated an unsupported capture configuration: {details}")

    width, height = main_size
    return StreamInfo(
        width=width,
        height=height,
        fps=0.0,
        fourcc=main_format,
        raw_mjpeg=False,
        sensor_mode=f"{raw_size[0]}x{raw_size[1]} {raw_format}",
        bit_depth=bit_depth,
        tuning_file=tuning_file,
    )


def _apply_camera_controls(
    camera: Any,
    autofocus: str,
    af_range: str,
    ae_lock: bool,
    awb_lock: bool,
    colour_gains: tuple[float, float] | None,
) -> None:
    """Neutral ISP rendering plus autofocus, applied once after ``configure``.

    Imports libcamera's control enums lazily so USB and fake-camera use never
    require the Raspberry Pi camera stack. ``autofocus``/``af_range`` are
    validated by the caller, so the dict lookups below cannot raise ``KeyError``.
    """
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
    camera.set_controls(cam_controls)


def _cleanup_camera(camera: Any, *, stop: bool) -> None:
    """Best-effort constructor cleanup that cannot mask the setup failure."""
    if stop:
        try:
            camera.stop()
        except Exception:
            pass
    try:
        camera.close()
    except Exception:
        pass
