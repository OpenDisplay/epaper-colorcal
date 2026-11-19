"""The instrument port: spectra on any wavelength grid, and instruments other than the CR30."""

from __future__ import annotations

import json

import pytest

from epaper_colorcal.colorimetry import reading_from_spectrum
from epaper_colorcal.displays import SimDisplay
from epaper_colorcal.emit import render_palette, spectra_sidecar
from epaper_colorcal.instruments import Instrument, SyntheticInstrument
from epaper_colorcal.measure import measure_all
from epaper_colorcal.schemes import Ink, get_scheme
from epaper_colorcal.spectrum import CR30_WAVELENGTHS, Spectrum, average_spectra

WIDE = tuple(float(w) for w in range(380, 731, 10))  # e.g. an X-Rite i1Pro: 36 bands


def test_spectrum_validates_its_grid() -> None:
    with pytest.raises(ValueError, match="values for"):
        Spectrum((400.0, 410.0), (1.0,))
    with pytest.raises(ValueError, match="increasing"):
        Spectrum((410.0, 400.0), (1.0, 2.0))
    assert Spectrum.cr30([5.0] * 31).wavelengths == tuple(CR30_WAVELENGTHS)


def test_average_spectra_needs_one_grid() -> None:
    a, b = Spectrum((400.0, 500.0), (10.0, 20.0)), Spectrum((400.0, 500.0), (20.0, 40.0))
    assert average_spectra([a, b]).values == (15.0, 30.0)
    with pytest.raises(ValueError, match="one wavelength grid"):
        average_spectra([a, Spectrum((400.0, 510.0), (1.0, 1.0))])


def test_colour_does_not_depend_on_the_grid_for_the_same_reflectance() -> None:
    narrow = reading_from_spectrum(Spectrum.cr30([42.0] * 31))
    wide = reading_from_spectrum(Spectrum(WIDE, (42.0,) * len(WIDE)))
    assert wide.lab_d65 == pytest.approx(narrow.lab_d65, abs=1e-6)


class _WideInstrument(Instrument):
    """An instrument with a 380-730 nm grid that reads the simulated panel as a flat grey."""

    def __init__(self, display: SimDisplay) -> None:
        self.display = display

    @property
    def description(self) -> str:
        return "Example Spectro 9000"

    @property
    def serial_number(self) -> str:
        return "SN42"

    async def measure(self) -> Spectrum:
        assert self.display.current is not None
        level = 5.0 if self.display.current.name == "black" else 80.0
        return Spectrum(WIDE, (level,) * len(WIDE))


async def test_another_instrument_and_grid_flow_through_to_the_outputs() -> None:
    scheme = get_scheme("MONO")
    display = SimDisplay()
    instrument = _WideInstrument(display)
    colors = await measure_all(scheme, display, instrument, count=2)

    assert all(c.wavelengths == WIDE and len(c.spds[0]) == 36 for c in colors)
    palette = json.loads(render_palette(scheme, colors, serial="SN42", instrument=instrument.description))
    assert palette["source"].startswith("Example Spectro 9000 s/n SN42")
    sidecar = spectra_sidecar("x", scheme, colors, serial="SN42", instrument=instrument.description)
    assert sidecar["instrument"] == "Example Spectro 9000"
    assert sidecar["wavelengths_nm"] == list(WIDE)


async def test_the_synthetic_instrument_reads_what_the_sim_display_shows() -> None:
    display = SimDisplay()
    instrument = SyntheticInstrument(display)
    with pytest.raises(RuntimeError, match="nothing is shown"):
        await instrument.measure()
    await display.show(0, Ink("black", "#000000"))
    black = reading_from_spectrum(await instrument.measure())
    await display.show(1, Ink("white", "#ffffff"))
    white = reading_from_spectrum(await instrument.measure())
    assert white.lab_d65[0] > black.lab_d65[0] + 40


async def test_instruments_without_calibration_say_so() -> None:
    with pytest.raises(NotImplementedError):
        await SyntheticInstrument(SimDisplay()).calibrate_black()
