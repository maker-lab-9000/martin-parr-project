# Parr camera refinement implementation plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task. Track evidence here; do not promote a candidate automatically.

**Goal:** Preserve the starter, freeze 26 comparisons, isolate colour/tone experiments, and train scene-separated camera candidates against curated Parr references.

**Architecture:** Offline experiment utilities wrap the existing artifact and runtime pipeline APIs. Explicit file/scene manifests replace random image splitting for this experiment. Candidate artifacts retain the existing runtime format and never replace package defaults.

**Tech Stack:** Python 3.12, NumPy, Pillow, existing SciPy trainer, pytest.

**Spec:** User-approved design in this document: steps 1–4 approved on 2026-09-07; additional sources restricted to `/Users/george.babanau/2026-09-06`.

## Global constraints

- Preserve `parr/data/parr.cube` and `parr/data/params.json` byte for byte.
- Preserve all original camera/reference images; no network collection, deployment or push.
- Freeze all 26 September 7 ungraded/starter/v3 triplets with SHA256, capture metadata and baseline artifacts in ignored `data/refinement-2026-09-07/`.
- Keep a versionable checksum/selection manifest and human report; no photographs in git.
- Treat the 26 already-reviewed scenes as regression/development evidence, never an untouched final test.
- Never fit on regression images. Use only September 6 camera sources for fitting; keep scene groups disjoint between fitting and reported scene-held-out development checks.
- Reference selection favours documented Parr attribution, coherent direct-lit colour work, clean single images, one member per duplicate group; retain provenance and exclusion reasons.
- Compare starter-derived controls independently; true neutrals remain neutral, red/orange hue separation is preserved, shaded skin protection is a colour-range heuristic rather than semantic segmentation.
- Neutral-cap sweep belongs to trained LUTs: 0.005, 0.0075, 0.010 with all other training inputs/settings fixed.
- Fixed grain seeds, identical normalization, independent output directories, artifact hashes and no-overwrite publication.
- Explicitly label small-data training exploratory. Gate failures remain visible; never relax gates to pass a run.

## Task 1: Freeze regression evidence

**Files:** `parr/experiments/regression.py`, `tests/test_regression.py`, ignored data snapshot, `docs/experiments/parr-refinement-manifest.json`.

**Interface:** `freeze_regression(source_dir, graded_dir, out_dir, baseline_dir) -> dict`; `verify_snapshot(root) -> dict`.

- [x] Write tests for complete triplets, missing mates, duplicate records, checksums, source preservation and refusal to overwrite.
- [x] Run `.venv/bin/python -m pytest tests/test_regression.py -q`; confirm absent functionality fails.
- [x] Implement snapshot using staged copies, SHA256 checks and atomic rename; verify every file against the manifest.
- [x] Run focused tests; freeze real 26 triplets and 81 verified files, including log and starter artifacts.
- [x] Copy metadata-only manifest into docs with final results.

## Task 2: Starter-derived candidates

**Files:** `parr/experiments/candidates.py`, `tests/test_candidates.py`.

**Interface:** `candidate_lut(size=33, colour=0, highlights=0, shadows=0) -> LUT3D`; zero controls reproduce `starter_lut` exactly.

- [x] Write tests for zero-control equality, bounded finite output, neutral ramp, coloured highlight retention, shadow readability and red/orange order.
- [x] Run failing tests, then implement smooth Oklab controls and hue-preserving gamut compression. Colour boost tapers to zero at true neutral/high chroma; highlight control reduces upper tone lift; shadow control reduces lower tone darkening for skin-like colours.
- [x] Publish separate baseline, colour-only, highlights-only, shadows-only and combined artifacts, labelled untrained; retain existing grain and normalization parameters.
- [x] Run tests and synthetic ramp diagnostics before rendering the 26 images.

## Task 3: Controlled evaluation and explicit partitions

**Files:** `parr/experiments/evaluate.py`, `parr/experiments/partitions.py`, `tests/test_experiment_evaluate.py`, `tests/test_partitions.py`.

**Interfaces:** `evaluate_candidates(snapshot, artifacts, out) -> dict`; `load_partition(manifest, root, excluded_hashes=()) -> (train_paths, val_paths)`.

