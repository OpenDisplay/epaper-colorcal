"""Synthetic reflectance SPDs for the ``--dry-run`` path (no hardware required).

These are NOT physically accurate — they exist so the full pipeline (averaging →
colorimetry → Rust/JSON emission) can be exercised and tested before a CR30 is
in hand. Each target sRGB is turned into a plausible smooth reflectance built
from red/green/blue Gaussian bases, so the round-tripped color is sane (white
lighter than black, hue roughly preserved).
"""

from __future__ import annotations

import numpy as np

from .colorimetry import CR30_WAVELENGTHS

_WL = np.asarray(CR30_WAVELENGTHS, dtype=float)


def _gaussian(center: float, sigma: float) -> np.ndarray:
    g = np.exp(-0.5 * ((_WL - center) / sigma) ** 2)
    return np.asarray(g / g.max(), dtype=float)


_BASIS_B = _gaussian(450.0, 45.0)
_BASIS_G = _gaussian(550.0, 45.0)
_BASIS_R = _gaussian(640.0, 45.0)
_BASELINE = 0.02  # so pure black isn't an all-zero curve

# Idealized sRGB per color name, used to seed dry-run synthetic spectra. Whites/blacks
# are dimmed/lifted toward real e-paper reflectance so the dry-run output resembles a
# plausible measured palette rather than pure 0/255.
IDEAL_SRGB: dict[str, tuple[int, int, int]] = {
    "black": (20, 18, 22),
    "white": (190, 196, 198),
    "red": (150, 30, 25),
    "yellow": (200, 185, 20),
    "blue": (35, 70, 140),
    "green": (45, 95, 65),
    "gray1": (70, 70, 70),
    "gray2": (130, 130, 130),
    "gray3": (160, 160, 160),
}


def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def synthetic_spd(srgb: tuple[int, int, int], *, jitter: float = 0.0, seed: int | None = None) -> list[float]:
    """Build a plausible 31-band reflectance for a target sRGB color.

    ``jitter`` adds small per-band noise (fraction of signal) so averaging
    multiple reads is meaningful in the dry-run; ``seed`` makes it reproducible.
    """
    r, g, b = (_srgb_to_linear(float(c)) for c in srgb)
    refl = _BASELINE + r * _BASIS_R + g * _BASIS_G + b * _BASIS_B
    refl = np.clip(refl, 0.0, 1.0)

    if jitter:
        rng = np.random.default_rng(seed)
        refl = np.clip(refl * (1.0 + jitter * rng.standard_normal(refl.shape)), 0.0, 1.0)

    return [float(v) for v in refl]
