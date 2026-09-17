# Raspberry Pi 4 + Camera Module 3 Wide (IMX708) Roadmap

> **Status (reviewed 2026-09-13):** design-level roadmap, originally written
> before hardware bring-up. Phase 9's baked-LUT path is implemented in
> `d349fec` and `d44c08d`; its optional runtime path remains unimplemented.
> The other phases remain planned, and hardware acceptance is not yet recorded.
> Each remaining phase becomes its own task-by-task implementation plan
> (the `superpowers:writing-plans` format, with tests and commits) before coding.
> Track execution separately in [roadmap progress](2026-09-13-rpi4-imx708-progress.md).

**Hardware update, 2026-09-14:** the user reports delivery of the IMX708
12-megapixel autofocus camera. The exact lens variant and connection to the
Pi 4 still need confirmation; the Wide-specific tuning below remains a
bring-up assumption. [Phase 1 implementation plan](2026-09-14-picamera2-acquisition.md).

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
| 8 | Scene statistics | independent of the first retrain | Needed for adaptive runtime controls and 10; not required by baked highlight protection |
| 9 | Highlight-protected LUT blending | baked path complete; use during 5 | Both CLIs accept `--highlights`; choosing its IMX708 value needs development photos, not new runtime code |
| 10 | Tiny scene classifier, only if statistics are not enough | same | Correct instinct: a few thresholds on the statistics will likely do |
| 11 | Physical flash, eventually | **move to a cheap experiment right after 4** | The measurements in `todo.md` section 1 say it is the largest quality lever there is, and it decides how the source corpus for step 5 should look |

Remaining sequence: **1, 2, 3, 4, flash experiment and capture-policy decision,
6, 5 (including highlight selection), 7, 8, optional 9 runtime blend, optional
10.** Synthetic benchmarking and Phase 6 implementation can start before the
hardware is ready; their acceptance still needs real captures. Phase 7 can run
after 4 independently of retraining. Build the final flash before collecting
the production corpus if flash is part of the intended capture policy; otherwise
ship an ambient-light fit and treat a later flash as a new training cycle.

## Dependencies after highlight protection

The training path is `normalise source photos -> fit LUT -> protect highlights
-> final trainer projection`; runtime normalises each frame and applies one
finished LUT. See the [implementation record](2026-09-12-highlight-protected-lut-progress.md)
and [26-capture regression comparison](../../experiments/2026-09-12-highlight-protected-lut.md).
That comparison used the previous camera's reviewed set, not IMX708 images.
It supports keeping the control available, not promoting `0.6` to a new-camera
default. Both CLIs still default to `0.0`.

| Work | Required dependency / effect of the completed control |
| --- | --- |
| 1–3: acquisition, controls, originals | No dependency on highlight protection; establish reproducible source pixels and metadata first. |
| 4: benchmark | Baked protection adds no runtime pass. Decide the actual ISP stream and resizing path before final validation. |
| F: lighting experiment | Compare flash/ambient inputs with the same grading settings, initially highlights off, so LUT changes do not confound the lighting decision. |
| 6: normalisation | Preserve existing `--highlights` flags and provenance while adding normalisation controls. The selected source parameters must drive training, artifact serialization and runtime consistently. |
| 5: retrain | Fit under frozen normalisation; choose highlight strength on development scenes and evaluate the final projected artifact. A value change needs a rebuilt/re-evaluated artifact, not new source photographs. |
| 7: grain | Post-LUT effect; not a prerequisite for fitting the colour LUT. Validate the final grain setting for delivery. |
| 8 / 9 runtime / 10 | Statistics are a dependency for adaptive control, not for the existing baked operation or the first retrain. Avoid accidentally applying the baked correction a second time at runtime. |

**Training-tool gap to plan in Phase 5.** `pifilm-train` exposes `--highlights`,
but its automatic split is by image, not scene. The explicit scene-partition
runner in `pifilm/experiments/train.py` already passes `FitConfig` to the shared
fitter and records it; its CLI currently exposes only `--neutral-cap`.
Before the IMX708 production run, provide a reproducible scene-grouped route
that accepts the chosen highlight value and frozen normalisation. Either extend
that runner or add explicit scene partitions to the production trainer; do not
claim scene-held-out validation from an ordinary random image split.

## When new-camera source photos are needed

**No photo corpus is needed to start implementation.** Use fake requests and
synthetic frames for acquisition, metadata, file-lifetime and compatibility
tests. Real camera access is needed for hardware acceptance; a source-photo
handoff becomes useful once Phases 1–3 produce stable, traceable originals.

| Gate | Photos needed | What they enable |
| --- | --- | --- |
| Bring-up, during 1–3 | A few real shots, including the Phase 2 three-distance focus test | Verify RGB order, exposure/AWB metadata, original/DNG pairing and replay. These are diagnostics, not a training corpus. |
| Pilot, after 1–3 and before finalising F/6 | Planning target: 20–30 usable originals across 8–10 varied scenes; add the ten same-framing flash/ambient pairs if evaluating flash | Choose capture/lighting policy, inspect clipping and focus, compare normalisation and benchmark real frames. This is the first useful photo handoff. |
| Production source collection, after capture/lighting policy is stable | At least 100 usable originals across at least 25 development scenes, **plus** 3–5 separate whole scenes reserved for the final test | Build training and scene-held-out validation partitions. Originals can be collected while Phase 6 is being finished; freeze its parameters before fitting. |
| Final acceptance, after selecting normalisation, fit and highlight value | Open the reserved final scenes once the candidate is fixed | Blind A/B against the starter, using the final runtime input path. Do not use these scenes to choose highlight strength or normalisation. |

