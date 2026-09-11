# Raspberry Pi 4 + Camera Module 3 Wide (IMX708) Roadmap

> **Status:** design-level roadmap, written 2026-09-11 before the hardware is on
> the bench. Each phase below becomes its own task-by-task implementation plan
> (the `superpowers:writing-plans` format, with tests and commits) when it is
> about to start. Nothing here is executable yet; it fixes the order, the
> decisions and the acceptance criteria so the later plans argue from one spec.

**Goal:** move the camera from the Innomaker USB module on a Pi 3B to a
Raspberry Pi 4 with the Camera Module 3 Wide, capture at the sensor's native
4608 × 2592, keep the original JPEG, a DNG and the graded output for every
shot, and raise the quality of the graded result with a LUT trained on this
sensor, gentler normalisation, resolution-aware grain, scene statistics and
highlight protection.

**Hardware assumed:** Raspberry Pi 4 with 8 GB RAM (confirmed), Camera Module 3 Wide (IMX708,
120° diagonal, f/2.2, PDAF autofocus from 5 cm, I2C-driven lens), the
existing Geekworm X728 UPS (Pi 4 is supported), the existing StickS3.

**Software assumed:** Raspberry Pi OS Trixie, `libcamera` and `python3-picamera2`
from apt (Picamera2 must match the OS's libcamera build, so it is never
installed from pip), the project venv created with `--system-site-packages`
exactly as today.

## Order

Your proposed order, and the order this roadmap recommends, with the reason
for each move:

| # | Your order | Recommended | Why the change |
|---|---|---|---|
| 1 | Picamera2 + native 4608 × 2592 capture | same | Everything else needs frames from this sensor |
| 2 | Autofocus + AE/AWB control and metadata | same | Consistent, documented input is the foundation of every quality step |
| 3 | Keep original + RAW/DNG + processed | same | Cheap once the request object is in hand; DNG makes every later experiment re-processable |
| 4 | Benchmark the pipeline at 12 MP | same, but start today on the Pi 3B with a synthetic frame | Tells you whether 12 MP processing is seconds or minutes before you design around it |
| 5 | Retrain the LUT on IMX708 frames | **move after 6 and after the flash decision** | The LUT is fitted on normalised input. Changing normalisation later invalidates it; adding a flash later changes the source distribution. Retrain once, not three times |
| 6 | Gentler, configurable normalisation | **move before retraining** | See above; also cheap, it is already parameterised in `params.json` |
| 7 | Resolution-aware grain | same, any time after 4 | Independent of the LUT |
| 8 | Scene statistics | same | Needed as input for 9 and 10, and valuable in `captures.jsonl` on its own |
| 9 | Highlight-protected LUT blending | same; prefer baking it into the LUT first | The September 7 experiments already showed highlight protection helps, as a baked LUT control with zero runtime cost |
| 10 | Tiny scene classifier, only if statistics are not enough | same | Correct instinct: a few thresholds on the statistics will likely do |
| 11 | Physical flash, eventually | **move to a cheap experiment right after 4** | The measurements in `todo.md` section 1 say it is the largest quality lever there is, and it decides how the source corpus for step 5 should look |

Recommended sequence: **1, 2, 3, 4, flash experiment, 6, 5, 7, 8, 9, 10, flash
for real.**

## Phase 1: Picamera2 with native 4608 × 2592 capture

**Design.** A new `Picamera2Camera` in `parr/capture/camera.py` implementing
the existing `Camera` protocol (`stream_info`, `read() -> Frame`, `close()`),
alongside `V4L2Camera` and `FakeCamera`, selected by a `--camera {v4l2,picamera2}`
flag with `picamera2` the default when the module imports. Nothing above the
protocol changes in this phase.

- Configuration: `create_still_configuration(main={"size": (4608, 2592), "format": "RGB888"}, raw={"size": (4608, 2592)}, buffer_count=2)`. Run it permanently rather than switching modes per shot: IMX708 delivers about 14 fps at full resolution and the ISP does the work, so a `capture_request()` returns the next full frame with no mode-switch latency. Revisit if idle CPU or power turns out to matter; the alternative is a low-resolution running configuration and `switch_mode_and_capture_request()` at about one second per shot.
- `read()` calls `capture_request()`, converts `make_array("main")` to RGB, and releases the request. The array is 4608 × 2592 × 3 uint8, 36 MB.
- `StreamInfo` gains `sensor_mode`, `bit_depth` and `tuning_file` fields, still serialised into every capture record.
- Tuning: load `imx708_wide.json` explicitly via `Picamera2.load_tuning_file`, so a system default change never silently alters the colour science the LUT was trained on. Record the file name.

