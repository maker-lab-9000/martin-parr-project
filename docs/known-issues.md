# Known issues

Understood-but-unfixed defects and hardware limitations. Each entry records the
symptom, the verified root cause, what was ruled out, the current decision, and
how to confirm it is resolved.

## IMX708 second-capture "Camera frontend has timed out" on the Raspberry Pi 3B

**Status:** open — deferred to the Raspberry Pi 4 migration; native 12 MP capture
kept for now. Revisit only if it still times out on the Pi 4.

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

### Decision

Keep native 12 MP capture and re-test on the **Raspberry Pi 4**, which has more
CPU headroom — the grade will be shorter, so the servicing gap shrinks. Expected
to help, but it may not fully remove the warning: 12 MP grading still exceeds the
1-second watchdog even on faster hardware.

### If it persists on the Pi 4 — the fix

Stop grading at full 12 MP. The contained change is a configurable
capture/grading resolution (for example a half-res `2304×1296` binned stream, or
`1920×1080`), keeping full resolution only for the saved original/DNG if wanted.
Grading 2–3 MP is several times faster, which both speeds up each capture and
closes the camera-servicing gap that trips the watchdog. Optionally raise
`buffer_count` and/or CMA on the Pi 4, where there is room.

### How to confirm resolved

On the Pi 4 with the IMX708, take three or more captures in a row and confirm each
returns within a few seconds with no "Camera frontend has timed out" error.
`journalctl -u pifilm-capture` should stay clean across repeated shots.