The development-set count excludes the untouched final scenes. Include indoor
and outdoor light, mixed light, bright coloured objects, skin, neutrals and
colour-chart frames; several near-identical shots do not count as new scenes.
If both flash and ambient operation will ship, cover both and validate them
separately rather than training solely on flash and assuming ambient generalises.
The existing trainer's 30-source minimum is a software guard, not this roadmap's
production-data target. References remain a separate corpus of at least 200
coherent images and can be prepared now.

**Photo handoff.** Preserve capture/session directories or use unique IDs so
repeated `HHMMSS` filenames cannot overwrite each other. Supply `_original.jpg`
files, the matching `captures.jsonl`, a scene-ID and lighting-mode manifest, and
DNGs where enabled. Record the actual sensor/ISP mode, tuning-file identity
(preferably content hash), capture controls and software versions. Keep graded
`_graded.jpg` files out of the source corpus. DNGs are useful archives; the current
trainer consumes rendered images, so raw development is not a prerequisite.

**Freeze and refit rules.**

- Changing normalisation: reuse the same suitable originals, rebuild pixel
  pools, refit, and reselect highlight strength. Do not feed previously
  normalised or graded exports back as source originals.
- Changing only highlight strength: reuse source photos and partitions. Start
  each candidate from the same unprotected fit (or rerun the deterministic fit),
  then protect once and project; do not repeatedly protect an already protected
  artifact. Re-evaluate all final-artifact gates.
- Changing sensor, ISP tuning, capture controls or lighting policy: collect
  representative new frames and refit, unless equivalence is demonstrated on
  held-out data. DNGs do not by themselves reproduce a changed live ISP path.
- Changing only post-LUT grain: no colour-LUT refit is required. Changing ISP
  mode, crop or pre-LUT resizing needs source/runtime parity checks; the 512-px
  training sample size alone does not prove those paths equivalent.
- If a final-test scene influences a later setting change, treat it as
  development data and collect a fresh untouched final set before promotion.

## Phase 1: Picamera2 with native 4608 × 2592 capture

**Design.** A new `Picamera2Camera` in `pifilm/capture/camera.py` implementing
the existing `Camera` protocol (`stream_info`, `read() -> Frame`, `close()`),
alongside `V4L2Camera` and `FakeCamera`, selected by a `--camera {v4l2,picamera2}`
flag with `picamera2` the default when the module imports. Nothing above the
protocol changes in this phase.

- Configuration: `create_still_configuration(main={"size": (4608, 2592), "format": "RGB888"}, raw={"size": (4608, 2592)}, buffer_count=2)`. Run it permanently rather than switching modes per shot: IMX708 delivers about 14 fps at full resolution and the ISP does the work, so a `capture_request()` returns the next full frame with no mode-switch latency. Revisit if idle CPU or power turns out to matter; the alternative is a low-resolution running configuration and `switch_mode_and_capture_request()` at about one second per shot.
- `read()` calls `capture_request()`, converts `make_array("main")` to RGB, and releases the request. The array is 4608 × 2592 × 3 uint8, 36 MB.
- `StreamInfo` gains `sensor_mode`, `bit_depth` and `tuning_file` fields, still serialised into every capture record.
- Tuning: load `imx708_wide.json` explicitly via `Picamera2.load_tuning_file`, so a system default change never silently alters the colour science the LUT was trained on. Record the file name.

**Acceptance.** `pifilm-capture --camera picamera2 --no-preview` saves a
4608 × 2592 `_ungraded.jpg` and `_graded.jpg`; `captures.jsonl` records the
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
`HHMMSS.dng` (via `request.save_dng(path)`, sensor-native Bayer with the metadata
needed to develop it later), and `HHMMSS_graded.jpg` as now. Record the DNG
name and size. The `_ungraded.jpg` fallback disappears for this camera since
the original is always available.

**Storage.** About 5 MB JPEG + 18 MB DNG + 5 MB graded per shot, roughly
28 MB. A 64 GB card holds about 2,000 shots; add a `--no-dng` flag for long
sessions and a note in the setup guide on pulling photos.

**Why DNG at all.** It enables a future "develop from raw" path that skips
the ISP's 8-bit rendering. The ungraded original JPEG is already sufficient
to apply a new LUT or normalisation; neither requires a DNG developer.

**Source/runtime parity.** Resolve the input boundary before collecting the
production corpus. If training and replay consume the saved JPEG, the live
grade must consume the decode of those same JPEG bytes to promise exact replay.
Grading the pre-JPEG request array and later decoding a lossy JPEG does not
provide identical pixels. The Phase 3 implementation plan must choose and test
that boundary and retain the request until all request-dependent saves finish.

