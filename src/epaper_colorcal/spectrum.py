"""A spectral reflectance measurement, independent of the instrument that took it.

Kept free of numpy and colour-science so instrument adapters can return one cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass

CR30_WAVELENGTHS: list[float] = [float(w) for w in range(400, 701, 10)]
"""The CR30's grid: 31 bands, 400-700 nm in 10 nm steps."""


@dataclass(frozen=True)
class Spectrum:
    """A spectral reflectance in **percent** (0-100) at the given wavelengths (nm)."""

    wavelengths: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.wavelengths) != len(self.values):
            raise ValueError(f"{len(self.values)} values for {len(self.wavelengths)} wavelengths")
        if len(self.wavelengths) < 2 or any(b <= a for a, b in zip(self.wavelengths, self.wavelengths[1:])):
            raise ValueError("wavelengths must be at least two, strictly increasing")

    @classmethod
    def cr30(cls, values: list[float] | tuple[float, ...]) -> Spectrum:
        """A spectrum on the CR30's grid (400-700 nm, 10 nm)."""
        return cls(tuple(CR30_WAVELENGTHS), tuple(float(v) for v in values))


def average_spectra(spectra: list[Spectrum]) -> Spectrum:
    """Average several reads of one sample, band by band. They must share one wavelength grid."""
    if not spectra:
        raise ValueError("no spectra to average")
    grid = spectra[0].wavelengths
    if any(s.wavelengths != grid for s in spectra):
        raise ValueError("spectra to average must share one wavelength grid")
    n = len(spectra)
    return Spectrum(grid, tuple(sum(band) / n for band in zip(*(s.values for s in spectra))))
