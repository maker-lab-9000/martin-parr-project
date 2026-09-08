# TODO: project improvements

Written 2026-09-07 after reading the code, the three training reports, the
September 7 refinement experiment, and the trained artifacts on disk. Items are
checkboxes grouped by theme and ordered by expected payoff within each group.

---

## 1. Better training results

### What the evidence says

- The only model that passed all gates (`personal-collection-01-v1`) never saw
  the camera. Its source corpus was 399 public-domain web photos from the
  Kodachrome project, carrying 10 different ICC profiles, with a normalization
  clamp rate of 22.8%. It learned "random web photo → Parr-ish", not
  "Innomaker frame → Parr-ish".
- The camera-trained pilots used 15 frames from one bedroom. All three failed
  the held-out gate and the grey-axis gate. Fifteen neighbouring frames cannot
  span the colour cube; 71% of LUT nodes held no source pixel in earlier fits.
- The reference corpus is 150 mixed-quality reproductions (gallery JPEGs around
  550×450 px, book scans, Pinterest re-uploads) from several series and decades.
  The README's own advice (one coherent period, 200+ images) was not met.
- `lutfit.fit_lut` applies `cap_neutral_axis` once, then
  `enforce_monotone(enforce_grey_axis(enforce_monotone(...)))`. The later
  projections re-introduce tint, so the requested cap is not achieved
  (measured 0.0136 against a requested 0.005).
- The handcrafted starter itself fails `channel_monotone` and `clipped_volume`
  when probed on the uniform cube (about 70% of interior nodes on the gamut
  boundary). The production baseline does not pass the trainer's own gates.
- Parr's saturation depends on direct flash. The camera has no flash, so the
  source distribution can never contain the specular highlights and hard
  shadows the references have. A LUT cannot invent them.

### Priority 1: a real camera source corpus

- [ ] Shoot at least 100 frames across at least 25 distinct scenes with the
      Innomaker camera. Cover: tungsten interior, window daylight, overcast and
      sunny exterior, people and skin, food, signage, painted surfaces, beach or
      pool if possible. Vary distance and exposure.
- [ ] Include 10 to 20 "cube coverage" frames: a ColorChecker or printed colour
      swatches, saturated toys, fabrics. They do not need to be good photos;
      they populate LUT nodes that real scenes never touch.
- [ ] Reserve whole scenes for validation before looking at any result, and keep
      a second set of whole scenes as an untouched final test. Never select a
      candidate on the final test.
- [ ] Port scene-grouped partitions from `parr.experiments.partitions` into
      `parr-train` (a `--partition manifest.json` flag) so the production
      trainer stops doing random per-image splits.
- [ ] Lock the camera before collecting: fix white balance and exposure via
      `v4l2-ctl` (`white_balance_automatic=0`, manual `auto_exposure`, fixed
      `exposure_time_absolute`), and set in-camera saturation, contrast,
      sharpness and gamma to neutral. Record the control values in
      `captures.jsonl` (spec 7.5 already asks for this). Auto WB and auto
      exposure change the input distribution frame to frame, which the
      normalizer partially undoes but never fully.
- [ ] Add the flash (section 3) before the main collection run. Source data
      with flash is the single largest change you can make to the input
      distribution.

### Priority 2: a coherent reference corpus

- [ ] Choose one period and lighting style and stick to it: the flash-lit
      saturated 1990s work (Common Sense, The Last Resort colour reprints,
      The Cost of Living, Benidorm). Drop the digital-era and muted images.
- [ ] Minimum quality bar: short side ≥ 800 px, no visible paper texture or
      page curl, no screen photographs, no watermarks, no borders. Convert
      everything to sRGB once at ingest so the corpus profile table is uniform.
- [ ] Balance series so no single series exceeds about 30% of the corpus, and
      deduplicate by scene (the SIFT+RANSAC screening from the personal
      collection review already does this).
- [ ] Get to 200+ images before trusting a held-out number. Below that, the
      validation split is under 40 images and the SWD noise floor dominates.

### Priority 3: paired supervision (the biggest methodological upgrade)

`lutfit.fit_lut` already fits from (input, target) pixel pairs. Today those
pairs come from unpaired distribution transport, which is where content bias
and the neutral-tint drift enter. Real pairs remove both problems.

