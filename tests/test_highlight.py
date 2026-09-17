"""Highlight protection reduces a LUT's lightness lift in bright inputs only."""

import numpy as np
import pytest

from pifilm.color import oklab_to_linear, srgb_to_oklab
from pifilm.highlight import protect_highlights
from pifilm.lut import LUT3D
from pifilm.preset import starter_lut
from pifilm.train.evaluate import clipped_volume_fraction


def _lightness(table: np.ndarray) -> np.ndarray:
    return srgb_to_oklab(table)[..., 0]


def test_zero_strength_returns_an_independent_identical_table():
    lut = starter_lut()

    out = protect_highlights(lut, 0.0)

    assert np.array_equal(out.table, lut.table)
    assert not np.shares_memory(out.table, lut.table)


def test_protection_lowers_the_lightness_lift_of_bright_inputs():
    lut = starter_lut()
    grid_l = _lightness(LUT3D.identity(lut.size).table)
    lift_before = _lightness(lut.table) - grid_l

    lift_after = _lightness(protect_highlights(lut, 0.8).table) - grid_l

    lifted_bright = (grid_l > 0.90) & (lift_before > 1e-3)
    assert lifted_bright.any()
    assert np.all(lift_after[lifted_bright] < lift_before[lifted_bright] - 1e-4)


def test_protection_leaves_shadows_and_midtones_bit_for_bit_untouched():
    lut = starter_lut()
    below_window = _lightness(LUT3D.identity(lut.size).table) <= 0.55

    out = protect_highlights(lut, 1.0)

    assert np.array_equal(out.table[below_window], lut.table[below_window])


def test_protection_does_not_raise_a_darkening_lut():
    table = LUT3D.identity(9).table.copy()
    table *= np.float32(0.75)
    lut = LUT3D(table)

    out = protect_highlights(lut, 1.0)

    assert np.array_equal(out.table, lut.table)


def test_protection_leaves_an_identity_lut_bit_for_bit_unchanged():
    lut = LUT3D.identity(9)

    out = protect_highlights(lut, 1.0)

    assert np.array_equal(out.table, lut.table)
    assert not np.shares_memory(out.table, lut.table)


def test_protection_preserves_oklab_chroma_where_adjusted_colour_is_in_gamut():
    lut = starter_lut()
    input_l = _lightness(LUT3D.identity(lut.size).table)
    lab_before = srgb_to_oklab(lut.table)
    lift = lab_before[..., 0] - input_l
    x = np.clip((input_l - 0.55) / (0.90 - 0.55), 0.0, 1.0)
    weight = x * x * (3.0 - 2.0 * x)
    reduction = 0.7 * weight * np.maximum(lift, 0.0)
    requested = lab_before.copy()
    requested[..., 0] -= reduction
    raw_rgb = oklab_to_linear(requested)
    changed_in_gamut = (reduction > 0.0) & ((raw_rgb >= 0.0) & (raw_rgb <= 1.0)).all(axis=-1)

    lab_after = srgb_to_oklab(protect_highlights(lut, 0.7).table)

    assert changed_in_gamut.any()
    assert np.allclose(
        requested[changed_in_gamut, 0], lab_after[changed_in_gamut, 0], atol=1e-6
    )
    assert np.allclose(
        lab_before[changed_in_gamut, 1:], lab_after[changed_in_gamut, 1:], atol=1e-6
    )


def test_protection_keeps_neutral_nodes_neutral():
    lut = starter_lut(17)
    diagonal = np.arange(lut.size)

    neutral = protect_highlights(lut, 1.0).table[diagonal, diagonal, diagonal]

    assert np.max(np.ptp(neutral, axis=-1)) < 1e-6


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


def test_protection_does_not_mutate_the_input_lut():
    lut = starter_lut()
    before = lut.table.copy()

    protect_highlights(lut, 0.8)

    assert np.array_equal(lut.table, before)


@pytest.mark.parametrize("bad", [-0.1, 1.1, float("nan"), float("inf")])
def test_strength_outside_zero_to_one_is_rejected(bad):
    with pytest.raises(ValueError, match="highlights"):
        protect_highlights(starter_lut(), bad)


@pytest.mark.parametrize(
    ("low", "high"),
    [
        (-0.1, 0.9),
        (0.55, 1.1),
        (0.55, 0.55),
        (0.9, 0.55),
        (float("nan"), 0.9),
        (0.55, float("nan")),
        (float("-inf"), 0.9),
        (0.55, float("inf")),
    ],
)
def test_invalid_highlight_window_is_rejected(low, high):
    with pytest.raises(ValueError, match="window"):
        protect_highlights(starter_lut(), 0.5, low=low, high=high)