**Acceptance.** `parr-capture --camera picamera2 --no-preview` saves a
4608 × 2592 `_ungraded.jpg` and `_parr.jpg`; `captures.jsonl` records the
sensor mode and tuning file; the Stick still receives its 240 × 135 thumbnail.

**Memory.** One RGB frame is 36 MB and the pipeline's float32 intermediates
are 143 MB each; with 8 GB this is a non-issue, and it leaves room to keep
several requests in flight or a lores preview stream later.

## Phase 2: autofocus, AE/AWB control, metadata

**Design.**

- Autofocus: `AfMode.Continuous` while idle so the lens is roughly right, then
  on the shutter press `AfMode.Auto` with `AfTrigger.Start` and wait for
  `AfState` to leave `Scanning` (Picamera2's `autofocus_cycle()` does exactly
  this, with a timeout), then capture. Record `LensPosition`, `AfState`,
  `FocusFoM`. Expose `--af-range {normal,macro,full}`; the Wide module focuses
  from 5 cm, useful for the food and object shots the references favour.
- Exposure and white balance: keep auto by default, as today, for the reasons
  in `docs/training.md` section 2 (the LUT is fitted on the camera plus
  normalisation as one system). Add `--ae-lock` and `--awb-lock` options for
  controlled shoots, and `--colour-gains R,B` for the flash case in Phase F,
  where a fixed daylight balance is the right answer because the flash
  dominates.
