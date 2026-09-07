# StickS3 remote capture and Pi deployment

This guide connects the M5StickS3 button to the Pi's authenticated capture API.
It uses the Pi at `192.168.178.56`, account `george`, and project checkout
`/home/george/repos/martin-parr-project`. Keep credentials in the ignored local
`.env`; never paste them into a shell command, firmware source, service unit,
terminal transcript, or Git commit.

## Local configuration

On the Mac or Pi checkout, make the local file with restrictive permissions:

```sh
cp .env.example .env
chmod 600 .env
```

Set these values in `.env`:

```dotenv
PI_HOST=192.168.178.56
PI_USER=george
PI_PROJECT_DIR=/home/george/repos/martin-parr-project
PI_SSH_PASSWORD=replace-locally
WIFI_SSID=replace-locally
WIFI_PASSWORD=replace-locally
PARR_REMOTE_TOKEN=replace-locally-with-a-long-random-token
PI_ARTIFACT_DIR=/home/george/repos/martin-parr-project/artifacts/personal-collection-01-v1
```

`PI_ARTIFACT_DIR` is the selected artifact directory. Verify it on the Pi before
starting capture: it must contain both `params.json` and `parr.cube`. If the
artifact lives elsewhere, use that verified absolute path in both the local env
file and the service/desktop command.

The scripts parse this file as `KEY=VALUE` data. They do not source it, expand
variables, run command substitutions, or execute any of its contents. The Pi
SSH password is used only for the SSH connection. The firmware generator passes
only Wi-Fi SSID, Wi-Fi password, API URL, and remote token to PlatformIO; it
never writes a credentials file and never passes `PI_SSH_PASSWORD` to firmware.

Install the optional, cross-platform SSH dependency before using deployment:

```sh
.venv/bin/python --version  # requires Python 3.11 or newer
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[deploy]'
```

If the environment uses an older Python, preserve it and recreate it first
(on macOS with Python 3.12 installed):

```sh
mv .venv .venv-old
python3.12 -m venv .venv
```

Then run the installation commands above. Pip 21.2.4 cannot install this
project in editable mode; upgrading pip fixes that error only when the Python
version also meets the project requirement.

Add the Pi host key before deployment, by checking its fingerprint in person
and accepting it once with normal OpenSSH:

```sh
ssh george@192.168.178.56
```

`scripts/deploy_remote.py` deliberately uses Paramiko with your system known
hosts and a reject-unknown-host policy. It will not silently trust a changed or
unknown host key.

## Start the Pi capture process

First check the Pi's existing state without restarting anything:

```sh
.venv/bin/python scripts/deploy_remote.py --env .env
```

It checks the project directory, selected artifact, existing `parr-capture`
processes, `/dev/video*` owners, and logged-in desktop sessions before a restart
is considered. Resolve a reported camera owner first; this prevents two capture
processes from competing for the same camera.

For **both-screen mode** (Pi screen plus Stick), run the following command from
the actual logged-in Pi desktop session or that session's autostart entry:

```sh
.venv/bin/parr-capture --no-preview --show-captures --remote-listen 192.168.178.56:8765 --artifacts <verified-pi-artifact-directory>
```

Replace the placeholder with the verified `PI_ARTIFACT_DIR`. The token must be
present in that desktop session's environment as `PARR_REMOTE_TOKEN`, but do not
put the token literal in the command. An SSH login does not inherit `DISPLAY`,
`WAYLAND_DISPLAY`, `XAUTHORITY`, or the desktop display authorization, so do not
launch `--show-captures` through SSH and expect it to appear on the Pi screen.
Use a desktop autostart entry or launch it manually after logging into that
desktop session.

For **Stick-only mode**, omit `--show-captures` and use the supplied headless
systemd example. On the Pi, create `/etc/parr-capture.env` as root-owned mode
`600` containing only `PARR_REMOTE_TOKEN=...`, then install and enable the unit:

```sh
sudo install -m 644 deploy/parr-capture.service.example /etc/systemd/system/parr-capture.service
sudo systemctl daemon-reload
sudo systemctl enable --now parr-capture.service
sudo systemctl status parr-capture.service
```

The service is intentionally headless and has `StandardInput=null`; it needs no
terminal controls. Once it is installed and `sudo -n systemctl` is authorized
for `george`, a guarded remote restart is available:

```sh
.venv/bin/python scripts/deploy_remote.py --env .env --restart
```

