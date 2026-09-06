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
.venv/bin/pip install -e '.[deploy]'
```

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
python3 scripts/deploy_remote.py --env .env
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
python3 scripts/deploy_remote.py --env .env --restart
```

The script stops the service first, verifies that no `parr-capture` process
remains, and only then starts it. It refuses to restart when a camera is already
owned. For a service change, run the inspection command again afterward and use
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
