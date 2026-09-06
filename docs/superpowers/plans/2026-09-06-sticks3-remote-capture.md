# StickS3 Remote Capture Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Implementation is on `feature/remote-trigger-stickS3`; software progress is tracked below. Physical acceptance remains pending.

**Goal:** Use the StickS3 button to take a graded photograph on the Raspberry Pi, give audible feedback, show TV colour bars while processing, and retain the returned photograph on the Stick display until the next capture.

**Architecture:** One persistent Pi capture process owns the camera and grading pipeline. A token-authenticated LAN HTTP interface submits capture requests and serves status and display-sized JPEGs. SSH handles deployment and administration using the user's local credentials.

**Tech stack:** Existing Python/OpenCV/Pillow application; Python standard-library HTTP server for a small trusted-LAN interface; Arduino C++ with PlatformIO, M5Unified, M5GFX and the official StickS3 power-management configuration. Pin firmware dependencies after verifying a hardware build.

**Spec:** The design and acceptance criteria below are the specification. The user approved HTTP transport and displaying captures on both screens.

## Context and constraints

- Local project: `/Users/george.babanau/repos/raspberry-pi/martin-parr-project`.
- Existing branch: `feature/remote-trigger-stickS3`; working tree was clean during inspection.
- Pi: `george@192.168.178.56`; project: `/home/george/repos/martin-parr-project`.
- Existing command spelling: `.venv/bin/parr-capture --no-preview --show-captures`.
- That command defaults to the bundled starter look. Deployment must verify and explicitly select the intended trained artifact directory with `--artifacts`; local ignored artifacts do not arrive through Git.
- Current capture entry point is `CaptureSession.capture()` in `parr/capture/app.py`. Both GUI and terminal loops call it synchronously. There is no existing remote command interface.
- Preserve full-resolution original/graded files, audit records, fullscreen fitting, SPACE triggering and fake-camera support.
- Only one process/thread owns camera reads. OpenCV window calls remain on the main GUI thread.
- StickS3 uses 2.4 GHz Wi-Fi, a 135x240 screen, programmable buttons and a speaker. Default UI orientation: landscape 240x135, photo fitted without cropping and with black borders.
- Use a short shutter sample at moderate volume, below the manufacturer's recommended battery limit of 75%.
- Firmware and deployment support live inside this repository. Do not print or commit credentials. Do not read the user's `.env` during planning.

## Transport decision

Recommended: SSH for deployment and HTTP for device traffic. The Stick sends short requests, polls processing status and downloads JPEG bytes. A bearer token scopes access to the camera service; the Pi login password is not placed on the Stick. Plain HTTP is suitable only under the user's trusted-LAN assumption: the token and photo transfer are not encrypted.

Alternative: SSH end to end. This requires validating an embedded SSH client, host-key verification and binary file transfer on the Stick, plus a structured Pi command interface. Sending SPACE to an arbitrary SSH terminal is insufficient: the currently running desktop application owns its own input and display session. Choose this route only if the user requires SSH as the device transport.

## Observable behaviour

`Connecting -> Ready -> Requesting -> Processing -> Downloading -> Photo displayed`

- Boot connects Wi-Fi and checks authenticated Pi readiness. Show Ready only after camera/pipeline initialization succeeds and no job is active.
- A debounced primary-button press immediately draws colour bars and submits one request. Play the shutter click once the Pi accepts it. This is acceptance feedback, not hardware-synchronized exposure feedback.
- Draw bars locally using the same seven colours and lower dark text area as `_capture_loading_screen`; keep them visible throughout capture, grading and downloading. Use an animated indicator and elapsed time, not invented percentage progress.
- Download and decode the completed job's JPEG into a back buffer, then replace the screen only after successful decoding.
- The photo stays visible until another capture. Connectivity status may use a small overlay without clearing the photo.
- Ignore extra shutter presses while busy. A failed request shows a short actionable error and restores the last photo, or Ready if none exists. A lost connection retains the pending request ID and resumes status lookup after reconnecting.
- Pi screen follows the same job lifecycle if enabled. GUI failure can fall back to remote operation without requiring a terminal.

## Task 1: Shared capture controller

**Files:** Create `parr/capture/controller.py`; modify `parr/capture/app.py`; add `tests/test_capture_controller.py`; extend `tests/test_app.py`.

**Interface:** `submit(request_id: str) -> JobSnapshot`, `status(request_id: str) -> JobSnapshot | None`, `snapshot() -> ControllerSnapshot`, `close() -> None`. Job snapshots expose ID, state, error code and completed result reference. States: queued, processing, complete, failed.

