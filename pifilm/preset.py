"""A reproducible, untrained starting look for saturated color-negative rendering."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .artifacts import write_artifact
from .color import oklab_to_linear, oklab_to_srgb, srgb_to_oklab
from .grain import GrainParams
from .highlight import protect_highlights
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


def write_starter(out: str | Path, highlights: float = 0.0) -> Path:
    lut = protect_highlights(starter_lut(), highlights)
    # Chosen 2026-09-19 on the 108-shot IMX708 pilot: at ref 0.02 every outdoor
    # shot's lift is removed (outdoor median gamma 0.577 -> 1.0, 5th-percentile
    # luma 0.170 -> 0.037) and outdoor MEAN clip falls 13.3% -> 9.5% with white
    # balance off; the ISP's AWB has already balanced Picamera2 frames, and
    # grey-world on top pushed blue up to 1.6x. ref 0.05 matches 0.02 on the
    # outdoor aggregate but only partly damps the worst shots (172404 gamma
    # 0.86, 172258 0.83 vs 1.00 at 0.02); the user chose 0.02 to have those
    # fully corrected, at the cost of more of the indoor lift (indoor median
    # gamma 0.764 -> 0.975, versus 0.856 at ref 0.05).
    # Full numbers: docs/experiments/2026-09-19-imx708-normalisation.md
    normalize = NormalizeParams(levels=True, white_balance=False, levels_lift_highlight_ref=0.02)
    return write_artifact(
        out, lut, normalize, GrainParams(),
        training={
            "kind": "handcrafted-preset",
            "trained": False,
            "preset_version": 1,
            "highlights": highlights,
            "note": "Untrained saturated color-negative starter. No Martin Parr images used. "
                    "Not a calibrated film-stock or photographer emulation.",
            "normalisation_frozen": "2026-09-19 IMX708 pilot",
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, prog="pifilm-preset")
    parser.add_argument("--out", type=Path, default=Path("artifacts/starter"))
    parser.add_argument(
        "--highlights", type=float, default=0.0,
        help="protect coloured highlights: 0 = off, up to 1 removes the tone lift at the top",
    )
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"destination already exists: {args.out}; choose a new directory")
    try:
        destination = write_starter(args.out, args.highlights)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Wrote untrained starter preset to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