- [ ] Hand-graded pairs (cheapest, no rights issue, camera-calibrated): take
      30 to 50 of your own camera captures, grade them in darktable, RawTherapee
      or Lightroom with the references open beside you, export as sRGB JPEG.
      Add `parr-train --paired SRC_DIR TGT_DIR` that matches filenames, samples
      pixels at identical coordinates, and calls `fit_lut` directly, skipping
      `hue_weights` and IDT. This is how commercial film-emulation LUTs are
      built.
- [ ] Film pairs (most faithful): shoot the same scenes on a saturated colour
      negative stock with flash (Kodak Ektar 100, Gold 200 or Ultramax 400) and
      on the Pi camera from a tripod; lab-scan; align with the existing
      SIFT+RANSAC review code; sample paired pixels. Even 20 paired scenes
      beat 150 unpaired web JPEGs. The `ektar100/` and `velvia/` Commons
      corpora in this repo are unpaired and can only be distribution targets.
- [ ] ColorChecker under flash, photographed by the Pi camera, gives 24 exact
      pairs for free once you decide the target rendering of each patch. Use
      it as a per-patch ΔE regression test for every candidate.

### Priority 4: fix the fitter and the model shape

- [ ] Make the neutral cap and monotonicity a joint constraint: iterate
      `cap_neutral_axis` and the monotone/grey-axis projections until a fixed
      point (or a bounded number of rounds), then assert the measured neutral
      chroma is below the cap. Alternatively add the grey-axis nodes as
      high-weight rows in the least squares so the solver respects them
      directly instead of fixing them afterwards.
- [ ] Decouple tone from colour. Fit a monotone 1D luma curve first, then a
      low-parameter chroma model in Oklch: chroma gain g(L, h) and hue shift
      δ(L, h) on a small grid (for example 8 lightness × 12 hue bins) with
      smoothness across bins. Bake the result into the 33³ `.cube` for
      deployment. Far fewer degrees of freedom means empty cube regions stop
      drifting, and monotonicity is structural rather than projected.
- [ ] Fix the starter's gamut handling so the baseline passes its own gates:
      replace the bisection-to-boundary chroma compression in `preset.py`
      with a soft knee that leaves interior nodes off the boundary.
- [ ] Record provenance properly: `code_revision` is `unknown` in the trained
      artifacts because training ran from the sibling Kodachrome venv. Run
      `parr-train` from this repo's venv so the git hash lands in
      `params.json`.

### Priority 5: evaluation protocol and sweeps

- [ ] Script a hyperparameter sweep over `lambda_smooth` {0.01, 0.03, 0.1},
      `lambda_identity` {1, 3, 10}, `strength` {0.6, 0.8, 1.0, 1.2},
      `iterations` {40, 80} using `parr.experiments.train`, selecting on the
      scene-grouped dev set only.
- [ ] Blind A/B contact sheets: randomize candidate order per page and hide
      labels until after scoring. `parr.experiments.evaluate` already produces
      the sheets; add the shuffle and an answer key file.
- [ ] Add a ColorChecker ΔE table (per patch, before and after) to the report.
- [ ] Keep every rejected artifact and its report. The refinement doc's
      discipline (no threshold relaxed, exit code 3 retained) is right; keep it.

---

## 2. Should `parr.cube` and `params.json` be committed?

Short answer: yes for those two files, never the `report/` folder, and
consider shipping the look as package data instead of un-ignoring a path.

Facts checked:

- `parr.cube` is 970 KB of text, `params.json` is 4 KB. Fine for git, but the
  cube is effectively binary for diffing. Commit it rarely, or use Git LFS if
  you expect to iterate through many versions.
- `report/` contains contact sheets built from the reference photographs. Those
  images are marked "copyright-or-unverified" in the manifest. Keep the report
  ignored.
- `params.json` embeds your absolute local paths including your macOS username
  in `training.command` and `training.source.dir`, and the licence line
  `"copyright-or-unverified": 150`. Decide whether you are happy publishing
  that, or add a `--scrub-paths` option to `write_artifact` that records paths
  relative to the repo.
- A 33³ LUT is aggregate colour statistics, not a copy of any image. Committing
  it is a much smaller step than committing the corpus, but the training data
  itself has no redistribution permission, so this is your call.

Git cannot re-include a file whose parent directory is excluded, so the current
`/artifacts/` rule must become `/artifacts/*`. This pattern was verified in a
scratch repo to track exactly the two files and nothing else under `artifacts/`:

