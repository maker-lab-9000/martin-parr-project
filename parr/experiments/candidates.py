"""Isolated starter-derived controls, baked into ordinary deployable 3D LUTs."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from ..artifacts import Artifacts, write_artifact
from ..color import oklab_to_linear, oklab_to_srgb, srgb_to_oklab
from ..lut import LUT3D
from ..preset import starter_lut


def smooth(low, high, values):
    x = np.clip((values - low) / (high - low), 0, 1)
    return x * x * (3 - 2 * x)


def candidate_lut(size=33, colour=0.0, highlights=0.0, shadows=0.0) -> LUT3D:
    for name, value in [('colour', colour), ('highlights', highlights), ('shadows', shadows)]:
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'{name} must be finite and in [0, 1]')
    if colour == highlights == shadows == 0:
        return starter_lut(size)
    grid = LUT3D.identity(size).table
    lab = srgb_to_oklab(grid)
    lightness = np.clip(lab[..., 0], 0, 1)
    chroma = np.linalg.norm(lab[..., 1:], axis=-1)
    hue = np.arctan2(lab[..., 2], lab[..., 1])
    # A conservative colour-range heuristic, not a face/skin detector.
    hue_distance = np.abs(np.angle(np.exp(1j * (hue - np.deg2rad(45)))))
    skin = (1 - smooth(np.deg2rad(20), np.deg2rad(55), hue_distance))
    skin *= smooth(0.01, 0.035, chroma) * (1 - smooth(0.12, 0.20, chroma))

    def tone(values):
        delta = 0.065 * np.sin(2 * np.pi * (values - 0.5))
        return values + delta * (1 - highlights * smooth(0.55, 0.90, values))

    lab[..., 0] = tone(lightness)
    negative_delta = np.minimum(0.065 * np.sin(2 * np.pi * (lightness - 0.5)), 0)
    lab[..., 0] -= shadows * skin * negative_delta
    saturation = 1.45 - 0.20 * np.clip((lightness - 0.8) / 0.2, 0, 1)
    weight = smooth(0.008, 0.04, chroma) * (1 - smooth(0.08, 0.18, chroma))
    weight *= smooth(0.08, 0.25, lightness) * (1 - smooth(0.80, 0.98, lightness))
    weight *= 1 - 0.5 * skin
    lab[..., 1:] *= (saturation * (1 + colour * weight))[..., None]
    low, high = np.zeros(lightness.shape), np.ones(lightness.shape)
    for _ in range(16):
        amount = (low + high) / 2
        candidate = lab.copy()
        candidate[..., 1:] *= amount[..., None]
        rgb = oklab_to_linear(candidate)
        valid = ((rgb >= -1e-6) & (rgb <= 1 + 1e-6)).all(axis=-1)
        low, high = np.where(valid, amount, low), np.where(valid, high, amount)
    lab[..., 1:] *= low[..., None]
    graded = np.clip(oklab_to_srgb(lab), 0, 1)
    blend = smooth(2 / (size - 1), 2 / (size - 1) + 0.12, np.ptp(grid, axis=-1))
    result = tone(grid) * (1 - blend[..., None]) + graded * blend[..., None]
    return LUT3D(np.clip(result, 0, 1).astype(np.float32))


VARIANTS = {
    'starter-control': {},
    'colour-only': {'colour': 0.25},
    'highlights-only': {'highlights': 0.6},
    'shadows-only': {'shadows': 0.6},
    'combined': {'colour': 0.25, 'highlights': 0.6, 'shadows': 0.6},
}


def write_candidates(out, baseline):
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    base = Artifacts.load(baseline)
    out.mkdir(parents=True)
    for name, controls in VARIANTS.items():
        write_artifact(out / name, candidate_lut(**controls), base.normalize, base.grain,
                       training={'kind': 'starter-derived-experiment', 'trained': False,
                                 'parent_lut_sha1': base.lut_sha1, 'controls': controls,
                                 'note': 'Untrained style controls; no simulated flash lighting.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=Path('parr/data'))
    args = parser.parse_args()
    write_candidates(args.out, args.baseline)


if __name__ == '__main__':
    main()
