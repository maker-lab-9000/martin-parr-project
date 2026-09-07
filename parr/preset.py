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

_NEEDS_TRAIN = (
    "Regenerating the preset needs SciPy, which arrives with the [train] extra:\n"
    "  pip install -e '.[train]'\n"
    "The shipped artifact in parr/data/ was generated on a training machine, so "
    "capture and processing do not need it."
)


def _enforce_monotone():
    """Import the monotone projection lazily, so this module stays importable.

    ``parr.train.lutfit`` imports SciPy at module scope and SciPy is only in
    the [train] extra. A Pi installed with a bare ``pip install -e .`` has
    ``parr-preset`` on its PATH; importing SciPy at the top of this file would
    turn that into a bare ModuleNotFoundError for a tool that used to work.
    """
    try:
        from .train.lutfit import enforce_monotone
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on the install
        raise ModuleNotFoundError(_NEEDS_TRAIN) from exc
    return enforce_monotone


#: Chroma gain applied to already-colourful pixels, tapering in highlights.
BASE_SATURATION = 1.45
#: Chroma treated as "fully colourful": the lift is 1.0 here and rises below it.
VIVID_REFERENCE_CHROMA = 0.15
#: Exponent at ``vividness=1``. Calibrated, not guessed: on 26 indoor captures
#: it puts 14.8% of pixels above chroma 0.06 and 2.4% above 0.12, against
#: 14.6% and 2.6% in the Ektar 100 reference corpus. ``vividness=1.5`` reaches
#: 0.55, which overshoots Ektar toward Velvia (16.2% / 3.8%).
VIVID_EXPONENT_AT_ONE = 0.70
#: Ceiling on the lift, so a nearly-neutral pixel cannot be multiplied without
#: bound. It binds: at vividness 1 the gain is 4.0 (capped) at chroma 0.005,
#: 2.65 at 0.02, 1.91 at 0.06 and the 1.45 base at 0.15. Raising it to 2.5 or
#: 4.0 measured identically on the captures, so the cap only guards the
#: near-neutral tail rather than shaping the look.
VIVID_MAX_GAIN = 4.0
#: Below this Oklab lightness the lift fades out, because near-neutral shadow
#: pixels are mostly sensor noise and lifting their chroma colours it.
VIVID_SHADOW_FLOOR = 0.20


def chroma_gain(chroma: np.ndarray, lightness: np.ndarray, vividness: float) -> np.ndarray:
    """Chroma multiplier: strongest on weak colour, settling to the base gain.

    The original starter look multiplied chroma by a constant, which preserves
    the ratio between weak and strong colour: a pixel at chroma 0.01 lands at
    0.0145 and still reads, to the eye, as grey. Measured on 26 indoor
    captures, 64% of pixels sit below chroma 0.02 against 27-37% in the Ektar
    and Velvia reference corpora, and the graded output left that majority
    where it was. Saturated film does not merely deepen colour that is already
    colourful; it makes weakly coloured things read as coloured.

    So the gain follows a power curve in chroma, ``(C / C_ref) ** (p - 1)``
    with ``p < 1``: unity at the reference chroma and rising as chroma falls.
    A power curve was chosen over an exponential decay after measuring both --
    the exponential form moved mean chroma only 0.0251 to 0.0270 across its
    whole range, while this reaches 0.0284 and matches the reference's *shape*
    on the bands that matter.

    True neutrals are untouched at any setting: a multiplier cannot colour
    chroma zero, and the caller additionally blends the grey diagonal back in.

    This is a declared stylistic control, not something fitted to a reference.
    The reference corpora cannot supply it -- what separates them from these
    captures is subject matter, not grade (see
    ``docs/training-ektar100-2026-09-07.md``). Mean chroma deliberately stays
    far below Velvia's 0.0497: two thirds of these frames are white wall and
    grey floor, and colouring those would be wrong, not vivid.
    """
    if not 0.0 <= vividness <= 1.5:
        raise ValueError(f"vividness must be in [0, 1.5], got {vividness}")
    base = BASE_SATURATION - 0.20 * np.clip((lightness - 0.8) / 0.2, 0, 1)
    power = 1.0 - (1.0 - VIVID_EXPONENT_AT_ONE) * vividness
    ratio = np.maximum(chroma, 1e-6) / VIVID_REFERENCE_CHROMA
    lift = np.clip(ratio ** (power - 1.0), 1.0, VIVID_MAX_GAIN)
    shadow = np.clip(lightness / VIVID_SHADOW_FLOOR, 0.0, 1.0)
    return base * (1.0 + (lift - 1.0) * shadow)


def starter_lut(size: int = 33, vividness: float = 1.0) -> LUT3D:
    """Add contrast and saturation, compressing chroma to stay inside sRGB.

    ``vividness`` scales the low-chroma lift described in ``chroma_gain``:
    0 is the original constant-gain look, 1 matches the Ektar 100 reference's
    chroma distribution, 1.5 leans toward Velvia.
    """
    grid = LUT3D.identity(size).table
    lab = srgb_to_oklab(grid)
    lightness = np.clip(lab[..., 0], 0, 1)
    lab[..., 0] = lightness + 0.065 * np.sin(2 * np.pi * (lightness - 0.5))
    chroma = np.linalg.norm(lab[..., 1:], axis=-1)
    lab[..., 1:] *= chroma_gain(chroma, lightness, vividness)[..., None]
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
    table = np.clip(neutral_tone * (1 - blend) + graded * blend, 0, 1).astype(np.float32)
    # The per-node gamut search and the neutral blend can leave a channel
    # falling as its own input rises -- 53 such steps at vividness 0, the worst
    # reversing by 0.15 (38 of 255), which is the banding hazard the fitted
    # path already projects away. Measured cost here: mean node movement
    # 0.00003 and no change at all to mean chroma, so it is free.
    return _enforce_monotone()(LUT3D(table))


def write_starter(out: str | Path, vividness: float = 1.0) -> Path:
    return write_artifact(
        out, starter_lut(vividness=vividness), NormalizeParams(levels=True), GrainParams(),
        training={
            "kind": "handcrafted-preset",
            "trained": False,
            "preset_version": 2,
            "vividness": vividness,
            "note": "Untrained saturated color-negative starter. No Martin Parr images used. "
                    "Not a calibrated film-stock or photographer emulation.",
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, prog="parr-preset")
    parser.add_argument("--out", type=Path, default=Path("artifacts/starter"))
    parser.add_argument("--vividness", type=float, default=1.0,
                        help="low-chroma lift: 0 = original constant gain, 1 = Ektar-matched, "
                             "1.5 = Velvia-ward")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"destination already exists: {args.out}; choose a new directory")
    print(f"Wrote untrained starter preset to {write_starter(args.out, args.vividness)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
