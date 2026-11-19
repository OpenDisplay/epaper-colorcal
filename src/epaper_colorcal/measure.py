"""The measurement loop: show each ink, read it ``count`` times, average.

It joins the two ports: a :class:`~epaper_colorcal.displays.Display` puts the ink on the
panel, an :class:`~epaper_colorcal.instruments.Instrument` reads its reflectance. Manual and
automatic measurement, real and simulated, are all this one loop with different adapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .colorimetry import reading_from_spectrum
from .emit import MeasuredColor
from .spectrum import Spectrum, average_spectra

if TYPE_CHECKING:
    from .displays import Display
    from .instruments import Instrument
    from .schemes import Scheme


def measure_color(name: str, spds: list[list[float]], wavelengths: tuple[float, ...] | None = None) -> MeasuredColor:
    """Average the reads of one ink (reflectance %) and resolve it to sRGB/Lab.

    Without ``wavelengths`` the values are on the CR30's grid (400-700 nm, 10 nm).
    """
    spectra = [Spectrum.cr30(s) if wavelengths is None else Spectrum(wavelengths, tuple(s)) for s in spds]
    return measure_spectra(name, spectra)


def measure_spectra(name: str, spectra: list[Spectrum]) -> MeasuredColor:
    """Average several reads of one ink and resolve it to sRGB/Lab."""
    mean = average_spectra(spectra)
    return MeasuredColor(
        name=name,
        reading=reading_from_spectrum(mean),
        spds=[list(s.values) for s in spectra],
        wavelengths=mean.wavelengths,
    )


async def measure_all(scheme: Scheme, display: Display, instrument: Instrument, count: int) -> list[MeasuredColor]:
    """Show every ink of ``scheme`` on ``display`` in order and read each ``count`` times."""
    colors = []
    for index, ink in enumerate(scheme.inks):
        await display.show(index, ink)
        colors.append(measure_spectra(ink.name, [await instrument.measure() for _ in range(count)]))
    return colors
