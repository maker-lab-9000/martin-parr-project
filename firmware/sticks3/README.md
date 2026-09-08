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

## Battery indicator

The bottom-right corner of every screen shows the Stick's own battery as a
small badge: `87%` on battery, `87%+` while external power is attached over
USB, `--%` when the power chip cannot report a level. It turns red at 15% or
below on battery. The READY caption is centred in the space left of the badge.

The level comes from M5Unified's `M5.Power.getBatteryLevel()`, which on the
StickS3 derives it from the PM1 power chip's battery voltage. The voltage sags
while the Wi-Fi radio transmits, so raw readings swing by five or six points
between polls (81, 75, 80, 75 was measured). Readings are averaged with a time
constant of about four polls, and the shown level then holds until the average
differs from it by at least 3 points. A sustained change of a few points shows
within a minute or so; a steady drain is tracked with a lag of a couple of
points. The `+` mark means external power is present, read from the PM1's
power-source register. It deliberately does not follow M5Unified's
`isCharging()`, which on the StickS3 reads the charger's CHG_STAT pin: with the
cable attached that pin cycles on and off for about 20 seconds at a time as the
charger regulates, which made the mark blink. If the power-source read fails
the charger pin is used instead, with a two-poll debounce before the mark is
dropped. An unknown level shows `--%` at once; an unknown power state leaves
the mark as it was. Expect the level to move in steps rather than smoothly, and
to read high while a charger is attached. The chip is polled every 10 seconds
by `BatteryMonitor` (`include/battery_status.h`), which is Arduino-free and
covered by the native tests; the display repaints the badge only when the text
changes. Each change is also logged on the serial port, with the PM1 source
bitmap (bit 0 VIN, bit 1 VIN/OUT, bit 2 battery):

```text
[1203] battery 87%+ (level 87, external power, power sources 0x05, 4012 mV)
```

Network traffic runs in a FreeRTOS worker. The UI loop remains responsive; Wi-Fi
reconnects back off from one to ten seconds. The shutter tone is queued only
after a 2xx capture acknowledgement. A job still unresolved after 120 seconds
stays attached to its original UUID and continues lookup without submitting a
replacement capture.
