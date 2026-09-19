# Phase 6: Gentler, Configurable Normalisation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the normaliser lifting already-clipped frames and white-balancing ISP-balanced frames twice, add capture-side AE controls, and choose/freeze the parameters on the 108-shot IMX708 pilot so Phase 5 fits the LUT once.

**Architecture:** One new field on `NormalizeParams` and a small damping function inside `compute_gains()` — the single implementation both the Pi (`normalize_u8`) and the trainer (`normalize_float`) call, so parity is automatic. White balance stays a per-artifact parameter (as `levels` already is), exposed on `pifilm-train` and set in the bundled starter. AE controls extend `_apply_camera_controls` with lazily imported libcamera enums. An experiments module measures candidates on the pilot set; the user picks the value, then the starter is regenerated with it.

**Tech Stack:** Python 3.11+, NumPy, Pillow, OpenCV (`require_cv2`), pytest, ruff (E,F,I,B,UP; line length 100). Run everything with `.venv/bin/...`.

**Spec:** `docs/superpowers/specs/2026-09-19-phase6-normalisation-design.md` — read the section named in each task before starting it.

## Global Constraints

- Every task: `.venv/bin/pytest -q -m 'not slow'` green (559+ tests) and `.venv/bin/ruff check .` clean before commit.
- TDD: write the failing test, run it and see it fail, then implement, then see it pass.
- `compute_gains` is the ONLY place the damping maths lives. Do not duplicate it in `normalize_u8`/`normalize_float`.
- `levels_lift_highlight_ref=None` must reproduce today's output bit-for-bit. `PARAMS_VERSION` stays 2.
- No runtime flag may override a trained artifact's normalisation (no `--no-white-balance` on `pifilm-capture`/`pifilm-process`).
- Never commit anything under `source_*/` (gitignored). The experiment reads it by path.
- Module docstrings carry design rationale; extend them, do not delete existing rationale.
- Commit attribution line for every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Implementers never dispatch subagents.

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `pifilm/normalize.py` | `LEVELS_HIGHLIGHT_LIN`, `_damp_lift()`, new param + validation, diagnostics | 1 |
| `tests/test_normalize.py` | damping behaviour tests | 1 |
| `pifilm/train/fit.py` | `train()` kwargs + CLI flags | 2 |
| `tests/test_fit.py` | flags reach params.json | 2 |
| `pifilm/capture/picamera.py` | AE constraint / metering / EV controls | 3 |
| `pifilm/capture/app.py` | three flags, rejection list, constructor wiring | 3 |
| `tests/test_picamera.py`, `tests/test_app.py` | fake libcamera AE enums, flag tests | 3 |
| `pifilm/experiments/normalisation.py` | pilot-set evaluation | 4 |
| `tests/test_experiment_normalisation.py` | synthetic run | 4 |
| `pifilm/preset.py`, `pifilm/data/params.json`, `tests/test_preset.py` | freeze the chosen values | 6 |
| `README.md`, `docs/how-it-works.md`, `docs/picamera2-bringup.md`, `docs/experiments/2026-09-19-imx708-normalisation.md`, `docs/superpowers/plans/2026-09-13-rpi4-imx708-progress.md` | documentation | 7 |

Task 0 (gitignore `source_*/`) is already done in commit `79b35c3`.

---

### Task 1: Clipping-aware lift in `compute_gains` (spec D1)

**Files:**
- Modify: `pifilm/normalize.py` (`NormalizeParams`, `__post_init__`, `compute_gains`; add constant + helper)
- Test: `tests/test_normalize.py`

**Interfaces:**
- Consumes: existing `compute_gains(rgb, params) -> Gains`; `Gains.levels: dict`.
- Produces: `NormalizeParams.levels_lift_highlight_ref: float | None = None`; module constant `LEVELS_HIGHLIGHT_LIN = 0.97`; `_damp_lift(raw_gamma, highlight_frac, ref) -> tuple[float, float]`; `Gains.levels` gains keys `raw_gamma`, `highlight_frac`, `lift_weight` (floats, always present on the levels path). Later tasks rely on these exact names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_normalize.py`:

```python
# --- clipping-aware lift (Phase 6) --------------------------------------------

LIFT = NormalizeParams(white_balance=False, levels=True, levels_lift_highlight_ref=0.05)


def _scene(frac_ceiling: float, ceiling_value: float = 1.0, h: int = 40, w: int = 60):
    """A dark gradient body (sRGB 0.30-0.60) plus ``frac_ceiling`` of its pixels at
    ``ceiling_value``. With the body this dark the levels median lands below the
    exposure target, so raw_gamma < 1: a lift, the outdoor failure mode."""
    body = np.linspace(0.30, 0.60, w, dtype=np.float32)
    img = np.repeat(body[None, :], h, axis=0)[..., None].repeat(3, axis=2).copy()
    n = int(round(frac_ceiling * h * w))
    flat = img.reshape(-1, 3)
    flat[:n] = ceiling_value
    return flat.reshape(h, w, 3)


def test_lift_ref_none_is_bit_for_bit_the_old_path_and_records_weight_one():
    img = _scene(0.10)
    old = compute_gains(img, NormalizeParams(white_balance=False, levels=True))
    assert old.levels["lift_weight"] == 1.0
    assert old.levels["gamma"] == pytest.approx(
        float(np.clip(old.levels["raw_gamma"], 0.5, 2.0))
    )
    for key in ("raw_gamma", "highlight_frac", "lift_weight"):
        assert key in old.levels