The script refuses to stop the service when its initial inspection finds a
foreign camera/capture owner. It permits only the service's own known process,
then stops it, verifies that no process or camera owner remains, and only then
starts it. For a service change, run the inspection command again afterward and use
`journalctl -u parr-capture.service -n 100` on the Pi for diagnostics.

## Generate and flash StickS3 configuration

Validate the local configuration without printing or writing secrets:

```sh
python3 firmware/sticks3/scripts/generate_config.py --env .env
pio run -d firmware/sticks3
```

The PlatformIO pre-build script reads `.env` and appends the four device defines
while retaining the base environment build flags. On a clean clone with no
`.env`, it adds no defines and the firmware keeps its safe empty defaults; the
explicit validation command above still requires a complete env file. First USB
flash and serial diagnostics are:

```sh
pio run -d firmware/sticks3 -t upload
pio device monitor -d firmware/sticks3 -b 115200
```

Confirm `StickS3 remote capture boot`, the boot screen/tone, and colour bars.
Then confirm the device joins the configured Wi-Fi, reaches the Pi, and produces
one capture per deliberate button press. See `firmware/sticks3/README.md` for
the expected screen and button behaviour.

## Stop, rollback, and replace a token

For desktop mode, stop the process in its desktop session with `Q` or Escape.
For headless mode, use:

```sh
sudo systemctl stop parr-capture.service
```

To roll back, first stop the current process/service and verify `/dev/video*`
has no owner. Then start the previously recorded working capture command from
the same desktop context, or restore the prior service unit and run `daemon-reload`
before starting it. Do not start the old command until the new process has
stopped.

To replace a compromised or expired token, generate a new long random token,
replace the local `PARR_REMOTE_TOKEN` in `.env`, update the secured Pi service
environment (or desktop session environment), restart the Pi process only after
inspection, then rebuild and flash the StickS3. The old token stops working as
soon as the Pi process has been restarted with the new value.

## 2026-09-07: "the Stick shows the ungraded photo" — what was checked

**The Pi serves the graded image. Proven, not inferred.** A real
`CaptureSession` with the fake camera, a real `RemoteCaptureServer`, and one
capture over HTTP: the served bytes are byte-identical to
`fitted_jpeg(result.parr)` and differ from `fitted_jpeg(result.original)`.
`capture()` assigns `parr = save_jpeg(graded, ...)` and `_image` reads
`job.result.parr`, so the whole chain is right.

**The grade is clearly visible at thumbnail size**, so a subtle-grade
explanation does not hold on the numbers: between the two 240×135
thumbnails the Stick could receive, mean Oklab difference is 0.083–0.110 and
p95 is 0.177–0.224, five to ten times a just-noticeable difference.

**A test gap that would have hidden exactly this bug.** The `SavedCapture`
double carried only `parr`, so every test passed one file as both images and
none could tell which the handler returned. Swapping `parr` for `original`
in `_image` passed the whole remote suite. `SavedCapture` now carries
`original` too, and a new test asserts the served bytes are the graded file
and not the original — falsified by making that swap, which now fails.

**A real firmware defect, found while looking, which is NOT this bug.**
`fetchJpeg` writes the download into `jpeg_back_buffer` while holding no
lock, taking `jpeg_mutex` only at the end to publish `jpeg_back_size` and
`jpeg_ready`. `loop()` holds the mutex while `decodeAndStore` reads that
same buffer, so a download landing during a decode can overwrite the bytes
being decoded. The symptom would be a torn or garbled frame rather than a
correctly-decoded wrong image, so it does not explain this report — but it
should be fixed: either take the mutex around the write, or double-buffer
and publish a pointer.

**Not explained.** No mechanism found by which the *camera original* reaches
the Stick. Remaining candidates, in order: the panel itself (small
low-gamut TFT, and the shipped preset is now `vividness 0.5`, a deliberately
gentler look than the 1.0 these observations may have been made against);
a stale `photo_` buffer surviving a failed fetch or decode, which shows an
older but still graded capture; or a Pi running an older revision than the
branch. The decisive check is to fetch the endpoint directly from the Pi and
look at the bytes:

```bash
curl -s -H "Authorization: Bearer $PARR_REMOTE_TOKEN" \
  http://localhost:PORT/v1/captures/<request-id>/image.jpg -o /tmp/served.jpg
```

If `/tmp/served.jpg` is graded, the Pi is correct and the fault is on the
Stick; if it is not, the capture that produced it is worth keeping.