- [x] Add tests proving one camera read per accepted capture, one active job, duplicate IDs returning the original job, a distinct ID receiving busy while active, and camera errors permitting a subsequent capture.
- [x] Implement a single camera-owning worker and thread-safe immutable status snapshots. Route keyboard and remote requests through the same controller; do not start a camera process per request.
- [x] Update GUI rendering to poll controller state while keeping GUI calls on the main thread. Preserve the existing non-remote preview path; initially permit remote mode only without live preview.
- [x] Add tests that both trigger sources display loading before results, retain the previous photo on errors, and preserve current output/audit semantics.
- [x] Run focused controller/app tests, then commit this independently testable change.

## Task 2: Authenticated capture and image API

**Files:** Create `parr/capture/remote.py` and `parr/capture/thumbnail.py`; modify `parr/capture/app.py`; add `tests/test_remote.py` and `tests/test_thumbnail.py`.

**Proposed interface:** All routes require `Authorization: Bearer <token>`.

| Route | Behaviour |
| --- | --- |
| `GET /v1/status` | Server instance ID, readiness, active capture ID, last completed ID |
| `POST /v1/captures` with `{ "request_id": "<UUID>" }` | 202 with capture ID/state; repeat ID returns existing state; distinct request while busy returns 409 |
| `GET /v1/captures/<id>` | queued/processing/complete/failed plus error or image URL; unknown/expired ID returns 404 |
| `GET /v1/captures/<id>/image.jpg` | Exact completed capture, fitted to 240x135; no-store caching; never a global latest-file lookup |

- [x] Test missing/wrong tokens, malformed IDs, bounded request bodies, duplicate requests, busy responses, expired IDs and rejection of arbitrary filesystem paths.
- [x] Implement opt-in `--remote-listen 192.168.178.56:8765` and a token loaded from the process environment. Refuse startup without a token. Start no network listener by default.
- [x] Serve handlers independently of the camera worker; cap HTTP timeouts, body sizes and concurrent connections. Poll status at 500 ms from the Stick.
- [x] Generate thumbnails from the saved graded image with Pillow. Preserve the original files, aspect ratio and black borders. Cap JPEG transfers at 64 KiB; reject oversized or invalid images on the Stick.
- [x] Keep a bounded registry of the last 100 jobs during the server lifetime; never evict an active job. Expose a new server instance ID on restart. On an unknown job after restart, the Stick must report interrupted/unknown outcome and require a fresh deliberate press; never automatically resubmit a capture of uncertain outcome.
- [x] Test startup/operation without a TTY, fake-camera HTTP capture, GUI fallback, landscape/portrait images and continued responsiveness during grading. Run focused tests and commit.

## Task 3: StickS3 firmware

**Files:** Create `firmware/sticks3/platformio.ini`, `firmware/sticks3/src/main.cpp`, `firmware/sticks3/src/capture_client.cpp`, `firmware/sticks3/include/capture_client.h`, `firmware/sticks3/src/display.cpp`, `firmware/sticks3/include/display.h`, `firmware/sticks3/test/test_state_machine/test_main.cpp`, and `firmware/sticks3/README.md`.

**Interfaces:** Client exposes readiness, submission, job polling and bounded JPEG retrieval. UI consumes states connecting, ready, requesting, processing, downloading, photo and error; only a successful JPEG decode replaces the stored photo buffer.

- [x] Implement StickS3 PlatformIO configuration and button/display/speaker support; verify the target build.
- [ ] Verify board identity, power initialization, button, display and speaker on physical hardware.
- [x] Implement debouncing and a generated UUID per deliberate press. Keep the active ID until terminal status, and use the same ID when resolving an ambiguous submission within the same server instance.
- [x] Implement state-driven networking with bounded timeouts in a worker task so screen updates, button handling and Wi-Fi reconnection remain responsive.
- [x] Implement Ready, locally drawn colour bars, elapsed timer, once-only shutter sound, JPEG back-buffer decoding, and the persistent photo screen. Derive layout from actual display width/height after rotation.
- [x] Back off reconnect attempts from 1 to 10 seconds. After 120 seconds of an unresolved job, show a timeout/reconnect message and keep looking up that ID; do not fire a replacement capture automatically.
- [x] Test state transitions, held-button behaviour, lost acknowledgements, server restart, failed/truncated JPEG and no sound repetition during retries. Build firmware with `pio run -d firmware/sticks3` and run native state-machine tests, then commit. Physical device tests remain pending.

## Task 4: Configuration and Pi deployment

