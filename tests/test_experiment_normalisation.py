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
