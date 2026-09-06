# Task 2 — authenticated capture and image API

Implementation commit: `364cc8239d6c69412b5c424bf1cb82850060ec37`

Authentication hardening follow-up: `2ed8d42030f9d886d262b79f0fae8759fcbe2cec`

## Delivered

- Added `parr/capture/remote.py`: a token-authenticated, localhost/LAN HTTP
  server with the four `/v1` routes, UUID validation, bounded 8 KiB JSON
  bodies, 5-second socket timeouts, eight concurrent connections, idempotent
  capture requests, busy conflicts, and an instance UUID.
- Added a server-lifetime API registry limited to 100 completed jobs. Active
  work is never evicted; expired job IDs return 404 and cannot be resubmitted.
- Added `parr/capture/thumbnail.py`: Pillow-created 240x135 RGB JPEG previews
  preserving aspect ratio with black letterboxing, capped at 64 KiB. It reads
  only the completed capture result's graded path and leaves originals/audit
  records unchanged.
- Added opt-in `parr-capture --remote-listen HOST:PORT`. It requires
  `PARR_REMOTE_TOKEN`; without the flag no listener is opened. Remote mode
  shares `CaptureController` with the capture-only GUI/headless path and stays
  available when stdin is not a TTY.

## Tests and verification

- Focused: `pytest tests/test_app.py tests/test_capture_controller.py
  tests/test_thumbnail.py tests/test_remote.py -q -p no:cacheprovider` —
  65 passed.
- Full: `pytest -q -p no:cacheprovider` — passed.
- Lint: `ruff check parr tests` — passed.
- `git diff --check` — passed.
- Follow-up: `pytest tests/test_remote.py -q -p no:cacheprovider` — 6 passed;
  `ruff check parr/capture/remote.py tests/test_remote.py` — passed.

New coverage includes bearer failures, malformed UUIDs, oversized bodies,
idempotency and busy responses, arbitrary-path rejection, completed-image
serving, thumbnail letterboxing and limits, expiry after 100 jobs, missing
token startup refusal, no-TTY remote operation, and malformed non-ASCII bearer
headers returning 401 without terminating their handler.

## Decisions and remaining concerns

- The service uses the Python standard library rather than adding a web
  framework dependency, keeping deployment suitable for the Raspberry Pi.
- The API job registry is deliberately separate from the controller's internal
  worker bookkeeping, so remote clients cannot discover older controller jobs
  or filesystem paths.
- The CLI `HOST:PORT` parser intentionally supports hostnames and IPv4-style
  addresses; bracketed IPv6 listen syntax is not implemented.
- Hardware/StickS3 end-to-end polling has not been performed in this task; the
  included integration tests use the project's fake camera/controller path.
