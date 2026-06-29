"""Colorimetry: convert a CR30 spectral reflectance curve to sRGB and CIE Lab.

The CR30 reports a 31-band spectral power distribution (SPD) — really a
*reflectance* curve — from 400-700 nm in 10 nm steps. Reflectance is the
illuminant-independent physical property of the panel; the colour you perceive
depends on which illuminant you view it under. So we integrate the same
reflectance against different illuminants for different purposes:

* **sRGB under D65/2°** — to match the dithering pipeline. ``epaper-dithering``'s
  ``color_space_lab.rs`` uses the D65 sRGB matrix (``M_RGB_XYZ``), so the measured
  palette entries it consumes must be D65-referenced sRGB.
* **CIE Lab under D50/2°** — to compare against manufacturer datasheets, which
  (per the OpenDisplay #color-calibration discussion) are quoted under a 45°/0°,
  D50 spectrophotometer configuration.

We deliberately do the colorimetry here with ``colour-science`` rather than the
vendored upstream code, so the illuminant/observer are explicit and controllable.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

# colour-science warns when optional accelerators (scipy/matplotlib) are absent and when it
# aligns our 400-700 nm reflectance onto the CMF shape (constant-extrapolated outside the
# measured range, which is fine for reflectance). We only use the pure-numpy "Integration"
# path, so silence the noise for this CLI tool.
warnings.filterwarnings("ignore", message=".*related API features are not available.*")
warnings.filterwarnings("ignore", message=".*Aligning .* shape.*")

import colour  # noqa: E402
import numpy as np  # noqa: E402
from colour import MSDS_CMFS, SDS_ILLUMINANTS, SpectralDistribution, SpectralShape  # noqa: E402

# CR30: 31 bands, 400-700 nm, 10 nm interval.
CR30_SHAPE = SpectralShape(400, 700, 10)
CR30_WAVELENGTHS: list[float] = list(np.arange(400, 701, 10, dtype=float))

_OBSERVER = "CIE 1931 2 Degree Standard Observer"
_CMFS = MSDS_CMFS[_OBSERVER]
# xy chromaticity coordinates of the standard illuminants for the 2° observer.
_CCS = colour.CCS_ILLUMINANTS[_OBSERVER]


@dataclass(frozen=True)
class ColorReading:
    """A single panel color resolved into the spaces we care about."""

    srgb: tuple[int, int, int]
    """sRGB 0-255, D65/2°, gamut-clamped — the value pasted into measured_palettes.rs."""
    lab_d50: tuple[float, float, float]
    """CIE L*a*b* under D50/2° — for datasheet comparison (goes in the Rust comment)."""
    xyz_d65: tuple[float, float, float]
    """CIE XYZ (Y in 0-1, perfect diffuse white = 1.0) under D65/2°."""
    clipped: bool
    """True if the D65 sRGB was outside [0, 1] and had to be clamped (out of gamut)."""


def _reflectance_sd(spd: list[float], wavelengths: list[float] | None = None) -> SpectralDistribution:
    """Build a colour SpectralDistribution from a raw CR30 SPD, normalised to [0, 1].

    The absolute scale of the CR30 floats is not documented by the reverse-engineering
    work. We accept either a 0-1 fraction or a 0-100 percentage and normalise to a
    fraction; values are then clipped into [0, 1] (a calibrated reflectance cannot
    exceed the white tile).
    """
    wl = list(wavelengths) if wavelengths is not None else CR30_WAVELENGTHS
    if len(spd) != len(wl):
        raise ValueError(f"SPD has {len(spd)} samples but {len(wl)} wavelengths were given")

    values = np.asarray(spd, dtype=float)
    if np.nanmax(values) > 1.5:  # looks like a percentage
        values = values / 100.0
    values = np.clip(values, 0.0, 1.0)

    return SpectralDistribution(dict(zip(wl, values)), name="CR30 reflectance")


def _reflectance_to_xyz(sd: SpectralDistribution, illuminant_name: str) -> np.ndarray:
    """Integrate a reflectance SD against an illuminant → XYZ with Y in [0, 1].

    ``sd_to_XYZ`` returns XYZ on a 0-100 scale where a perfect diffuse reflector
    yields Y = 100; we rescale to 0-1 so downstream ``XYZ_to_*`` (reference domain)
    behave. The "Integration" method is used so arbitrary 10 nm shapes are accepted
    without the ASTM E308 standard-shape constraint.
    """
    illuminant = SDS_ILLUMINANTS[illuminant_name]
    xyz = colour.sd_to_XYZ(sd, _CMFS, illuminant, method="Integration")
    return np.asarray(xyz, dtype=float) / 100.0


def reading_from_spd(spd: list[float], wavelengths: list[float] | None = None) -> ColorReading:
    """Convert a (possibly averaged) CR30 SPD into a :class:`ColorReading`."""
    sd = _reflectance_sd(spd, wavelengths)

    # sRGB under D65 — reflectance integrated against D65, then the standard sRGB
    # encode (which is itself D65-referenced, so no chromatic adaptation needed).
    xyz_d65 = _reflectance_to_xyz(sd, "D65")
    rgb_linear_clamped = colour.XYZ_to_sRGB(xyz_d65)
    clipped = bool(np.any(rgb_linear_clamped < 0.0) or np.any(rgb_linear_clamped > 1.0))
    rgb = np.clip(rgb_linear_clamped, 0.0, 1.0)
    srgb = tuple(int(round(float(c) * 255.0)) for c in rgb)

    # Lab under D50 — datasheet reference geometry/illuminant.
    xyz_d50 = _reflectance_to_xyz(sd, "D50")
    lab = colour.XYZ_to_Lab(xyz_d50, _CCS["D50"])
    lab_d50 = tuple(round(float(v), 1) for v in lab)

    return ColorReading(
        srgb=srgb,  # type: ignore[arg-type]
        lab_d50=lab_d50,  # type: ignore[arg-type]
        xyz_d65=tuple(round(float(v), 4) for v in xyz_d65),  # type: ignore[arg-type]
        clipped=clipped,
    )


def average_spds(spds: list[list[float]]) -> list[float]:
    """Average several SPD reads band-by-band (noise reduction)."""
    if not spds:
        raise ValueError("no SPDs to average")
    arr = np.asarray(spds, dtype=float)
    if arr.ndim != 2:
        raise ValueError("all SPDs must have the same length")
    return [float(v) for v in arr.mean(axis=0)]