```gitignore
# Data and generated output
/data/
/artifacts/*
!/artifacts/personal-collection-01-v1/
/artifacts/personal-collection-01-v1/*
!/artifacts/personal-collection-01-v1/parr.cube
!/artifacts/personal-collection-01-v1/params.json
```

Cleaner alternative:

- [ ] Add the trained look as package data at `parr/data/looks/personal-01/`
      and extend `Artifacts.resolve` with a `--look NAME` option (or make it the
      default once it is proven on the camera). Then the Pi gets the model via
      `pip install -e .` and `PI_ARTIFACT_DIR`, the systemd unit and the deploy
      script no longer need an absolute artifact path. The README's
      "untrained starter is the default" statement would need updating.

---

## 3. Streamline the setup: Pi boots into camera mode, handheld use

### Operating system and boot

- [ ] Use Raspberry Pi OS Lite (no desktop) for the handheld build. Faster
      boot, lower power, fewer moving parts. `python3-opencv` from apt still
      works headless; only the `--show-captures` two-screen mode needs GTK.
- [ ] Disable Bluetooth (`dtoverlay=disable-bt` in `config.txt`) and consider
      turning HDMI off when headless. Both save power and a little boot time.
- [ ] Fit a real-time clock. The Pi 3B has none. Offline, with no home network,
      the clock will be wrong after every boot and `YYYY-MM-DD/HHMMSS` file
      names will lie. A DS3231 module costs a few euros; PiSugar and PiJuice
      HATs include one. Until then, add a monotonic capture counter to the file
      name as a fallback.
- [ ] Protect the SD card against power loss: put `~/Pictures/parr` on its own
      partition or a USB stick, and consider `overlayroot` for a read-only root
      filesystem. A battery pull mid-write is the most likely way this project
      corrupts its card.

### systemd unit hardening

- [ ] Move hard-coded values out of `ExecStart`. Put `PARR_LISTEN`,
      `PARR_ARTIFACTS` and `PARR_OUT` in `/etc/parr-capture.env` alongside the
      token and reference them as `${PARR_LISTEN}` in the unit.
- [x] Bind to `0.0.0.0:8765` (or add `net.ipv4.ip_nonlocal_bind=1`). Binding to
      a specific address races the hotspot bringing that address up at boot and
      fails with "cannot assign requested address" until systemd restarts it.
      (Done in `deploy/parr-capture.service.example`, 2026-09-08.)
- [x] Add `StartLimitIntervalSec=0` under `[Unit]`. The camera can take several
      seconds to enumerate; without the limit reset, systemd gives up after five
      fast failures. (Done; `Restart=on-failure` kept so a clean `Q` exit in
      desktop mode is not immediately restarted.)
- [ ] Optionally bind the unit to the camera device: a udev rule tagging the
      camera with `TAG+="systemd"` plus `BindsTo=dev-v4l-by-id-<name>.device`
      makes the service start when the camera appears and stop when it is
      unplugged.
- [x] Keep `deploy_remote.build_capture_command` in sync: it now reads
      `PARR_LISTEN` from the env file (default `0.0.0.0:8765`) instead of
      deriving the bind address from `PI_HOST`. (Done 2026-09-08.)

### Install and deploy

- [ ] Write `scripts/pi_bootstrap.sh`: idempotent apt install, venv with
      `--system-site-packages`, `pip install -e .`, copy the unit, create the
      env file with prompts, set hostname, enable avahi, enable the hotspot
      (section 5), enable the service. One command from a fresh Lite image.
- [ ] Add a `Makefile` (or `justfile`) with `test`, `lint`, `firmware`,
      `flash`, `deploy`, `pull-photos` targets so the README commands have one
      home.
- [ ] Set `[tool.pytest.ini_options] pythonpath = ["."]` so bare `pytest`
      collects `tests/test_config.py` and `tests/test_deployment.py`. Today
      only `python -m pytest` works.
- [ ] Add GitHub Actions: ruff, fast pytest, and `pio test -e native`.
- [ ] Deploy by wheel rather than editable checkout on the Pi:
      `python -m build`, copy the wheel over Ethernet, `pip install`. The slow
      packaging test already proves this path works.

### Getting photos off the camera

- [ ] When wired: `rsync -av george@parr.local:Pictures/parr/ ~/Pictures/parr-pi/`.
      Add it as the `pull-photos` make target.
- [ ] Later: a `GET /v1/captures?since=<id>` listing plus a full-resolution
      download endpoint, so a phone on the Pi's hotspot can pull photos without
      a cable.

