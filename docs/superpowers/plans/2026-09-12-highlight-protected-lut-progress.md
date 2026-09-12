# Highlight-protected LUT implementation progress

Plan: `docs/superpowers/plans/2026-09-11-highlight-protected-lut.md`
Base: `1f06031` on `plan/rpi4-imx708-camera`. Started 2026-09-12.

## Status

- Task 1: complete (`d349fec`); spec and code-quality review passed — pure highlight operation and tests.
- Task 2: complete; spec and code-quality review passed — preset flag, provenance and README.
- Task 3: complete; spec and code-quality review passed — trainer flag, projection, provenance and guide.
- Full tests and frozen regression comparison: complete. Whole-change review: complete; no actionable findings.

## Plan review and decisions

| Scope | Interface / consistency check | Finding |
| --- | --- | --- |
| Tasks 1–2 | protect_highlights -> write_starter | Compatible; default must remain bit-identical. |
| Tasks 1–3 | protect_highlights -> fit | Compatible; trainer projects only when enabled. |
| Tasks 2–3 | independent preset/trainer CLI and provenance | No shared edits. |
| Task 1 | tests versus formula and global constraints | Sample formula raises negative lift; gamut clipping limits exact chroma preservation. |
| Task 2 | files and documentation | README is the actual documentation target. |
| Task 3 | tests versus real fitting API | PixelPool accepts srgb and n_images; use a deliberately lifting target instead of identity data. |

Ruling: Limit correction to positive lightness lift, preserving untouched nodes exactly — required by the never-brighten contract; differs from the sample formula for darkening LUTs.

Ruling: Preserve Oklab chroma before conversion, document that sRGB gamut clipping can change it — exact chroma preservation and arbitrary bounded RGB cannot both be guaranteed.

Ruling: Continue in the clean named feature checkout — work is already scoped to the user-specified plan branch; no main/master edits or external publication.

Ruling: Keep this tracked progress document separate; leave plan and roadmap unchanged. Skill helper task-brief cannot execute its non-executable sibling, so extracted task briefs directly into its scratch workspace.

## Verification log

- Initial sandbox run: 370 passed; 3 failures and 4 errors from packaging/network and local socket restrictions.
- Unrestricted run after core tests were added: **399 passed**, 83.47 seconds. Ruff: all checks passed.
- Frozen snapshot verified: 26 captures. Referenced September 7 experiment note is absent on this branch.
- Acceptance command correction: evaluator `--artifacts` expects a parent containing artifact directories, not the single artifact directory shown in the plan. Use its explicit mapping API for the paired comparison.

- Core commit: `d349fec`. 22 focused tests pass. Measured maximum stored a/b change after clipping: 0.008486 (in-gamut round-trip error: 5.96e-08); full protection can retain up to 0.000827 lightness lift on clipped nodes. The original whole-grid 0.002 chroma tolerance is therefore not valid; tests assert strict preservation on in-gamut nodes and bounded output globally.

Ruling: Batch Tasks 2 and 3 with one implementer and one scoped review — both wire the same validated operation into existing CLI/config/provenance paths, with disjoint code and tests.

Ruling: Replace plan loaded-table array_equal assertions with serialization-aware checks — `.cube` stores six decimals (observed max error 5.066395e-07). Keep exact comparisons for in-memory zero strength and artifact bytes between default and explicit zero. Compare the protected regression candidate with both frozen and freshly serialized unprotected controls.

- Frozen comparison complete: 26 captures. Coloured-highlight boundary occupancy 42.7721% → 0.2180%; mean chroma 0.05686796 → 0.05687742. Shaded-skin mean a/b both decrease slightly. Directional criteria met; chroma gain is tiny, no blind visual review or default promotion. Full evidence: `docs/experiments/2026-09-12-highlight-protected-lut.md`.

## Acceptance checklist

- [x] Pure NumPy operation; default window 0.55–0.90.
- [x] Finite strength in [0, 1]; validated window.
- [x] Zero strength, identity, shadows and nonpositive lift preserved exactly.
- [x] Positive lightness lift reduced; input not mutated; neutral nodes stay neutral.
- [x] In-gamut chroma preservation; stored gamut-clipping limitation measured.
- [x] Preset flag, provenance, CLI rejection and byte-identical zero default verified.
- [x] Trainer flag/config/provenance, post-fit projection and real fitting test verified.
- [x] Final full tests, lint, diff check and independent review.
- [x] Frozen paired regression and dated experiment note.
- [x] Bundled default remains unchanged; no runtime blend added.

- Preset TDD: 7 expected failures before implementation, then 11 passing tests and Ruff clean. CLI accepts/records highlights and rejects invalid values without creating artifacts.
- Integration commit deferred until final verification: sandbox blocks `.git/index.lock`; implementation continues independently of commit approval.

- Trainer TDD: 13 highlight-focused tests pass; all 29 trainer tests pass. Combined preset/trainer verification: **40 passed** in 10.07 seconds; full Ruff and diff checks clean. Real lifting pools: 65 bright lifted nodes, mean lift 0.01521663 → 0.00661331 at strength 0.8, both monotonicity diagnostics pass.

- Final full suite: **419 passed** in 67.90 seconds, outside sandbox for local HTTP and wheel-install coverage. Ruff: all checks passed. `git diff --check`: clean. Tasks 2–3 spec and quality review: passed with no findings.

## Completion

All three implementation tasks and the frozen regression comparison are complete. Final independent whole-change review found no actionable issues. The plan and roadmap remain unchanged; defaults remain zero and the bundled artifact is unchanged. Work stays on `plan/rpi4-imx708-camera`; no merge or push was requested.

Core commit: `d349fec`. The integration and progress/experiment records are included in the commit containing this completed document. The optional runtime blend and production-default promotion remain out of scope.
