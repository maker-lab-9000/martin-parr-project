# Known issues

Understood-but-unfixed defects and hardware limitations. Each entry records the
symptom, the verified root cause, what was ruled out, the current decision, and
how to confirm it is resolved.

## IMX708 second-capture "Camera frontend has timed out" on the Raspberry Pi 3B

**Status:** **resolved 2026-09-19** by the move to the Raspberry Pi 4. No code
change was needed and native 12 MP capture was kept — see
[Resolution](#resolution) for the measurements. The entry stays because the
failure mode is instructive and a Pi 3B is still affected.

**First seen:** 2026-09-18, Raspberry Pi 3B + Camera Module 3 Wide (IMX708),
`pifilm-capture` on `main`.

### Symptom

The first capture succeeds; the second (and later) captures log a libcamera
frontend timeout and can stall:

```
WARN  V4L2 /dev/video0[..:cap]: Dequeue timer of 1000000.00us has expired!
ERROR RPI  Camera frontend has timed out!
ERROR RPI  Please check that your camera sensor connector is attached securely.
ERROR RPI  Alternatively, try another cable and/or sensor.
```

In an interactive run both photos still saved (~20 s each); under the systemd
service / remote (Stick) path the stall escalated to a capture that never
returned (observed waiting >150 s).

### Root cause (verified)

It is **CPU/processing time at full resolution**, not memory and not the DNG:

- The camera is configured for the IMX708's native **4608×2592 (~12 MP)** with an
  RGB grading stream plus a raw stream (`pifilm/capture/picamera.py`,
  `create_still_configuration(..., buffer_count=2)`).
- Grading one 12 MP frame — normalize → 3D LUT → grain — takes **~20 s on the
  Pi 3B** (measured: `Saved … in 20394 ms`). During that grade the capture loop
  does not service the camera, so libcamera's 1-second dequeue watchdog on the
  CSI frontend expires and logs "frontend has timed out". The free-running camera
  then stalls; sometimes it recovers (the photo still saves), sometimes the next
  `capture_request()` blocks — the >150 s hang.

### Ruled out during diagnosis

- **DNG / raw write.** Reproduced with `--no-dng`; the raw stream is still
  configured and the second capture still timed out, so writing the DNG is not
  the trigger.
- **CMA / RAM.** The 256 MiB CMA pool had ~68 MiB free and `dmesg` showed no
  allocation failures; both photos saved. Memory pressure is not the cause.

### Environment

Raspberry Pi 3B, Raspberry Pi OS Trixie, libcamera 0.7.2, picamera2 0.3.37,
IMX708 (`imx708_wide`) at 4608×2592, `buffer_count=2`, CMA 256 MiB shared with
`vc4-kms-v3d`.

### Resolution

Measured on a Raspberry Pi 4 Model B running the migrated SD, 2026-09-19, with
the same 4608×2592 configuration and `buffer_count=2`:

| Metric | Pi 3B | Pi 4 |
|---|---|---|
| Grade one 12 MP frame (`pipeline_ms`) | ~20,400 ms | **~3,290 ms** |
| Shutter to saved (`shutter_to_saved_ms`) | — | **~5,300 ms** |
| `Camera frontend has timed out` | on the second capture | **0 across every capture in the boot** |

The Pi 4 grades a 12 MP frame roughly six times faster, so the capture loop no
longer leaves the camera unserviced long enough to trip libcamera's one-second
dequeue watchdog. Repeated captures complete with consistent timings
(3286.7 / 3284.8 / 3303.7 ms across three shots).

Native 12 MP is therefore kept, and the configurable grading resolution
considered during diagnosis was **not** needed.

### If it regresses — the fallback

Stop grading at full 12 MP: make the capture/grading resolution configurable (for
example a half-res `2304×1296` binned stream, or `1920×1080`), keeping full
resolution only for the saved original and DNG. Grading 2–3 MP is several times
faster, which closes the camera-servicing gap that trips the watchdog. Raising
`buffer_count` and/or CMA is a secondary lever where there is room.