### Physical controls

- [ ] Safe shutdown button: `dtoverlay=gpio-shutdown` on GPIO3 gives shutdown
      and wake-from-halt on the Pi 3 with a single momentary switch. The
      UPS HATs below also provide this.
- [ ] Shutdown from the Stick: add an authenticated `POST /v1/system/shutdown`
      that runs `systemctl poweroff` through a narrow sudoers rule, and bind it
      to a long press on the Stick's secondary button. Include Pi battery level
      in `/v1/status` if the HAT exposes it over I2C, and show it on the Stick.
- [ ] Flash: drive a high-power LED module (or a small ring light) from a GPIO
      through a MOSFET. A strobe cannot sync with a UVC video stream, so use a
      constant "torch" for about 300 to 500 ms: switch on, let auto-exposure
      settle a few frames (the existing `_drain` plus `warmup_frames` logic),
      `read()`, switch off. Add a `pre_capture`/`post_capture` hook on
      `CaptureSession.capture`. This is also a training item (section 1).

---

## 4. Battery for the Raspberry Pi 3B

### Power budget

The Pi 3B wants a 5.1 V supply rated 2.5 A. Official typical bare-board draw is
about 500 mA. Under this project's load (Wi-Fi hotspot, USB camera streaming
1080p MJPEG, a Python grading burst per shot) expect roughly:

| State | Estimate |
|---|---|
| Idle, hotspot up, camera open | 2.5 to 3.5 W |
| Capture and grade burst | 5 to 6 W |
| Average in use | about 4 W |

Measure it with an inline USB power meter before buying cells. Cable quality
matters as much as capacity: a thin micro-USB lead drops enough voltage to
trigger the under-voltage warning, and the first symptom is the USB camera
resetting mid-capture.

Rough runtimes at about 4 W average, allowing about 15% conversion loss:

| Pack | Nominal energy | Expected runtime |
|---|---|---|
| 10,000 mAh USB power bank | 37 Wh | 6 to 8 h |
| 20,000 mAh USB power bank | 74 Wh | 12 to 16 h |
| 2 × 18650 (3,400 mAh each) in a UPS HAT | about 25 Wh | 4 to 5 h |
| PiSugar 3 Plus (5,000 mAh) | 18.5 Wh | 3 to 4 h |
| PiJuice standard cell (1,820 mAh) | 6.7 Wh | 1 to 1.5 h |

### Options, in order of recommendation for this project

- [ ] **Geekworm X728 (V2.x) UPS HAT.** Two user-supplied 18650 cells, 5.1 V/3 A
      output, auto power-on when power is applied, hardware power button, and a
      GPIO shutdown signal with a Python daemon for safe power-off. Supports the
      3B. The best fit for a handheld that gets switched off by pulling power.
- [ ] **PiSugar 3 Plus.** 5,000 mAh built-in cell in the full-size Pi
      footprint, RTC included, I2C battery gauge, software power button,
      auto power-on. Neatest package for a 3D-printed case; smaller capacity
      than two 18650s.
- [ ] **PiJuice HAT.** Best software (RTC, wake schedules, safe shutdown, well
      documented) but the standard cell is small; you would swap in a larger
      3.7 V pack. Good if you value the software over the capacity.
- [ ] **Plain USB power bank** with ≥ 2.4 A output and pass-through charging.
      Cheapest and largest capacity. Downsides: no safe shutdown, no RTC, and
      many banks switch off when the load drops below about 100 mA, which the
      Pi never does in this setup, so that is usually fine. Avoid banks without
      pass-through if you want to charge while shooting.
- [ ] Waveshare UPS HAT (B) is a similar two-cell design with an INA219 gauge;
      confirm 3B compatibility before buying.

Whatever you choose:

- [ ] Wire a safe-shutdown path (HAT GPIO signal or the GPIO3 button). Never
      rely on cutting power.
- [ ] Use protected 18650 cells from a reputable brand if you go the UPS HAT
      route, and keep the cells' rated discharge current well above 3 A.
- [ ] Optional later step: a Pi Zero 2 W has the same CPU family at lower clock
      and roughly halves the power draw, but only 512 MB RAM. Test 1080p grading
      memory headroom before switching.

---

## 5. Stick S3 directly on the Pi's Wi-Fi, Ethernet for administration

