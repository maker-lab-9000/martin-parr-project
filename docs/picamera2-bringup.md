# IMX708 / Picamera2 bring-up

The camera has arrived; hardware acceptance is not yet recorded. This checklist
separates the local fake-backed software tests from tests on the actual Pi 4.
See [roadmap progress](superpowers/plans/2026-09-13-rpi4-imx708-progress.md).

## 1. Identify the board and camera

With the Pi powered off, connect the camera using the cable/connector procedure
for the delivered module, then boot the Pi. Record the product/variant from its
packaging: an IMX708 sensor alone does not identify the lens or tuning file.

Run on the Pi and retain the output with the hardware test record:

```sh
tr -d '\0' < /proc/device-tree/model
cat /etc/os-release
uname -a
rpicam-hello --list-cameras
/usr/bin/python3 -c 'from importlib.metadata import version; print("Picamera2", version("picamera2"))'
dpkg-query -W 'python3-picamera2' 'python3-libcamera' 'libcamera*' 'rpicam-apps*'
systemctl is-active parr-capture.service
```

If `rpicam-hello` is unavailable, inspect installed camera packages first; an
older OS may use the `libcamera-hello` command name. Do not assume the hardware
is absent from a missing command. Record detected model and supported modes,
including native dimensions and bit depth. No fixed FPS or raw bit depth is
assumed by the new backend.

Picamera2 must use the libcamera build supplied with the OS. Install the OS's
`python3-picamera2` package if missing, and expose system packages to the project
venv using `--system-site-packages`, as in the [setup guide](setup.md). Do not
install Picamera2 from pip into an otherwise isolated venv. Confirm imports
using the same interpreter that will run the service.

## 2. Establish tuning and exclusive camera ownership

Confirm the module's tuning file before acquiring it. The roadmap assumes
`imx708_wide.json`; a standard, NoIR or third-party module may require a
different file. Use the module/vendor guidance and installed libcamera tuning
files to select it. Keep the chosen filename in the capture log.

Check whether an existing capture service or preview owns the camera. Stop the
known owner before manual capture, then restore the intended service after the
test. Do not launch a second camera application to work around an acquisition
error. A Pi still running the USB setup should select `--camera v4l2` explicitly
once the new code is installed: availability of Picamera2 can change automatic
backend selection.

## 3. Phase 1 capture test

After the new backend is installed on the identified Pi, run from its checkout.
This example assumes the Wide variant has been confirmed:

```sh
.venv/bin/parr-capture --camera picamera2 --tuning-file imx708_wide.json \
  --no-preview --out ~/Pictures/parr-imx708-bringup
```

Use a terminal, press SPACE to capture, and Q to quit. Take a frame containing
red, green and blue objects plus a neutral patch; repeat several captures to
check that requests are returned and the camera does not stall. Confirm:

- `_ungraded.jpg` and `_parr.jpg` both have 4608 × 2592 pixels.
- Red and blue are not swapped. Picamera2 calls the BGR byte layout `RGB888`;
  the backend must convert it to the pipeline's RGB convention.
- `captures.jsonl` records the actual raw sensor mode, bit depth and tuning
  filename; a measured frame duration supplies FPS rather than a preset guess.
- The graded frame loads and shows the current artifact's look; this is not an
  IMX708-trained look yet.
- Normal shutdown releases the camera so a second run can acquire it.
- When the usual authenticated remote service is tested, the Stick receives
  its existing thumbnail. Do not expose an unauthenticated test listener.

Phase 1 deliberately produces `_ungraded.jpg`, not an original JPEG/DNG pair.
Autofocus control, per-shot exposure/AWB metadata and retained request saves
belong to Phases 2–3. Do not label these Phase 1 files as the production training
corpus before the capture pipeline and source/runtime input boundary are fixed.

## 4. Record acceptance and collect the pilot later

Append the actual board/OS/packages, camera product, tuning, command, saved
sizes, colour observation, repeated-capture result and remaining failures to
the separate progress document. Passing fake-backed tests is not evidence of
hardware acceptance.

After Phases 1–3, the first useful photo handoff is 20–30 pilot originals across
8–10 scenes with capture logs and scene IDs. Use them to choose lighting and
normalisation before collecting the production corpus. The complete collection
and retraining gates are in the [roadmap](superpowers/plans/2026-09-11-rpi4-imx708-roadmap.md#when-new-camera-source-photos-are-needed).

## API references

- [Official Picamera2 manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
- [Picamera2 project and installation guidance](https://github.com/raspberrypi/picamera2)
- [Raspberry Pi camera software documentation](https://www.raspberrypi.com/documentation/computers/camera_software.html)

Upstream APIs were checked on 2026-09-14; compare them with the versions actually
installed on the Pi before marking hardware acceptance complete.
