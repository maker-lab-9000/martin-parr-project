"""Saturated color-negative grading for USB-camera capture and batch processing.

The package has two halves that share code:

* ``parr.color``, ``normalize``, ``lut``, ``grain``, ``pipeline`` are the
  processing core used on the Pi. They depend only on NumPy, Pillow and OpenCV.
* ``parr.train`` fits the LUT on a Mac from curated reference photographs and
  needs SciPy and requests (``pip install -e ".[train]"``).

See README.md for training, reference selection and the untrained starter preset.
"""

__version__ = "0.1.0"
