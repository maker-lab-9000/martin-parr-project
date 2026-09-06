"""A reproducible, untrained starting look for saturated color-negative rendering."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .artifacts import write_artifact
from .color import oklab_to_linear, oklab_to_srgb, srgb_to_oklab
from .grain import GrainParams
from .lut import LUT3D
from .normalize import NormalizeParams


def starter_lut(size: int = 33) -> LUT3D:
    """Add contrast and saturation, compressing chroma to stay inside sRGB."""
    grid = LUT3D.identity(size).table
    lab = srgb_to_oklab(grid)
    lightness = np.clip(lab[..., 0], 0, 1)
    lab[..., 0] = lightness + 0.065 * np.sin(2 * np.pi * (lightness - 0.5))
    # Preserve near-neutral colours; boost colourful midtones most strongly.
    saturation = 1.45 - 0.20 * np.clip((lightness - 0.8) / 0.2, 0, 1)
    lab[..., 1:] *= saturation[..., None]
    low = np.zeros(lightness.shape, dtype=np.float32)
    high = np.ones(lightness.shape, dtype=np.float32)
    for _ in range(16):
        amount = (low + high) / 2
        candidate = lab.copy()
        candidate[..., 1:] *= amount[..., None]
        rgb = oklab_to_linear(candidate)
        in_gamut = ((rgb >= -1e-6) & (rgb <= 1 + 1e-6)).all(axis=-1)
        low = np.where(in_gamut, amount, low)
        high = np.where(in_gamut, high, amount)
    lab[..., 1:] *= low[..., None]
    graded = np.clip(oklab_to_srgb(lab), 0, 1)
    # Protect the whole set of cells touching the grey diagonal. Neutralising
    # just the diagonal nodes leaves tint between nodes under trilinear sampling.
    distance = np.ptp(grid, axis=-1)
    blend = np.clip((distance - 2 / (size - 1)) / 0.12, 0, 1)
    blend = (blend * blend * (3 - 2 * blend))[..., None]
    neutral_tone = grid + 0.065 * np.sin(2 * np.pi * (grid - 0.5))
    return LUT3D(np.clip(neutral_tone * (1 - blend) + graded * blend, 0, 1).astype(np.float32))


def write_starter(out: str | Path) -> Path:
    return write_artifact(
        out, starter_lut(), NormalizeParams(levels=True), GrainParams(),
        training={
            "kind": "handcrafted-preset",
            "trained": False,
            "preset_version": 1,
            "note": "Untrained saturated color-negative starter. No Martin Parr images used. "
                    "Not a calibrated film-stock or photographer emulation.",
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, prog="parr-preset")
    parser.add_argument("--out", type=Path, default=Path("artifacts/starter"))
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"destination already exists: {args.out}; choose a new directory")
    print(f"Wrote untrained starter preset to {write_starter(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
