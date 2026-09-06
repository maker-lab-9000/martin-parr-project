# Task 3 — StickS3 firmware

## Delivered

- Added the requested `firmware/sticks3` PlatformIO project, based on the
  official M5Stack StickS3 setup: `esp32-s3-devkitc-1`, the 8 MB partition
  table, QIO/OPI PSRAM, USB CDC, M5Unified, M5GFX, and M5PM1.
- Added a dependency-free `CaptureClient` state machine for connecting, ready,
  requesting, processing, downloading, photo, and error states. It debounces
  the primary button, creates one RFC 4122 v4 request ID per deliberate press,
  sends the shutter event only once, retains an ambiguous ID for polling, and
  cannot submit another capture while one is active.
- Added a FreeRTOS HTTP worker. It uses bearer authentication, 5-second HTTP
  bounds, authenticated `/v1/status` readiness and instance-ID observation,
  500 ms job polling, 1-to-10 second reconnect backoff, and a 120 second
  unresolved-job timeout that retains and continues polling the same ID.
  A changed server instance or unknown job is explicitly interrupted, stopped,
  and requires a fresh press; it is never resubmitted automatically.
- Added a display/speaker smoke path, local TV colour bars, state/elapsed UI,
  64 KiB bounded JPEG back buffer, a pinned JPEGDEC full-decode validation
  pass before persistent replacement, persistent last successful photo bytes,
  and geometry derived from the rotated display's measured dimensions.
- Added a README with configuration safety, build/flash/monitor commands, and
  a required physical smoke-test checklist. No Wi-Fi, API, or bearer values are
  committed; Task 4 may inject them through local build flags.

## Tests and verification

- Host state-machine test executable:
  `g++ -std=c++17 -Wall -Wextra -Werror -Iinclude src/capture_client.cpp test/test_state_machine/test_main.cpp -o /private/tmp/sticks3_state_tests && /private/tmp/sticks3_state_tests` — passed.
  It covers state transitions, held buttons, one-shot sound, lost submit
  acknowledgement, server restart/missing job lookup, malformed/truncated JPEG
  failure, known submit rejection recovery, timeout persistence, elapsed time,
  server readiness/instance interruption, reconnect backoff cap,
  reconnect-before-submit recovery, submit-start retry with the same UUID,
  acknowledgement-only shutter sound, authenticated-status busy recovery, and
  stale-readiness invalidation after status transport failure, and UUID v4
  layout.
- `pio test -d firmware/sticks3 -e native` — passed: 18 test cases succeeded.
- `pio run -d firmware/sticks3` — passed. Target size: 178,124 / 327,680 bytes
  RAM (54.4%) and 1,044,861 / 3,342,336 bytes flash (31.3%).
- `git diff --check` — passed before the fix commit.

## Remaining concern

The physical StickS3 flash/smoke test remains pending because no device is
attached to this environment. The target firmware build and JPEGDEC/M5GFX
compile path have been verified by PlatformIO.
