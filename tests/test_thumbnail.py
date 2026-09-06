from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from parr.capture.thumbnail import ThumbnailError, fitted_jpeg


def _decode(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def test_fitted_jpeg_letterboxes_a_landscape_image_without_changing_aspect_ratio(tmp_path):
    """Cropping or stretching the saved photograph would lose its composition."""
    source = tmp_path / "landscape.jpg"
    Image.fromarray(np.full((100, 400, 3), (220, 20, 10), dtype=np.uint8)).save(source)

    image = _decode(fitted_jpeg(source))

    assert image.shape == (135, 240, 3)
    assert image[0].max() == 0
    assert image[37:97, :, 0].mean() > 200


def test_fitted_jpeg_letterboxes_a_portrait_image_without_changing_aspect_ratio(tmp_path):
    """Portrait captures need side borders, not a rotated or cropped thumbnail."""
    source = tmp_path / "portrait.jpg"
    Image.fromarray(np.full((400, 100, 3), (10, 180, 40), dtype=np.uint8)).save(source)

    image = _decode(fitted_jpeg(source))

    assert image.shape == (135, 240, 3)
    assert image[:, 0].max() == 0
    assert image[:, 103:137, 1].mean() > 160


def test_fitted_jpeg_rejects_invalid_and_oversized_transfers(tmp_path):
    """Returning corrupt bytes or more than the radio budget defeats the remote API."""
    invalid = tmp_path / "not-an-image.jpg"
    invalid.write_bytes(b"not a jpeg")
    with pytest.raises(ThumbnailError):
        fitted_jpeg(invalid)

    noisy = tmp_path / "noisy.png"
    Image.fromarray(np.random.default_rng(4).integers(0, 256, (135, 240, 3), np.uint8)).save(noisy)
    with pytest.raises(ThumbnailError, match="transfer limit"):
        fitted_jpeg(noisy, max_bytes=100)