def test_a_dark_frame_with_nothing_at_the_ceiling_keeps_its_full_lift():
    # bright pixels at sRGB 0.977 (~0.95 linear) sit below the 0.97 ceiling line
    g = compute_gains(_scene(0.10, ceiling_value=0.977), LIFT)
    assert g.levels["raw_gamma"] < 1.0, "fixture must be a lift"
    assert g.levels["highlight_frac"] == 0.0
    assert g.levels["lift_weight"] == 1.0
    assert g.levels["gamma"] == pytest.approx(g.levels["raw_gamma"])


def test_a_frame_with_ref_or_more_at_the_ceiling_gets_no_lift():
    g = compute_gains(_scene(0.10), LIFT)  # 10 % at the ceiling, ref 5 %
    assert g.levels["raw_gamma"] < 1.0, "fixture must be a lift"
    assert g.levels["highlight_frac"] == pytest.approx(0.10, abs=0.005)
    assert g.levels["lift_weight"] == 0.0
    assert g.levels["gamma"] == pytest.approx(1.0)


def test_a_partial_ceiling_fraction_damps_the_lift_linearly():
    g = compute_gains(_scene(0.025), LIFT)  # half of ref
    assert g.levels["lift_weight"] == pytest.approx(0.5, abs=0.02)
    expected = 1.0 - (1.0 - g.levels["raw_gamma"]) * g.levels["lift_weight"]
    assert g.levels["gamma"] == pytest.approx(expected)


def test_darkening_is_never_damped():
    bright = np.full((40, 60, 3), 0.85, dtype=np.float32)
    bright.reshape(-1, 3)[:240] = 1.0  # 10 % at the ceiling
    g = compute_gains(bright, LIFT)
    assert g.levels["raw_gamma"] > 1.0, "fixture must be a darkening"
    assert g.levels["lift_weight"] == 1.0
    assert g.levels["gamma"] == pytest.approx(float(np.clip(g.levels["raw_gamma"], 0.5, 2.0)))


def test_highlight_fraction_counts_pixels_the_stats_mask_excludes():
    # The stats mask drops luminance > 0.90, so the ceiling pixels are invisible to
    # the median; highlight_frac must still see them or bright frames read as dark.
    g = compute_gains(_scene(0.10), LIFT)
    assert g.levels["highlight_frac"] == pytest.approx(0.10, abs=0.005)


def test_clamped_levels_reflects_the_damped_gamma():
    # Undamped raw_gamma is well below 1; damped to exactly 1.0 it is inside the
    # clamp, so the clamp flag must be False even though raw_gamma alone might clamp.
    g = compute_gains(_scene(0.10), NormalizeParams(
        white_balance=False, levels=True, levels_lift_highlight_ref=0.05,
        levels_gamma_min=0.95, levels_gamma_max=1.05,
    ))
    assert g.levels["gamma"] == pytest.approx(1.0)
    assert g.clamped["levels"] is False


@pytest.mark.parametrize("value", [0.0, -0.1, 1.5, float("nan")])
def test_lift_ref_validation_names_the_field(value):
    with pytest.raises(ValueError, match="levels_lift_highlight_ref"):
        NormalizeParams(levels_lift_highlight_ref=value)


def test_lift_ref_round_trips_and_is_optional():
    p = NormalizeParams(levels=True, levels_lift_highlight_ref=0.05)
    assert NormalizeParams.from_dict(p.to_dict()) == p
    assert NormalizeParams.from_dict({"levels": True}).levels_lift_highlight_ref is None


def test_a_second_pass_is_still_mild_with_the_lift_ref_set():
    img = _scene(0.02)
    once, _ = normalize_float(img, LIFT)
    twice_gains = compute_gains(once, LIFT)
    assert 0.9 <= twice_gains.levels["gamma"] <= 1.1


def test_u8_and_float_paths_agree_on_the_damped_gamma():
    img = _scene(0.03)
    _, g_float = normalize_float(img, LIFT)
    _, g_u8 = normalize_u8((img * 255).round().astype(np.uint8), LIFT)
    assert g_u8.levels["gamma"] == pytest.approx(g_float.levels["gamma"], abs=0.03)
    assert g_u8.levels["lift_weight"] == pytest.approx(g_float.levels["lift_weight"], abs=0.05)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_normalize.py -k "lift or ceiling or damped or second_pass_is_still or u8_and_float"`
Expected: FAIL — `TypeError: unexpected keyword argument 'levels_lift_highlight_ref'` and `KeyError: 'lift_weight'`.

- [ ] **Step 3: Implement**

In `pifilm/normalize.py`:

(a) After `_EPS = 1e-6` add:

```python
# A linear luminance at or above this (about sRGB 254/255) is "at the ceiling".
# Not a parameter: it is the definition of clipped, not a tuning knob.
LEVELS_HIGHLIGHT_LIN = 0.97
```

(b) In `NormalizeParams`, after `levels_target_median`:

```python
    # Clipping-aware lift. The levels gamma brightens a frame whose median is
    # below the exposure target regardless of how much of it is already at the
    # ceiling: on the IMX708 pilot 53 of 108 outdoor-ish shots were lifted while
    # their highlights sat at 1.0, which blew the highlights further and lifted
    # shadows to grey (read as "faded"). When set, the fraction of pixels at the
    # ceiling scales the lift down linearly, reaching zero lift at this fraction.
    # None keeps the old behaviour exactly; the artifact turns it on.
    levels_lift_highlight_ref: float | None = None
