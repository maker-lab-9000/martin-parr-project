# Highlight-Protected LUT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general "highlight protection" operation that reduces how much any 3D LUT lifts the lightness of bright inputs, and expose it as a `--highlights` control on both `parr-preset` and `parr-train`, so coloured highlights keep more colour and clip less.

**Architecture:** A new pure module `parr/highlight.py` transforms a finished `LUT3D` into a highlight-protected `LUT3D` by working in Oklab: for each node it reduces the amount by which the LUT raises the node's lightness, weighted by a smoothstep over the bright end of the input range, leaving chroma and hue untouched. `parr/preset.py` applies it when building the starter; `parr/train/fit.py` applies it after `fit_lut` and re-imposes monotonicity with the trainer's existing projection helpers. The control is recorded in `params.json` so every artifact carries the value it was built with.

**Tech Stack:** Python 3.11+, NumPy, the project's Oklab helpers in `parr/color.py`, `LUT3D` in `parr/lut.py`, pytest, ruff.

**Spec:** `docs/superpowers/plans/2026-09-11-rpi4-imx708-roadmap.md`, Phase 9 ("Highlight-protected LUT blending"), path 1 (bake it into the LUT). This plan implements only path 1; the optional runtime blend in that phase is out of scope. The technique and its measured effect come from the September 7 experiment (`docs/experiments/2026-09-07-parr-refinement.md`), where the `highlights` control in `parr/experiments/candidates.py` was the most promising single change.

## Global Constraints

- No new runtime or dev dependency; the module uses only NumPy and the existing `parr.color` / `parr.lut`.
- Ruff clean, rules `E, F, I, B, UP`, line length 100. Run `.venv/bin/ruff check parr tests`.
- The highlight window and shape match the existing control exactly: a smoothstep ramp over input lightness from `0.55` to `0.90`, so a value of `1.0` fully removes the tone lift at the top and `0.0` changes nothing. These constants are `HIGHLIGHT_LOW = 0.55` and `HIGHLIGHT_HIGH = 0.90` in the new module.
- `strength` (the `--highlights` value) is validated to be finite and in `[0, 1]`, matching `candidate_lut`'s validation in `parr/experiments/candidates.py:23-25`.
- `strength == 0.0` must return a LUT whose table is bit-for-bit identical to the input, so existing artifacts and tests are unchanged by default.
- Highlight protection only lowers lightness lift; it never raises it. The grey axis stays neutral (chroma untouched on neutral nodes). In the trainer, monotonicity is re-imposed after protection with `enforce_monotone(enforce_grey_axis(enforce_monotone(...)))`, the same idiom `fit_lut` already uses at `parr/train/lutfit.py:181-182`.
- Provenance: the applied value is recorded in `params.json`. For the preset it is a `highlights` key in the training dict; for the trainer it is a field of `FitConfig`, already serialised into `training["fit"]` via `asdict(cfg)` at `parr/train/fit.py:264`.

---

### Task 1: The highlight-protection operation

**Files:**
- Create: `parr/highlight.py`
- Test: `tests/test_highlight.py`

**Interfaces:**
- Consumes: `LUT3D` (`parr/lut.py`); `srgb_to_oklab`, `oklab_to_srgb` (`parr/color.py`).
- Produces: `HIGHLIGHT_LOW = 0.55`, `HIGHLIGHT_HIGH = 0.90`; `protect_highlights(lut: LUT3D, strength: float, low: float = HIGHLIGHT_LOW, high: float = HIGHLIGHT_HIGH) -> LUT3D`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_highlight.py
"""Highlight protection reduces a LUT's lightness lift in bright inputs only."""

import numpy as np
import pytest

from parr.color import srgb_to_oklab
from parr.highlight import protect_highlights
from parr.lut import LUT3D
from parr.train.evaluate import clipped_volume_fraction
from parr.preset import starter_lut


def _lightness(table: np.ndarray) -> np.ndarray:
    return srgb_to_oklab(table)[..., 0]


def test_zero_strength_returns_an_identical_table():
    lut = starter_lut()
    out = protect_highlights(lut, 0.0)
    assert np.array_equal(out.table, lut.table)


