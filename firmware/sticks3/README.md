# StickS3 remote capture firmware

This PlatformIO project turns an M5StickS3 into the authenticated remote
capture button for the local `parr` API. It displays local TV colour bars
while ready, then a state screen and elapsed timer while a request is active.
The most recent successfully decoded 240×135 JPEG remains on screen until a
later complete image replaces it.

## Prerequisites

Install PlatformIO Core and connect an M5StickS3 over USB-C. The project uses
M5Stack's documented StickS3 base: `esp32-s3-devkitc-1`, 8 MB partition table,
QIO/OPI PSRAM, USB CDC, M5Unified, M5GFX, and M5PM1.

The pre-build script reads the repository-root `.env`; see the
[deployment guide](../../docs/sticks3-remote.md). Missing configuration leaves
safe empty defaults and the device cannot join a network. Only Wi-Fi settings,
API URL and API token enter the firmware; the SSH password stays on the host.
Build outputs contain device credentials. Keep them private and avoid verbose
compiler logs when using real settings.

The server must expose the bearer-authenticated API contract at `/v1/status`
and `/v1/captures`. The device enters Ready only after `/v1/status` says the
Pi is ready and no other capture is active. It records that endpoint's
`instance_id`, submits `{"request_id":"UUID"}`, polls the same ID every
500 ms, and fetches `/v1/captures/<UUID>/image.jpg` only on completion. A
changed server instance or an unknown job interrupts the active request and
requires a fresh deliberate press; it never automatically resubmits it.

## Build, flash, and serial monitor

```sh
pio run -d firmware/sticks3
pio run -d firmware/sticks3 -t upload
pio device monitor -d firmware/sticks3 -b 115200
```

Run the hardware-independent state machine tests with:

```sh
pio test -d firmware/sticks3 -e native
```

On first flash, verify physical hardware before enabling network credentials:

1. Serial prints `StickS3 remote capture boot` and identifies the expected USB device.
2. The boot smoke screen appears, the short speaker tone is audible, and colour bars follow.
3. Press and hold the primary button: it should yield only one shutter tone and one request.

Network traffic runs in a FreeRTOS worker. The UI loop remains responsive; Wi-Fi
reconnects back off from one to ten seconds. The shutter tone is queued only
after a 2xx capture acknowledgement. A job still unresolved after 120 seconds
stays attached to its original UUID and continues lookup without submitting a
replacement capture.