**Acceptance.** Three files per shot, the DNG opens in darktable or
RawTherapee with correct colours, and `pifilm-process` on the original
reproduces the graded file bit-for-bit given the recorded grain seed, artifact,
processing settings and matching encoder/software versions.

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

Record the decision before production source collection: ambient-only, flash,
or both. If a temporary light will be replaced, finalise the real light first
or budget a second collection/refit; a prototype does not establish the final
source distribution merely because both lights are called flash.

## Phase 6: gentler, configurable normalisation

**Design.** The knobs already exist in `NormalizeParams` and are stored in
every artifact's `params.json`: `levels_max_stretch`, `levels_gamma_min` and
`_max`, `wb_gain_min` and `_max`, `exposure_target_median`,
`stats_lum_min` and `_max`. Add a single `strength` in [0, 1] that blends
each computed gain toward 1.0 (and the gamma toward 1.0), so "gentler" is one
number rather than five. Expose the fields as `pifilm-train` and `pifilm-preset`
flags so a look carries its own normalisation, and print the applied gains in
`captures.jsonl` as today.

**What gentler buys.** A well-exposed 12 MP frame from a modern ISP needs far
less rescue than the USB camera's output did. Over-normalising flattens the
flash falloff that gives the references their look; the September 7 report
noted haze-like lifted shadows from an earlier levels choice.

**Acceptance.** The starter and the trained look both re-render the frozen
regression set with `strength` 1.0 bit-identically to today; `strength` 0.5
shows measurably smaller gain excursions in `captures.jsonl` on a mixed shoot.

Keep normalisation strength distinct from the existing LUT `--strength` and
`--highlights` controls in both APIs and CLI naming. Use the IMX708 pilot set to
choose parameters, then freeze them for the first production fit. Stored
originals permit this tuning without reshooting; the old camera regression set
checks backwards compatibility, not new-camera quality.

## Phase 5: retrain the LUT on IMX708 frames

Follow `docs/training.md` end to end, with these specifics:

- Source corpus: at least 100 development frames from this camera across 25
  or more scenes, plus three to five separate untouched final-test scenes.
  Follow the collection gates above and the intended exposure, white-balance
  and lighting policy. Include colour-chart and saturated-object frames for
  cube coverage. Use `_original.jpg` files, with scene-grouped partitions.
- Normalisation fixed first (Phase 6), then fit. Training samples at 512 px,
  but validate the actual Phase 4 ISP/resizing path; a binned stream is not
  automatically equivalent to resizing the full-resolution original.
- Highlight protection is already implemented. Start with `--highlights 0`
  as the control, compare a small predeclared set of strengths on development
  scenes, and evaluate each final projected artifact. Record the selected
  value in `training.fit.highlights`; do not inherit `0.6` from the old-camera
  experiment without IMX708 evidence. Resolve the scene-partition CLI gap
  described above before this run.
- References: the coherent flash-lit set, 200 or more, per the training guide.
- Consider the hand-graded paired route from `todo.md` section 1 for a first
  strong result: 30 to 50 of your own IMX708 frames graded by hand, fitted
  directly with `fit_lut`, no transport.

**Acceptance.** Exit code 0, held-out improvement well above the noise floor,
scene-separated training and validation, and a blind A/B on the untouched final
test scenes against the current starter. Report highlight-region clipping and
chroma, shaded-skin colour changes, and the final artifact's monotonicity and
neutrality alongside the trainer gates.

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

**Design.** A `pifilm/scene.py` computing, on a 512-px downscale in Oklab: mean
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

**Baked path complete; adaptive runtime path optional.**

1. **Bake it into the LUT — implemented.** `pifilm/highlight.py` reduces positive
   Oklab lightness lift using the 0.55–0.90 smoothstep window. Both `pifilm-preset`
   and `pifilm-train` accept `--highlights` in [0, 1] and record it in provenance;
   the trainer reimposes monotonicity after protection. Zero leaves the LUT
   unchanged. Oklab chroma is preserved before conversion; sRGB clipping and
   the trainer's projections can change the stored colour. The finished LUT
   ships inside the `.cube`, with no extra runtime processing.
2. **Runtime blend, only if per-scene control is wanted.** A per-pixel weight
   `w(L)` with a soft knee above a lightness threshold blends LUT output back
   toward the normalised input in highlights. One extra luminance pass; cheap,
   and it can be driven by the Phase 8 statistics.

**Acceptance.** On the frozen regression set, mean chroma in the
coloured-highlight mask rises while channel-boundary occupancy falls, as in
the September 7 measurement, and skin in shaded midtones does not warm.

The [September 12 comparison](../../experiments/2026-09-12-highlight-protected-lut.md)
met those aggregate directions on the old-camera set: boundary occupancy
42.77% → 0.218%, chroma up only about 0.017%, with no aggregate shaded-skin
warming. IMX708 value selection remains part of Phase 5. No runtime blend or
new default has been shipped.

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

If this changes the lighting used for Phase 5's corpus, it precedes the final
flash corpus and fit, or triggers a new fit. It is not a dependency for an
explicitly ambient-only first release.

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