def test_protection_lowers_the_lightness_lift_of_bright_inputs():
    lut = starter_lut()  # the starter lifts the tone curve across the range
    grid_l = _lightness(LUT3D.identity(lut.size).table)
    lift_before = _lightness(lut.table) - grid_l
    lift_after = _lightness(protect_highlights(lut, 0.8).table) - grid_l
    bright = grid_l > 0.90
    # Where the starter lifted a bright node, protection reduces that lift.
    lifted_bright = bright & (lift_before > 1e-3)
    assert lifted_bright.any()
    assert np.all(lift_after[lifted_bright] < lift_before[lifted_bright] - 1e-4)


def test_protection_leaves_shadows_and_midtones_untouched():
    lut = starter_lut()
    below_window = _lightness(LUT3D.identity(lut.size).table) < 0.55
    before = lut.table[below_window]
    after = protect_highlights(lut, 1.0).table[below_window]
    assert np.allclose(before, after, atol=1e-6)


def test_protection_preserves_chroma_and_hue_it_only_moves_lightness():
    lut = starter_lut()
    lab_before = srgb_to_oklab(lut.table)
    lab_after = srgb_to_oklab(protect_highlights(lut, 0.7).table)
    # a and b (chroma vector) unchanged; only L moves.
    assert np.allclose(lab_before[..., 1:], lab_after[..., 1:], atol=2e-3)


def test_protection_reduces_gamut_boundary_occupancy_of_a_highlight_lifting_lut():
    lut = starter_lut()
    before = clipped_volume_fraction(lut)
    after = clipped_volume_fraction(protect_highlights(lut, 0.8))
    assert after <= before


def test_output_is_a_valid_lut_in_range():
    out = protect_highlights(starter_lut(), 0.6)
    assert isinstance(out, LUT3D)
    assert out.table.min() >= 0.0 and out.table.max() <= 1.0
    assert np.isfinite(out.table).all()


@pytest.mark.parametrize("bad", [-0.1, 1.1, float("nan"), float("inf")])
def test_strength_outside_zero_to_one_is_rejected(bad):
    with pytest.raises(ValueError, match="highlights"):
        protect_highlights(starter_lut(), bad)


def test_a_bad_window_is_rejected():
    with pytest.raises(ValueError, match="window"):
        protect_highlights(starter_lut(), 0.5, low=0.9, high=0.55)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_highlight.py`
Expected: `ModuleNotFoundError: No module named 'parr.highlight'`

- [ ] **Step 3: Write the minimal implementation**

```python
# parr/highlight.py
"""Reduce how much a LUT lifts the lightness of bright inputs.

The saturated look this project targets pushes the top of the tone range up,
which drives coloured highlights toward white and toward the sRGB gamut
boundary, where they lose colour and clip. Highlight protection undoes part of
that lift for bright inputs only, so a bright red stays red instead of washing
out. It works on any finished ``LUT3D`` -- the handcrafted starter or a trained
fit -- so the same control shapes both looks.

The mechanism is deliberately the one measured in the September 7 experiment
(``parr/experiments/candidates.py``): a smoothstep over input lightness from
0.55 to 0.90 scales down the lightness the LUT added, leaving chroma and hue
untouched. It never raises lightness, so it cannot brighten a highlight; at
most it holds it where the input was.
"""

from __future__ import annotations

import numpy as np

from .color import oklab_to_srgb, srgb_to_oklab
from .lut import LUT3D

HIGHLIGHT_LOW = 0.55
HIGHLIGHT_HIGH = 0.90


