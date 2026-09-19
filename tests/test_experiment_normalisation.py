"""The normalisation experiment re-grades a capture folder under candidate params
and measures clipping and shadow lift, so the Phase 6 values are chosen by
numbers on the IMX708 pilot rather than by eye."""

import json

import numpy as np
import pytest
from PIL import Image

from pifilm.experiments.normalisation import main


def _write(path, arr):
    Image.fromarray(arr).save(path, quality=95)


def _flat(values, height):
    """An (h, w, 3) grey frame whose columns follow ``values``."""
    column = np.asarray(values, dtype=np.float32)[None, :, None]
    return np.repeat(np.repeat(column, height, axis=0), 3, axis=2).astype(np.uint8)


def test_experiment_reports_more_clipping_for_a_blown_frame_and_writes_all_outputs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    h, w = 64, 96
    normal = _flat(np.linspace(40, 200, w), h)
    # An outdoor-like blown frame: a dark body the levels gamma wants to lift,
    # plus a quarter of the frame already at the ceiling. That is well past
    # ref=0.05, so the damped candidate must abandon the lift entirely while
    # the current parameters still apply it.
    blown = _flat(np.linspace(75, 150, w), h)
    blown[:, int(w * 0.75):, :] = 255
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

    # The metrics must come from grading with each candidate's own gains, not
    # from the shared original: clipping alone cannot show that, because a
    # pixel already at 255 stays there under every candidate. The lift does.
    current, damped = report["per_shot"]["current"], report["per_shot"]["ref=0.05"]
    assert current["100001"]["gamma"] < 1.0
    assert current["100001"]["lift_weight"] == pytest.approx(1.0)
    assert damped["100001"]["gamma"] == pytest.approx(1.0)
    assert damped["100001"]["lift_weight"] == pytest.approx(0.0)
    assert damped["100001"]["p5_luma"] < current["100001"]["p5_luma"]
    # The unblown frame is below the highlight reference, so the candidates
    # must agree on it -- the damping is clipping-aware, not a global change.
    assert damped["100000"]["gamma"] == pytest.approx(current["100000"]["gamma"])

    assert (out / "report.md").exists()
    assert (out / "contact_sheet.jpg").exists()
