import numpy as np
import pytest

from parr.artifacts import Artifacts
from parr.color import srgb_to_oklab
from parr.preset import BASE_SATURATION, chroma_gain, starter_lut, write_starter
from parr.train.fit import build_parser


def test_starter_keeps_neutrals_neutral_and_tone_monotonic():
    lut = starter_lut()
    ramp = np.repeat(np.linspace(0, 1, 256)[:, None], 3, axis=1).astype(np.float32)
    graded = lut.apply_numpy(ramp)
    assert np.max(np.ptp(graded, axis=1)) < 0.001
    assert np.all(np.diff(graded, axis=0) >= -1e-6)
    assert np.allclose(graded[0], 0, atol=1e-5)
    assert np.allclose(graded[-1], 1, atol=1e-5)


def test_starter_boosts_midtone_chroma_without_invalid_values():
    lut = starter_lut()
    colours = np.array([[0.65, 0.35, 0.35], [0.35, 0.55, 0.65]], dtype=np.float32)
    before = np.linalg.norm(srgb_to_oklab(colours)[:, 1:], axis=1)
    after = np.linalg.norm(srgb_to_oklab(lut.apply_numpy(colours))[:, 1:], axis=1)
    assert np.all(after > before * 1.2)
    assert np.isfinite(lut.table).all()
    assert lut.table.min() >= 0 and lut.table.max() <= 1


def test_starter_artifact_records_untrained_provenance(tmp_path):
    art = Artifacts.load(write_starter(tmp_path / "starter"))
    assert art.training["trained"] is False
    assert art.training["kind"] == "handcrafted-preset"
    assert art.grain.strength == 0.004


def test_training_skips_reference_levels_stretch_by_default():
    args = build_parser().parse_args(["--source", "source"])
    assert args.target_levels is False
    assert args.grain_strength == 0.004
    assert str(args.target) == "data/references"


def test_vividness_lifts_weak_colour_much_more_than_strong():
    """The point of the control: weak colour must gain more than strong colour.

    A constant multiplier preserves the ratio, so a chroma-0.01 pixel stays
    grey to the eye. Measured on 26 indoor captures, 64% of pixels sit below
    chroma 0.02 against 27-37% in the reference corpora.
    """
    weak, strong = np.array([0.01]), np.array([0.15])
    mid = np.array([0.6])
    assert chroma_gain(weak, mid, 0.0)[0] == chroma_gain(strong, mid, 0.0)[0]
    lifted_weak = chroma_gain(weak, mid, 1.0)[0]
    lifted_strong = chroma_gain(strong, mid, 1.0)[0]
    assert lifted_weak > 2.0 * lifted_strong
    assert lifted_strong == pytest.approx(BASE_SATURATION, abs=1e-6)
    # Monotone in vividness, and 0 reproduces the original look exactly.
    gains = [chroma_gain(weak, mid, v)[0] for v in (0.0, 0.5, 1.0, 1.5)]
    assert gains == sorted(gains)
    for bad in (-0.01, 1.51):
        with pytest.raises(ValueError, match="vividness"):
            chroma_gain(weak, mid, bad)


def test_vividness_never_colours_a_true_neutral_or_a_deep_shadow():
    """A multiplier cannot colour chroma zero, and shadow noise must not be lifted."""
    for v in (0.0, 1.0, 1.5):
        lut = starter_lut(vividness=v)
        ramp = np.repeat(np.linspace(0, 1, 256)[:, None], 3, axis=1).astype(np.float32)
        assert np.max(np.ptp(lut.apply_numpy(ramp), axis=1)) < 0.001, v
    # The lift is faded out below VIVID_SHADOW_FLOOR.
    weak = np.array([0.01])
    assert chroma_gain(weak, np.array([0.0]), 1.5)[0] == pytest.approx(
        chroma_gain(weak, np.array([0.0]), 0.0)[0], abs=1e-6)
    assert chroma_gain(weak, np.array([0.6]), 1.5)[0] > chroma_gain(weak, np.array([0.05]), 1.5)[0]


def test_starter_lut_is_channel_monotone_at_every_vividness():
    """The gamut search and neutral blend left 53 falling steps, worst 0.15
    (38 of 255) -- the banding hazard the fitted path already projects away."""
    from parr.train.evaluate import channels_are_monotone, grey_axis_is_monotone
    for v in (0.0, 1.0, 1.5):
        lut = starter_lut(vividness=v)
        assert channels_are_monotone(lut), v
        assert grey_axis_is_monotone(lut), v
