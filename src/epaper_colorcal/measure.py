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


# A panel can keep showing the old colour for a few seconds after it has the new image, and can
# pause on an intermediate colour mid-refresh. So the colour must first move away from what the
# panel showed before (the refresh has started), then hold steady for longer than such a pause.
SETTLE_CHANGE = 3.0  # ΔE76 away from the previous colour that counts as "the refresh started"
SETTLE_TOLERANCE = 1.0  # ΔE76 within which reads count as steady (the CR30's noise is about 0.1)
SETTLE_STABLE = 15.0  # seconds the colour must hold steady
SETTLE_MIN_READS = 4
SETTLE_INTERVAL = 1.0
SETTLE_TIMEOUT = 240.0


async def wait_until_settled(instrument: Instrument, before: tuple[float, float, float] | None = None) -> float:
    """Read until the panel has refreshed and holds its colour; return the seconds it took.

    ``before`` is the colour (D65 Lab) the panel showed before the new ink was sent; until the
    colour moves away from it, the refresh hasn't started. Then the reads of the last
    :data:`SETTLE_STABLE` seconds (at least :data:`SETTLE_MIN_READS`) must agree within
    :data:`SETTLE_TOLERANCE`. Raises TimeoutError after :data:`SETTLE_TIMEOUT` seconds.
    """
    loop = asyncio.get_running_loop()
    start = loop.time()
    started = before is None
    window: list[tuple[float, tuple[float, float, float]]] = []
    while True:
        now, lab = loop.time(), reading_from_spectrum(await instrument.measure()).lab_d65
        if not started:
            started = before is not None and math.dist(lab, before) > SETTLE_CHANGE
        elif window and max(math.dist(lab, other) for _, other in window) > SETTLE_TOLERANCE:
            window = []  # still changing: start the steady window again from this read
        if started:
            window.append((now, lab))
            if len(window) >= SETTLE_MIN_READS and now - window[0][0] >= SETTLE_STABLE:
                return now - start
        if now - start > SETTLE_TIMEOUT:
            reason = "kept changing" if started else "never changed from the previous colour"
            raise TimeoutError(
                f"The panel did not settle within {SETTLE_TIMEOUT:g} s: its colour {reason}. "
                "Is the instrument seated flat and still, and did the panel refresh?"
            )
        await asyncio.sleep(SETTLE_INTERVAL)


async def measure_all(scheme: Scheme, display: Display, instrument: Instrument, count: int) -> list[MeasuredColor]:
    """Show every ink of ``scheme`` on ``display`` in order and read each ``count`` times.

    Unless the display guarantees the panel has finished refreshing when ``show()`` returns,
    the instrument is read until the panel is stable before the counted reads are taken.
    """
    colors = []
    for index, ink in enumerate(scheme.inks):
        before = None if display.settled_after_show else reading_from_spectrum(await instrument.measure()).lab_d65
        await display.show(index, ink)
        if before is not None:
            print(f"  {ink.name}: waiting for the panel to refresh and settle…", file=sys.stderr)
            seconds = await wait_until_settled(instrument, before)
            print(f"  {ink.name}: settled after {seconds:.0f} s", file=sys.stderr)
        colors.append(measure_spectra(ink.name, [await instrument.measure() for _ in range(count)]))
    return colors