Feasible and a good fit. The Pi 3B's onboard radio (2.4 GHz b/g/n) supports
access-point mode with the standard `brcmfmac` driver, and the ESP32-S3 is
2.4 GHz only, so the two match. The firmware uses `WiFi.mode(WIFI_STA)` and
`WiFi.begin(ssid, password)`, which is plain WPA2-PSK; no firmware change is
needed beyond rebuilding with the new SSID, passphrase and API URL.

### Pi as hotspot (Raspberry Pi OS Bookworm, NetworkManager)

- [ ] Set the Wi-Fi country first (`sudo raspi-config nonint do_wifi_country XX`).
      Without it the radio stays soft-blocked.
- [ ] Create an autoconnecting AP profile with a fixed address:

```sh
sudo nmcli con add type wifi ifname wlan0 con-name parr-ap autoconnect yes ssid parr-cam
sudo nmcli con modify parr-ap 802-11-wireless.mode ap 802-11-wireless.band bg \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk 'a-long-passphrase'
sudo nmcli con up parr-ap
```

`ipv4.method shared` runs a DHCP server for the Stick and NATs to Ethernet if
that is up, so the Pi keeps internet access when you wire it to a router.

- [ ] Point the firmware and the service at the AP address. In `.env`, set
      `PARR_REMOTE_URL=http://10.42.0.1:8765` (already supported by
      `generate_config.py`) and keep `PI_HOST` as the SSH address used by
      `deploy_remote.py`. Rebuild and flash the Stick.
- [x] Set `--remote-listen 0.0.0.0:8765` in the unit. (Done 2026-09-08.)
- [x] Repo side: `scripts/pi_hotspot.py` writes the hotspot as a root-only
      NetworkManager keyfile from `.env`; `.env.example` and
      `docs/sticks3-remote.md` describe the hotspot topology. (Done 2026-09-08;
      the Pi-side steps above and below still need to be run on the device.)
- [ ] Expect 10 to 20 s after Pi boot before the AP is up. The firmware already
      backs off reconnects between 1 and 10 s, so the Stick will settle into
      READY on its own.
- [ ] The API is plain HTTP with a bearer token. On a private WPA2 hotspot with
      a strong passphrase that is acceptable; keep the token anyway so a guest
      on the hotspot cannot fire the shutter.

### Ethernet for administration

The Pi 3B port is auto-MDI-X, so a normal patch cable straight into a laptop
works.

- [ ] Set a memorable hostname (`sudo hostnamectl set-hostname parr`); avahi is
      installed by default on Raspberry Pi OS, and macOS resolves `parr.local`
      natively.
- [ ] Make the wired profile fall back to link-local when no DHCP server is
      present, so a direct cable gives `ssh george@parr.local` with no static
      IP dance, while a router or macOS Internet Sharing still hands out DHCP:

```sh
sudo nmcli con modify 'Wired connection 1' ipv4.method auto ipv4.link-local fallback
```

  (Verify the `ipv4.link-local` property exists on the installed NetworkManager
  version with `nmcli con show 'Wired connection 1' | grep link-local`; if not,
  a second static profile on `192.168.7.2/24` with the Mac set to
  `192.168.7.1` is the simple alternative.)

- [ ] Enable macOS Internet Sharing from Wi-Fi to the Ethernet port when you
      want the Pi to reach apt and pip. The Pi then gets a `192.168.2.x`
      address and full internet through the Mac.
- [x] Update `docs/sticks3-remote.md` to describe this topology instead of the
      home-LAN one, and remove the hard-coded `192.168.178.56` from the service
      example and the guide. (Done 2026-09-08.)

---

## 6. Smaller items noticed along the way

- [ ] `.venv-python39-backup-20260906/` and `build/` are in the working tree;
      both are gitignored, but delete the old venv once you are sure the
      Python 3.12 venv is complete.
- [ ] `README.md` says `.venv/bin/pytest -q -m 'not slow'`; change to
      `.venv/bin/python -m pytest` or fix `pythonpath` as above.
- [ ] The Stick shows no battery level of its own. M5Unified exposes
      `M5.Power.getBatteryLevel()`; a small indicator on the READY screen is a
      few lines in `display.cpp`.
- [ ] The deployment plan's manual checklist item "double presses, camera
      disconnection, disk-save failure, invalid token, missing desktop session"
      in `docs/superpowers/plans/2026-09-06-sticks3-remote-capture.md` is still
      unchecked. Run it once on the hotspot topology.