```

(c) In `__post_init__`, after the `levels_target_median` check:

```python
        ref = self.levels_lift_highlight_ref
        if ref is not None and not 0.0 < ref <= 1.0:
            raise ValueError(f"levels_lift_highlight_ref must be in (0, 1], got {ref}")
```
(The existing `_check_finite` loop already rejects NaN for this numeric field.)

(d) Add the helper before `compute_gains`:

```python
def _damp_lift(raw_gamma: float, highlight_frac: float, ref: float | None) -> tuple[float, float]:
    """Scale a brightening lift down as the frame's highlights approach the ceiling.

    Returns ``(gamma, weight)``. ``weight`` is 1.0 when nothing was damped: ``ref``
    is None, the frame is being darkened (``raw_gamma >= 1``), or no pixel is at
    the ceiling. It falls linearly to 0.0 as ``highlight_frac`` reaches ``ref``,
    at which point the lift is removed entirely (gamma 1.0). Darkening is never
    touched: a frame that is too bright should still be brought down.
    """
    if ref is None or raw_gamma >= 1.0:
        return raw_gamma, 1.0
    weight = float(np.clip(1.0 - highlight_frac / ref, 0.0, 1.0))
    return 1.0 - (1.0 - raw_gamma) * weight, weight
```

(e) In `compute_gains`, replace the block from `raw_gamma = ...` through the `return Gains(...)` of the levels path with:

```python
    raw_gamma = math.log(target) / math.log(median)
    # Over ALL balanced pixels, not the stats mask: the mask excludes luminance
    # above 0.90, so it can never see the ceiling -- that exclusion is why a
    # bright frame reads as "dark" to the median in the first place.
    highlight_frac = float(np.mean(lum_b >= LEVELS_HIGHLIGHT_LIN))
    damped, lift_weight = _damp_lift(raw_gamma, highlight_frac, params.levels_lift_highlight_ref)
    gamma = float(np.clip(damped, params.levels_gamma_min, params.levels_gamma_max))
    clamped = raw_stretch > params.levels_max_stretch or not (
        params.levels_gamma_min <= damped <= params.levels_gamma_max
    )
    return Gains(
        wb=wb,
        exposure=1.0,
        clamped={"wb": wb_clamped, "exposure": False, "levels": bool(clamped)},
        levels={"low": lo, "high": hi, "stretch": stretch, "gamma": gamma,
                "raw_gamma": float(raw_gamma), "highlight_frac": highlight_frac,
                "lift_weight": lift_weight,
                "black_rgb_spread": float(lo_c.max() - lo_c.min()), "tone": params.levels_tone},
    )
```

(f) Module docstring: add one paragraph after the existing levels paragraph explaining the clipping-aware lift (the pilot numbers above, why the fraction is measured off-mask, that `None` is the old path and the artifact turns it on).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/test_normalize.py` then `.venv/bin/pytest -q -m 'not slow'` and `.venv/bin/ruff check .`
Expected: all pass, ruff clean. If an existing test compared the full `levels` dict by equality, extend its expected dict with the three new keys rather than weakening the assertion.

- [ ] **Step 5: Commit**

```bash
git add pifilm/normalize.py tests/test_normalize.py
git commit -m "Damp the levels lift as highlights approach the ceiling

... (why: pilot numbers; what: levels_lift_highlight_ref, _damp_lift, diagnostics; None = old path)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Trainer flags for source white balance and lift ref (spec D2, trainer part)

**Files:**
- Modify: `pifilm/train/fit.py` (`train()` signature, `source_normalize`, `build_parser()`, `main()`)
- Test: `tests/test_fit.py`

**Interfaces:**
- Consumes: `NormalizeParams(white_balance=..., levels=..., levels_lift_highlight_ref=...)` from Task 1.
- Produces: `train(..., source_white_balance: bool = True, source_lift_highlight_ref: float | None = None)`; CLI `--no-source-white-balance`, `--source-lift-highlight-ref FLOAT`. Recorded in `params.json` via the existing `normalize.to_dict()`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_fit.py`, next to `test_train_end_to_end_publishes_a_loadable_artifact` (reuse exactly its source/target fixture setup and `cfg`/`sample` construction):

```python
def test_train_records_source_white_balance_and_lift_ref_in_the_artifact(tmp_path):
    # same fixture setup as test_train_end_to_end_publishes_a_loadable_artifact
    ...
    out = tmp_path / "out"
    train(tmp_path / "src", tmp_path / "tgt", out, cfg, sample, None, allow_small=True,
          source_white_balance=False, source_lift_highlight_ref=0.05)
    normalize = Artifacts.load(out).normalize
    assert normalize.white_balance is False
    assert normalize.levels_lift_highlight_ref == 0.05
    assert normalize.levels is True


def test_cli_exposes_source_white_balance_and_lift_ref_flags():
    from pifilm.train.fit import build_parser
    args = build_parser().parse_args(["--source", "s", "--no-source-white-balance",
                                      "--source-lift-highlight-ref", "0.05"])
    assert args.source_white_balance is False
    assert args.source_lift_highlight_ref == 0.05
    defaults = build_parser().parse_args(["--source", "s"])
    assert defaults.source_white_balance is True
    assert defaults.source_lift_highlight_ref is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_fit.py -k "white_balance or lift_ref"`
Expected: FAIL — unexpected keyword / unrecognized arguments.

- [ ] **Step 3: Implement**