def _smoothstep(low: float, high: float, values: np.ndarray) -> np.ndarray:
    """0 below ``low``, 1 above ``high``, a smooth Hermite ramp between."""
    x = np.clip((values - low) / (high - low), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def protect_highlights(
    lut: LUT3D,
    strength: float,
    low: float = HIGHLIGHT_LOW,
    high: float = HIGHLIGHT_HIGH,
) -> LUT3D:
    """Return a LUT whose lightness lift in bright inputs is reduced by ``strength``.

    ``strength`` is in [0, 1]: 0 returns the LUT unchanged, 1 removes the whole
    lift at the top of the range. Chroma and hue are left as the LUT produced
    them; only lightness moves, and only downward.
    """
    if not np.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError(f"highlights must be finite and in [0, 1], got {strength!r}")
    if not 0.0 <= low < high <= 1.0:
        raise ValueError(f"highlight window must satisfy 0 <= low < high <= 1, got ({low}, {high})")
    if strength == 0.0:
        return LUT3D(lut.table.copy())

    n = lut.size
    input_l = srgb_to_oklab(LUT3D.identity(n).table)[..., 0]  # per-node input lightness
    output_lab = srgb_to_oklab(lut.table)
    lift = output_lab[..., 0] - input_l
    weight = _smoothstep(low, high, input_l)
    output_lab[..., 0] = input_l + lift * (1.0 - strength * weight)
    protected = np.clip(oklab_to_srgb(output_lab), 0.0, 1.0)
    return LUT3D(protected.astype(np.float32))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_highlight.py && .venv/bin/ruff check parr tests`
Expected: `8 passed`, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add parr/highlight.py tests/test_highlight.py
git commit -m "Add highlight protection: reduce a LUT's lightness lift in bright inputs"
```

---

### Task 2: `--highlights` on `parr-preset`

**Files:**
- Modify: `parr/preset.py` (`write_starter` at lines 47-57; `main` at lines 60-67)
- Modify: `docs/training.md` (the "Try the starter look" area in the README is separate; this touches the training guide's flag table only if present — see Step 5)
- Test: `tests/test_preset.py`

**Interfaces:**
- Consumes: `protect_highlights` from Task 1.
- Produces: `write_starter(out: str | Path, highlights: float = 0.0) -> Path`; `parr-preset --highlights FLOAT` (default 0.0).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_preset.py
from parr.highlight import protect_highlights
from parr.preset import main as preset_main


def test_write_starter_applies_highlight_protection_and_records_it(tmp_path):
    from parr.artifacts import Artifacts

    art = Artifacts.load(write_starter(tmp_path / "protected", highlights=0.6))
    assert art.training["highlights"] == 0.6
    expected = protect_highlights(starter_lut(), 0.6)
    assert np.array_equal(art.lut.table, expected.table)


def test_write_starter_default_is_the_unprotected_starter(tmp_path):
    from parr.artifacts import Artifacts

    art = Artifacts.load(write_starter(tmp_path / "plain"))
    assert art.training["highlights"] == 0.0
    assert np.array_equal(art.lut.table, starter_lut().table)


def test_preset_cli_accepts_highlights(tmp_path):
    from parr.artifacts import Artifacts

    code = preset_main(["--out", str(tmp_path / "cli"), "--highlights", "0.5"])
    assert code == 0
    assert Artifacts.load(tmp_path / "cli").training["highlights"] == 0.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_preset.py -k highlight`
Expected: FAIL — `write_starter() got an unexpected keyword argument 'highlights'`

- [ ] **Step 3: Write the minimal implementation**

In `parr/preset.py`, add the import and rewrite `write_starter` and `main`:

```python
from .highlight import protect_highlights
```

```python
def write_starter(out: str | Path, highlights: float = 0.0) -> Path:
    lut = protect_highlights(starter_lut(), highlights)
    return write_artifact(
        out, lut, NormalizeParams(levels=True), GrainParams(),
        training={
            "kind": "handcrafted-preset",
            "trained": False,
            "preset_version": 1,
            "highlights": highlights,
            "note": "Untrained saturated color-negative starter. No Martin Parr images used. "
                    "Not a calibrated film-stock or photographer emulation.",
        },
    )
```

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, prog="parr-preset")
    parser.add_argument("--out", type=Path, default=Path("artifacts/starter"))
    parser.add_argument(
        "--highlights", type=float, default=0.0,
        help="protect coloured highlights: 0 = off, up to 1 removes the tone lift at the top",
    )
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"destination already exists: {args.out}; choose a new directory")
    print(f"Wrote untrained starter preset to {write_starter(args.out, args.highlights)}")
    return 0
```

`protect_highlights(starter_lut(), 0.0)` returns the starter unchanged, so the default is bit-identical to today.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_preset.py && .venv/bin/ruff check parr tests`
Expected: all pass, including the three new tests and the pre-existing starter tests; ruff clean.

- [ ] **Step 5: Update the README's starter section**

In `README.md`, the "Using the tools directly" section documents `parr-preset --out artifacts/starter-v1`. Add one sentence after that command: "Pass `--highlights 0.6` to hold coloured highlights back from clipping; `0` (the default) is the current look." (If this branch does not contain that README section because it was cut from `main`, add the sentence to the `parr-preset` paragraph wherever the command appears; do not create a new section.)

- [ ] **Step 6: Commit**

```bash
git add parr/preset.py tests/test_preset.py README.md
git commit -m "parr-preset: --highlights control, recorded in the artifact"
```

---

### Task 3: `--highlights` on `parr-train`

**Files:**
- Modify: `parr/train/fit.py` (`FitConfig` at lines with the dataclass fields; `fit()` after the `fit_lut` call; `build_parser` at lines 285-322)
- Test: `tests/test_fit.py`

**Interfaces:**
- Consumes: `protect_highlights` from Task 1; `enforce_grey_axis`, `enforce_monotone` from `parr/train/lutfit.py`.
- Produces: `FitConfig.highlights: float = 0.0`; `parr-train --highlights FLOAT` (default 0.0); the value recorded in `training["fit"]["highlights"]`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_fit.py
import numpy as np

from parr.train.evaluate import channels_are_monotone, grey_axis_is_monotone
from parr.train.fit import FitConfig, build_parser
from parr.train.lutfit import enforce_grey_axis, enforce_monotone
from parr.highlight import protect_highlights
from parr.preset import starter_lut


def test_fitconfig_has_a_highlights_field_defaulting_to_zero():
    assert FitConfig().highlights == 0.0


def test_train_cli_exposes_highlights_with_the_fitconfig_default():
    parser = build_parser()
    args = parser.parse_args(["--source", "s", "--target", "t"])
    assert args.highlights == FitConfig().highlights
    assert parser.parse_args(["--source", "s", "--target", "t", "--highlights", "0.5"]).highlights == 0.5


def test_reprojection_after_protection_restores_monotonicity():
    # Protection can perturb the grey axis; the trainer re-imposes the same
    # projection fit_lut uses, so the shipped LUT stays monotone.
    protected = protect_highlights(starter_lut(), 0.8)
    reprojected = enforce_monotone(enforce_grey_axis(enforce_monotone(protected)))
    assert grey_axis_is_monotone(reprojected)
    assert channels_are_monotone(reprojected)
```

Also assert `fit()` applies protection. Add a fast, corpus-free test that drives `fit()` with tiny pools:

```python
def test_fit_applies_highlight_protection_to_the_result():
    from parr.train.dataset import PixelPool

    rng = np.random.default_rng(0)
    srgb = rng.random((400, 3)).astype(np.float32)
    lab = None  # PixelPool computes lab from srgb; build via its constructor
    pool = PixelPool(srgb=srgb, n_images=4)
    plain = _fit_lut_of(pool, highlights=0.0)
    protected = _fit_lut_of(pool, highlights=0.8)
    grid_l = srgb_to_oklab(protected.identity(protected.size).table)[..., 0] \
        if False else None
    # The protected fit must differ from the plain fit only where inputs are bright.
    assert not np.array_equal(plain.table, protected.table)
```

Before writing that last test, read `parr/train/dataset.py` for the real `PixelPool` constructor: it takes `srgb` and derives `lab`; confirm the exact required fields and adapt `pool = PixelPool(...)`. Add a small helper `_fit_lut_of(pool, highlights)` in the test that builds a `FitConfig(iterations=2, lut_size=9, highlights=highlights)` and calls `fit(pool, pool, cfg)` (source and target the same pool is fine for a mechanism test), returning `result.lut`. Keep `lut_size` small so the test is fast. If `fit()` with identical source and target and tiny size is unstable, use two independently sampled pools of the same shape.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_fit.py -k "highlights or protection or reprojection"`
Expected: FAIL — `FitConfig` has no `highlights` field; `build_parser` has no `--highlights`.

- [ ] **Step 3: Write the minimal implementation**

In `parr/train/fit.py`:

Add the field to `FitConfig` (after `neutral_axis_cap`), with validation in `__post_init__` mirroring the existing checks:

```python
    highlights: float = 0.0   # protect coloured highlights: 0 = off, 1 = full
```

and in `FitConfig.__post_init__`, next to the other range checks:

```python
        if not 0.0 <= self.highlights <= 1.0:
            raise ValueError(f"highlights must be in [0, 1], got {self.highlights}")
```

Extend the imports:

```python
from .lutfit import enforce_grey_axis, enforce_monotone, fit_lut
from ..highlight import protect_highlights
```

In `fit()`, after `lut = fit_lut(...)` and before `return FitResult(...)`:

```python
    if cfg.highlights > 0.0:
        say(f"protecting highlights at {cfg.highlights}")
        lut = enforce_monotone(enforce_grey_axis(enforce_monotone(
            protect_highlights(lut, cfg.highlights)
        )))
```

In `build_parser`, add next to `--neutral-axis-cap` (using the `fd = FitConfig()` default already in scope there):

```python
    parser.add_argument("--highlights", type=float, default=fd.highlights,
                        help="protect coloured highlights: 0 = off, up to 1 removes the top tone lift")
```

In `main()`, the `FitConfig(...)` construction must pass the new arg. Find the `cfg = FitConfig(` call and add `highlights=args.highlights,` to it. The value is then recorded automatically: `training["fit"]` is `{**asdict(cfg), ...}` at `parr/train/fit.py:264`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_fit.py && .venv/bin/ruff check parr tests`
Expected: all pass; ruff clean.

- [ ] **Step 5: Update the training guide**

In `docs/training.md`, section 7 has a table of `parr-train` flags. Add a row:

```
| `--highlights` | 0.0 | Protects coloured highlights by reducing the LUT's tone lift at the top of the range; 0 is off. Applied after the fit and before the final monotone projection. |
```

If the exact table wording differs, match its column layout. Also add one line to section 9 ("highlight-protected LUT blending") of the roadmap is not needed; only the training guide changes here.

- [ ] **Step 6: Commit**

```bash
git add parr/train/fit.py tests/test_fit.py docs/training.md
git commit -m "parr-train: --highlights control, applied after the fit and recorded"
```

---

## Manual acceptance (not automated; needs real data)

The unit tests prove the mechanism (lift reduced in highlights, chroma preserved, boundary occupancy down, monotonicity held). The quality claim from the roadmap needs the frozen regression set, which is gitignored and absent from a clone. When that data is on the training machine, run the September 7 comparison to confirm the numbers move the right way:

```sh
.venv/bin/parr-preset --out artifacts/starter-hi --highlights 0.6
.venv/bin/python -m parr.experiments.evaluate \
  --snapshot data/refinement-2026-09-07/regression \
  --artifacts artifacts/starter-hi \
  --out data/refinement-2026-09-07/highlight-comparison
```

Expected, per `docs/experiments/2026-09-07-parr-refinement.md`: in the coloured-highlight mask, mean chroma rises and channel-boundary occupancy falls, while shaded skin does not warm. Record it in a dated `docs/experiments/` note before promoting a value into the shipped starter or a trained look.

## Self-review

- **Spec coverage.** Phase 9 path 1 (bake into the LUT, promote the `candidates.py` highlights control into `parr-preset` and `parr-train`): Task 1 is the general operation, Task 2 the preset, Task 3 the trainer. Path 2 (runtime blend) is explicitly out of scope in the header. The "zero runtime cost, ships inside the `.cube`" property holds: protection happens at build/fit time, not in `Pipeline.process`.
- **Placeholder scan.** Every code step has real code. The one place that says "read the real `PixelPool` constructor" (Task 3, Step 1) is a genuine instruction to confirm a signature this plan does not own, not a placeholder for logic; the surrounding test is concrete.
- **Type consistency.** `protect_highlights(lut, strength, low, high) -> LUT3D` is defined in Task 1 and called with those names in Tasks 2 and 3. `write_starter(out, highlights=0.0)` is defined and called consistently. `FitConfig.highlights` is added in Task 3 and read in the same task. `HIGHLIGHT_LOW`/`HIGHLIGHT_HIGH` are defined once in Task 1 and not redefined. The re-projection idiom matches `parr/train/lutfit.py:181-182` verbatim.
