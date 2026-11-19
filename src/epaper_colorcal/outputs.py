"""Outputs: what a finished measurement becomes.

:class:`Output` is the port; every adapter takes the same :class:`Measurement`:

* ``epaper-palette``: an ``epaper-palette`` JSON file for ``epaper-dithering`` and
  py-opendisplay (Lab under D65, normalised to the panel's white),
* ``oepl``: a ``perceptual`` block for an OpenEPaperLink tag type (sRGB relative to the
  panel's white, per colour, in the tag's colour-table order),
* ``spectra``: the raw spectra of every read plus each ink's colour, for re-processing.

``--format`` picks what goes to stdout; ``--out`` writes the spectra to a file.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from .emit import MeasuredColor, build_palette, render_palette, spectra_sidecar
from .schemes import Scheme


@dataclass(frozen=True)
class Measurement:  # pylint: disable=too-many-instance-attributes  # a plain record
    """A finished measurement of one panel."""

    palette_id: str
    scheme: Scheme
    colors: list[MeasuredColor]
    instrument: str = "CHNSpec CR30"
    serial: str = "unknown"
    temperature_c: float | None = None
    note: str = ""
    measured_on: date = field(default_factory=date.today)


class Output(ABC):
    """Turns a measurement into a document."""

    name: str
    """The ``--format`` name."""

    @abstractmethod
    def render(self, measurement: Measurement) -> str: ...


class EpaperPaletteOutput(Output):
    name = "epaper-palette"

    def render(self, measurement: Measurement) -> str:
        m = measurement
        return render_palette(
            m.scheme,
            m.colors,
            serial=m.serial,
            instrument=m.instrument,
            note=m.note,
            measured_on=m.measured_on,
            temperature_c=m.temperature_c,
        )


class OEPLOutput(Output):
    """A ``perceptual`` block for an OpenEPaperLink tag type (``resources/tagtypes/*.json``).

    OEPL's web UI draws (and dithers) tag images with ``perceptual`` when a tag type has one:
    sRGB 0-255 relative to the panel's white, so white stays ``[255, 255, 255]``. Every ink is
    written, in scheme order (the tag's colour-table order when the scheme came from the tag):
    the web UI reads the block as a list, so a missing colour would shift the ones after it.
    """

    name = "oepl"

    def render(self, measurement: Measurement) -> str:
        m = measurement
        palette = build_palette(m.scheme, m.colors, serial=m.serial, instrument=m.instrument)
        rgb = dict(zip(m.scheme.colors, palette.preview_rgb()))
        # Inline [r, g, b] per colour, as the tag-type files write them.
        lines = [f"    {json.dumps(name)}: {json.dumps(list(rgb[name]))}" for name in m.scheme.colors]
        return '{\n  "perceptual": {\n' + ",\n".join(lines) + "\n  }\n}"


class SpectraOutput(Output):
    name = "spectra"

    def render(self, measurement: Measurement) -> str:
        m = measurement
        payload = spectra_sidecar(
            m.palette_id,
            m.scheme,
            m.colors,
            serial=m.serial,
            instrument=m.instrument,
            measured_on=m.measured_on,
            temperature_c=m.temperature_c,
        )
        return json.dumps(payload, indent=2)


OUTPUTS: dict[str, Output] = {o.name: o for o in (EpaperPaletteOutput(), OEPLOutput(), SpectraOutput())}


def get_output(name: str) -> Output:
    if name not in OUTPUTS:
        raise ValueError(f"unknown format {name!r}; choose one of: {', '.join(OUTPUTS)}")
    return OUTPUTS[name]