`train()`: add parameters `source_white_balance: bool = True, source_lift_highlight_ref: float | None = None` (after `target_median`), and:

```python
    source_normalize = NormalizeParams(
        white_balance=source_white_balance,
        levels=source_levels,
        levels_lift_highlight_ref=source_lift_highlight_ref,
    )
```

`build_parser()`, after `--no-source-levels`:

```python
    parser.add_argument(
        "--no-source-white-balance", dest="source_white_balance", action="store_false",
        help="do not grey-world the source frames; use for cameras whose ISP has already "
             "white-balanced them (Picamera2/IMX708). Recorded in the artifact and applied "
             "identically by the Pi",
    )
    parser.add_argument(
        "--source-lift-highlight-ref", type=float, default=None, metavar="FRACTION",
        help="clipping-aware lift: fraction of pixels at the ceiling at which the levels "
             "lift is fully suppressed (e.g. 0.05); default off. Recorded in the artifact",
    )
```

`main()`: pass `source_white_balance=args.source_white_balance, source_lift_highlight_ref=args.source_lift_highlight_ref` to `train(...)`. `NormalizeParams` validation errors surface through the existing `except ValueError` around config construction only if built there; since `NormalizeParams` is built inside `train()`, wrap: catch `ValueError` from `train()` in `main()` the same way the existing code reports config errors (print `error: ...`, return 1). Check how `main()` currently handles exceptions from `train()` and follow it.

- [ ] **Step 4: Run tests, full suite, ruff** — all green.

- [ ] **Step 5: Commit** — `git add pifilm/train/fit.py tests/test_fit.py` — message: "Expose source white balance and lift ref on pifilm-train" (+ attribution).

---

### Task 3: Capture-side AE controls (spec D3)

**Files:**
- Modify: `pifilm/capture/picamera.py` (module tuples, constructor, `_apply_camera_controls`)
- Modify: `pifilm/capture/app.py` (three flags, rejection list, constructor call)
- Test: `tests/test_picamera.py`, `tests/test_app.py`

**Interfaces:**
- Produces: `Picamera2Camera(..., ae_constraint: str = "normal", ae_metering: str = "centre", ev: float = 0.0)`; tuples `_AE_CONSTRAINTS = ("normal", "highlight", "shadows")`, `_AE_METERING = ("centre", "spot", "matrix")`, `_EV_RANGE = (-8.0, 8.0)`; `_apply_camera_controls(camera, autofocus, af_range, ae_lock, awb_lock, colour_gains, ae_constraint, ae_metering, ev)`; CLI `--ae-constraint`, `--ae-metering`, `--ev`.

- [ ] **Step 1: Extend the fake libcamera and write failing tests**

In `tests/test_picamera.py`, add sentinel enums beside `_AfModeEnum`:

```python
class _AeConstraintModeEnum:
    Normal = "AeConstraintMode.Normal"
    Highlight = "AeConstraintMode.Highlight"
    Shadows = "AeConstraintMode.Shadows"


class _AeMeteringModeEnum:
    CentreWeighted = "AeMeteringMode.CentreWeighted"
    Spot = "AeMeteringMode.Spot"
    Matrix = "AeMeteringMode.Matrix"
```

Give `_fake_libcamera_module(*, with_noise_reduction=True, with_ae_enums=True)` a second toggle that adds `AeConstraintModeEnum=_AeConstraintModeEnum, AeMeteringModeEnum=_AeMeteringModeEnum` to `controls_ns` when true; thread `with_ae_enums` through `install_picamera(...)` like `with_noise_reduction`.

Update `test_default_construction_applies_neutral_rendering_and_continuous_af`'s expected dict to also contain:

```python
        "AeConstraintMode": _AeConstraintModeEnum.Normal,
        "AeMeteringMode": _AeMeteringModeEnum.CentreWeighted,
        "ExposureValue": 0.0,
```

Add:

```python
def test_ae_constraint_metering_and_ev_reach_the_controls(install_picamera):
    state = install_picamera()
    camera = Picamera2Camera(ae_constraint="highlight", ae_metering="matrix", ev=-0.5)
    controls = state.instance.set_controls_calls[-1]
    assert controls["AeConstraintMode"] == _AeConstraintModeEnum.Highlight
    assert controls["AeMeteringMode"] == _AeMeteringModeEnum.Matrix
    assert controls["ExposureValue"] == -0.5
    camera.close()


def test_ae_enums_are_omitted_on_older_libcamera_but_ev_is_still_set(install_picamera):
    state = install_picamera(with_ae_enums=False)
    camera = Picamera2Camera(ae_constraint="highlight")
    controls = state.instance.set_controls_calls[-1]
    assert "AeConstraintMode" not in controls
    assert "AeMeteringMode" not in controls
    assert controls["ExposureValue"] == 0.0
    camera.close()


@pytest.mark.parametrize("kwargs, match", [
    ({"ae_constraint": "bright"}, "ae_constraint"),
    ({"ae_metering": "average"}, "ae_metering"),
    ({"ev": 9.0}, "ev"),
    ({"ev": -8.5}, "ev"),
])
def test_invalid_ae_settings_raise_camera_error(install_picamera, kwargs, match):
    install_picamera()
    with pytest.raises(CameraError, match=match):
        Picamera2Camera(**kwargs)
```

In `tests/test_app.py`: add to `test_camera_specific_options_reject_conflicting_backend`'s parametrize:

