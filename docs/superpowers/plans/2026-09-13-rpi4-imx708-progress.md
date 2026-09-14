# Pi 4 / IMX708 roadmap progress

Roadmap: [2026-09-11-rpi4-imx708-roadmap.md](2026-09-11-rpi4-imx708-roadmap.md).
Dependency review: 2026-09-13, following highlight-protection commits
`d349fec` and `d44c08d` on `plan/rpi4-imx708-camera`.

## Phase status

| Phase | Status | Next prerequisite |
| --- | --- | --- |
| 1: Picamera2 acquisition | Implementation in progress | Task-by-task plan; fake-request tests can start without photos. Hardware required for acceptance. |
| 2: capture controls and metadata | Not implemented | Phase 1 acquisition and hardware control tests. |
| 3: original / DNG / graded output | Not implemented | Request ownership and source/runtime pixel boundary settled with Phases 1–2. |
| 4: benchmark | Not recorded for this roadmap | Synthetic benchmark can start now; real Pi 4 capture and DNG timings follow 1–3. |
| F: lighting experiment | Not recorded for IMX708 | Stable originals, pilot captures and paired lighting test. |
| 6: gentler normalisation | Not implemented | Code can start independently; choose parameters on IMX708 pilot photos before fitting. |
| 5: IMX708 retraining | Not performed | Stable capture/lighting policy, frozen normalisation, source corpus and scene-grouped training route. |
| 7: grain | Not implemented | Phase 4 timing/resolution decision; independent of colour-LUT fitting. |
| 8: scene statistics | Not implemented | Acquisition metadata for full integration; not a blocker for the first retrain. |
| 9: baked highlight protection | Implemented and tested | Select the IMX708 value in Phase 5; current default remains zero. |
| 9: runtime blend | Not implemented; optional | Evidence of need and Phase 8 adaptive inputs. |
| 10: classifier | Not implemented; conditional | Labelled data and evidence simple scene rules are insufficient. |
| F′: final flash | Not recorded | Prototype decision; collect final flash corpus after final lighting is established. |

## Dependency review completed

- Removed the dependency of baked highlight protection on scene statistics.
- Moved highlight-value selection into the first IMX708 training workflow;
  old-camera results do not select a new-camera default.
- Preserved separate controls for normalisation, LUT strength and highlights.
- Identified the scene-grouped CLI gap: `parr/experiments/train.py` accepts a
  `FitConfig` through its Python API but its CLI only exposes `--neutral-cap`.
  `parr-train` exposes highlights but partitions automatically by image.
- Added an explicit source/runtime parity requirement: pre-JPEG pixels and
  decoded saved-JPEG pixels are not identical inputs for exact replay.
- Clarified that new normalisation requires a refit, but suitable originals
  can be reused; DNG development is not needed for the current JPEG trainer.
- Corrected the assumption that 512-px training sampling makes all capture
  modes and pre-LUT resizing paths interchangeable.
- Moved final lighting establishment before the production flash corpus, or
  required a later recollection/refit if the light changes.

## Photo milestones

1. **Implementation can start now without a corpus.** Real shots are needed
   to accept acquisition, metadata and saved-file behaviour on hardware.
2. **First useful handoff: after Phases 1–3.** Target 20–30 pilot originals
   across 8–10 scenes, with capture logs and scene IDs. Include ten matched
   flash/ambient pairs if testing a light. Use these for F/6 decisions.
3. **Production collection: after capture and lighting are stable.** At least
   100 development originals over 25 scenes, plus 3–5 separate final-test
   scenes. Collection may overlap Phase 6 implementation; normalisation must
   be fixed before fitting. Prepare at least 200 coherent references separately.
4. **First production fit: Phase 5.** Use scene-held-out development data to
   select the fit and highlights; inspect the untouched final scenes only
   after settings are fixed. No IMX708 quality claim exists yet.

## Next implementation unit

Prepare the Phase 1 task-by-task plan against `parr/capture/camera.py`,
`parr/capture/app.py` and the existing fake-camera tests. Include how request
ownership can support Phase 3 without prematurely releasing saved-image data,
and preserve the V4L2/FakeCamera paths and Stick thumbnail behaviour.
Photo collection is not a blocker for writing or testing that software plan.
The remaining hardware/API assumptions in the roadmap must be checked against
the installed Picamera2/libcamera versions during that planning and bring-up.

## Validation of the September 13 roadmap review

Reviewed current highlight/config/provenance code, capture frame/session code,
normalisation and dataset handling, scene-partition training, training guide,
and the completed highlight experiment/progress records. Roadmap-relative
Markdown file links resolve and `git diff --check` passes. That review changed
documentation only; implementation progress is recorded below.

## 2026-09-14 — camera delivered; Phase 1 started

User reports the IMX708 autofocus camera has arrived. Connection to the Pi 4, SSH address, installed stack and exact lens variant are not yet confirmed.

Implementation plan: [Picamera2 acquisition](2026-09-14-picamera2-acquisition.md). Baseline camera/app/controller tests: 85 passed. Use fake Picamera2 requests for development; hardware acceptance remains separate. Preserve the prior roadmap review edits.

- Backend implemented: optional stream metadata, native BGR-to-RGB copy, measured FPS, request/close cleanup and lazy OS dependency. Focused camera tests: **50 passed**; Ruff and diff checks clean. Scoped spec and quality review passed; CLI integration in progress.

- Hardware checklist: [Picamera2 bring-up](../../picamera2-bringup.md). Hardware identity, SSH access and native capture acceptance remain pending. Existing deploy script/service examples omit backend selection; migration must set the intended backend/tuning explicitly.

- CLI selection checks: **63 app tests passed**. Explicit backend/tuning, automatic selection, fake bypass and dependency/conflict errors verified. Native session/thumbnail acceptance test and final suite remain in progress.
