"""The measurement loop: show each ink, read it ``count`` times, average.

It joins the two ports: a :class:`~epaper_colorcal.displays.Display` puts the ink on the
panel, an :class:`~epaper_colorcal.instruments.Instrument` reads its reflectance. Manual and
automatic measurement, real and simulated, are all this one loop with different adapters.
"""

from __future__ import annotations

import asyncio
import math
import sys
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


# Settling: the panel counts as settled once this many reads, this far apart, agree within this
# colour difference (ΔE76, D65 Lab). The CR30's own noise is about ΔE 0.1; a refreshing panel
# changes by far more than 1 between reads a second apart.
SETTLE_READS = 4
SETTLE_INTERVAL = 1.0
SETTLE_TOLERANCE = 1.0
SETTLE_TIMEOUT = 180.0


async def wait_until_settled(instrument: Instrument) -> int:
    """Read until the last :data:`SETTLE_READS` reads agree; return how many reads it took.

    Raises TimeoutError if the panel hasn't settled within :data:`SETTLE_TIMEOUT` seconds.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SETTLE_TIMEOUT
    window: list[tuple[float, float, float]] = []
    reads = 0
    while True:
        window = [*window, reading_from_spectrum(await instrument.measure()).lab_d65][-SETTLE_READS:]
        reads += 1
        if len(window) == SETTLE_READS and max(math.dist(a, b) for a in window for b in window) <= SETTLE_TOLERANCE:
            return reads
        if loop.time() > deadline:
            raise TimeoutError(
                f"The panel did not settle within {SETTLE_TIMEOUT:g} s: the colour kept changing. "
                "Is the CR30 seated flat and still?"
            )
        await asyncio.sleep(SETTLE_INTERVAL)


async def measure_all(scheme: Scheme, display: Display, instrument: Instrument, count: int) -> list[MeasuredColor]:
    """Show every ink of ``scheme`` on ``display`` in order and read each ``count`` times.

    Unless the display guarantees the panel has finished refreshing when ``show()`` returns,
    the instrument is read until the panel is stable before the counted reads are taken.
    """
    colors = []
    for index, ink in enumerate(scheme.inks):
        await display.show(index, ink)
        if not display.settled_after_show:
            print(f"  {ink.name}: waiting for the panel to settle…", file=sys.stderr)
            reads = await wait_until_settled(instrument)
            print(f"  {ink.name}: settled after {reads} reads", file=sys.stderr)
        colors.append(measure_spectra(ink.name, [await instrument.measure() for _ in range(count)]))
    return colors
