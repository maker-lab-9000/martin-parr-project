"""Reduce a LUT's positive lightness lift for bright inputs.

Highlight protection applies a smoothstep over input Oklab lightness from
0.55 to 0.90. Within that window it subtracts a selected fraction of only the
positive lightness lift added by the LUT. A LUT that already darkens a node is
therefore left alone, as are all nodes below the window.

For changed nodes the operation holds Oklab ``a`` and ``b`` fixed while it
lowers ``L``. Converting the result to bounded sRGB can clip an out-of-gamut
colour, so the stored LUT may show a small chroma or hue change at those gamut
boundaries. Untouched nodes are copied directly and remain bit-for-bit exact.
"""

from __future__ import annotations

import numpy as np

from .color import oklab_to_srgb, srgb_to_oklab
from .lut import LUT3D

HIGHLIGHT_LOW = 0.55
HIGHLIGHT_HIGH = 0.90


def _smoothstep(low: float, high: float, values: np.ndarray) -> np.ndarray:
    """Return a smooth Hermite ramp from zero at ``low`` to one at ``high``."""
    x = np.clip((values - low) / (high - low), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def protect_highlights(
    lut: LUT3D,
    strength: float,
    low: float = HIGHLIGHT_LOW,
    high: float = HIGHLIGHT_HIGH,
) -> LUT3D:
    """Return a copy with positive highlight lightness lift reduced.

    ``strength`` must be finite and in ``[0, 1]``. At zero, the table is
    copied unchanged. At one, the requested Oklab colour has all positive lift
    removed above ``high``; bounded sRGB conversion can leave a small residual
    in the stored LUT. The window scales the reduction from ``low`` to ``high``.
    """
    if not np.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError(f"highlights must be finite and in [0, 1], got {strength!r}")
    if not np.isfinite(low) or not np.isfinite(high) or not 0.0 <= low < high <= 1.0:
        raise ValueError(
            "highlight window must satisfy 0 <= low < high <= 1, "
            f"got ({low!r}, {high!r})"
        )

    protected = lut.table.copy()
    if strength == 0.0:
        return LUT3D(protected)

    input_l = srgb_to_oklab(LUT3D.identity(lut.size).table)[..., 0]
    output_lab = srgb_to_oklab(lut.table)
    lift = output_lab[..., 0] - input_l
    reduction = strength * _smoothstep(low, high, input_l) * np.maximum(lift, 0.0)
    changed = reduction > 0.0
    if not np.any(changed):
        return LUT3D(protected)

    changed_lab = output_lab[changed].copy()
    changed_lab[..., 0] -= reduction[changed]
    protected[changed] = oklab_to_srgb(changed_lab)
    return LUT3D(protected)
