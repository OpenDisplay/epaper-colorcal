"""Emit a measured palette as an ``epaper-palette`` JSON file, plus a raw-spectra sidecar.

The palette file is what ``epaper-dithering`` 7 loads (``Palette.load``) and what
``py-opendisplay`` ships per panel in ``src/opendisplay/palettes/``. It is built with
``epaper_dithering.Palette.from_absolute_lab`` so normalisation to the panel's white and
validation are exactly the library's own.

The JSON sidecar keeps the raw spectra so a measurement can be re-processed later (e.g.
for kepstin's "define the gamut as a volume in XYZ" idea) without re-measuring the panel.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from epaper_dithering import Palette, PaletteEntry

from .colorimetry import CR30_WAVELENGTHS, ColorReading
from .schemes import Scheme

# The colour that requests each ink: what a caller draws to get that ink solid.
NOMINALS: dict[str, str] = {
    "black": "#000000",
    "white": "#ffffff",
    "yellow": "#ffff00",
    "red": "#ff0000",
    "blue": "#0000ff",
    "green": "#00ff00",
}


@dataclass(frozen=True)
class MeasuredColor:
    """One measured color: its reading plus the raw spectra it came from."""

    name: str
    reading: ColorReading
    spds: list[list[float]]
    """The individual SPD reads (before averaging) for this color."""


def _temp_phrase(temperature_c: float | None) -> str:
    """Panel temperature clause for the palette's source.

    e-paper color is temperature-dependent (see OpenDisplay #color-calibration:
    cold panels shift color noticeably and even select a different LUT), so a
    measured palette is only valid near the temperature it was captured at.
    """
    if temperature_c is None:
        return "panel temperature unrecorded"
    return f"panel at {temperature_c:g}°C"


def build_palette(
    scheme: Scheme,
    colors: list[MeasuredColor],
    *,
    serial: str = "unknown",
    note: str = "",
    measured_on: date | None = None,
    temperature_c: float | None = None,
) -> Palette:
    """Build the measured palette, normalised so the panel's white is L* 100, a* = b* = 0.

    Appearances come from the unclamped D65 Lab, so colours outside sRGB keep their
    measured values.
    """
    if [c.name for c in colors] != list(scheme.colors):
        raise ValueError(f"scheme {scheme.name} needs colors {list(scheme.colors)}, got {[c.name for c in colors]}")

    entries = [PaletteEntry(c.reading.lab_d65, c.name, NOMINALS[c.name]) for c in colors]
    on = (measured_on or date.today()).isoformat()
    source = f"CHNSpec CR30 s/n {serial}, measured {on}, D65/2°, {_temp_phrase(temperature_c)}"
    if note:
        source = f"{note}; {source}"
    return Palette.from_absolute_lab(entries, scheme.colors.index("white"), measured=True).with_source(source)


def render_palette(
    scheme: Scheme,
    colors: list[MeasuredColor],
    *,
    serial: str = "unknown",
    note: str = "",
    measured_on: date | None = None,
    temperature_c: float | None = None,
) -> str:
    """The measured palette as an ``epaper-palette`` JSON document."""
    palette = build_palette(
        scheme,
        colors,
        serial=serial,
        note=note,
        measured_on=measured_on,
        temperature_c=temperature_c,
    )
    return palette.to_json()


def spectra_sidecar(
    palette_id: str,
    scheme: Scheme,
    colors: list[MeasuredColor],
    *,
    serial: str = "unknown",
    measured_on: date | None = None,
    temperature_c: float | None = None,
) -> dict[str, Any]:
    """Build the raw-spectra JSON sidecar payload."""
    return {
        "id": palette_id,
        "scheme": scheme.name,
        "firmware_id": scheme.firmware_id,
        "instrument": "CHNSpec CR30",
        "serial": serial,
        "measured_on": (measured_on or date.today()).isoformat(),
        "temperature_c": temperature_c,
        "wavelengths_nm": CR30_WAVELENGTHS,
        "colors": [
            {
                "name": c.name,
                "srgb_d65": list(c.reading.srgb),
                "lab_d65": list(c.reading.lab_d65),
                "lab_d50": list(c.reading.lab_d50),
                "xyz_d65": list(c.reading.xyz_d65),
                "out_of_gamut": c.reading.clipped,
                "spd_reads": c.spds,
            }
            for c in colors
        ],
    }


def write_sidecar(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