```python
        (["--camera", "v4l2", "--ae-constraint", "highlight"], "--ae-constraint"),
        (["--camera", "v4l2", "--ae-metering", "matrix"], "--ae-metering"),
        (["--camera", "v4l2", "--ev", "-0.5"], "--ev"),
```
and to `test_implicit_v4l2_via_device_rejects_picamera2_only_flags`'s list: `["--ae-constraint", "highlight"]`, `["--ae-metering", "spot"]`, `["--ev", "0.3"]`. Find the existing test (around line 1099) that asserts `--ae-lock --awb-lock --colour-gains` reach the `Picamera2Camera` constructor kwargs and add a sibling asserting `ae_constraint="highlight", ae_metering="matrix", ev=-0.5` arrive, and that with no flags the constructor receives `ae_constraint="normal", ae_metering="centre", ev=0.0`.

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest -q tests/test_picamera.py tests/test_app.py -k "ae_ or ev"` → FAIL.

- [ ] **Step 3: Implement**

`picamera.py`, module level after `_AF_RANGES`:

```python
_AE_CONSTRAINTS = ("normal", "highlight", "shadows")
_AE_METERING = ("centre", "spot", "matrix")
_EV_RANGE = (-8.0, 8.0)
```

Constructor: add `ae_constraint: str = "normal", ae_metering: str = "centre", ev: float = 0.0` after `colour_gains`; validate in the same style as `autofocus`:

```python
        if ae_constraint not in _AE_CONSTRAINTS:
            raise CameraError(
                f"Unknown ae_constraint {ae_constraint!r}; expected one of {_AE_CONSTRAINTS}"
            )
        if ae_metering not in _AE_METERING:
            raise CameraError(
                f"Unknown ae_metering {ae_metering!r}; expected one of {_AE_METERING}"
            )
        if not _EV_RANGE[0] <= float(ev) <= _EV_RANGE[1]:
            raise CameraError(f"ev must be within {_EV_RANGE}, got {ev}")
```
and pass them to `_apply_camera_controls(camera, autofocus, af_range, ae_lock, awb_lock, colour_gains, ae_constraint, ae_metering, ev)`.

`_apply_camera_controls`: extend the signature; after the AF lines add:

```python
    # Auto-exposure shaping. Centre-weighted + normal constraint is libcamera's
    # default and today's behaviour; "highlight" protects a bright sky/wall that
    # centre-weighting would blow out (measured: shot 171656 on the IMX708 pilot).
    # Enum lookups are guarded like NoiseReductionMode for older libcamera.
    try:
        constraint_modes = {"normal": _lc.AeConstraintModeEnum.Normal,
                            "highlight": _lc.AeConstraintModeEnum.Highlight,
                            "shadows": _lc.AeConstraintModeEnum.Shadows}
        cam_controls["AeConstraintMode"] = constraint_modes[ae_constraint]
    except AttributeError:
        pass  # older libcamera: leave the default, recorded as unset
    try:
        metering_modes = {"centre": _lc.AeMeteringModeEnum.CentreWeighted,
                          "spot": _lc.AeMeteringModeEnum.Spot,
                          "matrix": _lc.AeMeteringModeEnum.Matrix}
        cam_controls["AeMeteringMode"] = metering_modes[ae_metering]
    except AttributeError:
        pass
    cam_controls["ExposureValue"] = float(ev)  # 0.0 is neutral; set always for determinism
```

`app.py`: after `--colour-gains`:

```python
    parser.add_argument(
        "--ae-constraint", choices=("normal", "highlight", "shadows"), default=None,
        help="Picamera2 AE constraint: highlight protects bright regions from clipping "
             "(default: normal)",
    )
    parser.add_argument(
        "--ae-metering", choices=("centre", "spot", "matrix"), default=None,
        help="Picamera2 AE metering (default: centre-weighted)",
    )
    parser.add_argument(
        "--ev", type=float, default=None, metavar="STOPS",
        help="Picamera2 exposure compensation in stops, -8 to 8 (default: 0)",
    )
```
Rejection list: append `("--ae-constraint", args.ae_constraint is not None), ("--ae-metering", args.ae_metering is not None), ("--ev", args.ev is not None)`. Constructor call: `ae_constraint=args.ae_constraint or "normal", ae_metering=args.ae_metering or "centre", ev=args.ev if args.ev is not None else 0.0`. Update the docstring of the rejection helper to name the new flags.

- [ ] **Step 4: Run tests, full suite, ruff** — green.

- [ ] **Step 5: Commit** — "Add AE constraint, metering and EV controls to the Picamera2 backend" (+ attribution).

---

### Task 4: Pilot-set evaluation module (spec D4)

**Files:**
- Create: `pifilm/experiments/normalisation.py`
- Test: `tests/test_experiment_normalisation.py`

**Interfaces:**
- Consumes: `Artifacts.resolve(path_or_None)`, `artifacts.lut.to_pillow()`, `artifacts.lut.apply_pillow(rgb_u8, filter)`, `normalize_u8(rgb_u8, params)`, `load_rgb(path)[0]`, `list_images(dir)`, `LUMA_709` from `pifilm.color`, `NormalizeParams` with `levels_lift_highlight_ref` (Task 1), `dataclasses.replace`.
- Produces: `python -m pifilm.experiments.normalisation --source DIR [--artifacts DIR] [--refs 0.02,0.05,0.10] [--no-wb] [--shots a,b,c] [--sample N] [--max-side 1536] --out DIR` writing `report.json`, `report.md`, `contact_sheet.jpg`.

- [ ] **Step 1: Write the failing test**

`tests/test_experiment_normalisation.py`:

```python
"""The normalisation experiment re-grades a capture folder under candidate params
and measures clipping and shadow lift, so the Phase 6 values are chosen by
numbers on the IMX708 pilot rather than by eye."""