- Neutral ISP rendering: set `Sharpness`, `Contrast` and `Saturation` to 1.0
  (or the tuning's neutral values) and `NoiseReductionMode` to `HighQuality`
  for stills, and record them. The grade should be ours, not the ISP's.
- Metadata: from `request.get_metadata()` record `ExposureTime`,
  `AnalogueGain`, `DigitalGain`, `ColourGains`, `ColourTemperature`, `Lux`,
  `LensPosition`, `AfState`, `FocusFoM`, `FrameDuration`, `SensorTimestamp`
  into the capture record. `Lux` and `ColourTemperature` are free scene
  statistics; Phase 8 builds on them.

**Acceptance.** A test shoot of the same scene at three distances shows
`LensPosition` changing and sharp results; the record carries every field
above; a locked shoot produces identical `ColourGains` across frames.

## Phase 3: keep original, DNG and processed output

**Design.** Extend `Frame` with `raw: object | None` (the retained request or
its raw array plus metadata) and give `CaptureSession.capture()` a third file:
`HHMMSS_original.jpg` (encoded by the ISP path from the same request via
`request.save("main", path)`, so it is the camera's own rendering),
`HHMMSS.dng` (via `request.save_dng(path)`, 12-bit Bayer with the metadata
needed to develop it later), and `HHMMSS_parr.jpg` as now. Record the DNG
name and size. The `_ungraded.jpg` fallback disappears for this camera since
the original is always available.

**Storage.** About 5 MB JPEG + 18 MB DNG + 5 MB graded per shot, roughly
28 MB. A 64 GB card holds about 2,000 shots; add a `--no-dng` flag for long
sessions and a note in the setup guide on pulling photos.

**Why DNG at all.** It is the only artefact that lets you re-develop a shot
after the colour science changes: a new LUT, a new normalisation, or a future
"develop from raw" path that skips the ISP's 8-bit output entirely.

**Acceptance.** Three files per shot, the DNG opens in darktable or
RawTherapee with correct colours, and `parr-process` on the original
reproduces the graded file bit-for-bit given the recorded grain seed.

## Phase 4: benchmark the pipeline at 12 MP

**Do this now, on the Pi 3B**, with `FakeCamera` fed a synthetic 4608 × 2592
frame: it answers the question that shapes the rest. Then repeat on the Pi 4.

**Measure** per stage in `Pipeline.process` and in `CaptureSession.capture`:
normalisation (three `cv2.LUT` calls, two `cvtColor`), the Pillow
`Color3DLUT` filter, grain (float conversion, `GaussianBlur`, back), JPEG
encode, DNG save, and shutter-to-saved. Record peak RSS.

**Expectations to verify, not trust:** on a Pi 4 the LUT filter is likely
0.3 to 0.8 s at 12 MP, grain 0.3 to 0.6 s because of the float round trip,
JPEG encode 0.5 to 1 s, DNG save around 0.5 s, for a total in the 2 to 4 s
range. If grain dominates, Phase 7 has a second reason to exist: compute it
on luminance in uint8 with a smaller kernel.

**Acceptance.** A table in `docs/` with per-stage timings on both boards and
a decision: process at full resolution, or grade a 2304 × 1296 binned frame
and keep the 12 MP original and DNG for later.

## Phase F: flash experiment (new, cheap, before retraining)

**Design.** A high-power LED module or a small ring light driven from a GPIO
through a MOSFET, on the Pi 4's header (avoid BCM 5, 6, 12, 16, 20, 26, which
the X728 uses). A strobe cannot be synchronised with a rolling-shutter stream,
so use a constant "torch" for about 300 ms: switch on, wait two or three frames
for AE and AWB to settle, `capture_request()`, switch off. Hook into
`CaptureSession.capture()` as `pre_capture()` / `post_capture()` callbacks.
With the flash on, lock white balance to the flash's colour temperature via
`--colour-gains`.

**Why now.** Every LUT is a multiplier on colour that is already in the frame;
an unlit room has almost none (1.3 % of pixels with any real colour in the
measured capture). Direct flash is how the reference photographs got their
saturation and their hard edges. Deciding whether the camera has a flash
decides what the training corpus in Phase 5 must look like.

**Acceptance.** Ten indoor pairs, flash on and off, same framing: the
flash-on frames should show a mean Oklab chroma several times higher and a
clipped-highlight fraction that stays under a few percent.

## Phase 6: gentler, configurable normalisation

**Design.** The knobs already exist in `NormalizeParams` and are stored in
every artifact's `params.json`: `levels_max_stretch`, `levels_gamma_min` and
`_max`, `wb_gain_min` and `_max`, `exposure_target_median`,
`stats_lum_min` and `_max`. Add a single `strength` in [0, 1] that blends
each computed gain toward 1.0 (and the gamma toward 1.0), so "gentler" is one
number rather than five. Expose the fields as `parr-train` and `parr-preset`
flags so a look carries its own normalisation, and print the applied gains in
`captures.jsonl` as today.

**What gentler buys.** A well-exposed 12 MP frame from a modern ISP needs far
less rescue than the USB camera's output did. Over-normalising flattens the
flash falloff that gives the references their look; the September 7 report
noted haze-like lifted shadows from an earlier levels choice.

**Acceptance.** The starter and the trained look both re-render the frozen
regression set with `strength` 1.0 bit-identically to today; `strength` 0.5
shows measurably smaller gain excursions in `captures.jsonl` on a mixed shoot.

## Phase 5: retrain the LUT on IMX708 frames

Follow `docs/training.md` end to end, with these specifics:

- Source corpus: at least 100 frames from this camera, 25 or more scenes, shot
  the way the camera will be used (auto exposure and white balance unless the
  flash is fitted, in which case flash on and gains locked), plus colour-chart
  and saturated-object frames for cube coverage. Use the `_original.jpg`
  files. Reserve three to five whole scenes as the untouched final test.
- Normalisation fixed first (Phase 6), then fit. The Phase 4 decision on
  processing resolution does not affect training, which samples at 512 px.
- References: the coherent flash-lit set, 200 or more, per the training guide.
- Consider the hand-graded paired route from `todo.md` section 1 for a first
  strong result: 30 to 50 of your own IMX708 frames graded by hand, fitted
  directly with `fit_lut`, no transport.

**Acceptance.** Exit code 0, held-out improvement well above the noise floor,
and a blind A/B on the final test scenes against the current starter.

## Phase 7: resolution-aware grain

**Design.** Grain is specified today in pixels (`blur_sigma` 0.7) and in
luminance units (`strength` 0.004), tuned on 1080p. At 12 MP the same numbers
give grain a quarter the visual size. Add `reference_height` (default 1080) to
`GrainParams`; scale `blur_sigma` by `height / reference_height` and keep
`strength` in luminance units. Store it in `params.json` so old artifacts keep
their look. Consider generating the noise at reduced resolution and upsampling,
which is both cheaper and closer to how grain clumps.

**Acceptance.** A 12 MP frame and its 1080p downscale, both grained, look
alike when viewed at the same size; the timing from Phase 4 improves.

## Phase 8: scene statistics

**Design.** A `parr/scene.py` computing, on a 512-px downscale in Oklab: mean
and median lightness, lightness standard deviation, chroma percentiles (50,
95), fraction of pixels above 0.05 chroma, clipped fraction per channel,
dominant hue bins, and an estimated cast from the white-balance gains. Merge
the camera metadata from Phase 2 (`Lux`, `ColourTemperature`, exposure). Write
all of it into every `captures.jsonl` record and, for training corpora, into
the report. Cost: a few milliseconds.

**Uses.** First, analysis: which scenes look good, which do not, and why.
Second, control: a per-shot grade `strength` chosen from the statistics
(low-chroma dim interior: stronger; saturated flash-lit close-up: gentler),
which is the "scene-adaptive" behaviour without any classifier.

**Acceptance.** Statistics present in every record; a notebook or script that
plots them for a day's shoot; one adaptive rule implemented behind a flag.

## Phase 9: highlight-protected LUT blending

**Two ways, in this order.**

1. **Bake it into the LUT.** `parr/experiments/candidates.py` already
   implements a `highlights` control that reduces the tone lift in the top
   of the range while keeping colour; the September 7 report measured it as
   the most promising single change. Promote that control into `parr-preset`
   and into `parr-train` as a post-fit shaping step. Zero runtime cost, and it
   ships inside the `.cube`.
2. **Runtime blend, only if per-scene control is wanted.** A per-pixel weight
   `w(L)` with a soft knee above a lightness threshold blends LUT output back
   toward the normalised input in highlights. One extra luminance pass; cheap,
   and it can be driven by the Phase 8 statistics.

**Acceptance.** On the frozen regression set, mean chroma in the
coloured-highlight mask rises while channel-boundary occupancy falls, as in
the September 7 measurement, and skin in shaded midtones does not warm.

## Phase 10: tiny scene classifier, only if needed

If the Phase 8 rules are not enough, a logistic regression or nearest-neighbour
over the statistics vector, trained on a few hundred labelled shots (indoor
flash, indoor ambient, outdoor sun, outdoor overcast, close-up), selecting
between two or three LUTs or a strength. No neural network, no GPU, no new
dependency beyond NumPy. Hold to the same discipline as the LUT: held-out
scenes, fixed gates, blind comparison.

## Phase F′: physical flash, for real

Once the experiment proves the gain: a proper LED flash module with its own
driver and capacitor, or a small hot-shoe flash triggered by GPIO, a 3D-printed
mount, a `--flash` mode in the service, and the retrained LUT from Phase 5
shot with it. The Stick could gain a flash on/off toggle on its second button.

## Cross-cutting notes

- **Camera abstraction.** Keep `V4L2Camera`; the Pi 3B and USB camera remain
  a working fallback and the test rig for the pipeline.
- **Two-screen mode** becomes cheap on the Pi 4 (HDMI + desktop is fine with
  8 GB), but the handheld stays headless.
- **Power.** The Pi 4 draws roughly twice the Pi 3B; expect 2.5 to 3 hours on
  two 3,400 mAh cells instead of 4 to 5. The X728 supplies 5.1 V at 5 A, so
  the camera and a flash are within budget; measure with a USB meter.
- **Thumbnails and the Stick** are unaffected: the 240 × 135 preview comes from
  the graded JPEG regardless of its size.
- **Tests.** Every phase adds unit tests against fakes (a `FakePicamera2`
  request object, synthetic frames, fixed seeds) and keeps the native firmware
  suite untouched. Hardware checks are documented as manual acceptance steps,
  as in `docs/x728-ups.md` section 8.

## Open questions to settle before Phase 1

1. Do you want a live preview on the Stick eventually? It changes the
   configuration choice in Phase 1 (a `lores` stream would be needed).
2. Processing resolution if Phase 4 says 12 MP is too slow: grade the binned
   2304 × 1296 frame and keep the 12 MP original, or accept 3 to 4 seconds
   per shot?
3. Flash form factor: LED torch on the camera body, or a real flash unit?