- [x] Write failing tests for deterministic rendering, missing metadata, split leakage, unknown roles, path escape and modified input bytes.
- [x] Implement checked scene partitions and reusable paired comparisons. Report per-scene and per-region lightness/chroma/clipping, independent ramp safety, and no-grain metrics alongside fixed-seed display JPEGs.
- [x] Render existing starter/v3 plus candidate contact sheets and inspect portraits, coloured objects and outdoors; record trade-offs without auto-promotion.

## Task 4: Curate and retrain

**Files:** `parr/experiments/train.py`, `tests/test_experiment_train.py`, source/reference selection manifests, `docs/experiments/2026-09-07-parr-refinement.md`.

**Interface:** experiment runner uses `build_pool`, `fit`, `evaluate`, `check_gates`, `write_artifact` with explicit train/validation path lists; records the full manifest and settings in each artifact.

- [x] Inspect all 15 September 6 source photos and relevant curated reference contact sheets; group related camera scenes and duplicate/related reference scenes before splitting.
- [x] Write failing tests proving fitting receives training paths only and exclusions are enforced before any fit.
- [x] Fit three neutral-cap candidates on identical camera/reference pools, seed 0, size 33, 40 rounds, strength 1, smoothness 0.01, identity regularization 1.0; clearly label the small source corpus.
- [x] Keep existing numerical gates; evaluate all three on the same validation pools and regression set; do not rank unmatched target distributions.
- [x] Run the full test suite, lint, snapshot hash verification and baseline hash check. Document candidate paths, decisions, limitations, progress and exact rerun commands.

## Progress / decisions

- Planning: approved direction and source restriction recorded. Existing feature branch retained; no unrelated Velvia files will be touched.
- Initial inventory: 26 regression triplets; 15 September 6 ungraded source files. Source diversity and overlap still need visual audit.
- Baseline test attempt: 332 passed; 6 socket-related failures/errors caused by sandbox localhost restrictions. Elevated rerun started before implementation.
- The tasks share manifests and runtime interfaces, so execution is sequential in this session.
- Baseline elevated rerun: 338 passed, 1 slow packaging test deselected.
- Inventory-driven split adjustment: all 15 September 6 sources are one bedroom scene. Fit those 15; validate on 10 September 7 images from dining room, bathroom and street. The other 16 September 7 images remain in-domain regression checks. No September 7 image is fitted; all 26 were previously reviewed, so none is a blind final test.
- Reference subset: 23 documented-attribution colour images from the existing curated corpus; 19 fit / 4 validation. The two sunbather close-ups and two decorated-cake images are validation groups. No Ektar/Velvia or new downloads.
- Task 1: complete snapshot, 26 triplets, 81 checksums verified.
- Task 2: complete, five artifacts and 130 candidate renders; production preset unchanged.
- Task 3: paired metrics/contact sheets generated; manual selection and final write-up in progress.
- Task 4: trainer implemented; first run found relative-path provenance error after fitting, published nothing. Reproduced with a failing test and fixed; three-cap rerun started.
- Review fixes: protect existing published artifacts even if created during fitting, record actual package source hashes, and assert the real fitting pools exclude validation data. 23 focused tests pass after fixes.
- Safety caveat: starter and all starter-derived variants fail the generic channel-monotonicity/full-cube boundary gates. Grey ramps remain monotone and neutral. These are not production-promoted; distinguish full-cube boundary occupancy from measured clipping in actual photos.
- Task 3: complete. Highlight-only shortlisted; combined retains overly warm shaded skin and increases boundary occupancy in some coloured regions. No auto-promotion.
- Task 4: complete as an exploratory experiment; all three artifacts rejected. Distribution distance 0.056739 before -> 0.082814 / 0.082693 / 0.082593 after. Each fails improvement and grey-axis monotonicity gates; requested neutral caps are not achieved hard bounds in the final LUTs. Solver behavior was not altered to force acceptance.
- Final verification: full suite 362 passed, experiment lint clean, 81 snapshot checksums valid, original source/reference photos and production artifacts unchanged. Scoped independent re-review resolved all substantive code findings.
- Results and commands: `docs/experiments/2026-09-07-parr-refinement.md`. Metadata-only regression, source/reference partitions, exclusions and curation decisions copied into `docs/experiments/`; all photos/artifacts remain ignored.
