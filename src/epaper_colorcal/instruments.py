"""Instruments: what reads the panel's reflectance.

:class:`Instrument` is the port. Adapters: the CHNSpec CR30 over USB or Bluetooth
(:mod:`epaper_colorcal.cr30`) and :class:`SyntheticInstrument` for dry runs. An instrument
returns a :class:`~epaper_colorcal.spectrum.Spectrum` on its own wavelength grid; the
colorimetry works on any grid.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .spectrum import Spectrum

if TYPE_CHECKING:
    from .displays import SimDisplay


class Instrument(ABC):
    """A reflectance instrument. Use as ``async with`` or call :meth:`connect`/:meth:`close`."""

    @property
    def model(self) -> str:
        return "unknown"

    @property
    def serial_number(self) -> str:
        return "unknown"

    @property
    def description(self) -> str:
        """Maker and model, as recorded in a palette's source."""
        return self.model

    async def connect(self) -> None:  # noqa: B027 - optional hook
        """Open the connection, if any."""

    async def close(self) -> None:  # noqa: B027 - optional hook
        """Release the connection, if any."""

    @abstractmethod
    async def measure(self) -> Spectrum:
        """Take one reading of whatever the instrument is on."""

    async def calibrate_black(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__} does not support explicit calibration")

    async def calibrate_white(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__} does not support explicit calibration")

    async def __aenter__(self) -> Instrument:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class SyntheticInstrument(Instrument):
    """For dry runs: plausible spectra of whatever the simulated display shows."""

    @property
    def model(self) -> str:
        return "synthetic"

    @property
    def serial_number(self) -> str:
        return "DRYRUN"

    def __init__(self, display: SimDisplay) -> None:
        self._display = display
        self._reads = 0

    async def measure(self) -> Spectrum:
        from .synthetic import IDEAL_SRGB, synthetic_spd  # pylint: disable=import-outside-toplevel

        ink = self._display.current
        if ink is None:
            raise RuntimeError("nothing is shown on the simulated display")
        self._reads += 1  # a new seed per read, so averaging is meaningful
        return Spectrum.cr30(synthetic_spd(IDEAL_SRGB.get(ink.name, ink.rgb), jitter=0.01, seed=self._reads))
