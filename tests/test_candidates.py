import numpy as np
import pytest

from parr.color import srgb_to_oklab
from parr.preset import starter_lut


def test_zero_controls_reproduce_existing_starter():
    from parr.experiments.candidates import candidate_lut
    np.testing.assert_array_equal(candidate_lut().table, starter_lut().table)


def test_candidate_preserves_neutrals_and_valid_range():
    from parr.experiments.candidates import candidate_lut
    lut = candidate_lut(colour=0.25, highlights=0.6, shadows=0.6)
    grey = np.repeat(np.linspace(0, 1, 1024)[:, None], 3, axis=1)
    output = lut.apply_numpy(grey)
    assert np.max(np.ptp(output, axis=1)) < 0.002
    assert np.diff(output, axis=0).min() >= -1e-5
    assert np.isfinite(lut.table).all()
    assert lut.table.min() >= 0 and lut.table.max() <= 1


def test_colour_control_increases_restrained_colour_without_hue_collapse():
    from parr.experiments.candidates import candidate_lut
    rgb = np.array([[0.60, 0.42, 0.40], [0.62, 0.48, 0.38],
                    [0.40, 0.52, 0.43], [0.40, 0.48, 0.60]], dtype=np.float32)
    before = srgb_to_oklab(starter_lut().apply_numpy(rgb))
    after = srgb_to_oklab(candidate_lut(colour=0.25).apply_numpy(rgb))
    assert np.all(np.linalg.norm(after[:, 1:], axis=1) >
                  np.linalg.norm(before[:, 1:], axis=1))
    hues = np.arctan2(after[:, 2], after[:, 1])
    assert hues[1] - hues[0] > 0.15


def test_highlights_retain_more_colour_and_shaded_skin_stays_readable():
    from parr.experiments.candidates import candidate_lut
    highlights = np.array([[0.98, 0.72, 0.46], [0.94, 0.78, 0.64]], np.float32)
    starter = srgb_to_oklab(starter_lut().apply_numpy(highlights))
    changed = srgb_to_oklab(candidate_lut(highlights=0.6).apply_numpy(highlights))
    assert np.all(changed[:, 0] < starter[:, 0])
    assert np.all(np.linalg.norm(changed[:, 1:], axis=1) >=
                  np.linalg.norm(starter[:, 1:], axis=1) - 0.002)
    skin = np.array([[0.38, 0.25, 0.20], [0.53, 0.37, 0.29]], np.float32)
    before = srgb_to_oklab(starter_lut().apply_numpy(skin))
    after = srgb_to_oklab(candidate_lut(shadows=0.6).apply_numpy(skin))
    assert np.all(after[:, 0] > before[:, 0])


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), 2])
def test_invalid_controls_are_rejected(value):
    from parr.experiments.candidates import candidate_lut
    with pytest.raises(ValueError):
        candidate_lut(colour=value)
