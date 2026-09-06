import numpy as np

from parr.artifacts import Artifacts
from parr.color import srgb_to_oklab
from parr.preset import starter_lut, write_starter
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
