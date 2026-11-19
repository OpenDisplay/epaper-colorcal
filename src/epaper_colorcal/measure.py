"""The measurement loop: show each ink, read it ``count`` times, average.

It joins the two ports: a :class:`~epaper_colorcal.displays.Display` puts the ink on the
panel, an :data:`SpdSource` reads its reflectance (a CR30, or synthetic spectra for a dry
run). Manual and automatic measurements are the same loop with different displays.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from .colorimetry import average_spds, reading_from_spd
from .emit import MeasuredColor
from .synthetic import IDEAL_SRGB, synthetic_spd

if TYPE_CHECKING:
    from .cr30 import CR30
    from .displays import Display
    from .schemes import Ink, Scheme

SpdSource = Callable[["Ink"], Awaitable[list[float]]]
"""One reflectance read (31 bands, percent) of the ink currently shown."""


def measure_color(name: str, spds: list[list[float]]) -> MeasuredColor:
    """Average the reads of one ink and resolve it to sRGB/Lab."""
    return MeasuredColor(name=name, reading=reading_from_spd(average_spds(spds)), spds=spds)


async def measure_all(scheme: Scheme, display: Display, read: SpdSource, count: int) -> list[MeasuredColor]:
    """Show every ink of ``scheme`` on ``display`` in order and read each ``count`` times."""
    colors = []
    for index, ink in enumerate(scheme.inks):
        await display.show(index, ink)
        colors.append(measure_color(ink.name, [await read(ink) for _ in range(count)]))
    return colors


def cr30_source(cr30: CR30) -> SpdSource:
    async def read(_ink: Ink) -> list[float]:
        return await cr30.measure()

    return read


def synthetic_source() -> SpdSource:
    """Plausible spectra for a dry run: dimmed e-paper colours for known inks, else the nominal."""
    reads = 0

    async def read(ink: Ink) -> list[float]:
        nonlocal reads
        reads += 1  # a new seed per read, so averaging is meaningful
        return synthetic_spd(IDEAL_SRGB.get(ink.name, ink.rgb), jitter=0.01, seed=reads)

    return read