import json

import numpy as np
from PIL import Image

from pifilm.experiments.normalisation import main


def _write(path, arr):
    Image.fromarray(arr).save(path, quality=95)


def test_experiment_reports_more_clipping_for_a_blown_frame_and_writes_all_outputs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    h, w = 64, 96
    ramp = np.linspace(40, 200, w, dtype=np.float32)[None, :, None]
    normal = np.repeat(np.repeat(ramp, h, axis=0), 3, axis=2).astype(np.uint8)
    blown = normal.copy()
    blown[:, w // 2:, :] = 255  # right half at the ceiling
    _write(src / "100000_original.jpg", normal)
    _write(src / "100001_original.jpg", blown)
    out = tmp_path / "out"

    rc = main(["--source", str(src), "--refs", "0.05", "--no-wb", "--sample", "0",
               "--shots", "100001", "--out", str(out)])

    assert rc == 0
    report = json.loads((out / "report.json").read_text())
    assert {"current", "ref=0.05", "current+nowb", "ref=0.05+nowb"} <= set(report["candidates"])
    per_shot = report["per_shot"]["current"]
    assert per_shot["100001"]["clip_pct"] > per_shot["100000"]["clip_pct"]
    assert (out / "report.md").exists()
    assert (out / "contact_sheet.jpg").exists()
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pifilm/experiments/normalisation.py`**

```python
"""Measure candidate normalisation parameters on a capture folder.

Phase 6 of the IMX708 roadmap: the levels lift brightened already-clipped
outdoor frames (53 of 108 pilot shots) and grey-world white balance stacked on
the ISP's AWB (up to 1.6x blue). This module re-normalises every original under
each candidate ``NormalizeParams``, applies the artifact's LUT with grain OFF so
only normalisation differs, and reports per shot and in aggregate:

- ``clip_pct``: percent of pixels with any channel >= 254 in the graded output.
- ``p1_luma`` / ``p5_luma``: 1st and 5th percentile of BT.709 luma of the graded
  output in [0, 1]. High values mean lifted, faded blacks.
- the applied ``gamma``, ``wb_blue``, ``highlight_frac`` and ``lift_weight``.

Aggregates are split indoor/outdoor by ``camera_metadata.Lux > 1500`` when a
``captures.jsonl`` sits beside the originals. A contact sheet shows
original | current | each candidate for named and sampled shots. Never changes
production defaults; outputs go to ``--out`` (gitignored).
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from ..artifacts import Artifacts
from ..color import LUMA_709
from ..imageio import list_images, load_rgb
from ..normalize import NormalizeParams, normalize_u8

OUTDOOR_LUX = 1500.0
CLIP_LEVEL = 254
TILE_W = 480


def candidate_params(base: NormalizeParams, refs: list[float], no_wb: bool) -> dict[str, NormalizeParams]:
    out = {"current": base}
    for ref in refs:
        out[f"ref={ref:g}"] = replace(base, levels_lift_highlight_ref=ref)
    if no_wb:
        for name, params in list(out.items()):
            out[f"{name}+nowb"] = replace(params, white_balance=False)
    return out


def grade(rgb_u8: np.ndarray, params: NormalizeParams, artifacts: Artifacts, lut_filter) -> tuple[np.ndarray, dict]:
    normalised, gains = normalize_u8(rgb_u8, params)
    graded = artifacts.lut.apply_pillow(normalised, lut_filter)
    return graded, gains


def measure(graded_u8: np.ndarray, gains) -> dict:
    clip = np.any(graded_u8 >= CLIP_LEVEL, axis=2)
    luma = (graded_u8.astype(np.float32) / 255.0) @ LUMA_709
    p1, p5 = np.percentile(luma, [1, 5])
    levels = gains.levels or {}
    return {
        "clip_pct": round(float(clip.mean() * 100.0), 3),
        "p1_luma": round(float(p1), 4),
        "p5_luma": round(float(p5), 4),
        "gamma": levels.get("gamma"),
        "wb_blue": round(float(gains.wb[2]), 4),
        "highlight_frac": levels.get("highlight_frac"),
        "lift_weight": levels.get("lift_weight"),
    }


def stem_of(path: Path) -> str:
    return path.stem.removesuffix("_original").removesuffix("_ungraded")


def load_lux(source: Path) -> dict[str, float]:
    log = source / "captures.jsonl"
    if not log.exists():
        return {}
    lux: dict[str, float] = {}
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        value = (rec.get("camera_metadata") or {}).get("Lux")
        if value is not None and rec.get("original"):
            lux[stem_of(Path(rec["original"]))] = float(value)
    return lux


def downscale(rgb_u8: np.ndarray, max_side: int) -> np.ndarray:
    im = Image.fromarray(rgb_u8)
    im.thumbnail((max_side, max_side))
    return np.asarray(im)


def aggregate(per_shot: dict[str, dict], lux: dict[str, float]) -> dict:
    def summarise(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0}
        clip = np.array([r["clip_pct"] for r in rows])
        gammas = np.array([r["gamma"] for r in rows if r["gamma"] is not None])
        return {
            "n": len(rows),
            "clip_pct_mean": round(float(clip.mean()), 3),
            "clip_pct_median": round(float(np.median(clip)), 3),
            "shots_clip_over_1pct": int((clip > 1.0).sum()),
            "p1_luma_median": round(float(np.median([r["p1_luma"] for r in rows])), 4),
            "p5_luma_median": round(float(np.median([r["p5_luma"] for r in rows])), 4),
            "gamma_min": round(float(gammas.min()), 3) if gammas.size else None,
            "gamma_median": round(float(np.median(gammas)), 3) if gammas.size else None,
            "gamma_max": round(float(gammas.max()), 3) if gammas.size else None,
        }

    rows = list(per_shot.values())
    result = {"all": summarise(rows)}
    if lux:
        outdoor = [m for s, m in per_shot.items() if lux.get(s, 0.0) > OUTDOOR_LUX]
        indoor = [m for s, m in per_shot.items() if s in lux and lux[s] <= OUTDOOR_LUX]
        result["outdoor"] = summarise(outdoor)
        result["indoor"] = summarise(indoor)
    return result


def contact_sheet(rows: list[tuple[str, list[np.ndarray]]], headers: list[str], out: Path) -> None:
    tiles = [[ImageOps.contain(Image.fromarray(a), (TILE_W, TILE_W)) for a in imgs] for _, imgs in rows]
    tile_h = max(t.height for row in tiles for t in row)
    label_h = 18
    width = TILE_W * len(headers)
    height = label_h + len(rows) * (tile_h + label_h)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    for c, name in enumerate(headers):
        draw.text((c * TILE_W + 4, 2), name, fill="black")
    y = label_h
    for (stem, _), row in zip(rows, tiles):
        draw.text((4, y), stem, fill="black")
        for c, tile in enumerate(row):
            canvas.paste(tile, (c * TILE_W, y + label_h))
        y += tile_h + label_h
    canvas.save(out, quality=85)


def write_markdown(report: dict, out: Path) -> None:
    lines = ["# Normalisation candidates", ""]
    for name in report["candidates"]:
        lines.append(f"## {name}")
        for split, s in report["aggregate"][name].items():
            if s.get("n"):
                lines.append(
                    f"- **{split}** (n={s['n']}): clip mean {s['clip_pct_mean']}% / median "
                    f"{s['clip_pct_median']}%, shots >1% clipped {s['shots_clip_over_1pct']}, "
                    f"p1 {s['p1_luma_median']}, p5 {s['p5_luma_median']}, gamma "
                    f"{s['gamma_min']}/{s['gamma_median']}/{s['gamma_max']}"
                )
        lines.append("")
    out.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="folder of *_original.jpg")
    parser.add_argument("--artifacts", type=Path, default=None, help="artifact dir (default: bundled)")
    parser.add_argument("--refs", default="0.02,0.05,0.10",
                        help="comma-separated levels_lift_highlight_ref candidates")
    parser.add_argument("--no-wb", action="store_true",
                        help="also evaluate every candidate with white_balance=False")
    parser.add_argument("--shots", default="", help="comma-separated stems always on the sheet")
    parser.add_argument("--sample", type=int, default=6, help="extra random shots on the sheet")
    parser.add_argument("--max-side", type=int, default=1536,
                        help="downscale originals to this before grading (speed)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    artifacts = Artifacts.resolve(args.artifacts)
    lut_filter = artifacts.lut.to_pillow()
    refs = [float(r) for r in args.refs.split(",") if r.strip()]
    cands = candidate_params(artifacts.normalize, refs, args.no_wb)
    originals = [p for p in list_images(args.source)
                 if p.stem.endswith(("_original", "_ungraded"))]
    if not originals:
        print(f"error: no *_original/_ungraded images in {args.source}", file=sys.stderr)
        return 1
    lux = load_lux(args.source)
    args.out.mkdir(parents=True, exist_ok=True)

    named = {s for s in args.shots.split(",") if s}
    rng = random.Random(args.seed)
    pool = [p for p in originals if stem_of(p) not in named]
    sheet_stems = named | {stem_of(p) for p in rng.sample(pool, min(args.sample, len(pool)))}

    per_shot: dict[str, dict[str, dict]] = {name: {} for name in cands}
    sheet_rows: list[tuple[str, list[np.ndarray]]] = []
    for path in originals:
        stem = stem_of(path)
        rgb = downscale(load_rgb(path)[0], args.max_side)
        graded_by = {}
        for name, params in cands.items():
            graded, gains = grade(rgb, params, artifacts, lut_filter)
            per_shot[name][stem] = measure(graded, gains)
            graded_by[name] = graded
        if stem in sheet_stems:
            sheet_rows.append((stem, [rgb, *graded_by.values()]))
        print(f"{stem}: " + ", ".join(f"{n} clip {m[stem]['clip_pct']}%" for n, m in per_shot.items()))

    report = {
        "source": str(args.source), "artifacts": str(artifacts.path) if hasattr(artifacts, "path") else str(args.artifacts),
        "candidates": list(cands),
        "params": {name: p.to_dict() for name, p in cands.items()},
        "per_shot": per_shot,
        "aggregate": {name: aggregate(per_shot[name], lux) for name in cands},
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=1))
    write_markdown(report, args.out / "report.md")
    sheet_rows.sort(key=lambda r: r[0])
    contact_sheet(sheet_rows, ["original", *cands], args.out / "contact_sheet.jpg")
    print(f"wrote {args.out / 'report.json'}, report.md, contact_sheet.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
Add `import sys` to the imports. Check `Artifacts` for a path attribute name and use it (or drop that field). Ensure `Artifacts.resolve(None)` returns the bundled default (see `artifacts.py:174`).

- [ ] **Step 4: Run test, full suite, ruff** — green. Fix line lengths (>100) by wrapping.

- [ ] **Step 5: Commit** — "Add the normalisation-candidates experiment" (+ attribution).

---

### Task 5: Run the evaluation on the pilot set (controller; no subagent)

- [ ] Run:
```bash
.venv/bin/python -m pifilm.experiments.normalisation \
  --source source_imx708/2026-09-19 --refs 0.02,0.05,0.10 --no-wb \
  --shots 171656,172012,172111,172144,172258,172404 --sample 6 \
  --out /tmp/pifilm-phase6-eval
```
- [ ] Read `report.md`; view `contact_sheet.jpg`. Apply the spec's selection rule.
- [ ] **CALL THE USER IN**: show the aggregate tables and the sheet; confirm the `ref` value and whether `white_balance=False` is adopted. Do not proceed to Task 6 without that confirmation.

---

### Task 6: Freeze the chosen values in the bundled starter (spec D2, starter part)

Inputs from Task 5: `REF` (float) and `WB` (bool, expected False).

**Files:**
- Modify: `pifilm/preset.py` (`write_starter`), `pifilm/data/params.json`
- Test: `tests/test_preset.py`

- [ ] **Step 1: Failing tests** in `tests/test_preset.py`:

```python
def test_starter_normalisation_trusts_the_isp_and_damps_the_lift(tmp_path):
    out = write_starter(tmp_path / "s")
    normalize = Artifacts.load(out).normalize
    assert normalize.white_balance is False
    assert normalize.levels is True
    assert normalize.levels_lift_highlight_ref == REF   # literal chosen value


def test_bundled_params_match_write_starter_and_the_cube_is_unchanged(tmp_path):
    out = write_starter(tmp_path / "s")
    bundled = Artifacts.default()
    assert Artifacts.load(out).normalize == bundled.normalize
    assert (out / "pifilm.cube").read_bytes() == (bundled_dir / "pifilm.cube").read_bytes()
```
(Resolve `bundled_dir` the way existing preset tests locate `pifilm/data`; if `Artifacts` exposes the directory, use it.)

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement**: in `write_starter`, `NormalizeParams(levels=True, white_balance=WB, levels_lift_highlight_ref=REF)`; add a comment with the pilot numbers and the date. Regenerate the bundled params:

```bash
.venv/bin/python - <<'PY'
import tempfile, shutil, pathlib
from pifilm.preset import write_starter
tmp = pathlib.Path(tempfile.mkdtemp()); out = write_starter(tmp / "s")
bundled = pathlib.Path("pifilm/data")
assert (out / "pifilm.cube").read_bytes() == (bundled / "pifilm.cube").read_bytes(), "cube changed!"
shutil.copy(out / "params.json", bundled / "params.json"); print("params.json regenerated; cube identical")
PY
```
Confirm `git diff pifilm/data/` shows only `params.json` changed (`white_balance`, `levels_lift_highlight_ref`) and `lut_sha1` unchanged.

- [ ] **Step 4: Tests, suite, ruff** green. Also run `.venv/bin/pytest -q -m slow` once (wheel build uses the bundled data).

- [ ] **Step 5: Commit** — "Freeze Phase 6 normalisation in the bundled starter" (+ attribution).

---

### Task 7: Documentation (spec D2 trade-off, D3 flags, D4 write-up, progress)

**Files:** `README.md` (Camera backends flag table: add `--ae-constraint`, `--ae-metering`, `--ev`; one sentence in the colour-model summary that normalisation is per artifact and the starter targets the IMX708), `docs/how-it-works.md` (normalisation step: the clipping-aware lift and per-artifact white balance, with the pilot numbers), `docs/picamera2-bringup.md` (the three flags in §4; a follow-up item: shoot a 171656-type scene with `--ae-constraint highlight` and confirm the original keeps its highlights), `docs/experiments/2026-09-19-imx708-normalisation.md` (aggregate tables from `report.md`, the chosen values and why, ONE downscaled sheet ≤ 1 MB under `docs/experiments/imx708-normalisation/`), `docs/superpowers/plans/2026-09-13-rpi4-imx708-progress.md` (phase table: 6 done with the frozen values; dated entry; next = Phase 5 with corpus requirements).

- [ ] Write the docs; verify every relative link resolves; the sheet image is ≤ 1 MB (`ImageOps.contain` to 1600 px wide, JPEG q80).
- [ ] Commit — "Document Phase 6: normalisation write-up, flags, progress" (+ attribution).

---

## Self-review notes

- Spec coverage: D1→Task 1, D2 trainer→Task 2, D2 starter→Task 6, D3→Task 3, D4→Tasks 4–5, D5 done (`79b35c3`), docs→Task 7. User call-in at Task 5 as the spec requires.
- Type consistency: `levels_lift_highlight_ref` (Tasks 1, 2, 4, 6); `lift_weight`/`highlight_frac`/`raw_gamma` (Tasks 1, 4); `ae_constraint`/`ae_metering`/`ev` and `_AE_CONSTRAINTS`/`_AE_METERING` (Task 3 only); `_damp_lift` (Task 1 only).
- Placeholders: `REF`/`WB` in Task 6 are inputs produced by Task 5 and confirmed by the user; the implementer receives literal values in the dispatch.