**Files:** Modify `.gitignore` and `README.md`; create `.env.example`, `scripts/deploy_remote.py`, `firmware/sticks3/scripts/generate_config.py`, `deploy/parr-capture.service.example` and `docs/sticks3-remote.md`.

- [x] Ignore `.env`, `.env.*` except `.env.example`, firmware generated secrets, `.pio/` and firmware build outputs. Check ignore rules before the user supplies the password.
- [x] Document `PI_HOST=192.168.178.56`, `PI_USER=george`, `PI_PROJECT_DIR=/home/george/repos/martin-parr-project`, `PI_SSH_PASSWORD`, `WIFI_SSID`, `WIFI_PASSWORD`, `PARR_REMOTE_TOKEN`, and the selected artifact path. Keep real values out of examples and logs.
- [x] Generate device configuration with only Wi-Fi credentials, API URL and remote token. Do not copy the Pi SSH password into firmware or binaries. Parse the local env file as data, never execute it as shell code.
- [x] Deployment uses a password-capable SSH library with host-key verification. Inspect the existing Pi process, camera, artifact availability and desktop session before preparing a restart. Never leave two processes competing for the camera.
- [x] For both-screen mode use the actual logged-in desktop session/autostart context; SSH does not automatically inherit DISPLAY, WAYLAND_DISPLAY or display authorization. For Stick-only mode support a headless systemd service with no stdin dependency.
- [x] Document the proposed command: `.venv/bin/parr-capture --no-preview --show-captures --remote-listen 192.168.178.56:8765 --artifacts <verified-pi-artifact-directory>`. Omit `--show-captures` for Stick-only operation. The remote flag is new work, not an existing command.
- [x] Include first USB flash, serial diagnostics, startup, stop, rollback to the prior command, and token replacement instructions. Verify packaging and commit.

## Task 5: End-to-end acceptance

- [ ] Boot the Stick on the local 2.4 GHz Wi-Fi; confirm Ready means the Pi service and camera are initialized.
- [ ] Take 20 successive shots: each deliberate press produces exactly one original/graded pair and audit record, one shutter sound, bars until download completes, and the matching graded photo on both enabled screens.
- [ ] Confirm the full-resolution saved files are unchanged by thumbnail creation; check both landscape and portrait fitting.
- [ ] Unplug Wi-Fi during submission, processing and download; verify reconnection retrieves the same job without duplicate captures. Restart the Pi service mid-job and verify the explicit unknown-outcome behaviour.
- [ ] Exercise double presses, camera disconnection, disk-save failure, invalid token and a missing desktop session. Confirm errors are visible and a later valid capture works.
- [x] Run firmware native tests (20 passed), the configured StickS3 target build, Python lint and dependency consistency checks.
- [ ] Complete physical hardware tests; no Pi camera, screen or speaker observations are claimed by the software checks.

### Software verification record (2026-09-06)

- [x] Full Python regression suite: 339 passed, including isolated wheel installation and command execution.
- Python environment: Python 3.12.14, pip 26.2.1; editable installation with `train,deploy,dev` extras succeeded.
- Python dependencies tested: NumPy 2.5.3, Pillow 12.3.0, OpenCV 5.0.0.93, SciPy 1.18.1, Paramiko 5.0.0; pytest 9.1.1 and Ruff 0.16.6.
- Firmware: PlatformIO 6.1.19, espressif32 6.12.0, Arduino framework 3.20017.241212; M5Unified `8530f537`, M5GFX `d91077b9`, M5PM1 `be9a5456`, JPEGDEC tag 1.8.2 (`883a7917`). M5 revisions are pinned in `platformio.ini`.
- Final review approved fixes for Pi remote-job rendering, persistent Stick photos, failed-capture recovery, root configuration lookup and compiler macro quoting.
- During the failed configured build, compiler diagnostics exposed device settings. Rotate the affected Wi-Fi password and remote token before deployment; generated firmware/build files remain ignored.

## Configuration and hardware prerequisites

1. Resolved: HTTP for device traffic; SSH for deployment.
2. Resolved: both Pi and Stick screens remain active.
3. Supply the 2.4 GHz Wi-Fi settings in the ignored local configuration when implementation begins. No password is needed in chat.
4. Confirm the physical device is StickS3 (K150), not StickC/StickC Plus2. A photo is only needed if its model label is unclear.

## Sources

- https://docs.m5stack.com/en/core/StickS3 — board specifications, PlatformIO setup and power notes.
- https://docs.m5stack.com/en/arduino/m5sticks3/display — supported display library.
- https://docs.m5stack.com/en/arduino/m5sticks3/speaker — speaker API.
- Local `parr/capture/app.py` and `tests/test_app.py` — existing capture and display behaviour.
