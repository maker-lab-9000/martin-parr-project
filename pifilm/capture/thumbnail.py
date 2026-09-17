"""Small, bounded JPEG previews for the remote capture protocol."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

THUMBNAIL_SIZE = (240, 135)
MAX_JPEG_BYTES = 64 * 1024


class ThumbnailError(ValueError):
    """The saved grade cannot safely be represented by the remote thumbnail."""


def fitted_jpeg(
    source: Path,
    *,
    size: tuple[int, int] = THUMBNAIL_SIZE,
    max_bytes: int = MAX_JPEG_BYTES,
) -> bytes:
    """Return an aspect-preserving RGB JPEG on a black ``size`` canvas.

    ``source`` is deliberately a trusted capture result path supplied by the
    server; this function never interprets an HTTP path or filename.
    """
    try:
        with Image.open(source) as opened:
            image = opened.convert("RGB")
    except (OSError, UnidentifiedImageError) as exc:
        raise ThumbnailError("saved graded image is invalid") from exc

    width, height = size
    if width <= 0 or height <= 0 or max_bytes <= 0:
        raise ThumbnailError("invalid thumbnail limits")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "black")
    left = (width - image.width) // 2
    top = (height - image.height) // 2
    canvas.paste(image, (left, top))

    for quality in range(90, 19, -5):
        data = io.BytesIO()
        canvas.save(data, format="JPEG", quality=quality, optimize=True)
        encoded = data.getvalue()
        if len(encoded) <= max_bytes:
            return encoded
    raise ThumbnailError(f"thumbnail exceeds {max_bytes // 1024} KiB transfer limit")
